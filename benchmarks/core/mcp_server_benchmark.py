import json
import platform
import sys
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import mean, median, quantiles, stdev
from typing import Generic, NamedTuple, TypeVar

import anyio
import psutil
from mcp import ClientSession
from psutil import Process

from benchmarks.core import server_monitor
from benchmarks.core.memory_helpers import MEMORY_USAGE_UNIT

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _get_environment_info() -> dict[str, object]:
    return {
        "python_version": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine(),
        "cpu_model": platform.processor() or "unknown",
        "cpu_physical_cores": psutil.cpu_count(logical=False),
        "cpu_logical_cores": psutil.cpu_count(logical=True),
        "total_ram_gb": round(psutil.virtual_memory().total / (1024**3), 2),
    }


@dataclass
class Summary:
    min: float
    max: float
    mean: float  # Latency (mean)
    stddev: float
    median: float
    p95: float | str
    p99: float | str
    iqr: float
    outliers_low: int
    outliers_high: int
    unit: str
    sample_size: int


@dataclass
class Load:
    name: str
    rounds: int
    iterations: int
    concurrency: int


@dataclass
class RunResult:
    server_name: str
    load_name: str
    metrics: dict[str, Summary]


@dataclass
class ServerConfig:
    name: str
    lifespan: Callable[[], AbstractAsyncContextManager[tuple[ClientSession, Process]]]
    metadata: dict[str, str] = field(default_factory=dict)


class RunServerResult(NamedTuple):
    response_time: list[float]
    throughput_rps: list[float]
    cpu_time: list[float]
    memory_usage: list[float]
    max_memory_usage: list[float]

    def extend(self, other: "RunServerResult") -> None:
        self.response_time.extend(other.response_time)
        self.throughput_rps.extend(other.throughput_rps)
        self.cpu_time.extend(other.cpu_time)
        self.memory_usage.extend(other.memory_usage)
        self.max_memory_usage.extend(other.max_memory_usage)


R = TypeVar("R")  # Result type


class BenchmarkScenario(ABC, Generic[R]):
    @abstractmethod
    async def target(self, client: ClientSession, iteration_idx: int, concurrency_idx: int) -> R: ...

    @abstractmethod
    def validate_result(self, result: R, iteration_idx: int, concurrency_idx: int) -> bool: ...


