<p align="center">
  <a href="https://glassity.cloud">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset=".github/assets/logo-dark-mode.svg">
      <img src=".github/assets/logo-light-mode.svg" alt="Glassity" width="320">
    </picture>
  </a>
</p>

<p align="center">
  <a href="https://github.com/glassity/focus-mcp/actions/workflows/docker-publish.yml"><img src="https://github.com/glassity/focus-mcp/actions/workflows/docker-publish.yml/badge.svg" alt="Docker build"></a>
  <a href="https://hub.docker.com/r/glassity/focus-mcp"><img src="https://img.shields.io/docker/pulls/glassity/focus-mcp?color=0EA0BE" alt="Docker pulls"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-1E1839" alt="License: Apache-2.0"></a>
</p>

<p align="center">
  <a href="https://focus.finops.org/"><img src="https://img.shields.io/badge/FOCUS%20v1.0-36%20queries-blue.svg" alt="FOCUS v1.0: 36 queries"></a>
  <a href="https://focus.finops.org/"><img src="https://img.shields.io/badge/FOCUS%20v1.1-41%20queries-green.svg" alt="FOCUS v1.1: 41 queries"></a>
  <a href="https://focus.finops.org/"><img src="https://img.shields.io/badge/FOCUS%20v1.2-53%20queries-orange.svg" alt="FOCUS v1.2: 53 queries"></a>
</p>

# FOCUS MCP Server

