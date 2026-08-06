# Contributing

Thanks for your interest. This is a small Python project: one MCP server, a
query library extracted from the FOCUS specification, and a Docker image.

## Layout

- `focus_mcp_server.py`: the MCP server and all eight tools.
- `focus_queries.py` and `focus_spec_loader.py`: load the query library and
  the spec-derived column and attribute definitions.
- `resources/queries/`: use-case queries extracted from
  [focus.finops.org](https://focus.finops.org/use-cases/), keyed by FOCUS
  version. Each entry cites its source page.
- `resources/specifications/`: column and attribute definitions per FOCUS
  version.
- `scripts/`: the extractors that produce `resources/` from the published
  spec.
- `Dockerfile` and `.github/workflows/docker-publish.yml`: the image build,
  published to Docker Hub and GHCR on release tags.

## Developing

```bash
uv sync --extra dev
export FOCUS_DATA_LOCATION="/path/to/your/focus/data"   # your own FOCUS export
uv run python focus_mcp_server.py
```

Before opening a pull request, run the linter; it must come back clean:

```bash
uv run ruff check .
```

The fastest end-to-end check is pointing Claude Code at your checkout
(`claude mcp add focus-dev -- uv run --directory "$PWD" python
focus_mcp_server.py`) and asking it to inspect your data.

## Conventions

- Queries cite their source. Every entry in `resources/queries/` links the
  focus.finops.org page it came from. A query without a citation, or one
  edited away from what the source publishes, needs a comment explaining the
  divergence.
- Version claims are counted, not estimated. The per-version query counts in
  the README are what the server actually loads (the YAML minus the
  adjustments in `focus_use_cases_adjustments.yaml`), reported by the `Loaded
  N queries` line at startup. If your change adds or removes queries, re-run
  the server for each `FOCUS_VERSION` and update the README and badges.
- Credentials never cross the MCP boundary. Anything read from the
  environment stays inside the server process; tool responses carry data and
  metadata only.
- Commit subjects in the imperative mood; one logical change per pull
  request.

By contributing you agree that your contributions are licensed under the
Apache License 2.0, the same license that covers this repository.

## Security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).
