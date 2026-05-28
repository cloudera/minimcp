//! Shared setup for the benchmark MCP server binaries.
//!
//! Both the stdio and HTTP binaries build the same server via [`build_server`],
//! which registers the benchmark workload tools and disables concurrency and
//! idle-timeout limits (matching the Python benchmark servers).

use std::sync::Arc;

use minimcp::MiniMCP;

pub mod memory;
pub mod tools;

/// Build the benchmark server with all workload tools registered.
pub fn build_server() -> Arc<MiniMCP<()>> {
    let mcp = MiniMCP::<()>::new("minimcp-rs")
        .with_version(env!("CARGO_PKG_VERSION"))
        .with_max_concurrency(-1)
        .with_idle_timeout(-1);

    tools::register(&mcp);

    Arc::new(mcp)
}
