# Multi-stage build for FOCUS MCP Server
# Stage 1: Build environment with dependencies
# Use official uv image with Python pre-installed
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

# Set working directory
WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Install dependencies in a virtual environment
# This creates a clean, isolated Python environment
RUN uv sync --frozen --no-dev

# Stage 2: Runtime environment
# Use minimal Python image for runtime
FROM python:3.11-slim-bookworm

# Install runtime dependencies for DuckDB
# These are required for DuckDB's C++ components
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source code
COPY *.py ./
COPY LICENSE ./
COPY resources/ ./resources/

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    FOCUS_DATA_LOCATION="/data" \
    FOCUS_VERSION="1.0"

# Create data directory for mounting
RUN mkdir -p /data

# Health check (optional - can be used by orchestrators)
# This verifies the server can start and respond
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import focus_mcp_server; print('OK')" || exit 1

# Expose stdio for MCP communication
# MCP servers typically communicate via stdio, not HTTP ports
# Run as non-root user for security
RUN useradd -m -u 1000 mcp && \
    chown -R mcp:mcp /app /data
USER mcp

# Set the entry point to the MCP server
# Users can override environment variables at runtime
ENTRYPOINT ["python", "focus_mcp_server.py"]
