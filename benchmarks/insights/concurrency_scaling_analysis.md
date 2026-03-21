# Benchmark Insights: MiniMCP vs FastMCP at High Concurrency

## The Core Observation

MiniMCP is consistently faster than FastMCP at every load level, but the margin
narrows as concurrency increases. This document explains precisely why, what the
data reveals about each server's internal architecture, and which approach is
actually better.

---

## The Numbers: Advantage by Load Level

### HTTP transport — Response time advantage (MiniMCP over FastMCP)

| Scenario       | c=1 (sequential) | c=20 (light) | c=100 (medium) | c=300 (heavy) |
|----------------|------------------|--------------|----------------|---------------|
| Noop           | +52%             | +31%         | +13%           | +15%          |
| Sync tool      | +53%             | +38%         | +19%           | +19%          |
| I/O-bound async| +39%             | +25%         | +4%            | +10%          |

The advantage does not disappear — it compresses and then stabilises. Noop and
sync tools level off at ~19% from c=100 onwards. The I/O-bound scenario narrows
more sharply, for a different reason explained below.

---

## Why the Advantage Narrows: Event Loop Yield Points

### MiniMCP's architecture: one task per request, direct execution

For every HTTP request, MiniMCP runs the entire lifecycle inside a single async
task with no internal yield points (for sync or near-instant async tools):

```text
HTTP task
─────────
await request.body()          ← real I/O yield (socket read)
_parse_message()              ← synchronous Pydantic — no yield
async with nullcontext()      ← capacity limiter disabled — no yield
ClientRequest.model_validate()← synchronous Pydantic — no yield
await tool_func.execute()
  └─ self.func(**args)        ← sync tool called directly — no yield
json_rpc.build_response()     ← synchronous — no yield
await response.send()         ← real I/O yield (socket write)
```

Between the two socket I/O yields, `minimcp.handle()` runs as a single
uninterrupted block. While one request is in this block, every other concurrent
request is waiting for the event loop. This is confirmed by MiniMCP's throughput
efficiency staying at ~1.0× regardless of concurrency.

### FastMCP's architecture: two tasks per request, memory-stream handoff

FastMCP's stateless HTTP handler creates a pair of tasks per request that
communicate via anyio memory object streams:

```text
Task A (HTTP handler)                Task B (MCP server)
─────────────────────                ───────────────────
await tg.start(B)         ──yield──► starts, signals ready
await receive() [socket]  ──yield──► (event loop free)
write request → stream    ──yield──► await read_stream.receive()
await read_stream.receive ◄──yield── Pydantic + dispatch + tool
                                     write response → stream
await send() [socket]     ──yield──► (event loop free)
```

This produces 5+ yield points per request. At c=100, that is 500+
scheduling opportunities across all concurrent requests. The event loop can
interleave socket reads and writes with in-flight processing across many requests.

**Critical clarification: this is not CPU parallelism.** Both tasks run on the
same single-threaded event loop. The total CPU work is the same — actually
slightly more for FastMCP due to the memory stream overhead. What the extra
yield points provide is better **HTTP I/O pipelining**: the event loop can read
the next request body from the socket buffer while an earlier request is being
processed. This reduces queuing time at the socket level.

### The efficiency metric makes this concrete

"Throughput efficiency" is defined as (RPS at load N) ÷ (RPS at sequential).
A value of 1.0× means the server scales exactly as a serial queue would.
A value greater than 1.0× indicates I/O pipelining is reducing per-request
queuing overhead.

| Scenario (HTTP) | MiniMCP at c=100 | FastMCP at c=100 |
|-----------------|------------------|------------------|
| Noop            | 0.90×            | 1.61×            |
| Sync            | 0.91×            | 1.54×            |
| I/O-bound async | 1.34×            | 2.05×            |

MiniMCP's efficiency is flat at ~0.9–1.0×: it scales as expected for a server
that processes requests with minimal yield points. FastMCP's efficiency reaches
1.5–2.0×: its extra yield points give uvicorn many more chances to pipeline
socket I/O between concurrent requests.

FastMCP's superlinear scaling partially compensates for its 2× higher per-request
overhead, which is why the absolute gap in response time narrows.

---

## The I/O-Bound Scenario: A Separate Effect

The I/O-bound tool (`io_bound_compute_all_prime_factors`) has two explicit
`await anyio.sleep(0.001)` calls. At high concurrency these sleeps create a
**thundering herd**: all c=100 tasks start their first sleep simultaneously,
all 100 timers fire at the same moment, and all 100 resume and compete for the
event loop at once.

