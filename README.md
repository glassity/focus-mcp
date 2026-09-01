<p align="center">
  <a href="https://glassity.cloud/?utm_source=focus-mcp&utm_medium=readme&utm_content=logo">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset=".github/assets/logo-dark-mode.svg">
      <img src=".github/assets/logo-light-mode.svg" alt="Glassity" width="320">
    </picture>
  </a>
</p>

<p align="center">
  <a href="https://github.com/glassity/focus-mcp/actions/workflows/docker-publish.yml"><img src="https://github.com/glassity/focus-mcp/actions/workflows/docker-publish.yml/badge.svg" alt="Docker build"></a>
  <a href="https://hub.docker.com/r/glassity/focus-mcp"><img src="https://img.shields.io/docker/pulls/glassity/focus-mcp?color=0EA0BE" alt="Docker pulls"></a>
  <a href="https://pypi.org/project/focus-mcp/"><img src="https://img.shields.io/pypi/v/focus-mcp?color=0EA0BE&cacheSeconds=1800" alt="PyPI version"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-1E1839" alt="License: Apache-2.0"></a>
</p>

<p align="center">
  <a href="https://focus.finops.org/"><img src="https://img.shields.io/badge/FOCUS%20v1.0-36%20queries-blue.svg" alt="FOCUS v1.0: 36 queries"></a>
  <a href="https://focus.finops.org/"><img src="https://img.shields.io/badge/FOCUS%20v1.1-41%20queries-green.svg" alt="FOCUS v1.1: 41 queries"></a>
  <a href="https://focus.finops.org/"><img src="https://img.shields.io/badge/FOCUS%20v1.2-53%20queries-orange.svg" alt="FOCUS v1.2: 53 queries"></a>
  <a href="https://focus.finops.org/"><img src="https://img.shields.io/badge/FOCUS%20v1.3-58%20queries-yellow.svg" alt="FOCUS v1.3: 58 queries"></a>
  <a href="https://focus.finops.org/"><img src="https://img.shields.io/badge/FOCUS%20v1.4-66%20queries-red.svg" alt="FOCUS v1.4: 66 queries"></a>
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
warehouse to stand up. The server bundles 254 queries curated from the
official FOCUS use-case catalog, as a separate collection per specification
version (36 for v1.0, 41 for v1.1, 53 for v1.2, 58 for v1.3, 66 for v1.4),
and each query cites the page it came from.

## What is FOCUS?

[FOCUS](https://focus.finops.org/) (FinOps Open Cost & Usage Specification) is
the open standard for cloud billing data. AWS, Microsoft, and Google Cloud
export it natively, so one schema and one set of queries work across
providers.

## Quick start

### 1. Get FOCUS data

Each provider has an official export path:

- AWS: [FOCUS setup guide for AWS](https://focus.finops.org/get-started/aws/) (Data Exports → FOCUS 1.0 or 1.2)
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

The quickest path needs no container. `uvx` fetches and runs the published
package in one step:

```bash
claude mcp add focus -e FOCUS_DATA_LOCATION=/path/to/your/focus/data -- uvx focus-mcp
```

For Claude Desktop, add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "focus": {
      "command": "uvx",
      "args": ["focus-mcp"],
      "env": {
        "FOCUS_DATA_LOCATION": "/path/to/your/focus/data",
        "FOCUS_VERSION": "1.0"
      }
    }
  }
}
```

Reading GCS with Application Default Credentials needs the `gcs` extra, which
uvx installs when you name it:

```bash
claude mcp add focus -e FOCUS_DATA_LOCATION=gs://your-bucket/focus \
  -- uvx --from 'focus-mcp[gcs]' focus-mcp
