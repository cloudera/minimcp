//! Stdio transport.
//!
//! Mirrors `minimcp/transports/stdio.py`. Reads newline-delimited JSON-RPC
//! messages from stdin, dispatches each concurrently, and writes responses (and
//! any handler-sent notifications) to stdout. Per the MCP spec, logging must go
//! to stderr so it does not corrupt the stdout message stream.

use std::any::Any;
use std::sync::Arc;

use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::sync::mpsc::UnboundedSender;

use crate::error::InvalidMessageError;
use crate::server::MiniMCP;
use crate::types::{Message, Outcome, SendFn};

/// Stdio transport implementation.
pub struct StdioTransport<S = ()> {
    mcp: Arc<MiniMCP<S>>,
}

impl<S: Any + Send + Sync + 'static> StdioTransport<S> {
    /// Create a stdio transport for the given server.
    pub fn new(mcp: Arc<MiniMCP<S>>) -> Self {
        Self { mcp }
    }

    /// Run the transport until stdin is closed.
    ///
    /// A dedicated writer task owns stdout; all responses and notifications are
    /// funneled through an unbounded channel so concurrent handlers do not
    /// interleave partial lines.
    pub async fn run(&self) -> std::io::Result<()> {
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<Message>();

        let writer = tokio::spawn(async move {
            let mut stdout = tokio::io::stdout();
            while let Some(line) = rx.recv().await {
                if stdout.write_all(line.as_bytes()).await.is_err()
                    || stdout.write_all(b"\n").await.is_err()
                    || stdout.flush().await.is_err()
                {
                    break;
                }
            }
        });

        let mut lines = BufReader::new(tokio::io::stdin()).lines();
        while let Some(line) = lines.next_line().await? {
            let trimmed = line.trim().to_string();
            if trimmed.is_empty() {
                continue;
            }
            let mcp = self.mcp.clone();
            let tx = tx.clone();
            tokio::spawn(dispatch(mcp, trimmed, tx));
        }

        drop(tx);
        let _ = writer.await;
        Ok(())
    }
}

async fn dispatch<S: Any + Send + Sync + 'static>(
    mcp: Arc<MiniMCP<S>>,
    message: Message,
    tx: UnboundedSender<Message>,
) {
    let send_tx = tx.clone();
    let send: SendFn = Arc::new(move |msg: Message| {
        let tx = send_tx.clone();
        Box::pin(async move {
            let _ = tx.send(msg);
        })
    });

    match mcp.handle(message, Some(send), None).await {
        Ok(Outcome::Message(response)) => {
            let _ = tx.send(response);
        }
        Ok(Outcome::NoMessage(_)) => {}
        Err(InvalidMessageError { response, .. }) => {
            let _ = tx.send(response);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{json, Value};

    fn server() -> Arc<MiniMCP<()>> {
        let mcp = MiniMCP::<()>::new("stdio-test");
        Arc::new(mcp)
    }

    #[tokio::test]
    async fn dispatch_relays_response() {
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<Message>();
        let msg = json!({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "c", "version": "0"}}
        })
        .to_string();

        dispatch(server(), msg, tx).await;

        let response = rx.recv().await.expect("a response should be sent");
        let parsed: Value = serde_json::from_str(&response).unwrap();
        assert_eq!(parsed["id"], 1);
        assert!(parsed.get("result").is_some());
    }

    #[tokio::test]
    async fn dispatch_notification_sends_nothing() {
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<Message>();
        let msg = json!({"jsonrpc": "2.0", "method": "notifications/initialized"}).to_string();

        dispatch(server(), msg, tx).await;

        assert!(rx.try_recv().is_err(), "notifications produce no output");
    }

    #[tokio::test]
    async fn dispatch_invalid_message_relays_error_response() {
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<Message>();

        dispatch(server(), "{not json".to_string(), tx).await;

        let response = rx.recv().await.expect("an error response should be sent");
        let parsed: Value = serde_json::from_str(&response).unwrap();
        assert!(parsed.get("error").is_some());
    }
}