This effect hits MiniMCP harder than FastMCP. Here is why: FastMCP has 6.3ms
of protocol overhead per request vs MiniMCP's 3.0ms. The 2ms sleep (shared by
both) therefore hides a proportionally larger fraction of FastMCP's overhead.
In effect, FastMCP's heavier protocol work can be "stashed" behind the sleeps
during the thundering-herd recovery period; MiniMCP's lighter protocol work
leaves less room to hide.

This is why the I/O-bound advantage collapses to +4% at c=100 while noop/sync
stays at +13–19%: the sleeps benefit FastMCP more than they cost it.

In production, real I/O (database calls, HTTP requests, etc.) provides genuine
async suspension that distributes load smoothly over time rather than creating
a burst at a single millisecond boundary. The thundering herd is specific to
this benchmark tool design.

---

## Which Approach Is Better?

### MiniMCP wins on absolute performance at every measured point

Despite FastMCP's better concurrency efficiency, MiniMCP is faster in absolute
terms at every concurrency level tested:

| HTTP Noop         | MiniMCP RPS | FastMCP RPS |
|-------------------|-------------|-------------|
| Sequential (c=1)  | 327         | 157         |
| Light (c=20)      | 314         | 231         |
| Medium (c=100)    | 296         | 254         |
| Heavy (c=300)     | 324         | 252         |

FastMCP's 1.6× pipelining gain from c=1→c=100 is real, but it starts from a
much lower baseline (157 RPS vs 327 RPS). The gap narrows but never closes.

### The trade-off is simplicity vs concurrency-friendly scheduling

| Dimension                    | MiniMCP                          | FastMCP                          |
|------------------------------|----------------------------------|----------------------------------|
| Per-request cost             | ~3ms                             | ~6ms                             |
| Yield points per request     | 1–2 (tool's own awaits)          | 5+ (memory stream handoffs)      |
| Single-worker throughput     | Higher at all concurrencies      | Lower but more stable scaling    |
| Architecture complexity      | Single task, direct execution    | Two tasks + memory streams       |
| Real async tools (db, http)  | Natural yield points, full win   | Natural yield points, same       |

### When does each design choice matter?

**MiniMCP's design wins in all practical cases.** For real MCP tool handlers that
do actual I/O (`await db.execute(...)`, `await httpx.get(...)`,
`await anyio.to_thread.run_sync(...)`) the tool itself provides natural yield
points. The event loop gets exactly as many scheduling opportunities as it needs
without any architecture overhead, and MiniMCP's lower per-request cost is the
full story.

FastMCP's two-task architecture provides meaningful concurrency benefit only in
the narrow case of a server with extremely fast-completing sync tools (noop-like)
under very high concurrency on a single worker. Even in that case it does not
catch MiniMCP's throughput.

**For production scale, the standard answer is multiple uvicorn workers.** Each
worker is a separate OS process with its own event loop, providing true
multi-core parallelism. Both MiniMCP and FastMCP benefit equally from this — it
does not change the relative advantage. A 4-worker MiniMCP at c=100 delivers
roughly 4× the throughput of a single-worker MiniMCP, and still outperforms a
4-worker FastMCP by the same margin as single-worker.

### The one structural gap worth noting

For synchronous tool functions, `MCPFunc.execute()` calls the function directly
on the event loop (`self.func(**args)`) without dispatching to a thread pool.
This means a CPU-bound sync tool running for, say, 50ms would block the entire
event loop for that duration, preventing all other concurrent requests from
making progress. FastMCP's two-task architecture does not prevent this either —
blocking the event loop blocks both tasks equally.

The correct mitigation, for both MiniMCP and FastMCP, is the same: any
meaningfully CPU-bound synchronous work should be wrapped in
`await anyio.to_thread.run_sync(fn)` in the tool handler. This is a general
async programming principle, not a server-specific workaround.

---

## Summary

The narrowing of MiniMCP's advantage at high concurrency is real but explained
entirely by I/O pipelining mechanics, not CPU parallelism. FastMCP's two-task
architecture generates more event loop yield points, allowing uvicorn to
pipeline socket reads and writes more aggressively. This gives FastMCP a
~1.5–2.0× superlinear throughput scaling factor that partially offsets its 2×
higher per-request overhead.

MiniMCP remains faster in absolute terms at every concurrency level. Its simpler
architecture is not a liability: for real-world tool handlers with genuine async
I/O, both servers get the yield points they need naturally, and MiniMCP's lower
per-request cost is an unqualified advantage.
