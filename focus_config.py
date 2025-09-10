#!/usr/bin/env python3
"""
FOCUS MCP Server Configuration - Simplified
"""

import os

# Simple configuration - just environment variables
DATA_PATH = os.getenv("FOCUS_DATA_PATH", "data/focus-export")
FOCUS_VERSION = os.getenv("FOCUS_VERSION", "1.0")
