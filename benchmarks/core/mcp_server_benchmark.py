import json
import platform
import sys
import time
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean, median, quantiles, stdev
from typing import Generic, TypeVar

import anyio
from mcp import ClientSession
from psutil import Process

from benchmarks.core import server_monitor
from benchmarks.core.memory_helpers import MEMORY_USAGE_UNIT

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


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


@dataclass(frozen=True, slots=True, order=True)
class BenchmarkIndex:
    round_idx: int
    iteration_idx: int
    concurrency_idx: int


@dataclass
class Result:
    server_name: str
    load_name: str
    start_timestamp: str
    duration_seconds: float

    metrics: dict[str, Summary]


R = TypeVar("R")  # Result type


class MCPServerBenchmark(Generic[R]):
    loads: list[Load]
    name: str
    description: str
    min_sample_per_quartile_bin: int

    results: list[Result]

    def __init__(self, loads: list[Load], name: str = "", description: str = "", min_sample_per_quartile_bin: int = 10):
        """
        Args:
            loads: The loads to run the benchmark for.
            name: The name of the benchmark.
            description: A string that describes the benchmark.
            min_sample_per_quartile_bin: The minimum number of samples per quartile bin.
                Ideally around 10 samples per bin to get a good summary.
        """

        self.loads = loads
        self.name = name
        self.description = description
        self.min_sample_per_quartile_bin = min_sample_per_quartile_bin

        self.results = []

    async def _worker(
        self,
        benchmark_index: BenchmarkIndex,
        elapsed_times: list[float],
        client: ClientSession,
        target: Callable[[ClientSession, BenchmarkIndex], Awaitable[R]],
        result_validator: Callable[[R, BenchmarkIndex], Awaitable[bool]] | None = None,
    ) -> None:
        t0 = time.perf_counter()
        result = await target(client, benchmark_index)
        elapsed_times.append(time.perf_counter() - t0)

        if result_validator is not None:
            assert await result_validator(result, benchmark_index), "Results do not match, benchmark run failed"

    async def _get_memory_usage(self, client: ClientSession) -> tuple[float, float]:
        memory_usage = (await client.call_tool("get_memory_usage")).structuredContent
        if memory_usage is None:
            raise ValueError("Memory usage was not returned by the server.")

        delta_maxrss = memory_usage["maxrss"] - memory_usage["baseline_maxrss"]
        baseline_rss = memory_usage["baseline_rss"]
        return delta_maxrss, baseline_rss

    def _summarize_data(self, samples: list[float], unit: str) -> Summary:
        sample_size = len(samples)

        N_100_QUARTILES = 100 * self.min_sample_per_quartile_bin
        N_4_QUARTILES = 4 * self.min_sample_per_quartile_bin

        if sample_size >= N_100_QUARTILES:
            qs = quantiles(samples, n=100, method="inclusive")
            q1 = qs[24]  # 25th percentile
            q3 = qs[74]  # 75th percentile

            p95 = qs[94]
            p99 = qs[98]
        elif sample_size >= N_4_QUARTILES:
            qs = quantiles(samples, n=4, method="inclusive")
            q1 = qs[0]  # 25th percentile
            q3 = qs[2]  # 75th percentile

            p95 = f"N/A (Need at least {N_100_QUARTILES} samples)"
            p99 = p95
        else:
            raise ValueError(f"Need at least {N_4_QUARTILES} samples to summarize, but got {sample_size}")

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

    async def run(
        self,
        server_name: str,
        client_server_lifespan: Callable[[], AbstractAsyncContextManager[tuple[ClientSession, Process]]],
        target: Callable[[ClientSession, BenchmarkIndex], Awaitable[R]],
        result_validator: Callable[[R, BenchmarkIndex], Awaitable[bool]] | None = None,
    ) -> None:
        print(f"Running benchmark for server {server_name} ", end="", flush=True)

        # -- 1. Load
        for load in self.loads:
            response_time_samples: list[float] = []
            throughput_rps_samples: list[float] = []
            cpu_time_samples: list[float] = []
            memory_usage_samples: list[float] = []
            max_memory_usage_samples: list[float] = []

            load_start_time = datetime.now()

            # -- 2. Round
            for round_idx in range(load.rounds):
                # Create a new client and server per round and monitor the resource usage
                async with client_server_lifespan() as (client, server_process):
                    async with server_monitor.monitor_server_resource(server_process) as (cpu_times, memory_rss):
                        round_start_time = time.perf_counter()
                        elapsed_times: list[float] = []

                        # -- 3. Iteration
                        for iteration_idx in range(load.iterations):
                            # Create a new task group for each iteration and run the target concurrently
                            async with anyio.create_task_group() as tg:
                                # -- 4. Concurrency
                                for concurrency_idx in range(load.concurrency):
                                    benchmark_index = BenchmarkIndex(round_idx, iteration_idx, concurrency_idx)
                                    tg.start_soon(
                                        self._worker,
                                        benchmark_index,
                                        elapsed_times,
                                        client,
                                        target,
                                        result_validator,
                                    )

                        # Throughput (RPS) calculation - Including the overhead of the benchmark and validation.
                        round_wall_clock_time = time.perf_counter() - round_start_time
                        throughput_rps_samples.append(load.iterations * load.concurrency / round_wall_clock_time)

                        # Get the max memory usage
                        delta_maxrss, baseline_rss = await self._get_memory_usage(client)
                        max_memory_usage_samples.append(delta_maxrss)
                        memory_rss_delta = [m - baseline_rss for m in memory_rss]

                        # Append metric samples
                        response_time_samples += elapsed_times
                        cpu_time_samples += cpu_times
                        memory_usage_samples += memory_rss_delta

                print(".", end="", flush=True)  # -- Round end

            load_end_time = datetime.now()
            print("*", end="", flush=True)  # -- Load end

            # Summarize and save the results for current load
            self.results.append(
                Result(
                    server_name=server_name,
                    load_name=load.name,
                    start_timestamp=load_start_time.strftime(TIMESTAMP_FORMAT),
                    duration_seconds=(load_end_time - load_start_time).total_seconds(),
                    metrics={
                        "response_time": self._summarize_data(response_time_samples, "seconds"),
                        "throughput_rps": self._summarize_data(throughput_rps_samples, "requests per second"),
                        "cpu_time": self._summarize_data(cpu_time_samples, server_monitor.CPU_TIME_UNIT),
                        "memory_usage": self._summarize_data(memory_usage_samples, MEMORY_USAGE_UNIT),
                        "max_memory_usage": self._summarize_data(max_memory_usage_samples, MEMORY_USAGE_UNIT),
                    },
                )
            )

        print(" done")  # -- Run end

    async def write_json(self, file_path: str):
        benchmark_file = Path(sys.argv[0])
        name = self.name or benchmark_file.stem

        server_names = ", ".join({r.server_name for r in self.results})
        load_names = ", ".join({r.load_name for r in self.results})

        description = f"The benchmark is run on MCP servers {server_names} with loads {load_names}. \
            {len(self.results)} results are available."

        if self.description:
            description += f"\n{self.description}"

        benchmark_summary = {
            "name": name,
            "description": description,
            "metadata": {
                "timestamp": datetime.now().strftime(TIMESTAMP_FORMAT),
                "environment": f"Python {platform.python_version()}, {platform.system()} {platform.release()}",
                "benchmark_file": benchmark_file.name,
                "duration_seconds": sum(result.duration_seconds for result in self.results),
            },
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
            "results": [asdict(result) for result in self.results],
        }

        with open(file_path, "w") as f:
            json.dump(benchmark_summary, f, indent=2)

        print(f"Benchmark summary written to {file_path}")
