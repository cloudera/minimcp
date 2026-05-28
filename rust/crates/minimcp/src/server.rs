//! The [`MiniMCP`] orchestrator.
//!
//! Mirrors `minimcp/minimcp.py`. `MiniMCP` is a stateless entry point: it parses
//! an incoming JSON-RPC message, enforces concurrency and idle-timeout limits,
//! activates the per-request context, dispatches to a registered handler, and
//! formats results and errors back into JSON-RPC messages.

use std::any::Any;
use std::marker::PhantomData;
use std::sync::Arc;
use std::time::Duration;

use serde_json::{json, Value};
use tokio::sync::Semaphore;

use crate::context::{Context, ContextManager, CURRENT_CONTEXT};
use crate::error::{codes, Error, InvalidMessageError};
use crate::json_rpc::{self, Incoming, ParseError};
use crate::managers::tool::ToolManager;
use crate::mcp_types::{
    Implementation, InitializeResult, ListToolsResult, ServerCapabilities, LATEST_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
};
use crate::responder::Responder;
use crate::time_limiter::TimeLimiter;
use crate::types::{Message, NoMessage, Outcome, SendFn};

const DEFAULT_IDLE_TIMEOUT_SECS: i64 = 30;
const DEFAULT_MAX_CONCURRENCY: i64 = 100;

/// Stateless orchestrator for building MCP servers.
///
/// The generic parameter `S` is the optional per-request scope type (auth
/// details, user info, database handles, etc.), reachable inside handlers via
/// `mcp.context.get_scope()`. Use `MiniMCP<()>` when no scope is needed.
///
/// # Example
///
/// ```no_run
/// use minimcp::MiniMCP;
/// use serde_json::json;
///
/// # async fn run() {
/// let mcp = MiniMCP::<()>::new("my-server");
/// mcp.tool
///     .add(
///         "echo",
///         Some("Echo back the input"),
///         json!({"type": "object", "properties": {"value": {"type": "string"}}}),
///         None,
///         |args| async move { Ok(json!({"result": args["value"].clone()})) },
///     )
///     .unwrap();
/// # }
/// ```
pub struct MiniMCP<S = ()> {
    name: String,
    version: String,
    instructions: Option<String>,

    /// Tool registration and execution.
    pub tool: ToolManager,
    /// Accessor for the active request context.
    pub context: ContextManager<S>,

    semaphore: Option<Arc<Semaphore>>,
    idle_timeout: Option<Duration>,
    _scope: PhantomData<fn() -> S>,
}

impl<S> MiniMCP<S> {
    /// Create a server with default limits (idle timeout 30s, max concurrency 100).
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            version: "0.0.0".to_string(),
            instructions: None,
            tool: ToolManager::new(),
            context: ContextManager::new(),
            semaphore: Some(Arc::new(Semaphore::new(DEFAULT_MAX_CONCURRENCY as usize))),
            idle_timeout: Some(Duration::from_secs(DEFAULT_IDLE_TIMEOUT_SECS as u64)),
            _scope: PhantomData,
        }
    }

    /// Set the server version reported during the initialize handshake.
    pub fn with_version(mut self, version: impl Into<String>) -> Self {
        self.version = version.into();
        self
    }

    /// Set the human-readable usage instructions.
    pub fn with_instructions(mut self, instructions: impl Into<String>) -> Self {
        self.instructions = Some(instructions.into());
        self
    }

    /// Set the maximum number of concurrent handlers. Pass `-1` to disable the limit.
    pub fn with_max_concurrency(mut self, max_concurrency: i64) -> Self {
        self.semaphore = if max_concurrency == -1 {
            None
        } else {
            Some(Arc::new(Semaphore::new(max_concurrency.max(1) as usize)))
        };
        self
    }

    /// Set the per-handler idle timeout in seconds. Pass `-1` to disable the timeout.
    pub fn with_idle_timeout(mut self, idle_timeout_secs: i64) -> Self {
        self.idle_timeout = if idle_timeout_secs == -1 {
            None
        } else {
            Some(Duration::from_secs(idle_timeout_secs.max(0) as u64))
        };
        self
    }

    /// The server name.
    pub fn name(&self) -> &str {
        &self.name
    }

    /// The server version.
    pub fn version(&self) -> &str {
        &self.version
    }

    /// The server instructions, if any.
    pub fn instructions(&self) -> Option<&str> {
        self.instructions.as_deref()
    }
}

