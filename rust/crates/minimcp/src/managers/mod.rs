//! Registration and execution managers for MCP primitives.
//!
//! Mirrors `minimcp/managers/`. Only the tool manager is implemented in this
//! skeleton; prompt and resource managers follow the same pattern.
//!
//! TODO: Add `prompt` and `resource` managers to reach parity with the Python
//! implementation.

pub mod tool;

pub use tool::{ToolManager, ToolResult};
