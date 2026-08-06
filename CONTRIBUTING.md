# Contributing

Thanks for your interest. This is a small Python project: one MCP server, a
query library extracted from the FOCUS specification, and a Docker image.

## Layout

- `src/focus_mcp/server.py`: the MCP server and all eight tools.
- `src/focus_mcp/queries.py` and `src/focus_mcp/spec_loader.py`: load the
  query library and the spec-derived column and attribute definitions.
- `src/focus_mcp/resources/queries/`: use-case queries extracted from
  [focus.finops.org](https://focus.finops.org/use-cases/), keyed by FOCUS
  version. Each entry cites its source page.
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

## Fixing upstream queries

Use cases come from the FinOps Foundation. `scripts/sync_use_cases.py`
reads their JSON API and writes two files:

- `src/focus_mcp/resources/queries/upstream/focus_use_cases.yaml` is the
  verbatim snapshot. Never edit it by hand — it is the baseline every
  correction is measured against, so editing it silently redefines what
  counts as unchanged.
- `src/focus_mcp/resources/queries/focus_use_cases.yaml` is what the
  server runs. Edit this one.

A query that departs from the snapshot must carry a `fix_comment` saying
why. CI enforces both directions: an unexplained divergence fails, and so
does a `fix_comment` on a query that no longer differs — that means
upstream has since made the same fix and ours should be dropped.

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
from `GROUP BY`. Fix them in place and say so. Several have been published
unchanged across three spec versions, so do not wait on an upstream fix.

The sync never adds or removes a query on its own. Upstream republishes a
version bump as a new post with a `-2` slug, so automatic add/remove would
read as mass churn and orphan every correction; new and missing use cases
are reported for a human to decide on. It also declines to auto-apply a
rewrite that moves a query's version tags, since porting to a new spec
version can change which columns the query needs.

Queries are CC BY 4.0. Keep `source_url` pointing at the public use-case
page, and keep `fix_comment` accurate — the licence requires stating that
a work was modified, and that field is what the server surfaces.

## Security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).
