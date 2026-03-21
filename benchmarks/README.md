# MiniMCP vs FastMCP · Benchmarks

Latest report: [MiniMCP vs FastMCP Analysis](./reports/MINIMCP_VS_FASTMCP_ANALYSIS.md)

Once you've set up a development environment as described in [CONTRIBUTING.md](../../CONTRIBUTING.md), you can run the benchmark scripts.

## Running Benchmarks

Each transport has a separate benchmark script that can be run with the following commands. Only tool calling is used for benchmarking as other primitives aren't much different functionally. Each script produces two result files: one for sync tool calls and another for async tool calls.

```bash
# Stdio
uv run python -m benchmarks.macro.stdio_mcp_server_benchmark

# HTTP
uv run python -m benchmarks.macro.http_mcp_server_benchmark

# Streamable HTTP
uv run python -m benchmarks.macro.streamable_http_mcp_server_benchmark
```

> **FastMCP Version:** The benchmarks compare MiniMCP against the [FastMCP](https://pypi.org/project/fastmcp/) package. The version in use is pinned in the `dev` dependency group in `pyproject.toml`. To temporarily use a different version, run `uv pip install fastmcp==<version>` before running the scripts.

### System Preparation - Best practice in Ubuntu

The following steps can help you get consistent benchmark results. They are specifically for Ubuntu, but similar steps may exist for other operating systems.

```bash
# Stop unnecessary services
sudo systemctl stop snapd
sudo systemctl stop unattended-upgrades

# Disable CPU frequency scaling (use performance governor)
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Disable turbo boost for consistency (optional but recommended)
echo 1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo  # Intel
# OR for AMD:
echo 0 | sudo tee /sys/devices/system/cpu/cpufreq/boost
```

After the above steps, run the benchmark scripts as normal.

> **CPU Affinity:** The benchmarks automatically pin the client process to the lower half of CPU cores and each server subprocess to the upper half, so the client and server do not compete for the same cores. CPU affinity is Linux-only. On macOS it is silently skipped — results will still be valid but with more OS scheduling noise.

### Development Mode

Set `BENCHMARK_DEV=1` to run a single lightweight load (`concurrency=1, iterations=1, rounds=40`) instead of the full suite. Useful for quickly verifying benchmark changes without waiting for a full run.

```bash
BENCHMARK_DEV=1 uv run python -m benchmarks.macro.http_mcp_server_benchmark
```

### Load Profiles

The benchmark uses four load profiles to test performance under different concurrency levels:

| Load       | Concurrency | Iterations | Rounds | Total Messages |
|------------|-------------|------------|--------|----------------|
| Sequential | 1           | 30         | 40     | 1,200          |
| Light      | 20          | 30         | 40     | 24,000         |
| Medium     | 100         | 15         | 40     | 60,000         |
| Heavy      | 300         | 15         | 40     | 180,000        |

### Analyze Results

The `analyze_results.py` script provides a visual comparison of benchmark results between MiniMCP and FastMCP. It displays response time comparisons across all load profiles with visual bar charts, performance improvements as percentages, memory usage comparisons, key findings, and metadata.

You can run it for each result JSON file with:

```bash
# Stdio
uv run python benchmarks/analyze_results.py benchmarks/reports/stdio_mcp_server_sync_benchmark_results.json

uv run python benchmarks/analyze_results.py benchmarks/reports/stdio_mcp_server_io_bound_async_benchmark_results.json

uv run python benchmarks/analyze_results.py benchmarks/reports/stdio_mcp_server_noop_benchmark_results.json

# HTTP
uv run python benchmarks/analyze_results.py benchmarks/reports/http_mcp_server_sync_benchmark_results.json

uv run python benchmarks/analyze_results.py benchmarks/reports/http_mcp_server_io_bound_async_benchmark_results.json

uv run python benchmarks/analyze_results.py benchmarks/reports/http_mcp_server_noop_benchmark_results.json

# Streamable HTTP
uv run python benchmarks/analyze_results.py benchmarks/reports/streamable_http_mcp_server_sync_benchmark_results.json

uv run python benchmarks/analyze_results.py benchmarks/reports/streamable_http_mcp_server_io_bound_async_benchmark_results.json

uv run python benchmarks/analyze_results.py benchmarks/reports/streamable_http_mcp_server_noop_benchmark_results.json
```

## Profiling

The `profiles/` directory contains [viztracer](https://viztracer.readthedocs.io/) profiling scripts for investigating hot paths at the framework level. These scripts call transport dispatch functions directly (no network), so they isolate pure framework overhead.

### Available profiles

| Script | What it profiles |
|---|---|
| `profiles/profile_minimcp.py` | All four execution layers (raw handle → raw+send → HTTP → StreamableHTTP) across I/O-bound and noop workloads — the primary profiling entry point |
| `profiles/profile_streamable_http.py` | Focused comparison of StreamableHTTP vs plain HTTP under concurrent I/O-bound and noop tool calls |

```bash
# Full layered profile — raw handle, raw+send, HTTP, and StreamableHTTP (6 traces)
uv run python -m benchmarks.profiles.profile_minimcp

# Focused StreamableHTTP vs HTTP comparison (3 traces)
uv run python -m benchmarks.profiles.profile_streamable_http
```

Output trace files are written to `benchmarks/profiles/traces/` (git-ignored). Open any trace with:

```bash
# profile_minimcp.py outputs
uv run viztracer --open benchmarks/profiles/traces/profile_raw_io_bound.json
uv run viztracer --open benchmarks/profiles/traces/profile_raw_send_io_bound.json
uv run viztracer --open benchmarks/profiles/traces/profile_http_io_bound.json
uv run viztracer --open benchmarks/profiles/traces/profile_streamable_http_io_bound.json
uv run viztracer --open benchmarks/profiles/traces/profile_raw_noop.json
uv run viztracer --open benchmarks/profiles/traces/profile_streamable_http_noop.json

# profile_streamable_http.py outputs
uv run viztracer --open benchmarks/profiles/traces/profile_streamable_http_io_bound.json
uv run viztracer --open benchmarks/profiles/traces/profile_http_io_bound.json
uv run viztracer --open benchmarks/profiles/traces/profile_streamable_http_noop.json
```
