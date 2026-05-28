//! Benchmark workload tools.
//!
//! Mirrors `benchmarks/core/sample_tools.py`. The harness calls each tool with
//! `{"n": <int>}` and validates `structuredContent["result"]`, so the workload
//! tools wrap their integer result under a `result` key. The `get_memory_usage`
//! tool returns the memory payload directly.

use minimcp::MiniMCP;
use serde_json::json;

use crate::memory;

/// Count all prime factors of `n` (with repetition). Synchronous, CPU-bound.
///
/// Example: `n = 12` -> `2 * 2 * 3` -> returns `3`.
pub fn compute_all_prime_factors(mut n: i64) -> i64 {
    let mut factor_count = 0;

    while n % 2 == 0 {
        factor_count += 1;
        n /= 2;
    }

    let mut i = 3;
    while i * i <= n {
        while n % i == 0 {
            factor_count += 1;
            n /= i;
        }
        i += 2;
    }

    if n > 2 {
        factor_count += 1;
    }

    factor_count
}

fn input_schema() -> serde_json::Value {
    json!({
        "type": "object",
        "properties": {"n": {"type": "integer"}},
        "required": ["n"],
    })
}

fn result_output_schema() -> serde_json::Value {
    json!({
        "type": "object",
        "properties": {"result": {"type": "integer"}},
        "required": ["result"],
    })
}

fn extract_n(args: &serde_json::Value) -> Result<i64, String> {
    args.get("n")
        .and_then(serde_json::Value::as_i64)
        .ok_or_else(|| "missing or invalid argument 'n'".to_string())
}

/// Register the benchmark tools on the given server.
///
/// # Panics
///
/// Panics if any tool name is already registered.
pub fn register(mcp: &MiniMCP<()>) {
    mcp.tool
        .add(
            "compute_all_prime_factors",
            Some("Count all prime factors of n (CPU-bound)."),
            input_schema(),
            Some(result_output_schema()),
            |args| async move {
                let n = extract_n(&args)?;
                Ok(json!({"result": compute_all_prime_factors(n)}))
            },
        )
        .expect("register compute_all_prime_factors");

    mcp.tool
        .add(
            "io_bound_compute_all_prime_factors",
            Some("Simulated I/O-bound async workload: sleep, compute, sleep."),
            input_schema(),
            Some(result_output_schema()),
            |args| async move {
                let n = extract_n(&args)?;
                tokio::time::sleep(std::time::Duration::from_millis(1)).await;
                let result = compute_all_prime_factors(n);
                tokio::time::sleep(std::time::Duration::from_millis(1)).await;
                Ok(json!({"result": result}))
            },
        )
        .expect("register io_bound_compute_all_prime_factors");

    mcp.tool
        .add(
            "noop_tool",
            Some("Echo n back immediately (pure protocol overhead)."),
            input_schema(),
            Some(result_output_schema()),
            |args| async move {
                let n = extract_n(&args)?;
                Ok(json!({"result": n}))
            },
        )
        .expect("register noop_tool");

    mcp.tool
        .add(
            "get_memory_usage",
            Some("Return process RSS/max RSS and startup baselines (KB)."),
            json!({"type": "object", "properties": {}}),
            None,
            |_args| async move { Ok(memory::memory_usage()) },
        )
        .expect("register get_memory_usage");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prime_factor_counts() {
        // 12 = 2 * 2 * 3 -> 3 factors with repetition
        assert_eq!(compute_all_prime_factors(12), 3);
        // 100 = 2 * 2 * 5 * 5 -> 4
        assert_eq!(compute_all_prime_factors(100), 4);
        // 97 is prime -> 1
        assert_eq!(compute_all_prime_factors(97), 1);
    }

    #[tokio::test]
    async fn registers_all_benchmark_tools() {
        let mcp = MiniMCP::<()>::new("bench");
        register(&mcp);
        let names: Vec<String> = mcp.tool.list().into_iter().map(|t| t.name).collect();
        for expected in [
            "compute_all_prime_factors",
            "io_bound_compute_all_prime_factors",
            "noop_tool",
            "get_memory_usage",
        ] {
            assert!(
                names.contains(&expected.to_string()),
                "missing tool {expected}"
            );
        }
    }

    #[tokio::test]
    async fn workload_tools_return_result_key() {
        let mcp = MiniMCP::<()>::new("bench");
        register(&mcp);

        // The benchmark harness validates structuredContent["result"].
        let sync = mcp
            .tool
            .call("compute_all_prime_factors", json!({"n": 12}))
            .await
            .unwrap();
        assert_eq!(sync.structured_content.unwrap()["result"], 3);

        let noop = mcp.tool.call("noop_tool", json!({"n": 7})).await.unwrap();
        assert_eq!(noop.structured_content.unwrap()["result"], 7);

        let io = mcp
            .tool
            .call("io_bound_compute_all_prime_factors", json!({"n": 12}))
            .await
            .unwrap();
        assert_eq!(io.structured_content.unwrap()["result"], 3);
    }
}
