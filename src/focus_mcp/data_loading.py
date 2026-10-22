#!/usr/bin/env python3
"""
Data Loading Module - How focus_data_table sources its Parquet files.

Two strategies, picked at view-creation time:

1. Manifest-driven, for AWS BCM Data Exports. AWS writes
   {location}/metadata/<PARTITION>/<export>-Manifest.json once per
   billing period and rewrites it on every delivery; its dataFiles array
   lists the full URIs of exactly the current delivery. Globbing such an
   export is wrong: the prefix also holds blanked OVERWRITE_REPORT
   chunks (zero-byte Parquet that crashes read_parquet), superseded
   CREATE_NEW_REPORT executions, and partition folders orphaned when AWS
   switches the casing of billing_period= (which also makes DuckDB's
   Hive inference throw). None of those appear in a manifest, so reading
   the manifests needs no special-casing of any of them.
2. Glob fallback, for everything else - bundled sample data, BigQuery
   FOCUS exports written to GCS, arbitrary directories - which has no
   metadata/ prefix. An export whose manifests cannot be read is an
   error rather than a reason to glob it: the manifests are proof that
   globbing would double-count.

Both strategies run over the connection the storage backend prepared, so
they behave the same on local paths, s3:// and gs://.

A dataset can name several locations. Each is read on its own - so two
locations may use different strategies and different partition layouts
without either disturbing the other - and focus_data_table is the union of
them. Where two locations hold the same billing period the later one wins:
the same month delivered twice would otherwise be counted twice.
"""

import logging
import re
from typing import Optional, Sequence, Union

import duckdb

logger = logging.getLogger(__name__)

# Exactly one directory level: partition-level manifests only. Manifests
# of individual CREATE_NEW_REPORT executions live a level deeper, and the
# sibling <export>-Manifest-FOCUS.json does not end in "Manifest.json".
MANIFEST_GLOB = "{location}/metadata/*/*Manifest.json"

# The view every tool reads, and the per-location views it unions when a
# dataset has more than one location.
FOCUS_VIEW = "focus_data_table"
PART_VIEW = "focus_data_part_{index}"

# FOCUS's own month column: the one thing two locations of the same dataset
# are guaranteed to be able to overlap on.
BILLING_PERIOD_COLUMN = "BillingPeriodStart"

# AWS documents BILLING_PERIOD= but has delivered billing_period= too,
# so both the discovery filter and the derived column ignore casing.
PARTITION_DIR_PATTERN = re.compile(r"billing_period=\d{4}-\d{2}", re.IGNORECASE)
BILLING_PERIOD_EXPR = (
    r"regexp_extract(filename, '(?i)billing_period=(\d{4}-\d{2})', 1)"
)

# dataFiles holds the URIs of the bucket the export was delivered to. A
# copy of that export (aws s3 sync into a directory, a mirror in another
# bucket) keeps AWS's data/<PARTITION>/[<execution>/]<file> layout but not
# those URIs, so only the layout tail is trusted.
DATA_FILE_TAIL_PATTERN = re.compile(
    r"(?:^|/)(data/billing_period=\d{4}-\d{2}/.+)$", re.IGNORECASE
)


def _sql_literal(value: str) -> str:
    """Quote a string for inlining: views cannot carry bound parameters."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _is_partition_manifest(path: str) -> bool:
    """Whether the manifest sits directly in a billing-period directory."""
    segments = path.split("/")
    return len(segments) >= 2 and bool(
        PARTITION_DIR_PATTERN.fullmatch(segments[-2])
    )


def discover_manifests(
    conn: duckdb.DuckDBPyConnection, location: str
) -> list[str]:
    """Return the partition-level export manifests under the location.

    A location that is not an export simply globs to nothing. An error
    means the metadata/ prefix could not be listed, which must not be
    read as "no manifests here": that silently downgrades an export to
    the glob, so it propagates instead.
    """
    pattern = MANIFEST_GLOB.format(location=location)
    rows = conn.execute("SELECT file FROM glob(?)", [pattern]).fetchall()
    return sorted(p for (p,) in rows if _is_partition_manifest(p))


def read_manifest_data_files(
    conn: duckdb.DuckDBPyConnection, manifest: str
) -> list[str]:
    """Return the dataFiles URIs of one manifest, [] if it can't be read."""
    try:
        rows = conn.execute(
            "SELECT dataFiles FROM read_json_auto(?)", [manifest]
        ).fetchall()
    except duckdb.Error as e:
        logger.warning("Skipping unreadable manifest %s: %s", manifest, e)
        return []
    # dataFiles is a flat array of URIs; anything else isn't a file path
    return [
        entry
        for (data_files,) in rows
        for entry in (data_files or [])
        if isinstance(entry, str)
    ]


