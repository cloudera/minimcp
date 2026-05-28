//! MCP message type definitions.
//!
//! These are the Rust serde equivalents of the MCP message types defined by the
//! protocol (the Python port reuses `mcp.types`). Only the subset MiniMCP needs
//! to parse and produce is modeled here; the message *handling* is implemented
//! in MiniMCP style rather than delegated to an SDK.
//!
//! See <https://modelcontextprotocol.io/specification/2025-06-18>.

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// The JSON-RPC version string used by MCP.
pub const JSONRPC_VERSION: &str = "2.0";

/// The most recent MCP protocol version this implementation targets.
pub const LATEST_PROTOCOL_VERSION: &str = "2025-06-18";

/// Protocol versions this server can negotiate.
pub const SUPPORTED_PROTOCOL_VERSIONS: &[&str] = &["2025-06-18", "2025-03-26", "2024-11-05"];

/// A JSON-RPC request/response id, which may be a number or a string.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum RequestId {
    /// Numeric id.
    Number(i64),
    /// String id.
    String(String),
}

/// Server capability advertisement returned in the initialize handshake.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ServerCapabilities {
    /// Tool-related capabilities, present when the server exposes tools.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tools: Option<Value>,
    /// Prompt-related capabilities.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prompts: Option<Value>,
    /// Resource-related capabilities.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub resources: Option<Value>,
}

/// Identifies the server implementation to the client.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Implementation {
    /// Server name.
    pub name: String,
    /// Server version.
    pub version: String,
}

/// Result of the MCP `initialize` request.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct InitializeResult {
    /// Negotiated protocol version.
    pub protocol_version: String,
    /// Advertised server capabilities.
    pub capabilities: ServerCapabilities,
    /// Server implementation info.
    pub server_info: Implementation,
    /// Optional human-readable usage instructions.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub instructions: Option<String>,
}

/// A single tool definition as advertised by `tools/list`.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Tool {
    /// Unique tool identifier.
    pub name: String,
    /// Optional human-readable description.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    /// JSON Schema describing the tool's input.
    pub input_schema: Value,
    /// Optional JSON Schema describing the tool's structured output.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output_schema: Option<Value>,
}

/// Result of the `tools/list` request.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListToolsResult {
    /// All registered tools.
    pub tools: Vec<Tool>,
}

/// A single content block in a tool result. Only text is modeled in the skeleton.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum ContentBlock {
    /// Plain text content.
    Text {
        /// The text payload.
        text: String,
    },
}

/// Result of the `tools/call` request.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CallToolResult {
    /// Unstructured content blocks.
    pub content: Vec<ContentBlock>,
    /// Optional structured content validated against the tool's output schema.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub structured_content: Option<Value>,
    /// Whether the tool reported an execution error.
    pub is_error: bool,
}
