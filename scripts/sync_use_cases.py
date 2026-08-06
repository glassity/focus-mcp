#!/usr/bin/env python3
"""Sync the FinOps Foundation use case library.

focus.finops.org is WordPress and exposes the library as JSON, so this
reads the API rather than scraping HTML:

    /wp-json/focus/v1/use-cases          index, grouped by capability
    /wp-json/focus/v1/use-cases/{slug}   detail, including the SQL

Writes `upstream/focus_use_cases.yaml`, the verbatim snapshot, and
`focus_use_cases.yaml`, what the server runs. The two differ only where we
have corrected a query; those entries carry a fix_comment and are never
overwritten automatically.

It propagates text changes to queries already in the library, but never
adds or removes one: upstream republishes a version bump as a new post
with a "-2" slug, so automatic add/remove would read as mass churn and
orphan every correction. Those cases are reported instead.

Usage:
    python scripts/sync_use_cases.py            # write files, print report
    python scripts/sync_use_cases.py --dry-run  # print report only
"""

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

import yaml

API = "https://focus.finops.org/wp-json/focus/v1"
# Omitting a user-agent earns a 403 after a handful of requests.
HEADERS = {"accept": "application/json", "user-agent": "focus-mcp-sync/1.0"}
DELAY = 0.3

QUERIES = Path(__file__).resolve().parent.parent / "src" / "focus_mcp" / "resources" / "queries"
LIBRARY = QUERIES / "focus_use_cases.yaml"
SNAPSHOT = QUERIES / "upstream" / "focus_use_cases.yaml"

SNAPSHOT_HEADER = """\
# Verbatim snapshot of the FinOps Foundation use case library.
#
# Machine-written by scripts/sync_use_cases.py, covering the queries this
# repo carries. Do not edit by hand: it is the baseline every local
# correction is measured against, so an edit redefines "unchanged".
#
# Source: https://focus.finops.org/use-cases/  (CC BY 4.0)

"""

LIBRARY_HEADER = """\
# The queries this server actually runs.
#
# Derived from upstream/focus_use_cases.yaml. A query that departs from
# that snapshot MUST carry a fix_comment saying why; CI fails on an
# unexplained divergence, and on a fix_comment whose query no longer
# differs from upstream.
#
# See CONTRIBUTING.md, "Fixing upstream queries".
#
# Source: https://focus.finops.org/use-cases/  (CC BY 4.0)

"""


# --- fetching -------------------------------------------------------------

def get(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)


def fetch_upstream() -> dict:
    """Fetch every use case, keyed by slug.

    A partial fetch must never reach the merge: it would look exactly like
    upstream deleting the queries that failed, so any error aborts.
    """
    index = get(f"{API}/use-cases")
    slugs = [
        use_case["slug"]
        for group in index["results"].values()
        for use_case in group["use_cases"]
    ]
    if not slugs:
        raise SystemExit("upstream index returned no use cases; refusing to continue")
    if len(slugs) != index.get("count", len(slugs)):
        print(f"note: index count {index.get('count')} != {len(slugs)} listed",
              file=sys.stderr)

    fetched = {}
    for i, slug in enumerate(slugs, 1):
        print(f"  [{i}/{len(slugs)}] {slug}", file=sys.stderr)
        fetched[slug] = get(f"{API}/use-cases/{slug}")
        time.sleep(DELAY)
    return fetched


# --- shaping --------------------------------------------------------------

def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    for entity, char in (("&amp;", "&"), ("&#038;", "&"), ("&#8217;", "'"),
                         ("&quot;", '"'), ("&nbsp;", " ")):
        text = text.replace(entity, char)
    return " ".join(text.split())


def normalise_title(title: str) -> str:
    title = unicodedata.normalize("NFKD", strip_html(title))
    title = title.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def key_for(slug: str) -> str:
    """Derive a library key from a slug, dropping WordPress' -N suffix."""
    return re.sub(r"-\d+$", "", slug).replace("-", "_")


def pick_query(detail: dict) -> tuple[dict | None, int]:
    """Choose the SQL variant to use, and report how many there were.

    Upstream now ships per-version variants of some use cases. The newest
    wins, since the library is read at the newest version we support.
    """
    variants = detail.get("related_queries") or []
    if not variants:
        return None, 0

    def newest(variant):
        versions = [v.replace("-", ".").lstrip("v")
                    for v in (variant.get("focus_versions") or [])]
        return max((tuple(int(p) for p in v.split(".")) for v in versions),
                   default=(0,))

    return max(variants, key=newest), len(variants)


def to_entry(detail: dict) -> dict | None:
    """Shape an API detail payload into a library entry."""
    variant, _ = pick_query(detail)
    if not variant or not (variant.get("sql_query") or "").strip():
        return None
    return {
        "title": strip_html(detail.get("title", "")),
        "slug": detail.get("slug", ""),
        "source_url": detail.get("url", ""),
        "focus_versions": sorted(
            v.replace("-", ".") for v in (variant.get("focus_versions") or [])
        ),
        "description": strip_html(detail.get("content", "")),
        "sql": (variant.get("sql_query") or "").replace("\r\n", "\n").strip(),
    }


# --- matching -------------------------------------------------------------

