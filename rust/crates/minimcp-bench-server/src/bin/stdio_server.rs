//! Benchmark MCP server over the stdio transport.
//!
//! Launched as a subprocess by the Python benchmark harness, equivalent to
//! `benchmarks/macro/servers/minimcp_stdio_server.py`.

use minimcp::StdioTransport;
use minimcp_bench_server::{build_server, memory};

#[tokio::main]
async fn main() {
    // Capture the memory baseline as early as possible.
    memory::capture_baseline();

    let mcp = build_server();
    let transport = StdioTransport::new(mcp);

    if let Err(error) = transport.run().await {
        eprintln!("stdio transport error: {error}");
        std::process::exit(1);
    }
}