```

Docker remains available and is the better fit when you want a pinned,
attested image:

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
What columns are available in FOCUS v1.4?
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
- FOCUS v1.3: 58 queries
- FOCUS v1.4: 66 queries

Coverage includes cost allocation, commitment discount tracking, anomaly
detection, budget reconciliation, and provider comparison. `FOCUS_VERSION`
selects which set is active; match it to what your provider exports. The
specification runs ahead of the exports - AWS Data Exports currently
delivers FOCUS 1.0 and 1.2 - so the 1.3 and 1.4 collections are ready for
the day a provider ships them.

## Data locations

### Local files

```bash
export FOCUS_DATA_LOCATION="/path/to/your/focus/data"
```

A downloaded copy of an AWS Data Export (`aws s3 sync`, a mounted volume)
is loaded through the manifests it was copied with, exactly as the bucket
itself would be — see below.

### Amazon S3

```bash
export FOCUS_DATA_LOCATION="s3://your-bucket/focus-exports"
export AWS_REGION="us-west-2"        # defaults to us-east-1
```

Point the location at the export root, the prefix holding both `data/` and
`metadata/`. AWS Data Exports list every file of their latest delivery in a
per-billing-period manifest under `metadata/`, and the server loads those
files when the manifests are there: superseded chunks and re-delivered
periods left behind on the prefix are ignored instead of double-counted.
Locations without manifests — a BigQuery export, a directory of Parquet
files — are read by globbing every Parquet file underneath them.
`get_data_info` reports which of the two was used, and the file list is
refreshed every few minutes so new deliveries need no restart.

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

## Many datasets, one server

Every data tool takes an optional `dataset` handle and `focus_version`, so
one process can answer for several exports: a chat can compare last year's
FOCUS 1.0 archive with this month's 1.2 export without restarting anything.
Leave both out and the server uses `FOCUS_DATA_LOCATION` / `FOCUS_VERSION`.

Handles are names, not paths. The server resolves them in this order:

1. Datasets the request itself declares (HTTP only, see below).

2. `FOCUS_DATASETS`, a JSON map for self-hosted setups:

   ```bash
   export FOCUS_DATASETS='{
     "archive": {"location": "s3://billing/focus-2025", "version": "1.0"},
     "current": {"location": "s3://billing/focus", "version": "1.2"}
   }'
   ```

3. Over stdio, a raw location (`s3://…`, `/path`) is accepted as a handle
   too: the client is the same user as the server. Over HTTP it is refused
   unless `FOCUS_ALLOW_RAW_LOCATIONS=true`, because there the handle rides in
   a request header that intermediaries can read.

### Running as a shared server

```bash
FOCUS_TRANSPORT=streamable-http FOCUS_HTTP_HOST=0.0.0.0 FOCUS_HTTP_PORT=8000 uvx focus-mcp
```

The endpoint is `http://host:8000/mcp`, Streamable HTTP, stateless: every
request carries what it needs, so replicas can sit behind a plain load
balancer and the process holds no per-tenant configuration.

A request says what it may read, and brings the keys to read it with, in
headers:

| Header | Example | Meaning |
| --- | --- | --- |
| `X-Focus-Datasets` | `current=s3://billing/focus/, archive=s3://billing/focus-2025/@1.0` | Comma-separated `name=location`, optionally `@version`. The first entry is the default dataset. Only these names resolve for the request; the server's own `FOCUS_DATASETS` and default are not visible to it |
| `X-Focus-Version` | `1.2` | FOCUS version for every dataset without its own `@version` |
| `X-Aws-Access-Key-Id`, `X-Aws-Secret-Access-Key`, `X-Aws-Session-Token` | | AWS keys used for this request only, scoped to the dataset's location. Session token optional |
| `X-Aws-Region` | `eu-west-1` | Bucket region; falls back to `AWS_REGION` |

`get_data_info` reports `available_datasets` so the model knows what it may
name. Keys never go into tool arguments, and the server never logs them.

With Claude Code that is one line:

```bash
claude mcp add --transport http focus http://host:8000/mcp \
  --header "X-Focus-Datasets: current=s3://billing/focus/" \
  --header "X-Aws-Region: us-east-1" \
  --header "X-Aws-Access-Key-Id: AKIA…" \
  --header "X-Aws-Secret-Access-Key: …"
```

Hand the server short-lived keys where you can: an STS session whose
policy allows only the prefix in `X-Focus-Datasets` means a leaked header
buys one prefix for one hour. A service in front of the server (a chat
backend, a gateway) can mint such keys per tenant and set the headers
itself, which is how one server serves many tenants without storing any of
their credentials.

