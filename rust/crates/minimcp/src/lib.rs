//! MiniMCP - a minimal, stateless, and lightweight framework for building MCP servers.
//!
//! This is the Rust port of the Python [MiniMCP](https://github.com/cloudera/minimcp)
//! framework. It reuses the MCP message type definitions (modeled with serde in
//! [`mcp_types`]) but reimplements message handling in MiniMCP style rather than
//! delegating to an SDK.
//!
//! The core entry point is [`MiniMCP`], whose [`MiniMCP::handle`] method is a
//! stateless function from an incoming JSON-RPC message to an [`Outcome`].
//! Transports ([`StdioTransport`], [`HttpTransport`]) are thin adapters around it.

pub mod json_rpc;
pub mod managers;
pub mod mcp_types;
pub mod transports;

mod context;
mod error;
mod responder;
mod server;
mod time_limiter;
mod types;

pub use crate::context::{Context, ContextManager};
pub use crate::error::{ContextError, Error, InvalidMessageError};
pub use crate::managers::tool::ToolManager;
pub use crate::responder::Responder;
pub use crate::server::MiniMCP;
pub use crate::time_limiter::TimeLimiter;
pub use crate::transports::stdio::StdioTransport;
pub use crate::types::{Message, NoMessage, Outcome, SendFn, RESOURCE_NOT_FOUND};

#[cfg(feature = "http")]
pub use crate::transports::http::HttpTransport;