def match_existing(entry: dict, library: dict) -> str | None:
    """Find the library key an upstream use case corresponds to.

    A stored upstream.slug is exact and wins. Otherwise fall back to the
    title, which survives the "-2" re-slugging that a version bump causes.
    """
    slug = entry["slug"]
    for key, existing in library.items():
        if (existing.get("upstream") or {}).get("slug") == slug:
            return key

    wanted = normalise_title(entry["title"])
    hits = [key for key, existing in library.items()
            if normalise_title(existing.get("title", "")) == wanted]
    return hits[0] if len(hits) == 1 else None


# --- writing --------------------------------------------------------------

def literal(dumper, data):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


yaml.add_representer(str, literal)


def dump(obj: dict, path: Path, header: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.dump(obj, f, default_flow_style=False, allow_unicode=True,
                  sort_keys=False, width=1000)


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# --- the sync -------------------------------------------------------------

def sync(dry_run: bool = False) -> int:
    library = load(LIBRARY)
    previous = load(SNAPSHOT)

    print("Fetching use cases...", file=sys.stderr)
    fetched = fetch_upstream()

    upstream_entries, multi_variant, no_sql = {}, [], []
    for slug, detail in fetched.items():
        entry = to_entry(detail)
        if entry is None:
            no_sql.append(slug)
            continue
        if pick_query(detail)[1] > 1:
            multi_variant.append(slug)
        upstream_entries[slug] = entry

    # The snapshot is keyed by our library key, not upstream's slug, so the
    # two files stay aligned even as upstream re-slugs. Queries we do not
    # carry are reported rather than snapshotted.
    snapshot, applied, review, migrated, new = {}, [], [], [], []
    for slug, entry in upstream_entries.items():
        key = key_for(slug)
        target = key if key in library else match_existing(entry, library)
        if target is None:
            new.append(entry["title"])
            continue
        snapshot[target] = entry
        was = previous.get(target)
        current = library[target]
        # Record the identity we resolved, so later runs match exactly.
        current["upstream"] = {"slug": slug}
        if was is not None and was.get("sql") == entry["sql"]:
            continue  # upstream unchanged
        if current.get("fix_comment"):
            review.append((target, current["fix_comment"]))
            continue
        # A rewrite that moves the version tags is upstream porting the query
        # to a newer spec rather than correcting it, which can change the
        # columns it needs. That is a decision, not an update.
        if was is not None and was.get("focus_versions") != entry["focus_versions"]:
            migrated.append((target, was.get("focus_versions") or [],
                             entry["focus_versions"]))
            continue
        # slug is the identifier the MCP tools expose, so it stays ours;
        # upstream's lives in the upstream block.
        library[target] = {**current,
                           **{k: v for k, v in entry.items() if k != "slug"}}
        applied.append(target)

    # A query upstream no longer publishes keeps its old snapshot entry, so
    # it stays covered by the library invariants instead of falling out.
    missing = [k for k in library if k not in snapshot]
    for key in missing:
        if key in previous:
            snapshot[key] = previous[key]

    stale = [
        key for key, entry in library.items()
        if entry.get("fix_comment")
        and key in snapshot
        and entry.get("sql") == snapshot[key].get("sql")
    ]

    # --- report
    out = []
    out.append(f"FOCUS use case sync - {len(upstream_entries)} upstream queries\n")
    out.append(f"  {len(applied)} upstream change(s) applied cleanly")
    for key in applied:
        out.append(f"      {key}")
    out.append(f"\n  {len(review)} upstream change(s) under a local fix - REVIEW")
    for key, comment in review:
        out.append(f"      {key}")
        out.append(f"        our fix: {comment}")
    out.append(f"\n  {len(migrated)} query(ies) ported to a new spec version "
               "upstream - REVIEW")
    for key, before, after in migrated:
        out.append(f"      {key}: {', '.join(before) or '(untagged)'} "
                   f"-> {', '.join(after)}")
    out.append(f"\n  {len(stale)} local fix(es) no longer needed")
    for key in stale:
        out.append(f"      {key} - upstream matches ours; drop fix_comment")
    out.append(f"\n  {len(new)} new upstream use case(s) (not added)")
    for title in new:
        out.append(f"      {title}")
    out.append(f"\n  {len(missing)} library query(ies) with no upstream match (not removed)")
    for key in missing:
        out.append(f"      {key}")
    if multi_variant:
        out.append(f"\n  {len(multi_variant)} use case(s) ship several SQL variants; "
                   "took the newest")
        for slug in multi_variant:
            out.append(f"      {slug}")
    if no_sql:
        out.append(f"\n  {len(no_sql)} use case(s) carry no SQL; skipped")
    report = "\n".join(out)
    print(report)

    if dry_run:
        print("\n(dry run: nothing written)", file=sys.stderr)
        return 0

    dump(snapshot, SNAPSHOT, SNAPSHOT_HEADER)
    dump(library, LIBRARY, LIBRARY_HEADER)
    print(f"\nwrote {SNAPSHOT}\nwrote {LIBRARY}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing")
    args = parser.parse_args()
    try:
        return sync(dry_run=args.dry_run)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"upstream returned HTTP {e.code}; nothing written")
    except urllib.error.URLError as e:
        raise SystemExit(f"cannot reach upstream ({e.reason}); nothing written")


if __name__ == "__main__":
    raise SystemExit(main())
