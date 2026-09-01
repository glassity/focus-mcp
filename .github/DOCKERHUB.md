# FOCUS MCP Server

Ask your AI assistant what your cloud actually costs. This MCP (Model
Context Protocol) server connects Claude, or any other MCP client, to your
[FOCUS](https://focus.finops.org/) billing data, so questions like these
become one-line prompts instead of hand-written SQL:

- *"What are my highest-cost services by region this month?"*
- *"Show me commitment discount utilization trends."*
- *"Which accounts have unusual spending patterns?"*

Under the hood, [DuckDB](https://duckdb.org/) queries your Parquet exports
directly, whether they sit on local disk, S3, or GCS. There is no data
warehouse to stand up. The server bundles 254 queries curated from the
official FOCUS use-case catalog, one collection per specification version
(v1.0 through v1.4), and each query cites the page it came from.

FOCUS (FinOps Open Cost & Usage Specification) is the open standard for
cloud billing data. AWS, Microsoft, and Google Cloud export it natively, so
one schema and one set of queries work across providers.

## Tags

- `latest` - most recent build from the main branch
- `0.3.0`, `0.3`, `0` - releases; pin one of these for reproducible setups

Images are multi-arch (`linux/amd64`, `linux/arm64`) and also mirrored to
GitHub Container Registry as `ghcr.io/glassity/focus-mcp`, where every
release carries a build provenance attestation.

## Quick start

For Claude Code, one command:

```bash
claude mcp add focus -- docker run -i --rm \
  -v /path/to/your/focus/data:/data:ro \
  -e FOCUS_DATA_LOCATION=/data \
  glassity/focus-mcp:latest
```

For Claude Desktop, add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "focus": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-v", "/path/to/your/focus/data:/data:ro",
        "-e", "FOCUS_DATA_LOCATION=/data",
        "glassity/focus-mcp:latest"
      ]
    }
  }
}
```

For S3 or GCS data, drop the volume mount and point `FOCUS_DATA_LOCATION`
at the bucket. Set `FOCUS_VERSION` (1.0-1.4) to pick which query collection
and column reference the server exposes; it defaults to 1.0.

Then start your client and ask:

```
Show me what FOCUS data is loaded.
```

## Documentation

Full documentation - provider export guides, credential options for S3 and
GCS, the tool reference, and uvx/PyPI installation - lives in the
[GitHub repository](https://github.com/glassity/focus-mcp).

## License

Apache-2.0. The bundled query library is adapted from the
[FOCUS use case library](https://focus.finops.org/use-cases/) (CC BY 4.0),
and every query keeps its source citation.

---

Built by [Glassity](https://glassity.cloud/?utm_source=focus-mcp&utm_medium=dockerhub),
cloud cost visibility and optimization for AWS.
