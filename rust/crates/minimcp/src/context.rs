//! Per-request context available to handlers.
//!
//! Mirrors `minimcp/managers/context_manager.py`. The active [`Context`] is
//! stored in a task-local so handlers can reach request metadata (the raw
//! message, the user-supplied scope, and the responder) without it being
//! threaded through every function signature.

use std::any::Any;
use std::marker::PhantomData;
use std::sync::Arc;

use crate::error::ContextError;
use crate::responder::Responder;

/// Holds request metadata available to message handlers.
///
/// The scope is type-erased here so a single task-local can serve any
/// `MiniMCP<S>`; [`ContextManager::get_scope`] downcasts it back to `S`.
#[derive(Clone)]
pub struct Context {
    /// The raw incoming message being handled.
    pub message: String,
    /// Optional user-supplied per-request scope (auth, db handles, etc.).
    pub scope: Option<Arc<dyn Any + Send + Sync>>,
    /// Optional responder for sending notifications back to the client.
    pub responder: Option<Responder>,
}

tokio::task_local! {
    pub(crate) static CURRENT_CONTEXT: Context;
}

/// Accessor for the currently active request [`Context`].
///
/// Exposed as `mcp.context` on [`crate::MiniMCP`].
pub struct ContextManager<S> {
    _scope: PhantomData<fn() -> S>,
}

impl<S> Default for ContextManager<S> {
    fn default() -> Self {
        Self::new()
    }
}

impl<S> ContextManager<S> {
    /// Create a new context manager.
    pub fn new() -> Self {
        Self {
            _scope: PhantomData,
        }
    }

    /// Get a clone of the active context.
    ///
    /// # Errors
    ///
    /// Returns [`ContextError`] if called outside of an active handler.
    pub fn get(&self) -> Result<Context, ContextError> {
        CURRENT_CONTEXT.try_with(|c| c.clone()).map_err(|_| {
            ContextError("No Context: called outside of an active handler".to_string())
        })
    }

    /// Get the responder from the active context.
    ///
    /// # Errors
    ///
    /// Returns [`ContextError`] if there is no active context or the transport
    /// did not provide a responder.
    pub fn get_responder(&self) -> Result<Responder, ContextError> {
        self.get()?.responder.ok_or_else(|| {
            ContextError("Responder is not available in current context".to_string())
        })
    }
}

impl<S: Any + Send + Sync + 'static> ContextManager<S> {
    /// Get the typed scope from the active context.
    ///
    /// # Errors
    ///
    /// Returns [`ContextError`] if there is no active context, no scope was
    /// provided, or the scope type does not match `S`.
    pub fn get_scope(&self) -> Result<Arc<S>, ContextError> {
        let scope = self
            .get()?
            .scope
            .ok_or_else(|| ContextError("Scope is not available in current context".to_string()))?;

        Arc::downcast::<S>(scope)
            .map_err(|_| ContextError("Scope type mismatch in current context".to_string()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ctx_with_scope(scope: Option<Arc<dyn Any + Send + Sync>>) -> Context {
        Context {
            message: r#"{"jsonrpc":"2.0","id":1,"method":"t"}"#.to_string(),
            scope,
            responder: None,
        }
    }

    #[test]
    fn get_outside_active_context_errors() {
        let manager = ContextManager::<()>::new();
        assert!(manager.get().is_err());
    }

    #[test]
    fn get_scope_outside_active_context_errors() {
        let manager = ContextManager::<String>::new();
        assert!(manager.get_scope().is_err());
    }

    #[test]
    fn get_responder_outside_active_context_errors() {
        let manager = ContextManager::<()>::new();
        assert!(manager.get_responder().is_err());
    }

    #[tokio::test]
    async fn get_within_active_context_returns_message() {
        let manager = ContextManager::<()>::new();
        let ctx = ctx_with_scope(None);
        CURRENT_CONTEXT
            .scope(ctx, async {
                let active = manager.get().unwrap();
                assert!(active.message.contains("\"method\":\"t\""));
            })
            .await;
    }

    #[tokio::test]
    async fn get_scope_downcasts_to_concrete_type() {
        let manager = ContextManager::<String>::new();
        let scope: Arc<dyn Any + Send + Sync> = Arc::new("hello".to_string());
        CURRENT_CONTEXT
            .scope(ctx_with_scope(Some(scope)), async {
                let scope = manager.get_scope().unwrap();
                assert_eq!(*scope, "hello".to_string());
            })
            .await;
    }

    #[tokio::test]
    async fn get_scope_type_mismatch_errors() {
        let manager = ContextManager::<u32>::new();
        let scope: Arc<dyn Any + Send + Sync> = Arc::new("not a u32".to_string());
        CURRENT_CONTEXT
            .scope(ctx_with_scope(Some(scope)), async {
                assert!(manager.get_scope().is_err());
            })
            .await;
    }

    #[tokio::test]
    async fn get_scope_none_errors() {
        let manager = ContextManager::<String>::new();
        CURRENT_CONTEXT
            .scope(ctx_with_scope(None), async {
                assert!(manager.get_scope().is_err());
            })
            .await;
    }

    #[tokio::test]
    async fn get_responder_none_errors() {
        let manager = ContextManager::<()>::new();
        CURRENT_CONTEXT
            .scope(ctx_with_scope(None), async {
                assert!(manager.get_responder().is_err());
            })
            .await;
    }
}
