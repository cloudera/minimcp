# Known Issues

## 1. `httpcore.ReadError` / `ExceptionGroup` during streamable-HTTP benchmark teardown

**Status:** Workaround in place — upstream fix required in `mcp` SDK
**Affects:** `benchmarks/macro/streamable_http_mcp_server_benchmark.py`
**MCP SDK version observed:** 1.24.0
**Upstream repo:** <https://github.com/modelcontextprotocol/python-sdk>

---

### Symptom

At the end of each benchmark round the following `ExceptionGroup` is raised from
inside `mcp.client.streamable_http.streamable_http_client`:

```text
exceptiongroup.ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
  └─ httpx.ReadError
       └─ httpcore.ReadError          ← TCP read failed at response-header level
```

The innermost `httpcore.ReadError` occurs inside
`mcp/client/streamable_http.py::_handle_post_request` while waiting for HTTP
response headers from the server.

---

### Root Cause

`streamable_http_client` runs an internal `anyio` task group that manages
background tasks, including a dispatcher that converts writes on the MCP
`write` channel into HTTP POST requests and reads the server's responses.

The teardown sequence for a benchmark round is:

```text
ClientSession.__aexit__()           ← innermost context; sends a final
                                      MCP notification over the write channel
streamable_http_client.__aexit__()  ← cancels all background tasks immediately
```

Because these two exits are back-to-back (nested `async with` blocks), the
timeline is:

1. `ClientSession.__aexit__` writes a close notification to the `write` channel.
2. The `streamable_http_client` background dispatcher picks up the notification
   and fires an HTTP POST to the server.
3. `streamable_http_client.__aexit__` cancels its task group **before the
   server has responded**.
4. The cancelled task was blocked on `httpx` reading response headers →
   `httpcore.ReadError`.
5. The error is unhandled inside the background task, so it surfaces as an
   `ExceptionGroup` from the outer task group's `__aexit__`.

The server never gets a chance to send back headers; from the TCP layer's
perspective the client simply disappears, resulting in a connection reset.

---

### Workaround (current)

After `ClientSession.__aexit__` completes, the `write` channel is closed
explicitly. This signals EOF to the dispatcher task: it drains and processes
the final queued notification (the POST), then exits its own loop cleanly.
By the time `streamable_http_client.__aexit__` cancels the task group, the
dispatcher is already done — no task is blocked mid-read, so no
`ReadError`.

The `CancelScope(shield=True)` prevents an outer cancellation from
interrupting the `aclose` call itself. The `ClosedResourceError` guard
handles SDK versions that already close the write channel during
`ClientSession.__aexit__`.

```python
async with streamable_http_client(server_url, http_client=client) as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()
        yield session, process
    # Signal EOF so the dispatcher exits cleanly after the final POST.
    with anyio.CancelScope(shield=True):
        try:
            await write.aclose()
        except anyio.ClosedResourceError:
            pass
```

The previous workaround used `await anyio.sleep(0.5)`. That was sufficient
for tools with measurable latency but failed for near-zero-latency tools
(e.g. `noop_tool`) where the rapid connection churn made the 0.5 s window
unreliable. Closing the channel is deterministic rather than time-based.

---

### Proper Fix (upstream)

The root cause is that `streamable_http_client` does not gracefully drain
in-flight requests before cancelling its internal task group. The fix belongs
in the MCP Python SDK.

`streamable_http_client` should, before cancelling its task group:

1. Close (or signal EOF on) the write channel so the dispatcher task knows no
   more messages will arrive.
2. Wait for the dispatcher task to finish processing any already-queued
   messages (i.e., for all in-flight HTTP POST requests to complete or time
   out).
3. Only then cancel any remaining tasks (e.g. the GET-based SSE reader).

A concrete approach using anyio primitives would be:

```python
# Inside streamable_http_client's __aexit__ (pseudo-code):
async with anyio.CancelScope(deadline=anyio.current_time() + DRAIN_TIMEOUT):
    await write_channel.aclose()   # signal EOF to dispatcher
    await dispatcher_task_done.wait()  # wait for in-flight POST to finish
# Now safe to cancel the task group
tg.cancel_scope.cancel()
```

This mirrors the pattern used by well-behaved async producers/consumers and
avoids the race entirely.

---

### Tracking

File a bug or PR against `modelcontextprotocol/python-sdk` referencing this
file. The relevant client code lives in
`src/mcp/client/streamable_http.py`, around the `streamable_http_client`
async context manager and `handle_request_async` / `_handle_post_request`
methods.