class MCPServerBenchmark(Generic[R]):
    loads: list[Load]
    servers: list[ServerConfig]

    def __init__(
        self,
        loads: list[Load],
        servers: list[ServerConfig],
        reports_dir: str,
        min_sample_per_quartile_bin: int = 10,
        warmup_iterations: int = 2,
    ):
        """
        Args:
            loads: The loads to run the benchmark for.
            servers: The server configurations to benchmark against each other.
            reports_dir: Directory where result JSON files are written.
            min_sample_per_quartile_bin: The minimum number of samples per quartile bin.
                Ideally around 10 samples per bin to get a good summary.
            warmup_iterations: Number of iterations to run before timing begins for each
                server round. Warms up the server process (caches, socket buffers) so that
                measured samples reflect steady-state performance.
        """

        self.loads = loads
        self.servers = servers
        self._reports_dir = reports_dir

        self._min_samples = 4 * min_sample_per_quartile_bin
        self._min_samples_full = 100 * min_sample_per_quartile_bin
        self._warmup_iterations = warmup_iterations

        self._validate_loads()

    def _validate_loads(self) -> None:
        """
        Raise ValueError if any load produces fewer response time samples than the minimum required by _summarize_data.
        """

        for load in self.loads:
            total = load.rounds * load.iterations * load.concurrency
            if total < self._min_samples:
                raise ValueError(
                    f"Load '{load.name}' produces {total} response time samples but needs at least {self._min_samples} "
                    f"(rounds={load.rounds} * iterations={load.iterations} * concurrency={load.concurrency}). "
                    "Increase rounds, iterations, or concurrency, or lower min_sample_per_quartile_bin."
                )

    async def _worker(
        self,
        iteration_idx: int,
        concurrency_idx: int,
        elapsed_times: list[float],
        client: ClientSession,
        scenario: BenchmarkScenario[R],
    ) -> None:
        """
        Executes the target function, tracks the elapsed time and validates the result.
        """

        t0 = time.perf_counter()
        result = await scenario.target(client, iteration_idx, concurrency_idx)
        elapsed_times.append(time.perf_counter() - t0)
        assert scenario.validate_result(result, iteration_idx, concurrency_idx), (
            "Results do not match, benchmark run failed"
        )

    async def _get_memory_usage(self, client: ClientSession) -> tuple[float, float]:
        memory_usage = (await client.call_tool("get_memory_usage")).structuredContent
        if memory_usage is None:
            raise ValueError("Memory usage was not returned by the server.")

        delta_maxrss = memory_usage["maxrss"] - memory_usage["baseline_maxrss"]
        baseline_rss = memory_usage["baseline_rss"]
        return delta_maxrss, baseline_rss

    def _summarize_data(self, samples: list[float], unit: str) -> Summary:
        sample_size = len(samples)

        if sample_size >= self._min_samples_full:
            qs = quantiles(samples, n=100, method="inclusive")
            q1 = qs[24]  # 25th percentile
            q3 = qs[74]  # 75th percentile

            p95 = qs[94]
            p99 = qs[98]
        elif sample_size >= self._min_samples:
            qs = quantiles(samples, n=4, method="inclusive")
            q1 = qs[0]  # 25th percentile
            q3 = qs[2]  # 75th percentile

            p95 = f"N/A (Need at least {self._min_samples_full} samples)"
            p99 = p95
        else:
            raise ValueError(f"Need at least {self._min_samples} samples to summarize, but got {sample_size}")

        iqr = q3 - q1
        low_cut = q1 - 1.5 * iqr
        high_cut = q3 + 1.5 * iqr

        return Summary(
            min=min(samples),
            max=max(samples),
            mean=mean(samples),
            stddev=stdev(samples) if sample_size > 1 else 0.0,  # sample stdev
            median=median(samples),
            p95=p95,
            p99=p99,
            iqr=iqr,
            outliers_low=sum(v < low_cut for v in samples),
            outliers_high=sum(v > high_cut for v in samples),
            unit=unit,
            sample_size=sample_size,
        )

    async def _run_server(
        self,
        server_config: ServerConfig,
        scenario: BenchmarkScenario[R],
        load: Load,
    ) -> RunServerResult:
        async with server_config.lifespan() as (client, server_process):
            # Warmup: bring the server to steady state before monitoring and timing begin.
            for iteration_idx in range(self._warmup_iterations):
                async with anyio.create_task_group() as tg:
                    for concurrency_idx in range(load.concurrency):
                        tg.start_soon(scenario.target, client, iteration_idx, concurrency_idx)

            async with server_monitor.monitor_server_resource(server_process) as (cpu_times, memory_rss):
                start_time = time.perf_counter()
                elapsed_times: list[float] = []

                # -- 1. Iteration
                for iteration_idx in range(load.iterations):
                    # Create a new task group for each iteration and run the target concurrently
                    async with anyio.create_task_group() as tg:
                        # -- 2. Concurrency
                        # The task group with start_soon guarantees that requests are in-flight simultaneously
                        for concurrency_idx in range(load.concurrency):
                            tg.start_soon(
                                self._worker,
                                iteration_idx,
                                concurrency_idx,
                                elapsed_times,
                                client,
                                scenario,
                            )

                # Throughput (RPS) calculation - Including the overhead of the benchmark and validation.
                throughput_rps = load.iterations * load.concurrency / (time.perf_counter() - start_time)

                # Get the max memory usage
                delta_maxrss, baseline_rss = await self._get_memory_usage(client)
                memory_rss_delta = [m - baseline_rss for m in memory_rss]

                return RunServerResult(
                    response_time=elapsed_times,
                    throughput_rps=[throughput_rps],
                    cpu_time=cpu_times,
                    memory_usage=memory_rss_delta,
                    max_memory_usage=[delta_maxrss],
                )

    async def run(
        self,
        name: str,
        description: str,
        scenario: BenchmarkScenario[R],
    ) -> None:
        server_names = ", ".join(s.name for s in self.servers)
        print(f"Running benchmark for servers [{server_names}] ", end="", flush=True)

        run_start_time = datetime.now()
        results: list[RunResult] = []

        # -- 1. Load
        for load in self.loads:
            # Per-server sample accumulators reset for each load
            accumulated_samples: dict[str, RunServerResult] = {
                server.name: RunServerResult([], [], [], [], []) for server in self.servers
            }

            # Server runs are interleaved to reduce ordering bias. Server order is reversed
            # half way through the rounds to further reduce ordering bias.
            mid_index = load.rounds // 2
            reversed_servers = self.servers[::-1]

            # -- 2. Round
            for round_idx in range(load.rounds):
                # -- 3. Server
                for server in self.servers if round_idx < mid_index else reversed_servers:
                    result = await self._run_server(server, scenario, load)
                    accumulated_samples[server.name].extend(result)
                    print(".", end="", flush=True)

            # Summarize and save results for each server
            for server in self.servers:
                s = accumulated_samples[server.name]
                results.append(
                    RunResult(
                        server_name=server.name,
                        load_name=load.name,
                        metrics={
                            "response_time": self._summarize_data(s.response_time, "seconds"),
                            "throughput_rps": self._summarize_data(s.throughput_rps, "requests per second"),
                            "cpu_time": self._summarize_data(s.cpu_time, server_monitor.CPU_TIME_UNIT),
                            "memory_usage": self._summarize_data(s.memory_usage, MEMORY_USAGE_UNIT),
                            "max_memory_usage": self._summarize_data(s.max_memory_usage, MEMORY_USAGE_UNIT),
                        },
                    )
                )

            print("*", end="", flush=True)  # -- Load end

        run_end_time = datetime.now()
        print(" Done")  # -- Run end

        self._write_json(
            results,
            name=name,
            description=description,
            start_timestamp=run_start_time.strftime(TIMESTAMP_FORMAT),
            duration_seconds=(run_end_time - run_start_time).total_seconds(),
        )

    def _write_json(
        self,
        results: list[RunResult],
        name: str,
        description: str,
        start_timestamp: str,
        duration_seconds: float,
    ) -> None:
        result_file_path = f"{self._reports_dir}/{name}.json"
        benchmark_py_file = Path(sys.argv[0])

        server_names = ", ".join({r.server_name for r in results})
        load_names = ", ".join({r.load_name for r in results})

        full_description = (
            f"{description}. The benchmark is run on MCP servers {server_names} with loads {load_names}. "
            f"{len(results)} results are available."
        )

        benchmark_summary = {
            "name": name,
            "description": full_description,
            "metadata": {
                "start_timestamp": start_timestamp,
                "write_timestamp": datetime.now().strftime(TIMESTAMP_FORMAT),
                "benchmark_py_file": benchmark_py_file.name,
                "duration_seconds": duration_seconds,
                "environment": _get_environment_info(),
            },
            "server_info": [{"name": s.name, "metadata": s.metadata} for s in self.servers],
            "load_info": [asdict(load) for load in self.loads],
            "metrics_info": {
                "response_time": {
                    "unit": "seconds",
                    "description": (
                        "End-to-end latency of each request from client call to response. "
                        "Sample is collected per request."
                    ),
                },
                "throughput_rps": {
                    "unit": "requests per second",
                    "description": (
                        "Throughput of the server process, calculated as the number of "
                        "requests per second. Sample is collected per round."
                    ),
                },
                "cpu_time": {
                    "unit": server_monitor.CPU_TIME_UNIT,
                    "description": (
                        "Each sample is the CPU time (user + system) of the server process during "
                        "the measurement interval. Samples are collected every "
                        f"{server_monitor.SLEEP_SECONDS} seconds. Uses process.cpu_times() internally."
                    ),
                },
                "memory_usage": {
                    "unit": MEMORY_USAGE_UNIT,
                    "description": (
                        "Memory usage of the server process excluding the baseline memory footprint. "
                        f"Samples are collected every {server_monitor.SLEEP_SECONDS} seconds. "
                        "Baseline is taken at the start of the benchmark."
                        "Uses process.memory_info().rss internally."
                    ),
                },
                "max_memory_usage": {
                    "unit": MEMORY_USAGE_UNIT,
                    "description": (
                        "Max memory usage of the server process excluding the baseline memory footprint. "
                        "Samples are collected per round. Baseline is taken at the start of the benchmark."
                        "Uses resource.getrusage(resource.RUSAGE_SELF).ru_maxrss internally."
                    ),
                },
            },
            "results": [asdict(result) for result in results],
        }

        with open(result_file_path, "w") as f:
            json.dump(benchmark_summary, f, indent=2)

        print(f"Benchmark summary written to {result_file_path}")
