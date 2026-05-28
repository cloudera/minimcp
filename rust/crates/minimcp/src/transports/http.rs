//! HTTP transport (request/response only).
//!
//! Mirrors `minimcp/transports/http.py`. Exposes the server as an axum
//! [`Router`] that accepts a single JSON-RPC message per POST and returns the
//! response as JSON (or `202 Accepted` for notifications).

use std::any::Any;
use std::sync::Arc;

use axum::http::{header, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::post;
use axum::Router;

use crate::error::InvalidMessageError;
use crate::server::MiniMCP;
use crate::types::Outcome;

/// HTTP transport implementation backed by axum.
pub struct HttpTransport<S = ()> {
    mcp: Arc<MiniMCP<S>>,
}

impl<S: Any + Send + Sync + 'static> HttpTransport<S> {
    /// Create an HTTP transport for the given server.
    pub fn new(mcp: Arc<MiniMCP<S>>) -> Self {
        Self { mcp }
    }

    /// Build an axum [`Router`] serving the MCP endpoint at `path` (POST only).
    pub fn router(&self, path: &str) -> Router {
        let mcp = self.mcp.clone();
        Router::new().route(
            path,
            post(move |body: String| {
                let mcp = mcp.clone();
                async move { handle_post(mcp, body).await }
            }),
        )
    }
}

async fn handle_post<S: Any + Send + Sync + 'static>(
    mcp: Arc<MiniMCP<S>>,
    body: String,
) -> Response {
    match mcp.handle(body, None, None).await {
        Ok(Outcome::Message(response)) => {
            ([(header::CONTENT_TYPE, "application/json")], response).into_response()
        }
        Ok(Outcome::NoMessage(_)) => StatusCode::ACCEPTED.into_response(),
        Err(InvalidMessageError { response, .. }) => (
            StatusCode::BAD_REQUEST,
            [(header::CONTENT_TYPE, "application/json")],
            response,
        )
            .into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::MiniMCP;
    use serde_json::json;

    fn server() -> Arc<MiniMCP<()>> {
        Arc::new(MiniMCP::<()>::new("http-test"))
    }

    #[tokio::test]
    async fn post_request_returns_200() {
        let body = json!({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "c", "version": "0"}}
        })
        .to_string();
        let response = handle_post(server(), body).await;
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn post_notification_returns_202() {
        let body = json!({"jsonrpc": "2.0", "method": "notifications/initialized"}).to_string();
        let response = handle_post(server(), body).await;
        assert_eq!(response.status(), StatusCode::ACCEPTED);
    }

    #[tokio::test]
    async fn post_invalid_message_returns_400() {
        let response = handle_post(server(), "{not json".to_string()).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn router_builds() {
        let transport = HttpTransport::new(server());
        let _router = transport.router("/mcp");
    }
}