def rebase_data_file(location: str, uri: str) -> str:
    """Point a dataFiles URI at the location the export is read from.

    Reading the export where it was delivered rebases it onto itself; a
    copy of it is read from the copy instead of from the original bucket.
    """
    match = DATA_FILE_TAIL_PATTERN.search(uri)
    if not match:
        # Layout AWS does not write: the manifest's own URI is all we have
        logger.warning("Unexpected data file path in manifest: %s", uri)
        return uri
    return f"{location}/{match.group(1)}"


def collect_data_files(
    conn: duckdb.DuckDBPyConnection, manifests: list[str], location: str
) -> list[str]:
    """Union the manifests' dataFiles, deduped, in discovery order."""
    files: list[str] = []
    for manifest in manifests:
        files.extend(
            rebase_data_file(location, uri)
            for uri in read_manifest_data_files(conn, manifest)
        )
    return list(dict.fromkeys(files))


def manifest_view_sql(data_files: list[str], view: str = FOCUS_VIEW) -> str:
    """View over an explicit file list, with billing_period derived.

    union_by_name absorbs schema drift between billing periods (FOCUS 1.0
    months next to 1.2 months); Hive inference stays off because the file
    list already excludes the orphaned partitions it would trip over.
    """
    file_list = ", ".join(_sql_literal(f) for f in data_files)
    return f"""
        CREATE OR REPLACE VIEW {view} AS
        SELECT * EXCLUDE (filename), {BILLING_PERIOD_EXPR} AS billing_period
        FROM read_parquet(
            [{file_list}],
            union_by_name=true,
            hive_partitioning=false,
            filename=true
        )
    """


def glob_view_sql(location: str, hive_partitioning: bool, view: str = FOCUS_VIEW) -> str:
    """View over every Parquet file under the location.

    The recursive pattern reads whatever layout the location uses, so a
    partitioning scheme this server has never seen still loads.
    union_by_name absorbs schema drift between billing periods here for
    the same reason it does in manifest_view_sql.
    """
    pattern = _sql_literal(f"{location}/**/*.parquet")
    if hive_partitioning:
        return f"""
            CREATE OR REPLACE VIEW {view} AS
            SELECT * FROM read_parquet(
                {pattern}, union_by_name=true, hive_partitioning=true
            )
        """
    # Retry path: inference is off, so billing_period is derived from the
    # path instead of being dropped from the view.
    return f"""
        CREATE OR REPLACE VIEW {view} AS
        SELECT * EXCLUDE (filename), {BILLING_PERIOD_EXPR} AS billing_period
        FROM read_parquet(
            {pattern},
            union_by_name=true,
            hive_partitioning=false,
            filename=true
        )
    """


def _is_readable(conn: duckdb.DuckDBPyConnection, path: str) -> bool:
    """Whether DuckDB can still see a file a manifest points at."""
    try:
        return bool(
            conn.execute("SELECT count(*) FROM glob(?)", [path]).fetchone()[0]
        )
    except duckdb.Error:
        return False


def _create_manifest_view(
    conn: duckdb.DuckDBPyConnection,
    location: str,
    manifests: list[str],
    view: str,
) -> str:
    """Create the view from the export's own manifests."""
    data_files = collect_data_files(conn, manifests, location)
    if not data_files:
        # The manifests are proof this is an export, and globbing an
        # export double-counts it, so there is nothing to fall back to.
        raise RuntimeError(
            f"Found {len(manifests)} export manifest(s) under {location} but "
            "no data file in any of them; the export cannot be loaded "
            "without readable manifests"
        )
    logger.info(
        "Loading FOCUS data from %d export manifest(s): %d file(s)",
        len(manifests),
        len(data_files),
    )
    try:
        conn.execute(manifest_view_sql(data_files, view))
    except duckdb.IOException as e:
        # A manifest outlives its data when a period is expired or cleaned
        # up by hand. Serve the periods that are left rather than nothing.
        present = [f for f in data_files if _is_readable(conn, f)]
        if not present or len(present) == len(data_files):
            raise
        logger.warning(
            "%d of %d manifested file(s) under %s cannot be read (%s); "
            "loading the other %d",
            len(data_files) - len(present),
            len(data_files),
            location,
            e,
            len(present),
        )
        conn.execute(manifest_view_sql(present, view))
        return "manifest-partial"
    return "manifest"


