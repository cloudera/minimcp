//! JSON-RPC message parsing and building helpers.
//!
//! Mirrors `minimcp/utils/json_rpc.py`. Incoming messages are parsed into an
//! [`Incoming`] request or notification; outgoing responses and errors are
//! serialized back into JSON-RPC strings.

use serde::Serialize;
use serde_json::{json, Value};

use crate::mcp_types::{RequestId, JSONRPC_VERSION};
use crate::types::Message;

/// A parsed incoming JSON-RPC message.
#[derive(Debug, Clone)]
pub enum Incoming {
    /// A request that expects a response.
    Request(Request),
    /// A one-way notification.
    Notification(Notification),
}

/// A JSON-RPC request.
#[derive(Debug, Clone)]
pub struct Request {
    /// The request id.
    pub id: RequestId,
    /// The invoked method.
    pub method: String,
    /// The method parameters (defaults to null when absent).
    pub params: Value,
}

/// A JSON-RPC notification.
#[derive(Debug, Clone)]
pub struct Notification {
    /// The notification method.
    pub method: String,
    /// The notification parameters (defaults to null when absent).
    pub params: Value,
}

/// Failure modes while parsing an incoming message.
#[derive(Debug, Clone)]
pub enum ParseError {
    /// The payload is not valid JSON.
    Json(String),
    /// The payload is not a valid JSON-RPC object.
    JsonRpc(String),
}

/// Parse a raw message string into an [`Incoming`] request or notification.
pub fn parse_incoming(message: &str) -> Result<Incoming, ParseError> {
    let value: Value =
        serde_json::from_str(message).map_err(|e| ParseError::Json(e.to_string()))?;

    let obj = value
        .as_object()
        .ok_or_else(|| ParseError::JsonRpc("message must be a JSON object".to_string()))?;

    if obj.get("jsonrpc").and_then(Value::as_str) != Some(JSONRPC_VERSION) {
        return Err(ParseError::JsonRpc(
            "missing or invalid jsonrpc version".to_string(),
        ));
    }

    let method = obj
        .get("method")
        .and_then(Value::as_str)
        .ok_or_else(|| ParseError::JsonRpc("missing method".to_string()))?
        .to_string();

    let params = obj.get("params").cloned().unwrap_or(Value::Null);

    match obj.get("id") {
        Some(id_value) if !id_value.is_null() => {
            let id =
                parse_id(id_value).ok_or_else(|| ParseError::JsonRpc("invalid id".to_string()))?;
            Ok(Incoming::Request(Request { id, method, params }))
        }
        _ => Ok(Incoming::Notification(Notification { method, params })),
    }
}

fn parse_id(value: &Value) -> Option<RequestId> {
    if let Some(n) = value.as_i64() {
        Some(RequestId::Number(n))
    } else {
        value.as_str().map(|s| RequestId::String(s.to_string()))
    }
}

/// Best-effort extraction of the request id from a raw message (for error responses).
pub fn get_request_id(message: &str) -> Value {
    serde_json::from_str::<Value>(message)
        .ok()
        .and_then(|v| v.get("id").cloned())
        .filter(|v| !v.is_null())
        .unwrap_or_else(|| Value::String("no-id".to_string()))
}

/// Build a JSON-RPC success response message.
pub fn build_response_message<T: Serialize>(id: &RequestId, result: &T) -> Message {
    let payload = json!({
        "jsonrpc": JSONRPC_VERSION,
        "id": id,
        "result": result,
    });
    payload.to_string()
}

