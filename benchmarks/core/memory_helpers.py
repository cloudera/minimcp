import resource
import sys

from psutil import Process

MEMORY_USAGE_UNIT = "KB"


# On macOS, the max RSS is in bytes, on other platforms it is in kilobytes
_maxrss_divisor = 1 if sys.platform.startswith("linux") else 1024


def get_rss_kb(process: Process) -> float:
    return float(process.memory_info().rss) / 1024


def get_current_maxrss_kb() -> float:
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / _maxrss_divisor
