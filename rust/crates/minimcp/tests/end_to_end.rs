//! End-to-end tests driving the public `MiniMCP` API, mirroring the Python
//! `tests/integration` suite. These exercise a full request lifecycle through
//! `handle()` rather than internal helpers.

use std::sync::Arc;

use minimcp::{MiniMCP, NoMessage, Outcome};
use serde_json::{json, Value};

fn build_server() -> Arc<MiniMCP<()>> {
    let mcp = MiniMCP::<()>::new("integration").with_version("1.0.0");
    mcp.tool
        .add(
            "add",
            Some("Add two integers"),
            json!({
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"]
            }),
            Some(json!({"type": "object", "properties": {"result": {"type": "integer"}}})),
            |args| async move {
                let a = args["a"].as_i64().ok_or_else(|| "missing a".to_string())?;
                let b = args["b"].as_i64().ok_or_else(|| "missing b".to_string())?;
                Ok(json!({"result": a + b}))
            },
        )
        .unwrap();
    Arc::new(mcp)
}

fn message(outcome: Outcome) -> Value {
    match outcome {
        Outcome::Message(m) => serde_json::from_str(&m).unwrap(),
        Outcome::NoMessage(_) => panic!("expected a message outcome"),
    }
}

#[tokio::test]
async fn full_initialize_then_list_then_call() {
    let mcp = build_server();

    // initialize
    let init = json!({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "c", "version": "0"}}
    })
    .to_string();
    let init_response = message(mcp.handle(init, None, None).await.unwrap());
    assert_eq!(init_response["result"]["serverInfo"]["name"], "integration");

    // tools/list
    let list = json!({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).to_string();
    let list_response = message(mcp.handle(list, None, None).await.unwrap());
    assert_eq!(list_response["result"]["tools"][0]["name"], "add");

    // tools/call
    let call = json!({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "add", "arguments": {"a": 2, "b": 40}}
    })
    .to_string();
    let call_response = message(mcp.handle(call, None, None).await.unwrap());
    assert_eq!(call_response["result"]["structuredContent"]["result"], 42);
}

#[tokio::test]
async fn notification_yields_no_message() {
    let mcp = build_server();
    let note = json!({"jsonrpc": "2.0", "method": "notifications/initialized"}).to_string();
    let outcome = mcp.handle(note, None, None).await.unwrap();
    assert_eq!(outcome, Outcome::NoMessage(NoMessage::Notification));
}

#[tokio::test]
async fn invalid_message_is_reported_to_transport() {
    let mcp = build_server();
    let err = mcp
        .handle("{garbage".to_string(), None, None)
        .await
        .unwrap_err();
    let response: Value = serde_json::from_str(&err.response).unwrap();
    assert!(response.get("error").is_some());
}