Ask your AI assistant what your cloud actually costs. This MCP (Model Context
Protocol) server connects Claude, or any other MCP client, to your
[FOCUS](https://focus.finops.org/) billing data, so questions like these become
one-line prompts instead of hand-written SQL:

- *"What are my highest-cost services by region this month?"*
- *"Show me commitment discount utilization trends."*
- *"Which accounts have unusual spending patterns?"*
- *"Explain the difference between BilledCost and EffectiveCost."*

Under the hood, [DuckDB](https://duckdb.org/) queries your Parquet exports
directly, whether they sit on local disk, S3, or GCS. There is no data
warehouse to stand up. The server bundles 130 queries curated from the
official FOCUS use-case catalog (36 for v1.0, 41 for v1.1, 53 for v1.2), and
each query cites the page it came from.

## What is FOCUS?

[FOCUS](https://focus.finops.org/) (FinOps Open Cost & Usage Specification) is
the open standard for cloud billing data. AWS, Microsoft, and Google Cloud
export it natively, so one schema and one set of queries work across
providers.

## Quick start

### 1. Get FOCUS data

Each provider has an official export path:

- AWS: [FOCUS setup guide for AWS](https://focus.finops.org/get-started/aws/) (Data Exports → FOCUS 1.0)
- Microsoft Azure: [FOCUS setup guide for Microsoft](https://focus.finops.org/get-started/microsoft/)
- Google Cloud: [FOCUS setup guide for Google Cloud](https://focus.finops.org/get-started/google-cloud/), or see [GCS + BigQuery](#google-cloud-gcs--bigquery-focus-export) below
- Other providers: [all FOCUS setup guides](https://focus.finops.org/get-started/)

The server reads Parquet with Hive partitioning:

```
/path/to/your/focus/data/
├── billing_period=2025-05/
│   ├── file1.parquet
│   └── file2.parquet
├── billing_period=2025-06/
│   └── ...
```

### 2. Run the server

Images are published to Docker Hub and GitHub Container Registry on every
release:

```bash
docker pull glassity/focus-mcp:latest          # Docker Hub
docker pull ghcr.io/glassity/focus-mcp:latest  # GHCR
```

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
        "-e", "FOCUS_VERSION=1.0",
        "glassity/focus-mcp:latest"
      ]
    }
  }
}
```

For S3 or GCS data, drop the volume mount and point `FOCUS_DATA_LOCATION` at
the bucket. See [Data locations](#data-locations) for the credential options.

### 3. Ask something

Start your client and try:

```
Show me what FOCUS data is loaded.
```

The assistant calls `get_data_info` and reports row counts, date ranges, and
providers. From there, ask in plain language:

```
Run the service costs by region analysis for the last 3 months.
Show me the top 10 most expensive services across all accounts.
Find unused capacity reservations I can optimize.
Compare costs across providers and regions.
What columns are available in FOCUS v1.2?
```

## Tools

Eight tools, in two groups.

Data and query:

| Tool | What it does |
| --- | --- |
| `get_data_info` | Inspect the loaded data: row counts, date ranges, providers |
| `list_use_cases` | Browse the predefined analysis queries for your FOCUS version |
| `get_use_case` | One query in detail: SQL, parameters, citation to the spec |
| `execute_query` | Run a predefined query or custom SQL against your data |

Schema and specification:

| Tool | What it does |
| --- | --- |
| `list_columns` | All FOCUS columns with type and requirement level |
| `get_column_details` | Full definition of one column |
| `list_attributes` | FOCUS formatting standards and conventions |
| `get_attribute_details` | Full requirements of one attribute |

The schema tools answer from the FOCUS specification itself, so the assistant
can explain what a column means as well as query it.

## Query library

Every query is extracted from the official
[FOCUS use-case catalog](https://focus.finops.org/use-cases/) and carries a
citation back to its source page:

- FOCUS v1.0: 36 queries
- FOCUS v1.1: 41 queries
- FOCUS v1.2: 53 queries

Coverage includes cost allocation, commitment discount tracking, anomaly
detection, budget reconciliation, and provider comparison. `FOCUS_VERSION`
selects which set is active.

## Data locations

### Local files

```bash
export FOCUS_DATA_LOCATION="/path/to/your/focus/data"
```

### Amazon S3

```bash
export FOCUS_DATA_LOCATION="s3://your-bucket/focus-exports"
export AWS_REGION="us-west-2"        # defaults to us-east-1
```

Authentication uses the standard AWS credential chain, in order: IAM role
(automatic on EC2/ECS/Lambda), `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`
environment variables, `AWS_PROFILE`, then `~/.aws/credentials`.

```bash
export AWS_PROFILE="billing-reader"   # use a specific profile
```

Some buckets store keys with a leading slash; if listing fails, try a double
slash after the bucket name: `s3://your-bucket//focus/path`.

When running in Docker, pass credentials as `-e` variables or mount the
profile read-only:

```bash
docker run -i --rm \
  -v "$HOME/.aws:/home/mcp/.aws:ro" \
  -e FOCUS_DATA_LOCATION="s3://your-bucket/focus-exports" \
  -e AWS_REGION="us-west-2" \
  -e AWS_PROFILE="billing-reader" \
  glassity/focus-mcp:latest
```

### Google Cloud (GCS + BigQuery FOCUS export)

Google Cloud exports billing natively in FOCUS format:
**Billing → Billing export → FOCUS usage cost** (Preview) writes a FOCUS table
to BigQuery. Export it to Parquet in a GCS bucket:

```sql
EXPORT DATA OPTIONS (
  uri = 'gs://your-bucket/focus-export/*.parquet',
  format = 'PARQUET',
  overwrite = true
) AS
SELECT * FROM `your-project.your_focus_dataset.your_focus_table`;
```

Schedule that statement as a BigQuery scheduled query to keep the bucket
fresh; this also archives your data past the FOCUS export's 2-year TTL. Then:

```bash
export FOCUS_DATA_LOCATION="gs://your-bucket/focus-export"
```

Authentication is tried in this order:

1. HMAC keys: set `GCS_HMAC_KEY_ID` and `GCS_HMAC_SECRET` (create with
   `gcloud storage hmac create <service-account-email>`). This path uses
   DuckDB's native GCS support over the S3-interoperability API and needs no
   extra dependencies.
2. Application Default Credentials: included in the Docker image; from a
   source checkout, install the extra with `uv sync --extra gcs`. Then
   authenticate however you normally do: `gcloud auth application-default
   login`, a service-account JSON via `GOOGLE_APPLICATION_CREDENTIALS`, or
   workload identity on GCE/GKE.
3. No credentials: public buckets only.

Two methods exist because DuckDB's built-in GCS support only speaks HMAC; ADC
comes from the optional `gcsfs` dependency. Credentials are only ever read
inside the server process and are never exposed to MCP clients.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `FOCUS_DATA_LOCATION` | `data/focus-export` | Where the Parquet lives: a local path, `s3://…`, or `gs://…` |
| `FOCUS_VERSION` | `1.0` | FOCUS specification version: `1.0`, `1.1`, or `1.2` |
| `AWS_REGION` | `us-east-1` | Region for S3 access |
| `AWS_PROFILE` | (unset) | AWS profile for S3 authentication |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | (unset) | Static AWS credentials, if not using a role or profile |
| `GCS_HMAC_KEY_ID` / `GCS_HMAC_SECRET` | (unset) | HMAC credentials for GCS |
| `GOOGLE_APPLICATION_CREDENTIALS` | (unset) | Service-account JSON for GCS via ADC |

## Development

```bash
git clone https://github.com/glassity/focus-mcp.git
cd focus-mcp

uv sync                 # install (uv recommended)
uv sync --extra gcs     # + GCS ADC support
uv sync --extra dev     # + ruff, mypy, black

export FOCUS_DATA_LOCATION="/path/to/your/focus/data"
uv run python focus_mcp_server.py
```

Point a client at the source checkout instead of the Docker image:

```json
{
  "mcpServers": {
    "focus": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/focus-mcp", "python", "focus_mcp_server.py"],
      "env": {
        "FOCUS_DATA_LOCATION": "/path/to/your/focus/data",
        "FOCUS_VERSION": "1.0"
      }
    }
  }
}
```

Build and run your own image:

```bash
docker build -t focus-mcp:custom .
docker run -i --rm \
  -v "/path/to/your/focus/data:/data:ro" \
  -e FOCUS_DATA_LOCATION=/data \
  focus-mcp:custom
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions and checks before
opening a pull request.

## Roadmap

- Automated query synchronization from the FOCUS specification, so new
  use-case pages land here without manual extraction
- Richer response formatting: citations and educational context inline in
  query results
- Validation of every use-case query against real v1.1 and v1.2 exports
- Evaluate moving column and attribute definitions to MCP resources
- Surface conformance-gap notes from the spec in tool responses

## Security

Report vulnerabilities to the address in [SECURITY.md](SECURITY.md), not the
issue tracker. Know the trust model: `execute_query` runs SQL that the AI
assistant writes, inside the server process. Your Parquet files are a query
source, not a writable database, and every example here mounts them `:ro`;
keep that. Run the Docker image rather than a bare process if you want a hard
boundary, and give the server only the object-store credentials it needs,
scoped to the billing bucket.

## License

Apache-2.0. Copyright Glassity. See [LICENSE](LICENSE).

---

<p align="center">
  Built by <a href="https://glassity.cloud">Glassity</a>, cloud cost
  visibility and optimization for AWS.
</p>
