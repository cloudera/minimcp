# MiniMCP vs FastMCP · Benchmarks

Latest report: [Comprehensive Benchmark Report](./reports/COMPREHENSIVE_BENCHMARK_REPORT.md)

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

After the above steps, you can run the benchmark scripts with `taskset` to pin to specific CPU cores. This ensures the benchmark always runs on the same CPU cores, avoiding cache misses and CPU migration overhead.

```bash
taskset -c 0-3 uv run python -m <benchmark.module>
```

### Load Profiles

The benchmark uses four load profiles to test performance under different concurrency levels:

| Load       | Concurrency | Iterations | Rounds | Total Messages |
|------------|-------------|------------|--------|----------------|
| Sequential | 1           | 30         | 40     | 1,200          |
| Light      | 20          | 30         | 40     | 24,000         |
| Medium     | 100         | 15         | 40     | 60,000         |
| Heavy      | 300         | 15         | 40     | 180,000        |

## Analyze Results

The `analyze_results.py` script provides a visual comparison of benchmark results between MiniMCP and FastMCP. It displays response time comparisons across all load profiles with visual bar charts, performance improvements as percentages, memory usage comparisons, key findings, and metadata.

You can run it for each result JSON file with:

```bash
# Stdio
uv run python benchmarks/analyze_results.py benchmarks/reports/stdio_mcp_server_sync_benchmark_results.json

uv run python benchmarks/analyze_results.py benchmarks/reports/stdio_mcp_server_async_benchmark_results.json

# HTTP
uv run python benchmarks/analyze_results.py benchmarks/reports/http_mcp_server_sync_benchmark_results.json

uv run python benchmarks/analyze_results.py benchmarks/reports/http_mcp_server_async_benchmark_results.json

# Streamable HTTP
uv run python benchmarks/analyze_results.py benchmarks/reports/streamable_http_mcp_server_sync_benchmark_results.json

uv run python benchmarks/analyze_results.py benchmarks/reports/streamable_http_mcp_server_async_benchmark_results.json
```
