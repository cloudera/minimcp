import os

from benchmarks.core.mcp_server_benchmark import Load

# --- Server Configuration ---

SERVER_HOST = os.environ.get("TEST_SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("TEST_SERVER_PORT", "30789"))

HTTP_MCP_PATH = "/mcp"


# --- Paths ---

REPORTS_DIR = "benchmarks/reports"

# --- Load Configuration ---

LOADS = [
    Load(name="sequential_load", concurrency=1, iterations=30, rounds=40),
    Load(name="light_load", concurrency=20, iterations=30, rounds=40),
    Load(name="medium_load", concurrency=100, iterations=15, rounds=40),
    Load(name="heavy_load", concurrency=300, iterations=15, rounds=40),
]
