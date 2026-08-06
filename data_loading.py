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
"""

import logging
import re

import duckdb

logger = logging.getLogger(__name__)

# Exactly one directory level: partition-level manifests only. Manifests
# of individual CREATE_NEW_REPORT executions live a level deeper, and the
# sibling <export>-Manifest-FOCUS.json does not end in "Manifest.json".
MANIFEST_GLOB = "{location}/metadata/*/*Manifest.json"

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


def manifest_view_sql(data_files: list[str]) -> str:
    """View over an explicit file list, with billing_period derived.

    union_by_name absorbs schema drift between billing periods (FOCUS 1.0
    months next to 1.2 months); Hive inference stays off because the file
    list already excludes the orphaned partitions it would trip over.
    """
    file_list = ", ".join(_sql_literal(f) for f in data_files)
    return f"""
        CREATE OR REPLACE VIEW focus_data_table AS
        SELECT * EXCLUDE (filename), {BILLING_PERIOD_EXPR} AS billing_period
        FROM read_parquet(
            [{file_list}],
            union_by_name=true,
            hive_partitioning=false,
            filename=true
        )
    """


def glob_view_sql(location: str, hive_partitioning: bool) -> str:
    """View over every Parquet file under the location.

    union_by_name absorbs schema drift between billing periods here for
    the same reason it does in manifest_view_sql.
    """
    pattern = _sql_literal(f"{location}/**/*.parquet")
    if hive_partitioning:
        return f"""
            CREATE OR REPLACE VIEW focus_data_table AS
            SELECT * FROM read_parquet(
                {pattern}, union_by_name=true, hive_partitioning=true
            )
        """
    # Retry path: inference is off, so billing_period is derived from the
    # path instead of being dropped from the view.
    return f"""
        CREATE OR REPLACE VIEW focus_data_table AS
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
    conn: duckdb.DuckDBPyConnection, location: str, manifests: list[str]
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
        conn.execute(manifest_view_sql(data_files))
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
        conn.execute(manifest_view_sql(present))
        return "manifest-partial"
    return "manifest"


def _create_glob_view(conn: duckdb.DuckDBPyConnection, location: str) -> str:
    """Create the view from every Parquet file under the location."""
    logger.info(
        "No export manifests under %s; loading every Parquet file "
        "under the location",
        location,
    )
    try:
        conn.execute(glob_view_sql(location, hive_partitioning=True))
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
        conn.execute(glob_view_sql(location, hive_partitioning=False))
        return "glob-no-hive"
    return "glob"


def create_focus_view(conn: duckdb.DuckDBPyConnection, location: str) -> str:
    """Create the focus_data_table view over the data at the location.

    Returns the name of the strategy used, which callers surface: a glob
    over what turns out to be an export is the failure mode this module
    exists to avoid, and it is invisible otherwise.

    Errors propagate: the caller decides whether to attach a backend hint
    to them.
    """
    manifests = discover_manifests(conn, location)
    if manifests:
        return _create_manifest_view(conn, location, manifests)
    return _create_glob_view(conn, location)
