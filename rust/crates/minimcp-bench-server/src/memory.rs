//! Process memory measurement for the benchmark harness.
//!
//! Mirrors `benchmarks/core/memory_baseline.py` and `memory_helpers.py`. The
//! Python harness reads a `get_memory_usage` tool that returns the process RSS
//! and max RSS along with baselines captured at startup; this module produces
//! the same structured payload.

use std::sync::OnceLock;

use serde_json::{json, Value};

// On Linux `ru_maxrss` is in kilobytes; on macOS/BSD it is in bytes.
#[cfg(target_os = "linux")]
const MAXRSS_DIVISOR: f64 = 1.0;
#[cfg(not(target_os = "linux"))]
const MAXRSS_DIVISOR: f64 = 1024.0;

static BASELINE_RSS: OnceLock<f64> = OnceLock::new();
static BASELINE_MAXRSS: OnceLock<f64> = OnceLock::new();

fn current_rss_kb() -> f64 {
    match memory_stats::memory_stats() {
        Some(stats) => stats.physical_mem as f64 / 1024.0,
        None => 0.0,
    }
}

fn current_maxrss_kb() -> f64 {
    // SAFETY: getrusage only writes into the provided zero-initialized struct.
    let usage = unsafe {
        let mut usage: libc::rusage = std::mem::zeroed();
        libc::getrusage(libc::RUSAGE_SELF, &mut usage);
        usage
    };
    usage.ru_maxrss as f64 / MAXRSS_DIVISOR
}

/// Capture the baseline RSS and max RSS as early as possible in `main`.
pub fn capture_baseline() {
    BASELINE_RSS.get_or_init(current_rss_kb);
    BASELINE_MAXRSS.get_or_init(current_maxrss_kb);
}

/// Build the memory usage payload expected by the benchmark harness (values in KB).
pub fn memory_usage() -> Value {
    json!({
        "baseline_rss": *BASELINE_RSS.get_or_init(current_rss_kb),
        "current_rss": current_rss_kb(),
        "baseline_maxrss": *BASELINE_MAXRSS.get_or_init(current_maxrss_kb),
        "maxrss": current_maxrss_kb(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn memory_usage_has_harness_contract_fields() {
        capture_baseline();
        let usage = memory_usage();
        // Fields read by benchmarks/core/mcp_server_benchmark.py::_get_memory_usage.
        for field in ["baseline_rss", "current_rss", "baseline_maxrss", "maxrss"] {
            assert!(usage.get(field).is_some(), "missing field {field}");
            assert!(usage[field].is_number(), "field {field} should be numeric");
        }
    }
}
