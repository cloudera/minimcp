"""
memory_baseline must be first imported at the start of the benchmarked server file
before importing any other modules to get correct baseline RSS and max RSS values.

It provides a measure of the baseline memory footprint of the current process.
"""

import sys

# --- Validate memory_baseline was imported first ---
if "mcp" in sys.modules.keys():
    raise ImportError(
        "memory_baseline must be imported at the start before importing other libraries (specifically mcp) "
        "to get the best baseline RSS and max RSS values"
    )


from psutil import Process

from benchmarks.core.memory_helpers import get_current_maxrss_kb, get_rss_kb

_baseline_rss = get_rss_kb(Process())
_baseline_maxrss = get_current_maxrss_kb()


def get_memory_usage() -> dict[str, float]:
    return {
        "baseline_rss": _baseline_rss,
        "current_rss": get_rss_kb(Process()),
        "baseline_maxrss": _baseline_maxrss,
        "maxrss": get_current_maxrss_kb(),
    }
