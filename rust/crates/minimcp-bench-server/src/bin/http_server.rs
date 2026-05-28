//! Benchmark MCP server over the HTTP transport.
//!
//! Equivalent to `benchmarks/macro/servers/minimcp_http_server.py`. Honors the
//! `TEST_SERVER_HOST` / `TEST_SERVER_PORT` env vars used by the harness
//! (`benchmarks/configs.py`) and serves the MCP endpoint at `/mcp`.

use minimcp::HttpTransport;
use minimcp_bench_server::{build_server, memory};

#[tokio::main]
async fn main() {
    memory::capture_baseline();

    let mcp = build_server();
    let transport = HttpTransport::new(mcp);
    let app = transport.router("/mcp");

    let host = std::env::var("TEST_SERVER_HOST").unwrap_or_else(|_| "127.0.0.1".to_string());
    let port = std::env::var("TEST_SERVER_PORT").unwrap_or_else(|_| "30789".to_string());
    let addr = format!("{host}:{port}");

    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .unwrap_or_else(|e| panic!("failed to bind {addr}: {e}"));
    eprintln!("minimcp-rs http server listening on {addr}");

    axum::serve(listener, app)
        .await
        .expect("http server failed");
}
