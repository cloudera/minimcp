//! Server-to-client notifications.
//!
//! Mirrors `minimcp/responder.py`. A `Responder` is available to handlers (via
//! the request context) on transports that support bidirectional communication
//! and lets handlers push notifications, such as progress updates, to the
//! client.

use serde_json::{json, Value};

use crate::mcp_types::JSONRPC_VERSION;
use crate::time_limiter::TimeLimiter;
use crate::types::SendFn;

/// Enables message handlers to send notifications back to the client.
///
/// Sending a notification resets the idle timeout so an actively communicating
/// handler is not timed out.
#[derive(Clone)]
pub struct Responder {
    send: SendFn,
    time_limiter: Option<TimeLimiter>,
}

impl Responder {
    /// Create a responder.
    ///
    /// # Arguments
    ///
    /// * `send` - The callback used to transmit messages to the client.
    /// * `time_limiter` - The handler's idle-timeout limiter, if enabled.
    pub fn new(send: SendFn, time_limiter: Option<TimeLimiter>) -> Self {
        Self { send, time_limiter }
    }

    /// Send a JSON-RPC notification with the given method and params.
    ///
    /// The idle timeout is reset before the message is sent.
    pub async fn send_notification(&self, method: &str, params: Value) {
        if let Some(limiter) = &self.time_limiter {
            limiter.reset();
        }

        let message = json!({
            "jsonrpc": JSONRPC_VERSION,
            "method": method,
            "params": params,
        })
        .to_string();

        (self.send)(message).await;
    }

    /// Report progress for the current operation to the client.
    ///
    /// # Arguments
    ///
    /// * `progress_token` - The token supplied by the client in the request metadata.
    /// * `progress` - Current progress value.
    /// * `total` - Optional total value for computing completion percentage.
    /// * `message` - Optional human-readable status message.
    pub async fn report_progress(
        &self,
        progress_token: Value,
        progress: f64,
        total: Option<f64>,
        message: Option<String>,
    ) {
        let mut params = json!({
            "progressToken": progress_token,
            "progress": progress,
        });
        if let Some(total) = total {
            params["total"] = json!(total);
        }
        if let Some(message) = message {
            params["message"] = json!(message);
        }

        self.send_notification("notifications/progress", params)
            .await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Mutex};

    fn recording_responder() -> (Responder, Arc<Mutex<Vec<String>>>) {
        let recorded: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
        let sink = recorded.clone();
        let send: SendFn = Arc::new(move |msg: String| {
            let sink = sink.clone();
            Box::pin(async move {
                sink.lock().unwrap().push(msg);
            })
        });
        let limiter = TimeLimiter::new(std::time::Duration::from_secs(30));
        (Responder::new(send, Some(limiter)), recorded)
    }

    #[tokio::test]
    async fn send_notification_builds_jsonrpc() {
        let (responder, recorded) = recording_responder();
        responder
            .send_notification("notifications/test", json!({"k": "v"}))
            .await;

        let messages = recorded.lock().unwrap();
        assert_eq!(messages.len(), 1);
        let parsed: Value = serde_json::from_str(&messages[0]).unwrap();
        assert_eq!(parsed["jsonrpc"], "2.0");
        assert_eq!(parsed["method"], "notifications/test");
        assert_eq!(parsed["params"]["k"], "v");
        assert!(parsed.get("id").is_none());
    }

    #[tokio::test]
    async fn report_progress_full_params() {
        let (responder, recorded) = recording_responder();
        responder
            .report_progress(
                json!("tok-1"),
                42.5,
                Some(100.0),
                Some("halfway".to_string()),
            )
            .await;

        let messages = recorded.lock().unwrap();
        let parsed: Value = serde_json::from_str(&messages[0]).unwrap();
        assert_eq!(parsed["method"], "notifications/progress");
        assert_eq!(parsed["params"]["progressToken"], "tok-1");
        assert_eq!(parsed["params"]["progress"], 42.5);
        assert_eq!(parsed["params"]["total"], 100.0);
        assert_eq!(parsed["params"]["message"], "halfway");
    }

    #[tokio::test]
    async fn report_progress_omits_optional_fields() {
        let (responder, recorded) = recording_responder();
        responder
            .report_progress(json!("tok-2"), 10.0, None, None)
            .await;

        let messages = recorded.lock().unwrap();
        let parsed: Value = serde_json::from_str(&messages[0]).unwrap();
        assert_eq!(parsed["params"]["progress"], 10.0);
        assert!(parsed["params"].get("total").is_none());
        assert!(parsed["params"].get("message").is_none());
    }

    #[tokio::test]
    async fn multiple_notifications_are_all_sent() {
        let (responder, recorded) = recording_responder();
        for i in 0..5 {
            responder
                .report_progress(json!("tok"), i as f64 * 10.0, None, None)
                .await;
        }
        assert_eq!(recorded.lock().unwrap().len(), 5);
    }
}
