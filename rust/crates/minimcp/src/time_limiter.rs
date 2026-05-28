//! Idle timeout management for a single message handler.
//!
//! Mirrors `minimcp/time_limiter.py`. In the Python implementation the limiter
//! wraps the handler in an anyio cancel scope whose deadline can be reset. In
//! this skeleton [`crate::MiniMCP::handle`] applies the timeout via
//! `tokio::time::timeout`; `TimeLimiter` is the public handle exposed to
//! handlers for resetting the deadline.

use std::time::Duration;

/// Enforces an idle timeout for a single message handler.
///
/// The deadline can be extended via [`TimeLimiter::reset`] while the handler is
/// actively processing (for example, while streaming progress notifications).
#[derive(Debug, Clone)]
pub struct TimeLimiter {
    timeout: Duration,
}

impl TimeLimiter {
    /// Create a new limiter with the given idle timeout.
    pub fn new(timeout: Duration) -> Self {
        Self { timeout }
    }

    /// The configured idle timeout.
    pub fn timeout(&self) -> Duration {
        self.timeout
    }

    /// Reset the idle deadline, extending it from the current time.
    ///
    /// TODO: Wire this to the active timeout future so resets actually extend
    /// the deadline. The skeleton currently applies a fixed per-request timeout.
    pub fn reset(&self) {
        tracing::trace!("TimeLimiter::reset called (no-op in skeleton)");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stores_timeout() {
        let limiter = TimeLimiter::new(Duration::from_secs(30));
        assert_eq!(limiter.timeout(), Duration::from_secs(30));
    }

    #[test]
    fn reset_does_not_panic() {
        let limiter = TimeLimiter::new(Duration::from_millis(500));
        limiter.reset();
        limiter.reset();
    }

    #[test]
    fn clone_preserves_timeout() {
        let limiter = TimeLimiter::new(Duration::from_secs(5));
        assert_eq!(limiter.clone().timeout(), Duration::from_secs(5));
    }
}