impl<S: Any + Send + Sync + 'static> MiniMCP<S> {
    /// Handle a single incoming MCP message.
    ///
    /// # Arguments
    ///
    /// * `message` - The raw JSON-RPC message string from the client.
    /// * `send` - Optional callback for server-to-client messages (notifications).
    /// * `scope` - Optional per-request scope made available to handlers.
    ///
    /// # Errors
    ///
    /// Returns [`InvalidMessageError`] for parse and JSON-RPC envelope failures.
    /// All other failures are converted into a JSON-RPC error [`Outcome::Message`].
    pub async fn handle(
        &self,
        message: Message,
        send: Option<SendFn>,
        scope: Option<Arc<S>>,
    ) -> Result<Outcome, InvalidMessageError> {
        let incoming = match json_rpc::parse_incoming(&message) {
            Ok(incoming) => incoming,
            Err(ParseError::Json(msg)) => {
                return Err(self.invalid_message(&message, codes::PARSE_ERROR, &msg))
            }
            Err(ParseError::JsonRpc(msg)) => {
                return Err(self.invalid_message(&message, codes::INVALID_REQUEST, &msg))
            }
        };

        // Enforce concurrency limit for the duration of handling.
        let _permit = match &self.semaphore {
            Some(sem) => Some(sem.acquire().await.expect("semaphore closed")),
            None => None,
        };

        let time_limiter = self.idle_timeout.map(TimeLimiter::new);
        let responder = send.map(|s| Responder::new(s, time_limiter.clone()));
        let erased_scope = scope.map(|s| s as Arc<dyn Any + Send + Sync>);

        let context = Context {
            message: message.clone(),
            scope: erased_scope,
            responder,
        };

        let fut = CURRENT_CONTEXT.scope(context, self.dispatch(incoming));

        let dispatch_result = match self.idle_timeout {
            Some(timeout) => match tokio::time::timeout(timeout, fut).await {
                Ok(result) => result,
                Err(_) => Err(Error::Runtime("handler idle timeout".to_string())),
            },
            None => fut.await,
        };

        match dispatch_result {
            Ok(outcome) => Ok(outcome),
            Err(error) => {
                tracing::error!(error = %error, "error handling message");
                Ok(Outcome::Message(json_rpc::build_error_message(
                    &message,
                    error.code(),
                    &error.to_string(),
                )))
            }
        }
    }

    async fn dispatch(&self, incoming: Incoming) -> Result<Outcome, Error> {
        match incoming {
            Incoming::Request(request) => {
                let response = self.handle_request(request).await?;
                Ok(Outcome::Message(response))
            }
            Incoming::Notification(notification) => {
                // TODO: dispatch client notifications to registered handlers.
                tracing::debug!(method = %notification.method, "received notification");
                Ok(Outcome::NoMessage(NoMessage::Notification))
            }
        }
    }

    async fn handle_request(&self, request: json_rpc::Request) -> Result<Message, Error> {
        match request.method.as_str() {
            "initialize" => {
                let result = self.initialize(&request.params);
                Ok(json_rpc::build_response_message(&request.id, &result))
            }
            "ping" => Ok(json_rpc::build_response_message(&request.id, &json!({}))),
            "tools/list" => {
                let result = ListToolsResult {
                    tools: self.tool.list(),
                };
                Ok(json_rpc::build_response_message(&request.id, &result))
            }
            "tools/call" => {
                let name = request
                    .params
                    .get("name")
                    .and_then(Value::as_str)
                    .ok_or_else(|| Error::InvalidArguments("missing tool name".to_string()))?;
                let args = request
                    .params
                    .get("arguments")
                    .cloned()
                    .unwrap_or_else(|| json!({}));
                let result = self.tool.call(name, args).await?;
                Ok(json_rpc::build_response_message(&request.id, &result))
            }
            other => Err(Error::RequestHandlerNotFound(other.to_string())),
        }
    }

    fn initialize(&self, params: &Value) -> InitializeResult {
        let client_version = params
            .get("protocolVersion")
            .and_then(Value::as_str)
            .unwrap_or("");
        let negotiated = if SUPPORTED_PROTOCOL_VERSIONS.contains(&client_version) {
            client_version.to_string()
        } else {
            LATEST_PROTOCOL_VERSION.to_string()
        };

        InitializeResult {
            protocol_version: negotiated,
            capabilities: ServerCapabilities {
                tools: Some(json!({})),
                ..Default::default()
            },
            server_info: Implementation {
                name: self.name.clone(),
                version: self.version.clone(),
            },
            instructions: self.instructions.clone(),
        }
    }

    fn invalid_message(&self, raw: &str, code: i32, message: &str) -> InvalidMessageError {
        InvalidMessageError {
            message: message.to_string(),
            response: json_rpc::build_error_message(raw, code, message),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn parsed(outcome: Outcome) -> Value {
        match outcome {
            Outcome::Message(m) => serde_json::from_str(&m).unwrap(),
            Outcome::NoMessage(_) => panic!("expected a message outcome"),
        }
    }

    fn obj_schema() -> Value {
        json!({"type": "object", "properties": {"x": {"type": "integer"}}})
    }

    fn server_with_double() -> MiniMCP<()> {
        let mcp = MiniMCP::<()>::new("test-server").with_version("1.0.0");
        mcp.tool
            .add("double", None, obj_schema(), None, |args| async move {
                let x = args["x"].as_i64().ok_or_else(|| "missing x".to_string())?;
                Ok(json!({"result": x * 2}))
            })
            .unwrap();
        mcp
    }

    fn init_message(version: &str) -> String {
        json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": version, "capabilities": {}, "clientInfo": {"name": "c", "version": "0"}}
        })
        .to_string()
    }

    // --- construction ---

    #[test]
    fn new_has_defaults() {
        let mcp = MiniMCP::<()>::new("srv");
        assert_eq!(mcp.name(), "srv");
        assert_eq!(mcp.version(), "0.0.0");
        assert_eq!(mcp.instructions(), None);
    }

    #[test]
    fn builders_apply() {
        let mcp = MiniMCP::<()>::new("srv")
            .with_version("2.0")
            .with_instructions("do things")
            .with_max_concurrency(-1)
            .with_idle_timeout(-1);
        assert_eq!(mcp.version(), "2.0");
        assert_eq!(mcp.instructions(), Some("do things"));
        assert!(mcp.semaphore.is_none());
        assert!(mcp.idle_timeout.is_none());
    }

    // --- initialize ---

    #[tokio::test]
    async fn initialize_negotiates_supported_version() {
        let mcp = server_with_double();
        let outcome = mcp
            .handle(init_message("2025-06-18"), None, None)
            .await
            .unwrap();
        let response = parsed(outcome);
        assert_eq!(response["id"], 1);
        assert_eq!(response["result"]["protocolVersion"], "2025-06-18");
        assert_eq!(response["result"]["serverInfo"]["name"], "test-server");
        assert_eq!(response["result"]["serverInfo"]["version"], "1.0.0");
    }

    #[tokio::test]
    async fn initialize_falls_back_to_latest_for_unsupported_version() {
        let mcp = server_with_double();
        let outcome = mcp
            .handle(init_message("bogus-version"), None, None)
            .await
            .unwrap();
        let response = parsed(outcome);
        assert_eq!(
            response["result"]["protocolVersion"],
            LATEST_PROTOCOL_VERSION
        );
    }

    // --- ping / tools/list / tools/call ---

    #[tokio::test]
    async fn ping_returns_empty_result() {
        let mcp = server_with_double();
        let msg = json!({"jsonrpc": "2.0", "id": 7, "method": "ping"}).to_string();
        let response = parsed(mcp.handle(msg, None, None).await.unwrap());
        assert_eq!(response["id"], 7);
        assert_eq!(response["result"], json!({}));
    }

    #[tokio::test]
    async fn tools_list_returns_registered_tools() {
        let mcp = server_with_double();
        let msg = json!({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).to_string();
        let response = parsed(mcp.handle(msg, None, None).await.unwrap());
        let tools = response["result"]["tools"].as_array().unwrap();
        assert_eq!(tools.len(), 1);
        assert_eq!(tools[0]["name"], "double");
    }

    #[tokio::test]
    async fn tools_call_returns_structured_result() {
        let mcp = server_with_double();
        let msg = json!({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "double", "arguments": {"x": 9}}
        })
        .to_string();
        let response = parsed(mcp.handle(msg, None, None).await.unwrap());
        assert_eq!(response["result"]["structuredContent"]["result"], 18);
        assert_eq!(response["result"]["isError"], false);
    }

    #[tokio::test]
    async fn tools_call_unknown_tool_is_invalid_params() {
        let mcp = server_with_double();
        let msg = json!({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "missing", "arguments": {}}
        })
        .to_string();
        let response = parsed(mcp.handle(msg, None, None).await.unwrap());
        assert_eq!(response["error"]["code"], codes::INVALID_PARAMS);
    }

    // --- errors / notifications ---

    #[tokio::test]
    async fn unknown_method_is_method_not_found() {
        let mcp = server_with_double();
        let msg = json!({"jsonrpc": "2.0", "id": 5, "method": "does/not/exist"}).to_string();
        let response = parsed(mcp.handle(msg, None, None).await.unwrap());
        assert_eq!(response["error"]["code"], codes::METHOD_NOT_FOUND);
        assert_eq!(response["id"], 5);
    }

    #[tokio::test]
    async fn invalid_json_returns_invalid_message_error() {
        let mcp = server_with_double();
        let err = mcp
            .handle("{not json".to_string(), None, None)
            .await
            .unwrap_err();
        let response: Value = serde_json::from_str(&err.response).unwrap();
        assert_eq!(response["error"]["code"], codes::PARSE_ERROR);
    }

    #[tokio::test]
    async fn missing_jsonrpc_returns_invalid_message_error() {
        let mcp = server_with_double();
        let msg = json!({"id": 1, "method": "test"}).to_string();
        let err = mcp.handle(msg, None, None).await.unwrap_err();
        let response: Value = serde_json::from_str(&err.response).unwrap();
        assert_eq!(response["error"]["code"], codes::INVALID_REQUEST);
    }

    #[tokio::test]
    async fn notification_returns_no_message() {
        let mcp = server_with_double();
        let msg = json!({"jsonrpc": "2.0", "method": "notifications/initialized"}).to_string();
        let outcome = mcp.handle(msg, None, None).await.unwrap();
        assert_eq!(outcome, Outcome::NoMessage(NoMessage::Notification));
    }

    #[tokio::test]
    async fn error_recovery_after_invalid_message() {
        let mcp = server_with_double();
        assert!(mcp.handle("{bad".to_string(), None, None).await.is_err());
        // A valid request still works after an error.
        let outcome = mcp
            .handle(init_message("2025-06-18"), None, None)
            .await
            .unwrap();
        assert_eq!(parsed(outcome)["id"], 1);
    }

    #[tokio::test]
    async fn concurrent_requests_are_isolated() {
        use std::sync::Arc;
        let mcp = Arc::new(server_with_double());
        let mut handles = Vec::new();
        for i in 0..5i64 {
            let mcp = mcp.clone();
            handles.push(tokio::spawn(async move {
                let msg = json!({
                    "jsonrpc": "2.0", "id": i, "method": "tools/call",
                    "params": {"name": "double", "arguments": {"x": i}}
                })
                .to_string();
                let outcome = mcp.handle(msg, None, None).await.unwrap();
                match outcome {
                    Outcome::Message(m) => {
                        let v: Value = serde_json::from_str(&m).unwrap();
                        (
                            v["id"].as_i64().unwrap(),
                            v["result"]["structuredContent"]["result"].as_i64().unwrap(),
                        )
                    }
                    _ => panic!("expected message"),
                }
            }));
        }
        for handle in handles {
            let (id, result) = handle.await.unwrap();
            assert_eq!(result, id * 2);
        }
    }

    // --- scope reachable inside a handler via the request context ---

    #[tokio::test]
    async fn scope_is_reachable_inside_handler() {
        let mcp: Arc<MiniMCP<String>> = {
            let mcp = MiniMCP::<String>::new("scoped");
            mcp.tool
                .add("whoami", None, obj_schema(), None, {
                    let ctx = mcp_context_handle();
                    move |_args| {
                        let scope = ctx.get_scope().map(|s| (*s).clone());
                        async move { Ok(json!({"result": scope.unwrap_or_default()})) }
                    }
                })
                .unwrap();
            Arc::new(mcp)
        };

        let msg = json!({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "whoami", "arguments": {}}
        })
        .to_string();
        let outcome = mcp
            .handle(msg, None, Some(Arc::new("alice".to_string())))
            .await
            .unwrap();
        let response = parsed(outcome);
        assert_eq!(response["result"]["structuredContent"]["result"], "alice");
    }

    // Helper to grab a context accessor for the scope test above.
    fn mcp_context_handle() -> ContextManager<String> {
        ContextManager::<String>::new()
    }

    // --- idle timeout (private field access) ---

    #[tokio::test]
    async fn idle_timeout_cancels_slow_handler() {
        let mut mcp = MiniMCP::<()>::new("timeout-srv");
        mcp.idle_timeout = Some(Duration::from_millis(50));
        mcp.tool
            .add("slow", None, obj_schema(), None, |_| async move {
                tokio::time::sleep(Duration::from_millis(500)).await;
                Ok(json!({"result": 1}))
            })
            .unwrap();

        let msg = json!({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "slow", "arguments": {}}
        })
        .to_string();
        let response = parsed(mcp.handle(msg, None, None).await.unwrap());
        assert_eq!(response["error"]["code"], codes::INTERNAL_ERROR);
    }
}
