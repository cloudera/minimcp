//! Tool registration and execution.
//!
//! Mirrors `minimcp/managers/tool_manager.py`. Tools are registered with a
//! name, JSON Schemas, and an async handler. A handler receives the call
//! arguments as a JSON value and returns the structured-content value that is
//! placed in the tool result.

use std::collections::HashMap;
use std::future::Future;
use std::pin::Pin;
use std::sync::{Arc, RwLock};

use serde_json::Value;

use crate::error::Error;
use crate::mcp_types::{CallToolResult, ContentBlock, Tool};

/// A boxed, owned future returned by tool handlers.
pub type BoxFuture<T> = Pin<Box<dyn Future<Output = T> + Send>>;

/// Result returned by a tool handler.
///
/// `Ok` carries the structured-content value placed in the tool result; `Err`
/// carries a human-readable error message.
pub type ToolResult = Result<Value, String>;

type ToolHandler = Arc<dyn Fn(Value) -> BoxFuture<ToolResult> + Send + Sync>;

struct Registration {
    tool: Tool,
    handler: ToolHandler,
}

/// Registers and executes MCP tool handlers.
#[derive(Default)]
pub struct ToolManager {
    tools: RwLock<HashMap<String, Registration>>,
}

impl ToolManager {
    /// Create an empty tool manager.
    pub fn new() -> Self {
        Self::default()
    }

    /// Register a tool handler.
    ///
    /// # Arguments
    ///
    /// * `name` - Unique tool identifier.
    /// * `description` - Optional human-readable description.
    /// * `input_schema` - JSON Schema for the tool input.
    /// * `output_schema` - Optional JSON Schema for the structured output.
    /// * `handler` - Async function mapping call arguments to a structured result.
    ///
    /// # Errors
    ///
    /// Returns [`Error::Primitive`] if a tool with the same name is already registered.
    pub fn add<F, Fut>(
        &self,
        name: &str,
        description: Option<&str>,
        input_schema: Value,
        output_schema: Option<Value>,
        handler: F,
    ) -> Result<Tool, Error>
    where
        F: Fn(Value) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = ToolResult> + Send + 'static,
    {
        let tool = Tool {
            name: name.to_string(),
            description: description.map(str::to_string),
            input_schema,
            output_schema,
        };

        let boxed: ToolHandler = Arc::new(move |args: Value| {
            let fut = handler(args);
            Box::pin(fut) as BoxFuture<ToolResult>
        });

        let mut tools = self.tools.write().expect("tool registry poisoned");
        if tools.contains_key(name) {
            return Err(Error::Primitive(format!("Tool {name} already registered")));
        }

        tools.insert(
            name.to_string(),
            Registration {
                tool: tool.clone(),
                handler: boxed,
            },
        );
        tracing::debug!(tool = name, "tool added");

        Ok(tool)
    }

    /// Remove a tool by name.
    ///
    /// # Errors
    ///
    /// Returns [`Error::Primitive`] if the tool is not found.
    pub fn remove(&self, name: &str) -> Result<Tool, Error> {
        let mut tools = self.tools.write().expect("tool registry poisoned");
        tools
            .remove(name)
            .map(|reg| reg.tool)
            .ok_or_else(|| Error::Primitive(format!("Unknown tool: {name}")))
    }

    /// List all registered tools.
    pub fn list(&self) -> Vec<Tool> {
        let tools = self.tools.read().expect("tool registry poisoned");
        tools.values().map(|reg| reg.tool.clone()).collect()
    }

    /// Execute a tool by name with the given arguments.
    ///
    /// # Errors
    ///
    /// Returns [`Error::Primitive`] if the tool is unknown, or [`Error::Runtime`]
    /// if the handler reports a failure.
    pub async fn call(&self, name: &str, args: Value) -> Result<CallToolResult, Error> {
        // Clone the handler out before awaiting so the lock is not held across .await.
        let handler = {
            let tools = self.tools.read().expect("tool registry poisoned");
            match tools.get(name) {
                Some(reg) => reg.handler.clone(),
                None => return Err(Error::Primitive(format!("Unknown tool: {name}"))),
            }
        };

        let structured = handler(args).await.map_err(Error::Runtime)?;

        Ok(CallToolResult {
            content: vec![ContentBlock::Text {
                text: structured.to_string(),
            }],
            structured_content: Some(structured),
            is_error: false,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn obj_schema() -> Value {
        json!({"type": "object", "properties": {"x": {"type": "integer"}}})
    }

    fn manager_with_double() -> ToolManager {
        let manager = ToolManager::new();
        manager
            .add(
                "double",
                Some("doubles x"),
                obj_schema(),
                None,
                |args| async move {
                    let x = args["x"].as_i64().ok_or_else(|| "missing x".to_string())?;
                    Ok(json!({"result": x * 2}))
                },
            )
            .unwrap();
        manager
    }

    #[test]
    fn add_returns_tool_metadata() {
        let manager = ToolManager::new();
        let tool = manager
            .add("greet", Some("greets"), obj_schema(), None, |_| async {
                Ok(json!({}))
            })
            .unwrap();
        assert_eq!(tool.name, "greet");
        assert_eq!(tool.description.as_deref(), Some("greets"));
    }

    #[test]
    fn add_duplicate_errors() {
        let manager = manager_with_double();
        let err = manager
            .add("double", None, obj_schema(), None, |_| async {
                Ok(json!({}))
            })
            .unwrap_err();
        assert!(matches!(err, Error::Primitive(_)));
    }

    #[test]
    fn remove_existing_and_missing() {
        let manager = manager_with_double();
        assert_eq!(manager.remove("double").unwrap().name, "double");
        assert!(matches!(manager.remove("double"), Err(Error::Primitive(_))));
    }

    #[test]
    fn list_empty_and_populated() {
        let manager = ToolManager::new();
        assert!(manager.list().is_empty());
        manager
            .add("a", None, obj_schema(), None, |_| async { Ok(json!({})) })
            .unwrap();
        manager
            .add("b", None, obj_schema(), None, |_| async { Ok(json!({})) })
            .unwrap();
        assert_eq!(manager.list().len(), 2);
    }

    #[tokio::test]
    async fn call_success_wraps_structured_content() {
        let manager = manager_with_double();
        let result = manager.call("double", json!({"x": 21})).await.unwrap();
        assert!(!result.is_error);
        assert_eq!(result.structured_content, Some(json!({"result": 42})));
        assert_eq!(result.content.len(), 1);
    }

    #[tokio::test]
    async fn call_unknown_tool_errors() {
        let manager = ToolManager::new();
        let err = manager.call("nope", json!({})).await.unwrap_err();
        assert!(matches!(err, Error::Primitive(_)));
    }

    #[tokio::test]
    async fn call_handler_error_becomes_runtime_error() {
        let manager = manager_with_double();
        // missing "x" makes the handler return Err -> Runtime
        let err = manager.call("double", json!({})).await.unwrap_err();
        assert!(matches!(err, Error::Runtime(_)));
    }
}
