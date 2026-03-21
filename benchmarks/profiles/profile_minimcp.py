"""
Layered viztracer profile of MiniMCP framework overhead across four execution layers.

Calls each layer directly (no network) to isolate pure framework overhead:

    Layer 1 (raw):             mcp.handle(msg)                       — framework floor
    Layer 2 (raw + send):      mcp.handle(msg, noop_send)            — + send / Responder path
    Layer 3 (HTTP):            HTTPTransport.dispatch("POST", ...)    — + HTTP parse + response build
    Layer 4 (StreamableHTTP):  StreamableHTTPTransport.dispatch(...)  — + task group + SSE stream

Tool workloads:
    io_bound  — 2 ms of async I/O sleep + CPU work (realistic mixed workload)
    noop      — echoes the input immediately (measures pure protocol overhead)

Usage:
    uv run python -m benchmarks.profiles.profile_minimcp

Output (6 trace files):
    benchmarks/profiles/traces/profile_raw_io_bound.json
    benchmarks/profiles/traces/profile_raw_send_io_bound.json
    benchmarks/profiles/traces/profile_http_io_bound.json
    benchmarks/profiles/traces/profile_streamable_http_io_bound.json
    benchmarks/profiles/traces/profile_raw_noop.json
    benchmarks/profiles/traces/profile_streamable_http_noop.json

Open any .json with: uv run viztracer --open <file>
"""

import json
import logging

import anyio
from viztracer import VizTracer

from benchmarks.core.sample_tools import io_bound_compute_all_prime_factors, noop_tool
from minimcp import HTTPTransport, MiniMCP, StreamableHTTPTransport
from minimcp.types import Message

logging.disable(logging.CRITICAL)

