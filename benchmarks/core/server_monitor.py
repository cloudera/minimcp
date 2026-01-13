from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import anyio
from psutil import Process

from benchmarks.core.memory_helpers import get_rss_kb

CPU_TIME_UNIT = "seconds"
SLEEP_SECONDS = 0.1


def _total_cpu_time(process: Process) -> float:
    cpu_times = process.cpu_times()
    return cpu_times.user + cpu_times.system


async def _monitor_server_resource_task(
    run_monitor: anyio.Event,
    server_process: Process,
    cpu_time: list[float],
    memory_rss: list[float],
) -> None:
    """
    Monitor the resource usage of the server.
    """
    previous_cpu_time = _total_cpu_time(server_process)

    while not run_monitor.is_set():
        with server_process.oneshot():  # To speeds up the retrieval of multiple process information
            memory_rss.append(get_rss_kb(server_process))

            current_cpu_time = _total_cpu_time(server_process)
            cpu_time.append(current_cpu_time - previous_cpu_time)
            previous_cpu_time = current_cpu_time

        await anyio.sleep(SLEEP_SECONDS)

    # Exceptions are not expected, let the monitor and benchmark crash.
    # Final sample is not taken to keep it simple.


@asynccontextmanager
async def monitor_server_resource(server_process: Process) -> AsyncGenerator[tuple[list[float], list[float]], None]:
    """Monitor the resource usage of the server."""

    cpu_time: list[float] = []
    memory_rss: list[float] = []

    run_monitor = anyio.Event()

    async with anyio.create_task_group() as tg:
        tg.start_soon(_monitor_server_resource_task, run_monitor, server_process, cpu_time, memory_rss)
        try:
            yield cpu_time, memory_rss
        finally:
            run_monitor.set()
