# MiniMCP (Rust)

A Rust port of [MiniMCP](https://github.com/cloudera/minimcp), a minimal, stateless, and lightweight framework for building Model Context Protocol (MCP) servers.

This is an early scaffold. It reuses the MCP message type definitions (modeled with `serde`) but reimplements message handling in MiniMCP style rather than delegating to an SDK.

## Layout

```text
rust/
├── Cargo.toml                      # workspace
└── crates/
    ├── minimcp/                    # core library crate
    │   └── src/
    │       ├── lib.rs              # public re-exports
    │       ├── server.rs           # MiniMCP + handle()
    │       ├── types.rs            # Message, NoMessage, Outcome, SendFn
    │       ├── error.rs            # error hierarchy + JSON-RPC code mapping
    │       ├── mcp_types.rs        # MCP message type definitions (serde)
    │       ├── json_rpc.rs         # JSON-RPC parse/build helpers
    │       ├── context.rs          # per-request context (task-local)
    │       ├── responder.rs        # server-to-client notifications
    │       ├── time_limiter.rs     # idle timeout
    │       ├── managers/tool.rs    # tool registration/execution
    │       └── transports/         # stdio + http adapters
    └── minimcp-bench-server/       # benchmark server binaries
        └── src/
            ├── lib.rs              # build_server()
            ├── tools.rs            # workload tools + get_memory_usage
            ├── memory.rs           # RSS/maxrss measurement
            └── bin/
                ├── stdio_server.rs
                └── http_server.rs
```

## Mapping to the Python implementation

| Python (`src/minimcp/`) | Rust (`crates/minimcp/src/`) |
|---|---|
| `minimcp.py` (`MiniMCP.handle`) | `server.rs` |
| `types.py` | `types.rs` |
| `exceptions.py` | `error.rs` |
| `utils/json_rpc.py` | `json_rpc.rs` |
| `managers/context_manager.py` | `context.rs` |
| `managers/tool_manager.py` | `managers/tool.rs` |
| `responder.py` | `responder.rs` |
| `time_limiter.py` | `time_limiter.rs` |
| `transports/stdio.py` | `transports/stdio.rs` |
| `transports/http.py` | `transports/http.rs` |
| `mcp.types` (SDK) | `mcp_types.rs` |

## Build and test

```bash
cd rust
cargo build
cargo test
cargo clippy --all-targets
cargo fmt --check
```

## Tests

Tests are ported from the Python `tests/` suite, adapted to the Rust API. Unit
tests live in inline `#[cfg(test)] mod tests` blocks next to the code they
cover; end-to-end tests live in `crates/minimcp/tests/end_to_end.rs`.

| Python test file | Rust location |
|---|---|
| `tests/unit/utils/test_json_rpc.py` | `src/json_rpc.rs` |
| `tests/unit/test_minimcp.py` | `src/server.rs` |
| `tests/unit/managers/test_tool_manager.py` | `src/managers/tool.rs` |
| `tests/unit/managers/test_context_manager.py` | `src/context.rs` |
| `tests/unit/test_responder.py` | `src/responder.rs` |
| `tests/unit/test_time_limiter.py` | `src/time_limiter.rs` |
| `tests/unit/transports/test_stdio_transport.py` | `src/transports/stdio.rs` |
| `tests/unit/transports/test_http_transport.py` | `src/transports/http.rs` |
| `tests/integration/*` | `crates/minimcp/tests/end_to_end.rs` |
| benchmark tools / memory contract | `minimcp-bench-server/src/{tools,memory}.rs` |

### Not ported (feature not yet implemented)

These Python tests have no Rust counterpart because the corresponding behavior
is still on the TODO list below. They should be added as those features land:

- `tests/unit/utils/test_mcp_func.py` and the Pydantic schema-generation / type-coercion
  parts of `test_tool_manager.py` (no `MCPFunc` equivalent yet; Rust handlers take
  raw JSON and return structured JSON).
- HTTP header validation tests in `test_http_transport.py` / `test_base_http_transport.py`
  (Accept, Content-Type, `MCP-Protocol-Version`) — the Rust HTTP transport does not
  validate headers yet.
- `test_prompt_manager.py`, `test_resource_manager.py` — no prompt/resource managers yet.
- `test_streamable_http_transport.py` and `test_streamable_http_server.py` — no streamable
  HTTP/SSE transport yet.
- Stack-trace / error-metadata assertions in `test_minimcp.py` — the Rust error payload is
  minimal (`code` + `message`) and omits `errorType`/`errorModule`/`isoTimestamp`/`stackTrace`.

Build only the stdio transport (no HTTP / axum):

```bash
cargo build -p minimcp --no-default-features
```

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the development workflow and the Rust pre-commit hooks (`cargo fmt`, `cargo clippy`, `cargo test`).

## Running the benchmark servers

The Python benchmark harness in `../benchmarks/` is transport-agnostic: it drives any MCP server over stdio or HTTP using an MCP `ClientSession`. The Rust bench server slots in as another server under test.

Build the release binaries first:

```bash
cd rust
cargo build --release -p minimcp-bench-server
```

This produces:

- `target/release/stdio_server`
- `target/release/http_server`

Each binary exposes the same tools the harness expects: `compute_all_prime_factors`, `io_bound_compute_all_prime_factors`, `noop_tool`, and `get_memory_usage`. The HTTP binary honors `TEST_SERVER_HOST` / `TEST_SERVER_PORT` and serves `/mcp`.

### Wiring into the Python harness

Add a `ServerConfig` for the Rust server alongside the existing ones in `benchmarks/macro/*_mcp_server_benchmark.py`. For stdio, launch the compiled binary as a subprocess; for HTTP, start it on the configured port and connect a `ClientSession`. The Rust server then appears as an additional series in the result JSON and `analyze_results.py` output.

## Status / TODO

- [ ] Prompt and resource managers (+ their tests).
- [ ] Streamable HTTP (SSE) transport (+ its tests).
- [ ] Automatic JSON Schema generation from handler types (parity with `MCPFunc` + Pydantic), plus schema/validation tests.
- [ ] HTTP header validation (Accept, Content-Type, `MCP-Protocol-Version`) and its tests.
- [ ] Wire `TimeLimiter::reset` to the active timeout deadline.
- [ ] Client notification handler dispatch.
- [ ] `ServerConfig` entries in the Python benchmark harness for the Rust server.
