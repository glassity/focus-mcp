# Multi-stage build for FOCUS MCP Server
# Stage 1: Build environment with dependencies
# Use official uv image with Python pre-installed
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

WORKDIR /app

# Dependencies first, without the project, so this layer caches across
# source changes. README.md is copied because pyproject.toml declares it
# as the readme and hatchling reads project metadata here.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra gcs --no-install-project

# Now the project itself, installed into the same venv.
# --no-editable copies the package into site-packages instead of linking
# back to ./src, which would otherwise vanish when only .venv is copied
# into the runtime stage below.
COPY src/ ./src/
RUN uv sync --frozen --no-dev --extra gcs --no-editable

# Stage 2: Runtime environment
FROM python:3.11-slim-bookworm

# Runtime dependencies for DuckDB's C++ components
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The venv holds the installed package; no loose source is copied
COPY --from=builder /app/.venv /app/.venv
COPY LICENSE ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    FOCUS_DATA_LOCATION="/data" \
    FOCUS_VERSION="1.0"

RUN mkdir -p /data

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import focus_mcp.server; print('OK')" || exit 1

# stdio by default (no port); FOCUS_TRANSPORT=streamable-http serves /mcp on
# FOCUS_HTTP_PORT instead - set FOCUS_HTTP_HOST=0.0.0.0 to reach it from
# outside the container.
EXPOSE 8000
RUN useradd -m -u 1000 mcp && \
    chown -R mcp:mcp /app /data
USER mcp

ENTRYPOINT ["focus-mcp"]
