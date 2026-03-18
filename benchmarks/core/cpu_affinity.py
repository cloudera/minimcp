import logging
import sys

import psutil

logger = logging.getLogger(__name__)

CPU_SPLIT_FRACTION = 0.5

_CPU_AFFINITY_SUPPORTED = sys.platform == "linux"
_CPU_COUNT = psutil.cpu_count() or 0


def set_cpu_affinity(process: psutil.Process, start: float, end: float) -> bool:
    """
    Pin a process to the given CPU core range.
    The start and end are fractions of the total number of CPU cores, and must be between 0 and 1.

    Args:
        process: The process to pin.
        start: The start of the CPU core range as a fraction of the total number of CPU cores.
        end: The end of the CPU core range as a fraction of the total number of CPU cores.

    Returns:
        True if the CPU core range was set successfully, False otherwise.
    """

    if _CPU_AFFINITY_SUPPORTED and _CPU_COUNT >= 2:
        _server_cores = list(range(int(_CPU_COUNT * start), int(_CPU_COUNT * end)))
        try:
            # Use getattr to avoid pyright error if cpu_affinity is not supported on this platform.
            getattr(process, "cpu_affinity")(_server_cores)
            return True
        except (AttributeError, NotImplementedError) as e:
            logger.warning("Failed to set CPU affinity for process %s: %s", process.pid, e)

    return False