def _create_glob_view(
    conn: duckdb.DuckDBPyConnection, location: str, view: str
) -> str:
    """Create the view from every Parquet file under the location."""
    logger.info(
        "No export manifests under %s; loading every Parquet file "
        "under the location",
        location,
    )
    try:
        conn.execute(glob_view_sql(location, hive_partitioning=True, view=view))
    except duckdb.BinderException as e:
        if "hive partition" not in str(e).lower():
            raise
        # Mixed partition-key casings, no manifests to disambiguate them
        logger.warning(
            "Hive partition mismatch under %s (%s); loading without "
            "partition inference",
            location,
            e,
        )
        conn.execute(glob_view_sql(location, hive_partitioning=False, view=view))
        return "glob-no-hive"
    return "glob"


def create_location_view(
    conn: duckdb.DuckDBPyConnection, location: str, view: str
) -> str:
    """Create one view over the data at one location.

    Returns the name of the strategy used, which callers surface: a glob
    over what turns out to be an export is the failure mode this module
    exists to avoid, and it is invisible otherwise.
    """
    manifests = discover_manifests(conn, location)
    if manifests:
        return _create_manifest_view(conn, location, manifests, view)
    return _create_glob_view(conn, location, view)


def billing_periods(
    conn: duckdb.DuckDBPyConnection, view: str
) -> Optional[set[str]]:
    """The distinct billing periods in a view, or None if it has no column.

    Compared as text, so a location that stores the month as a timestamp
    and one that stores it as a string still line up. Rows without a month
    are left out: they cannot be said to overlap anything.
    """
    columns = {row[0] for row in conn.execute(f"DESCRIBE {view}").fetchall()}
    if BILLING_PERIOD_COLUMN not in columns:
        return None
    rows = conn.execute(
        f"SELECT DISTINCT CAST({BILLING_PERIOD_COLUMN} AS VARCHAR) FROM {view}"
        f" WHERE {BILLING_PERIOD_COLUMN} IS NOT NULL"
    ).fetchall()
    return {period for (period,) in rows}


def union_view_sql(views: list[str], superseded: list[set[str]]) -> str:
    """View over several location views, later ones winning on overlap.

    ``superseded[i]`` holds the billing periods a later location already
    covers, so the earlier location's rows for those months are filtered
    out. The sets are computed once, when the view is built, and inlined
    here: every query then pays only a comparison against a handful of
    literals. UNION ALL BY NAME lines the locations up by column name, so
    they need not share a schema.
    """
    selects = []
    for view, periods in zip(views, superseded):
        select = f"SELECT * FROM {view}"
        if periods:
            values = ", ".join(_sql_literal(p) for p in sorted(periods))
            select += (
                f" WHERE {BILLING_PERIOD_COLUMN} IS NULL"
                f" OR CAST({BILLING_PERIOD_COLUMN} AS VARCHAR) NOT IN ({values})"
            )
        selects.append(select)
    body = "\n            UNION ALL BY NAME\n            ".join(selects)
    return f"""
        CREATE OR REPLACE VIEW {FOCUS_VIEW} AS
            {body}
    """


def create_focus_view(
    conn: duckdb.DuckDBPyConnection, locations: Union[str, Sequence[str]]
) -> str:
    """Create the focus_data_table view over one or more locations.

    Returns the strategy each location was loaded with, joined with "+".

    Errors propagate: the caller decides whether to attach a backend hint
    to them.
    """
    if isinstance(locations, str):
        locations = [locations]
    locations = list(locations)
    if not locations:
        raise ValueError("A dataset needs at least one location")
    if len(locations) == 1:
        return create_location_view(conn, locations[0], FOCUS_VIEW)

    views = []
    strategies = []
    empty: list[str] = []
    for index, location in enumerate(locations):
        view = PART_VIEW.format(index=index)
        try:
            strategies.append(create_location_view(conn, location, view))
        except duckdb.IOException as e:
            # An export that is configured but has not delivered yet, or a
            # history prefix nothing was converted into. The dataset is the
            # locations that do have data; only when none do is it an error.
            if "no files found" not in str(e).lower():
                raise
            logger.warning("No data under %s yet; skipping it", location)
            empty.append(location)
            continue
        views.append(view)
    if not views:
        raise duckdb.IOException(
            f"No files found under any of: {', '.join(locations)}"
        )
    if len(views) == 1:
        conn.execute(f"CREATE OR REPLACE VIEW {FOCUS_VIEW} AS SELECT * FROM {views[0]}")
        return strategies[0]

    periods = [billing_periods(conn, view) for view in views]
    superseded = [
        set().union(*(later or set() for later in periods[index + 1:]))
        if periods[index] is not None
        else set()
        for index in range(len(views))
    ]
    logger.info(
        "Unioning %d location(s); %d dropped as superseded",
        len(views),
        sum(1 for s in superseded if s),
    )
    conn.execute(union_view_sql(views, superseded))
    return "+".join(strategies)