# --- Parameters ---
CONCURRENCY = 100  # Matches medium_load; the exact concurrency where regression appears
WARMUP_ROUNDS = 3  # Bring server to steady state before tracing
PROFILE_ROUNDS = 5  # Rounds within the traced window (CONCURRENCY × PROFILE_ROUNDS calls total)
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
    """Build a JSON-RPC tools/call request body."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": {"n": n}},
        }
    )


def build_mcp() -> MiniMCP:
    """Build a MiniMCP instance with both profiling tools registered.

    max_concurrency and idle_timeout are disabled (-1) so that their overhead
    does not appear in the traces — we are profiling the transport layers, not the limiters.
    """
    mcp: MiniMCP = MiniMCP[None](name="ProfileMCP", max_concurrency=-1, idle_timeout=-1)
    mcp.tool.add(io_bound_compute_all_prime_factors)
    mcp.tool.add(noop_tool)
    return mcp


# ---------------------------------------------------------------------------
# Shared runners
# ---------------------------------------------------------------------------


async def _noop_send(msg: Message) -> None:
    """No-op send callback for raw handle profiling."""


async def _raw_handshake(mcp: MiniMCP) -> None:
    """Perform the MCP initialize + initialized handshake at the raw handle layer."""
    await mcp.handle(INIT_BODY)
    await mcp.handle(INITIALIZED_BODY)


async def _http_handshake(dispatch_fn) -> None:
    """Perform the MCP initialize + initialized handshake at the HTTP/StreamableHTTP layer."""
    await dispatch_fn("POST", HEADERS_INIT, INIT_BODY)
    await dispatch_fn("POST", HEADERS_INIT, INITIALIZED_BODY)


async def _run_raw_concurrent(handle_fn, tool_name: str, rounds: int, id_offset: int = 0) -> None:
    """Run CONCURRENCY concurrent raw handle calls for `rounds` rounds."""
    for round_idx in range(rounds):
        async with anyio.create_task_group() as tg:
            for j in range(CONCURRENCY):
                n = 100 + round_idx * 100 + j
                req_id = id_offset + round_idx * CONCURRENCY + j
                body = make_call_body(req_id, tool_name, n)
                tg.start_soon(handle_fn, body)


async def _run_http_concurrent(dispatch_fn, tool_name: str, rounds: int, id_offset: int = 0) -> None:
    """Run CONCURRENCY concurrent HTTP dispatch calls for `rounds` rounds."""
    for round_idx in range(rounds):
        async with anyio.create_task_group() as tg:
            for j in range(CONCURRENCY):
                n = 100 + round_idx * 100 + j
                req_id = id_offset + round_idx * CONCURRENCY + j
                body = make_call_body(req_id, tool_name, n)
                tg.start_soon(dispatch_fn, "POST", HEADERS, body)


# ---------------------------------------------------------------------------
# Layer 1: raw mcp.handle() — framework floor
# ---------------------------------------------------------------------------


async def profile_raw(tool_name: str, output_file: str) -> None:
    """Profile raw mcp.handle() with no send callback.

    This is the absolute minimum overhead of the MiniMCP framework:
    JSON parse → route → tool execute → response build, with no send path.
    """
    mcp = build_mcp()
    await _raw_handshake(mcp)

    print(f"  Warming up raw/{tool_name} ({WARMUP_ROUNDS} rounds × {CONCURRENCY})...")
    await _run_raw_concurrent(mcp.handle, tool_name, WARMUP_ROUNDS, id_offset=10_000)

    print(f"  Tracing raw/{tool_name} ({PROFILE_ROUNDS} rounds × {CONCURRENCY})...")
    with VizTracer(log_async=True, output_file=output_file, max_stack_depth=15, tracer_entries=5_000_000):
        await _run_raw_concurrent(mcp.handle, tool_name, PROFILE_ROUNDS, id_offset=0)

    print(f"  Saved → {output_file}")


# ---------------------------------------------------------------------------
# Layer 2: raw mcp.handle() + noop send — send / Responder path overhead
# ---------------------------------------------------------------------------


async def profile_raw_send(tool_name: str, output_file: str) -> None:
    """Profile raw mcp.handle() with a no-op send callback.

    Compared to Layer 1, this adds the Responder creation and the send path
    (JSON serialization of the response + callback invocation). The difference
    between Layer 1 and Layer 2 is the cost of the send path.
    """
    mcp = build_mcp()
    await _raw_handshake(mcp)

    async def handle_with_send(body: str) -> None:
        await mcp.handle(body, _noop_send)

    print(f"  Warming up raw+send/{tool_name} ({WARMUP_ROUNDS} rounds × {CONCURRENCY})...")
    await _run_raw_concurrent(handle_with_send, tool_name, WARMUP_ROUNDS, id_offset=10_000)

    print(f"  Tracing raw+send/{tool_name} ({PROFILE_ROUNDS} rounds × {CONCURRENCY})...")
    with VizTracer(log_async=True, output_file=output_file, max_stack_depth=15, tracer_entries=5_000_000):
        await _run_raw_concurrent(handle_with_send, tool_name, PROFILE_ROUNDS, id_offset=0)

    print(f"  Saved → {output_file}")


# ---------------------------------------------------------------------------
# Layer 3: HTTPTransport — + HTTP request parse + JSON response build
# ---------------------------------------------------------------------------


async def profile_http(tool_name: str, output_file: str) -> None:
    """Profile HTTPTransport.dispatch().

    Compared to Layer 2, this adds the HTTP body parsing and JSON response
    building performed by BaseHTTPTransport._handle_post_request().
    """
    mcp = build_mcp()
    transport = HTTPTransport[None](mcp)

    await _http_handshake(transport.dispatch)

    print(f"  Warming up HTTP/{tool_name} ({WARMUP_ROUNDS} rounds × {CONCURRENCY})...")
    await _run_http_concurrent(transport.dispatch, tool_name, WARMUP_ROUNDS, id_offset=10_000)

    print(f"  Tracing HTTP/{tool_name} ({PROFILE_ROUNDS} rounds × {CONCURRENCY})...")
    with VizTracer(log_async=True, output_file=output_file, max_stack_depth=15, tracer_entries=5_000_000):
        await _run_http_concurrent(transport.dispatch, tool_name, PROFILE_ROUNDS, id_offset=0)

    print(f"  Saved → {output_file}")


# ---------------------------------------------------------------------------
# Layer 4: StreamableHTTPTransport — + task group + SSE stream
# ---------------------------------------------------------------------------


async def profile_streamable_http(tool_name: str, output_file: str) -> None:
    """Profile StreamableHTTPTransport.dispatch().

    Compared to Layer 3, this adds the per-request anyio task group startup,
    MemoryObjectStream pair creation, and SSE event serialization.
    """
    mcp = build_mcp()
    transport = StreamableHTTPTransport[None](mcp)

    async with transport:
        await _http_handshake(transport.dispatch)

        print(f"  Warming up StreamableHTTP/{tool_name} ({WARMUP_ROUNDS} rounds × {CONCURRENCY})...")
        await _run_http_concurrent(transport.dispatch, tool_name, WARMUP_ROUNDS, id_offset=10_000)

        print(f"  Tracing StreamableHTTP/{tool_name} ({PROFILE_ROUNDS} rounds × {CONCURRENCY})...")
        with VizTracer(log_async=True, output_file=output_file, max_stack_depth=15, tracer_entries=5_000_000):
            await _run_http_concurrent(transport.dispatch, tool_name, PROFILE_ROUNDS, id_offset=0)

    print(f"  Saved → {output_file}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run all six profiles sequentially and print instructions for opening traces."""
    print("\nProfiling MiniMCP: four layers × two workloads")
    print(f"Concurrency={CONCURRENCY}, warmup={WARMUP_ROUNDS} rounds, profile={PROFILE_ROUNDS} rounds\n")

    profiles = [
        (
            "[1/6] Layer 1 — raw handle, io_bound  (framework floor)",
            profile_raw,
            "io_bound_compute_all_prime_factors",
            "profile_raw_io_bound.json",
        ),
        (
            "[2/6] Layer 2 — raw + send, io_bound  (+ send/Responder path)",
            profile_raw_send,
            "io_bound_compute_all_prime_factors",
            "profile_raw_send_io_bound.json",
        ),
        (
            "[3/6] Layer 3 — HTTP, io_bound        (+ HTTP parse/build)",
            profile_http,
            "io_bound_compute_all_prime_factors",
            "profile_http_io_bound.json",
        ),
        (
            "[4/6] Layer 4 — StreamableHTTP, io_bound  (+ task group + SSE)",
            profile_streamable_http,
            "io_bound_compute_all_prime_factors",
            "profile_streamable_http_io_bound.json",
        ),
        (
            "[5/6] Layer 1 — raw handle, noop      (protocol floor, no work)",
            profile_raw,
            "noop_tool",
            "profile_raw_noop.json",
        ),
        (
            "[6/6] Layer 4 — StreamableHTTP, noop  (StreamableHTTP ceiling)",
            profile_streamable_http,
            "noop_tool",
            "profile_streamable_http_noop.json",
        ),
    ]

    trace_files = []
    for label, fn, tool_name, filename in profiles:
        print(label)
        output_file = f"{TRACES_DIR}/{filename}"
        anyio.run(fn, tool_name, output_file)
        trace_files.append(output_file)
        print()

    print("Done. Open any trace with:")
    for f in trace_files:
        print(f"  uv run viztracer --open {f}")


if __name__ == "__main__":
    main()