The `dataset` and `focus_version` parameters are declared with
[`x-mcp-header`](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#x-mcp-header),
so protocol 2026-07-28 clients mirror them into `Mcp-Param-Dataset` and
`Mcp-Param-Focus-Version` headers and a gateway can route or meter by
dataset without parsing the body. Older clients still work; the values just
travel in the body only. Clients mirror them only after they have seen the
tool schema: a `tools/call` sent before any `tools/list` is rejected by the
server as a header/body mismatch (`-32020`), and the client is expected to
list and retry.

To require a bearer token on top, set `FOCUS_JWKS_URL`: tokens are JWTs and
verified here against your identity provider's keys (install the `auth`
extra: `uvx --from 'focus-mcp[auth]' focus-mcp`). `FOCUS_OIDC_ISSUER` pins
the expected issuer, and `FOCUS_RESOURCE_URL` is this server's public URL —
the audience tokens must name, and what the protected-resource metadata at
`/.well-known/oauth-protected-resource/mcp` advertises. It defaults to the
bind address, so set it behind a proxy.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `FOCUS_DATA_LOCATION` | `data/focus-export` | Where the Parquet lives: a local path, `s3://…`, or `gs://…` |
| `FOCUS_VERSION` | `1.0` | FOCUS specification version of the default dataset: `1.0`, `1.1`, `1.2`, `1.3` or `1.4`. Selects which query collection loads |
| `FOCUS_DATASETS` | (unset) | JSON map of dataset handles to `{location, version}`; see [Many datasets, one server](#many-datasets-one-server) |
| `FOCUS_ALLOW_RAW_LOCATIONS` | `false` | Accept a location as the `dataset` over HTTP (always allowed over stdio) |
| `FOCUS_MAX_DATASETS` | `8` | Open DuckDB connections kept at once; least recently used is closed beyond that |
| `FOCUS_TRANSPORT` | `stdio` | `stdio` or `streamable-http` |
| `FOCUS_HTTP_HOST` / `FOCUS_HTTP_PORT` | `127.0.0.1` / `8000` | Bind address for `streamable-http` |
| `FOCUS_JWKS_URL` | (unset) | JWKS endpoint for verifying bearer tokens; unset means no authentication |
| `FOCUS_OIDC_ISSUER` | (unset) | Expected token issuer, published as the authorization server |
| `FOCUS_RESOURCE_URL` | (unset) | This server's URL: the audience tokens must be issued for |
| `FOCUS_REQUIRED_SCOPES` | (unset) | Space-separated scopes a token must carry |
| `AWS_REGION` | `us-east-1` | Region for S3 access |
| `AWS_PROFILE` | (unset) | AWS profile for S3 authentication |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | (unset) | Static AWS credentials, if not using a role or profile |
| `GCS_HMAC_KEY_ID` / `GCS_HMAC_SECRET` | (unset) | HMAC credentials for GCS |
| `GOOGLE_APPLICATION_CREDENTIALS` | (unset) | Service-account JSON for GCS via ADC |

## Development

```bash
git clone https://github.com/glassity/focus-mcp.git
cd focus-mcp

uv sync                 # install, including dev tools
uv sync --extra gcs     # + GCS ADC support

export FOCUS_DATA_LOCATION="/path/to/your/focus/data"
uv run focus-mcp
```

Point a client at the source checkout instead of the Docker image:

```json
{
  "mcpServers": {
    "focus": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/focus-mcp", "focus-mcp"],
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
- Validation of every use-case query against real provider exports (AWS
  ships FOCUS 1.0 and 1.2 today; 1.3+ as providers adopt them)
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
  Built by <a href="https://glassity.cloud/?utm_source=focus-mcp&utm_medium=readme&utm_content=footer">Glassity</a>, cloud cost
  visibility and optimization for AWS.
  <br>
  <a href="https://app.glassity.cloud/users/sign_in?utm_source=github&utm_medium=referral&utm_campaign=focus-mcp">Try Glassity</a> on your own AWS bill.
</p>
