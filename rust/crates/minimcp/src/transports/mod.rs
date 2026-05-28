//! Transport adapters.
//!
//! Mirrors `minimcp/transports/`. Transports are thin I/O layers that read a
//! message, call [`crate::MiniMCP::handle`], and write the response. The HTTP
//! transport is gated behind the `http` feature.
//!
//! TODO: Add a streamable HTTP (SSE) transport to reach parity with the Python
//! implementation.

pub mod stdio;

#[cfg(feature = "http")]
pub mod http;