/// Build a JSON-RPC error response message from a raw request message.
pub fn build_error_message(message: &str, code: i32, error_message: &str) -> Message {
    let id = get_request_id(message);
    let payload = json!({
        "jsonrpc": JSONRPC_VERSION,
        "id": id,
        "error": {
            "code": code,
            "message": error_message,
        },
    });
    payload.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    // --- parse_incoming ---

    #[test]
    fn parse_valid_request() {
        let msg = r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"a":1}}"#;
        match parse_incoming(msg).unwrap() {
            Incoming::Request(req) => {
                assert_eq!(req.id, RequestId::Number(1));
                assert_eq!(req.method, "initialize");
                assert_eq!(req.params["a"], 1);
            }
            other => panic!("expected request, got {other:?}"),
        }
    }

    #[test]
    fn parse_valid_notification() {
        let msg = r#"{"jsonrpc":"2.0","method":"notifications/initialized"}"#;
        match parse_incoming(msg).unwrap() {
            Incoming::Notification(note) => {
                assert_eq!(note.method, "notifications/initialized");
                assert_eq!(note.params, Value::Null);
            }
            other => panic!("expected notification, got {other:?}"),
        }
    }

    #[test]
    fn parse_null_id_is_notification() {
        let msg = r#"{"jsonrpc":"2.0","id":null,"method":"test"}"#;
        assert!(matches!(
            parse_incoming(msg).unwrap(),
            Incoming::Notification(_)
        ));
    }

    #[test]
    fn parse_string_id_request() {
        let msg = r#"{"jsonrpc":"2.0","id":"abc","method":"test"}"#;
        match parse_incoming(msg).unwrap() {
            Incoming::Request(req) => assert_eq!(req.id, RequestId::String("abc".into())),
            other => panic!("expected request, got {other:?}"),
        }
    }

    #[test]
    fn parse_invalid_json_is_json_error() {
        assert!(matches!(
            parse_incoming("{invalid"),
            Err(ParseError::Json(_))
        ));
    }

    #[test]
    fn parse_non_object_is_jsonrpc_error() {
        assert!(matches!(
            parse_incoming("[1,2,3]"),
            Err(ParseError::JsonRpc(_))
        ));
    }

    #[test]
    fn parse_missing_jsonrpc_is_jsonrpc_error() {
        let msg = r#"{"id":1,"method":"test"}"#;
        assert!(matches!(parse_incoming(msg), Err(ParseError::JsonRpc(_))));
    }

    #[test]
    fn parse_wrong_version_is_jsonrpc_error() {
        let msg = r#"{"jsonrpc":"1.0","id":1,"method":"test"}"#;
        assert!(matches!(parse_incoming(msg), Err(ParseError::JsonRpc(_))));
    }

    #[test]
    fn parse_missing_method_is_jsonrpc_error() {
        let msg = r#"{"jsonrpc":"2.0","id":1}"#;
        assert!(matches!(parse_incoming(msg), Err(ParseError::JsonRpc(_))));
    }

    // --- get_request_id ---

    #[test]
    fn get_request_id_integer() {
        let id = get_request_id(r#"{"jsonrpc":"2.0","id":123,"method":"t"}"#);
        assert_eq!(id, Value::from(123));
    }

    #[test]
    fn get_request_id_string() {
        let id = get_request_id(r#"{"jsonrpc":"2.0","id":"r-1","method":"t"}"#);
        assert_eq!(id, Value::from("r-1"));
    }

    #[test]
    fn get_request_id_zero() {
        let id = get_request_id(r#"{"jsonrpc":"2.0","id":0,"method":"t"}"#);
        assert_eq!(id, Value::from(0));
    }

    #[test]
    fn get_request_id_null_is_no_id() {
        let id = get_request_id(r#"{"jsonrpc":"2.0","id":null,"method":"t"}"#);
        assert_eq!(id, Value::from("no-id"));
    }

    #[test]
    fn get_request_id_missing_is_no_id() {
        let id = get_request_id(r#"{"jsonrpc":"2.0","method":"t"}"#);
        assert_eq!(id, Value::from("no-id"));
    }

    #[test]
    fn get_request_id_invalid_json_is_no_id() {
        assert_eq!(get_request_id("{invalid"), Value::from("no-id"));
    }

    #[test]
    fn get_request_id_non_object_is_no_id() {
        assert_eq!(get_request_id("[1,2,3]"), Value::from("no-id"));
    }

    // --- build_response_message / build_error_message ---

    #[test]
    fn build_response_round_trips() {
        let msg = build_response_message(&RequestId::Number(1), &json!({"ok": true}));
        let parsed: Value = serde_json::from_str(&msg).unwrap();
        assert_eq!(parsed["jsonrpc"], "2.0");
        assert_eq!(parsed["id"], 1);
        assert_eq!(parsed["result"]["ok"], true);
    }

    #[test]
    fn build_error_includes_code_and_id() {
        let request = r#"{"jsonrpc":"2.0","id":42,"method":"t"}"#;
        let msg = build_error_message(request, -32603, "boom");
        let parsed: Value = serde_json::from_str(&msg).unwrap();
        assert_eq!(parsed["jsonrpc"], "2.0");
        assert_eq!(parsed["id"], 42);
        assert_eq!(parsed["error"]["code"], -32603);
        assert_eq!(parsed["error"]["message"], "boom");
    }

    #[test]
    fn build_error_no_request_id() {
        let msg = build_error_message(r#"{"jsonrpc":"2.0","method":"t"}"#, -32700, "parse");
        let parsed: Value = serde_json::from_str(&msg).unwrap();
        assert_eq!(parsed["id"], "no-id");
        assert_eq!(parsed["error"]["code"], -32700);
    }
}
