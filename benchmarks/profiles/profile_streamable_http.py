"""
Focused viztracer profile comparing StreamableHTTPTransport vs HTTPTransport
under concurrent I/O-bound tool calls.

Calls dispatch() directly (no uvicorn/network) to isolate pure framework overhead.

Usage:
    uv run python -m benchmarks.profiles.profile_streamable_http

Output:
    benchmarks/profiles/traces/profile_streamable_http_io_bound.json  (Streamable HTTP)
    benchmarks/profiles/traces/profile_http_io_bound.json             (plain HTTP, baseline)
    benchmarks/profiles/traces/profile_streamable_http_noop.json      (Streamable HTTP noop, reference)

Open any .json with: uv run viztracer --open <file>
"""

import json
import logging

import anyio
from viztracer import VizTracer

from benchmarks.core.sample_tools import io_bound_compute_all_prime_factors, noop_tool
from minimcp import HTTPTransport, MiniMCP, StreamableHTTPTransport

logging.disable(logging.CRITICAL)

# --- Parameters ---
CONCURRENCY = 100  # Matches medium_load; the exact concurrency where regression appears
WARMUP_ROUNDS = 3  # Bring server to steady state before tracing
PROFILE_ROUNDS = 5  # Rounds within the traced window (CONCURRENCY * PROFILE_ROUNDS calls)
TRACES_DIR = "benchmarks/profiles/traces"

MCP_PROTOCOL_VERSION = "2025-03-26"

HEADERS_INIT = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
}

INIT_BODY = json.dumps(
    {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "profiler", "version": "0.1"},
        },
    }
)

INITIALIZED_BODY = json.dumps(
    {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
)


def make_call_body(request_id: int, tool_name: str, n: int) -> str:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": {"n": n}},
        }
    )


def build_mcp() -> MiniMCP:
    mcp: MiniMCP = MiniMCP[None](name="ProfileMCP", max_concurrency=1000)
    mcp.tool.add(io_bound_compute_all_prime_factors)
    mcp.tool.add(noop_tool)
    return mcp


async def _handshake(dispatch_fn) -> None:
    """Perform the MCP initialize + initialized handshake."""
    await dispatch_fn("POST", HEADERS_INIT, INIT_BODY)
    await dispatch_fn("POST", HEADERS_INIT, INITIALIZED_BODY)


async def _run_concurrent(dispatch_fn, tool_name: str, rounds: int, id_offset: int = 0) -> None:
    """Run CONCURRENCY concurrent tool calls for `rounds` rounds."""
    for round_idx in range(rounds):
        async with anyio.create_task_group() as tg:
            for j in range(CONCURRENCY):
                n = 100 + round_idx * 100 + j
                req_id = id_offset + round_idx * CONCURRENCY + j
                body = make_call_body(req_id, tool_name, n)
                tg.start_soon(dispatch_fn, "POST", HEADERS, body)


# ---------------------------------------------------------------------------
# StreamableHTTPTransport profiles
# ---------------------------------------------------------------------------


async def profile_streamable_http(tool_name: str, output_file: str) -> None:
    mcp = build_mcp()
    transport = StreamableHTTPTransport[None](mcp)

    async with transport:
        await _handshake(transport.dispatch)

        # Warmup
        print(f"  Warming up StreamableHTTP/{tool_name} ({WARMUP_ROUNDS} rounds × {CONCURRENCY})...")
        await _run_concurrent(transport.dispatch, tool_name, WARMUP_ROUNDS, id_offset=10_000)

        # Profiled window
        print(f"  Tracing StreamableHTTP/{tool_name} ({PROFILE_ROUNDS} rounds × {CONCURRENCY})...")
        with VizTracer(
            log_async=True,
            output_file=output_file,
            max_stack_depth=15,
            tracer_entries=5_000_000,
        ):
            await _run_concurrent(transport.dispatch, tool_name, PROFILE_ROUNDS, id_offset=0)

    print(f"  Saved → {output_file}")


# ---------------------------------------------------------------------------
# HTTPTransport baseline profile
# ---------------------------------------------------------------------------


async def profile_http(tool_name: str, output_file: str) -> None:
    mcp = build_mcp()
    transport = HTTPTransport[None](mcp)

    await _handshake(transport.dispatch)

    # Warmup
    print(f"  Warming up HTTP/{tool_name} ({WARMUP_ROUNDS} rounds × {CONCURRENCY})...")
    await _run_concurrent(transport.dispatch, tool_name, WARMUP_ROUNDS, id_offset=10_000)

    # Profiled window
    print(f"  Tracing HTTP/{tool_name} ({PROFILE_ROUNDS} rounds × {CONCURRENCY})...")
    with VizTracer(
        log_async=True,
        output_file=output_file,
        max_stack_depth=15,
        tracer_entries=5_000_000,
    ):
        await _run_concurrent(transport.dispatch, tool_name, PROFILE_ROUNDS, id_offset=0)

    print(f"  Saved → {output_file}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print("\nProfiling StreamableHTTPTransport vs HTTPTransport")
    print(f"Concurrency={CONCURRENCY}, warmup={WARMUP_ROUNDS} rounds, profile={PROFILE_ROUNDS} rounds\n")

    print("[1/3] StreamableHTTP + io_bound_compute_all_prime_factors  (the regressing case)")
    anyio.run(
        profile_streamable_http,
        "io_bound_compute_all_prime_factors",
        f"{TRACES_DIR}/profile_streamable_http_io_bound.json",
    )

    print("\n[2/3] HTTP (plain) + io_bound_compute_all_prime_factors  (baseline, no regression)")
    anyio.run(
        profile_http,
        "io_bound_compute_all_prime_factors",
        f"{TRACES_DIR}/profile_http_io_bound.json",
    )

    print("\n[3/3] StreamableHTTP + noop_tool  (reference: no regression in noop either)")
    anyio.run(
        profile_streamable_http,
        "noop_tool",
        f"{TRACES_DIR}/profile_streamable_http_noop.json",
    )

    print("\nDone. Open traces with:")
    print(f"  uv run viztracer --open {TRACES_DIR}/profile_streamable_http_io_bound.json")
    print(f"  uv run viztracer --open {TRACES_DIR}/profile_http_io_bound.json")
    print(f"  uv run viztracer --open {TRACES_DIR}/profile_streamable_http_noop.json")


if __name__ == "__main__":
    main()
