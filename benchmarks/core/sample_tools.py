"""Sample tools for benchmarking the MCP server."""

import resource

import anyio
from psutil import Process

from benchmarks.core.memory_helpers import get_current_maxrss_kb, get_rss_kb


def compute_all_prime_factors(n: int) -> int:
    """
    Count all the prime factors of n (with repetition) - A synchronous operation for benchmarking.

    Example: n=12 -> 2*2*3 -> returns 3
    """

    if n < 2:
        raise ValueError("n must be greater than 2 for consistent benchmarking.")

    factor_count = 0

    # Find all factor 2s
    while n % 2 == 0:
        factor_count += 1
        n //= 2

    # n must be odd at this point, so we can skip even numbers
    i = 3
    while i * i <= n:
        while n % i == 0:
            factor_count += 1
            n //= i
        i += 2

    # If n is a prime greater than 2
    if n > 2:
        factor_count += 1

    return factor_count


async def async_compute_all_prime_factors(n: int) -> int:
    """Async function simulating I/O and synchronous operations - realistic mixed workload."""

    # Simulate fetching data from external source (e.g., database, API)
    await anyio.sleep(0.001)  # 1ms I/O simulation

    # Do synchronous work with fetched data
    result = compute_all_prime_factors(n)

    # Simulate writing result or another I/O operation
    await anyio.sleep(0.001)  # 1ms I/O simulation

    return result


def get_resource_usage() -> dict[str, float]:
    usage = resource.getrusage(resource.RUSAGE_SELF)

    return {
        # CPU Usage
        "user_cpu_seconds": usage.ru_utime,
        "system_cpu_seconds": usage.ru_stime,
        # Memory Usage
        "current_rss_kb": get_rss_kb(Process()),
        "maxrss_kb": get_current_maxrss_kb(),
        # Context Switches
        "voluntary_context_switches": usage.ru_nvcsw,
        "involuntary_context_switches": usage.ru_nivcsw,
        # Page Faults
        "major_page_faults": usage.ru_majflt,
        "minor_page_faults": usage.ru_minflt,
    }
