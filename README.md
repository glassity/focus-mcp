# FOCUS MCP Server

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FOCUS v1.0](https://img.shields.io/badge/FOCUS%20v1.0-36%20queries-blue.svg)](https://focus.finops.org/)
[![FOCUS v1.1](https://img.shields.io/badge/FOCUS%20v1.1-41%20queries-green.svg)](https://focus.finops.org/)
[![FOCUS v1.2](https://img.shields.io/badge/FOCUS%20v1.2-53%20queries-orange.svg)](https://focus.finops.org/)

An educational MCP (Model Context Protocol) server for analyzing FOCUS (FinOps Open Cost & Usage Specification) billing data. This server provides AI assistants with powerful tools to query and analyze cloud cost data using the industry-standard FOCUS format.

## What is FOCUS?

[FOCUS](https://focus.finops.org/) (FinOps Open Cost & Usage Specification) is an open standard for cloud billing data that provides consistent, normalized cost and usage data across cloud providers like AWS, Azure, and Google Cloud. It enables organizations to:

- **Standardize** cost data across multiple cloud providers
- **Simplify** financial analysis and reporting
- **Enable** consistent FinOps practices
- **Improve** cost optimization and allocation

## What This Server Does

This MCP server connects AI assistants (like Claude) to your FOCUS billing data, enabling natural language queries for complex cost analysis. Instead of writing SQL manually, you can ask questions like:

- "What are my highest cost services by region this month?"
- "Show me commitment discount utilization trends"
- "Find anomalous spending patterns by account"

The server provides:

- 🔍 **36+ predefined queries** from the official FOCUS documentation
- 📊 **DuckDB-powered analytics** for fast querying of large datasets
- 🔄 **Multi-version support** (FOCUS v1.0, v1.1, v1.2)
- 📚 **Schema documentation** with column/attribute definitions from FOCUS spec
- 🎯 **Educational examples** with citations to official docs

## Features

### MCP Tools Available

**Data & Query Tools:**

1. **`get_data_info`** - Inspect your loaded FOCUS data (row counts, date ranges, providers)
2. **`list_use_cases`** - Browse 36+ predefined analysis queries
3. **`get_use_case`** - Get detailed info about specific queries (SQL, parameters, citations)
4. **`execute_query`** - Run custom SQL or predefined queries on your data

**Schema & Specification Tools:**

5. **`list_columns`** - List all FOCUS columns with metadata (type, requirement level)
6. **`get_column_details`** - Get detailed information for specific columns
7. **`list_attributes`** - List FOCUS formatting standards and conventions
8. **`get_attribute_details`** - Get detailed requirements for specific attributes

### Query Library

- **36+ Professional Queries (more queries for later versions)**: Curated from [focus.finops.org](https://focus.finops.org/) use cases
- **Version Support**: Queries for FOCUS v1.0, v1.1, and v1.2
- **Real-world Scenarios**: Cost optimization, budget tracking, anomaly detection
- **Official Citations**: Each query links back to the FOCUS documentation

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/glassity/focus-mcp.git
cd focus-mcp

# Install with uv (recommended)
uv sync

# Or install with pip
pip install -e .
```

### 2. Prepare Your FOCUS Data

This server works with FOCUS billing data in Parquet format with Hive partitioning.

```bash
# Set your data path
export FOCUS_DATA_PATH="/path/to/your/focus/data"

# Expected structure:
# /path/to/your/focus/data/
# ├── billing_period=2025-05/
# │   ├── file1.parquet
# │   └── file2.parquet
# ├── billing_period=2025-06/
# │   └── ...
```

**Getting FOCUS Data:**

- **AWS**: Enable FOCUS exports in Cost and Billing Preferences
- **Azure**: Use Cost Management exports with FOCUS format
- **GCP**: Export billing data in FOCUS format

### 3. Configure MCP Server

Add to your Claude Desktop `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "focus": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/focus-mcp",
        "python",
        "focus_mcp_server.py"
      ],
      "env": {
        "FOCUS_DATA_PATH": "/path/to/your/focus/data",
        "FOCUS_VERSION": "1.0"
      }
    }
  }
}
```

### 4. Test the Connection

Start Claude Desktop and try:

```
Can you show me information about my FOCUS data?
```

Claude will use the `get_data_info` tool to inspect your dataset.

## Usage Examples

```
# Inspect your data
"Show me what FOCUS data is loaded"

# Use a predefined query
"Run the service costs by region analysis for the last 3 months"

# Custom SQL analysis
"Show me the top 10 most expensive services across all accounts"

# Parameter-based queries
"Analyze commitment discount utilization for 2025-08-01 to 2025-09-01"

# Anomaly detection
"Find accounts with unusual spending patterns this month"

# Cost optimization
"Show me unused capacity reservations that I can optimize"

# Multi-provider analysis
"Compare costs across different cloud providers and regions"

# Schema exploration
"What columns are available in FOCUS v1.2?"
"Explain the difference between BilledCost and EffectiveCost"
```

## Configuration

### Environment Variables

| Variable          | Default             | Description                                 |
| ----------------- | ------------------- | ------------------------------------------- |
| `FOCUS_DATA_PATH` | `data/focus-export` | Path to your FOCUS parquet data             |
| `FOCUS_VERSION`   | `1.0`               | FOCUS specification version (1.0, 1.1, 1.2) |

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run locally
export FOCUS_DATA_PATH="data/focus-export"
uv run python focus_mcp_server.py
```

## Todo

- [ ] Implement automated query synchronization from FOCUS specification
- [x] Extract column definitions and attributes from FOCUS spec for enhanced data insights
- [ ] Enhance response formatting with citations and educational context for AI models
- [ ] Validate all use cases queries against v1.1 and v1.2 exports
- [ ] Evaluate if moving attributes/columns to MCP resources makes more sense
