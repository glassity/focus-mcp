# Contributing

Thanks for your interest. This is a small Python project: one MCP server, a
query library extracted from the FOCUS specification, and a Docker image.

## Layout

- `src/focus_mcp/server.py`: the MCP server and all eight tools.
- `src/focus_mcp/datasets.py`: turns a dataset handle into a location (static
  map, HTTP catalog, or a raw path over stdio) and pools one DuckDB
  connection per location.
- `src/focus_mcp/auth.py`: bearer-token verification for the HTTP transport.
- `src/focus_mcp/queries.py` and `src/focus_mcp/spec_loader.py`: load the
  query library and the spec-derived column and attribute definitions.
- `src/focus_mcp/resources/queries/curated/<version>/`: the queries the
  server runs, one file each, one directory per FOCUS version. Alongside it
  `upstream/<version>/` holds the verbatim text from
  [focus.finops.org](https://focus.finops.org/use-cases/) that each is
  measured against. Every entry cites its source page.
- `src/focus_mcp/resources/specifications/`: column and attribute definitions
  per FOCUS version.
- `scripts/`: the extractors that produce `src/focus_mcp/resources/` from the
  published spec.
- `Dockerfile` and `.github/workflows/docker-publish.yml`: the image build,
  published to Docker Hub and GHCR on release tags.

## Developing

```bash
uv sync
export FOCUS_DATA_LOCATION="/path/to/your/focus/data"   # your own FOCUS export
uv run focus-mcp
```

Before opening a pull request, run the linter; it must come back clean:

```bash
uv run ruff check .
```

The fastest end-to-end check is pointing Claude Code at your checkout
(`claude mcp add focus-dev -- uv run --directory "$PWD" focus-mcp`) and asking
it to inspect your data.

## Conventions

- Queries cite their source. Every entry in `src/focus_mcp/resources/queries/`
  links the focus.finops.org page it came from. A query without a citation,
  or one edited away from what the source publishes, needs a comment
  explaining the divergence.
- Version claims are counted, not estimated. The per-version query counts in
  the README are what the server actually loads, reported by the `Loaded N
  queries` line at startup. If your change adds or removes queries, re-run
  the server for each `FOCUS_VERSION` and update the README and badges.
- Credentials never cross the MCP boundary. Anything read from the
  environment stays inside the server process; tool responses carry data and
  metadata only.
- Commit subjects in the imperative mood; one logical change per pull
  request.

By contributing you agree that your contributions are licensed under the
Apache License 2.0, the same license that covers this repository.

## Working on queries

Each FOCUS version has its own collection under
`src/focus_mcp/resources/queries/curated/<version>/`, one file per query.
The directory listing *is* the collection: files carry no version field,
and `FOCUS_VERSION` simply selects a directory.

Beside it, `upstream/<version>/` holds the verbatim text from the FinOps
Foundation. Never edit that by hand — it is the baseline every correction
is measured against. A curated query that departs from its upstream twin
must carry a `fix_comment` saying why. CI enforces both directions: an
unexplained divergence fails, and so does a `fix_comment` on a query that
no longer differs, which is how a fix made upstream surfaces.

The library is written in MySQL dialect and is not tested against DuckDB,
so most corrections are mechanical translations:

| upstream (MySQL) | DuckDB |
| --- | --- |
| `JSON_UNQUOTE(JSON_EXTRACT(x, '$.k'))` | `json_extract_string(x, '$.k')` |
| `JSON_CONTAINS_PATH(x, 'all', '$.a', '$.b')` | `json_exists(x, '$.a') AND json_exists(x, '$.b')` |
| `json_extract_array(x)` | `json_extract(x, '$[*]')` |
| `CAST(x AS UNSIGNED)` | `CAST(x AS BIGINT)` |
| `Tags["Application"]` | `Tags->>'Application'` |

The rest are genuine upstream bugs: missing commas between select
expressions, aliases used in `GROUP BY`, `ORDER BY` on a column absent
from `GROUP BY`. Fix them in place and say so.

**Fixing a query means fixing it in every version that ships it.** A
correction applied to some collections and not others still executes in
the rest, it just answers wrong, so CI fails on any query whose SQL
differs between versions. Comparison normalises away layout and the
renames the specification declares, since neither is a missed fix; where a
real difference is deliberate — upstream rewriting a query for a newer
version, say — record it with `divergence_note`.

Adding a version means adding a directory. Seed `upstream/<version>/` from
the FinOps Foundation's version-filtered index
(`/wp-json/focus/v1/use-cases?version=v1-4`), copy it to
`curated/<version>/`, then re-apply corrections until the suite is green.
Queries needing a FOCUS dataset other than Cost and Usage are left out:
`focus_data_table` is a single table and they cannot run against it.

Collections freeze rather than grow forever: once a provider retires an
export version, its directory stops taking backported fixes.

Queries are CC BY 4.0. Keep `source_url` pointing at the public use-case
page and keep `fix_comment` accurate — the licence requires stating that a
work was modified, and that field is what the server surfaces.

## Security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).
