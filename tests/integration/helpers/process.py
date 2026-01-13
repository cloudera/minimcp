import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from subprocess import DEVNULL, Popen
from types import ModuleType

from psutil import NoSuchProcess, Process, ZombieProcess, process_iter  # type: ignore


def find_process(cmd_substr: str) -> Process | None:
    """Find a process by file_name"""
    try:
        for proc in process_iter(["pid", "name", "cmdline"]):
            cmdline = proc.info.get("cmdline", [])
            if cmdline and any(cmd_substr in str(cmd) for cmd in cmdline):
                return Process(proc.info["pid"])
    except (NoSuchProcess, ZombieProcess):
        pass

    return None


@asynccontextmanager
async def run_subprocess(cmd: list[str], cwd: Path) -> AsyncGenerator[Process, None]:
    """Run a subprocess and yield the process."""
    sub_proc = None

    try:
        sub_proc = Popen(
            cmd,
            stdout=DEVNULL,
            stderr=DEVNULL,
            text=True,
            cwd=cwd,
        )

        process = Process(sub_proc.pid)

        if not process.is_running():
            raise RuntimeError(f"Process for command {cmd} exited unexpectedly.")

        yield process

    finally:
        if sub_proc and sub_proc.poll() is None:
            sub_proc.terminate()
            sub_proc.wait(5)
            if sub_proc.poll() is None:
                raise RuntimeError("Process was not terminated.")


@asynccontextmanager
async def run_module(module: ModuleType) -> AsyncGenerator[Process, None]:
    """Run a module as a subprocess and yield the process."""

    project_root = Path(__file__).parent.parent.parent.parent
    path_relative_to_root = Path(module.__file__ or "").relative_to(project_root)
    module_name = str(path_relative_to_root.with_suffix("")).replace(os.sep, ".")

    cmd = ["uv", "run", "python", "-m", module_name]

    async with run_subprocess(cmd, project_root) as process:
        yield process
