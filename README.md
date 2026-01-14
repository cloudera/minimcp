<div align="center">

<!-- omit in toc -->
### ![✨ MiniMCP](https://raw.githubusercontent.com/cloudera/minimcp/main/docs/images/minimcp-logo.svg)

![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
[![PyPI version](https://img.shields.io/pypi/v/minimcp.svg)](https://pypi.org/project/minimcp/)
[![DeepWiki Badge](https://deepwiki.com/badge.svg)](https://deepwiki.com/cloudera/minimcp)

A **minimal, stateless, and lightweight** framework for building MCP servers.
</div>

_Simple async function interface_ ⭐ _Bidirectional messaging is optional_ ⭐ _Remote & local servers_ ⭐ _Built-in transports - stdio, HTTP, and 'Smart' Streamable HTTP_ ⭐ _Embeddable into any Python web application_ ⭐ _Based on official MCP Python specification._

## Table of Contents

- [What is MCP?](https://github.com/cloudera/minimcp/blob/main#what-is-mcp)
- [Why MiniMCP?](https://github.com/cloudera/minimcp/blob/main#why-minimcp)
  - [When to Use MiniMCP](https://github.com/cloudera/minimcp/blob/main#when-to-use-minimcp)
  - [Currently Supported Features](https://github.com/cloudera/minimcp/blob/main#currently-supported-features)
  - [Planned Features](https://github.com/cloudera/minimcp/blob/main#planned-features)
  - [Unlikely Features](https://github.com/cloudera/minimcp/blob/main#unlikely-features)
- [Using MiniMCP](https://github.com/cloudera/minimcp/blob/main#using-minimcp)
  - [Installation](https://github.com/cloudera/minimcp/blob/main#installation)
  - [Quick Start - Standalone ASGI App](https://github.com/cloudera/minimcp/blob/main#quick-start---standalone-asgi-app)
  - [Basic Setup](https://github.com/cloudera/minimcp/blob/main#basic-setup)
  - [FastAPI Integration](https://github.com/cloudera/minimcp/blob/main#fastapi-integration)
- [Benchmark - MiniMCP vs FastMCP](https://github.com/cloudera/minimcp/blob/main#benchmark---minimcp-vs-fastmcp)
- [API Reference](https://github.com/cloudera/minimcp/blob/main#api-reference)
  - [MiniMCP](https://github.com/cloudera/minimcp/blob/main#minimcp)
  - [Primitive Managers/Decorators](https://github.com/cloudera/minimcp/blob/main#primitive-managersdecorators)
    - [Tool Manager](https://github.com/cloudera/minimcp/blob/main#tool-manager)
    - [Prompt Manager](https://github.com/cloudera/minimcp/blob/main#prompt-manager)
    - [Resource Manager](https://github.com/cloudera/minimcp/blob/main#resource-manager)
  - [Context Manager](https://github.com/cloudera/minimcp/blob/main#context-manager)
- [Transports](https://github.com/cloudera/minimcp/blob/main#transports)
  - [Stdio Transport](https://github.com/cloudera/minimcp/blob/main#stdio-transport)
  - [HTTP Transport](https://github.com/cloudera/minimcp/blob/main#http-transport)
  - [Smart Streamable HTTP Transport](https://github.com/cloudera/minimcp/blob/main#smart-streamable-http-transport)
- [Testing](https://github.com/cloudera/minimcp/blob/main#testing)
- [Error Handling](https://github.com/cloudera/minimcp/blob/main#error-handling)
  - [Protocol-Level Errors](https://github.com/cloudera/minimcp/blob/main#protocol-level-errors)
  - [Transport Error Handling](https://github.com/cloudera/minimcp/blob/main#transport-error-handling)
- [Examples](https://github.com/cloudera/minimcp/blob/main#examples)
  - [1. Math MCP server](https://github.com/cloudera/minimcp/blob/main#1-math-mcp-server)
    - [Claude Desktop](https://github.com/cloudera/minimcp/blob/main#claude-desktop)
  - [2. Integrating With Web Frameworks](https://github.com/cloudera/minimcp/blob/main#2-integrating-with-web-frameworks)
- [FAQ](https://github.com/cloudera/minimcp/blob/main#faq)
- [Documentation](https://github.com/cloudera/minimcp/blob/main#documentation)
- [Contributing](https://github.com/cloudera/minimcp/blob/main#contributing)
- [License](https://github.com/cloudera/minimcp/blob/main#license)

## What is MCP?

The [Model Context Protocol (MCP)](https://modelcontextprotocol.io) is a powerful, standardized way for AI applications to connect with external data sources and tools. It follows a client–server architecture, where communication happens through well-defined MCP messages in the JSON-RPC 2.0 format. The key advantage of MCP is its interoperability: once a server supports MCP, any MCP-compatible AI client can connect to it without custom integration code. The official MCP Python SDK provides a low-level implementation of the protocol, while [FastMCP](https://github.com/jlowin/fastmcp) offers a higher-level, Pythonic interface.

## Why MiniMCP?

MiniMCP rethinks the MCP server from the ground up, keeping the core functionality lightweight and independent of transport layer, bidirectional communication, session management, and auth mechanisms. Additionally, instead of a stream-based interface, MiniMCP exposes a simple asynchronous handle function that takes a JSON-RPC 2.0 message string as input and returns a JSON-RPC 2.0 message string as output.

- **Stateless:** Scalability, simplicity, and reliability are crucial for remote MCP servers. MiniMCP provides all of those by being stateless at its core — each request is self-contained, and the server maintains no persistent session state.
  - This design makes it robust and easy to scale horizontally.
  - This also makes it a perfect fit for **serverless architectures**, where ephemeral execution environments are the norm.
  - Want to start your MCP server using uvicorn with multiple workers? No problem.
- **Bidirectional is optional:** Many use cases work perfectly with a simple request–response channel without needing bidirectional communication. MiniMCP was built with this in mind and provides a simple HTTP transport while adhering to the specification.
- **Embeddable:** Already have an application built with FastAPI (or another framework)? You can embed a MiniMCP server under a single endpoint, or multiple servers under multiple endpoints — _As a cherry on the cake, you can use your existing dependency injection system._
- **Scope and Context:** MiniMCP provides a type-checked scope object that travels with each message. This allows you to pass extra details such as authentication, user info, session data, or database handles. Inside the handler, the scope is available as part of the context — _So you’re free to use your preferred session or user management mechanisms._
- **Security:** MiniMCP encourages you to use your existing battle-tested security mechanism instead of enforcing one - _In other words, a MiniMCP server built with FastAPI can be as secure as any FastAPI application!_
- **Stream on Demand:** MiniMCP comes with a smart streamable HTTP transport. It opens an event stream only when the server needs to push notifications to the client.
- **Separation of Concerns:** The transport layer is fully decoupled from message handling. This makes it easy to adapt MiniMCP to different environments and transport protocols without rewriting your core business logic.
- **Minimal Dependencies:** MiniMCP keeps its footprint small, depending only on the official MCP SDK.

### When to Use MiniMCP

- If you need to embed MCP in an existing web application (FastAPI, Django, Flask, etc.)
- Want stateless, horizontally scalable MCP servers
- Are deploying to serverless environments (AWS Lambda, Cloud Functions, etc.)
- Use your existing battle-tested security mechanisms and middlewares
- Want simple HTTP endpoints without mandatory bidirectional communication
- Need better CPU usage, and resilience by running multiple workers (e.g., `uvicorn --workers 4`)

### Currently Supported Features

The following features are already available in MiniMCP.

- 🧩 Server primitives - Tools, Prompts and Resources
- 🔗 Transports - stdio, HTTP, Streamable HTTP
- 🔄 Server to client messages - Progress notification
- 🛠 Typed scope and handler context
- ⚡ Asynchronous and stateless message processing
- 📝 Easy handler registration for different MCP message types
- ⏱️ Enforces idle time and concurrency limits
- 📦 Web frameworks — In-built support for Starlette/FastAPI

### Planned Features

These features may be added in the future if the need arises.

- ⚠️ Built-in support for more frameworks — Flask, Django etc.
- ⚠️ Client primitives - Sampling, Elicitation, Logging
- ⚠️ Resumable Streamable HTTP with GET method support
- ⚠️ Fine-grained access control (FGAC)
- ⚠️ Pagination
- ⚠️ Authentication
- ⚠️ MCP Client (_As shown in the [integration tests](https://github.com/cloudera/minimcp/blob/main/tests/integration/), MiniMCP (All 3 transports) works seamlessly with existing MCP clients, hence there is no immediate need for a custom client_)

### Unlikely Features

The only feature that's not expected to be built into MiniMCP in the foreseeable future.

- 🚫 Session management

## Using MiniMCP

The snippets below provide a quick overview of how to use MiniMCP. Check out the [examples](https://github.com/cloudera/minimcp/blob/main/examples/) for more.

### Installation

**Python Requirement**: Version 3.10 or higher.

MiniMCP is built on top of the official MCP Python SDK. Install it using pip or uv:

```bash
# Using pip
pip install minimcp

# Using uv (recommended)
uv add minimcp
```

### Quick Start - Standalone ASGI App

MiniMCP can be easily deployed as an ASGI application.

```python
# test.py

from minimcp import MiniMCP, HTTPTransport

# Create an MCP instance
mcp = MiniMCP(name="MathServer")

# Register tools and other primitives
@mcp.tool(description="Add two numbers")
def add(a: int, b: int) -> int:
    return a + b

# MCP server as ASGI Application
app = HTTPTransport(mcp).as_starlette("/mcp")
```

You can now start the server using uvicorn with four workers as follows.

```bash
uv run uvicorn test:app --workers 4
```

### Basic Setup

The following example demonstrates simple registration and basic message processing using the handle function.

```python
from minimcp import MiniMCP

mcp = MiniMCP(name="MathServer")

# Tool
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

# Prompt
@mcp.prompt()
def problem_solving(problem_description: str) -> str:
    """Prompt to systematically solve math problems."""
    return f"""You are a math problem solver. Solve the following problem step by step.
Problem: {problem_description}
"""

# Resource
@mcp.resource("math://constants/pi")
def pi_value() -> float:
    """Value of π (pi) to be used"""
    return 3.14
```

Internally, transport layers call `handle()` with the optional `send` callback and `scope` object:

```python
# request_msg = '{"jsonrpc": "2.0", "id": "1", "method": "ping"}'
response_msg = await mcp.handle(request_msg, send_callback, scope)
# response_msg = '{"jsonrpc": "2.0", "id": "1", "result": {}}'
```

### FastAPI Integration

This minimal example shows how to expose an MCP tool over HTTP using FastAPI.

```python
from fastapi import FastAPI, Request
from minimcp import MiniMCP, HTTPTransport

# This can be an existing FastAPI/Starlette app (with authentication, middleware, etc.)
app = FastAPI()

# Create an MCP instance with optional typed scope
mcp = MiniMCP(name="MathServer")
transport = HTTPTransport(mcp)

# Register a simple tool
@mcp.tool(description="Add two numbers")
def add(a: int, b: int) -> int:
    return a + b

# Host MCP server
@app.post("/mcp")
async def handler(request: Request):
    # Pass auth, database connection and other metadata as part of scope (optional)
    scope = {"user_id": "123", "db": db_connection}
    return await transport.starlette_dispatch(request, scope)
```

## Benchmark - MiniMCP vs FastMCP

In our benchmarks, MiniMCP consistently outperforms FastMCP across all transport types and workloads:

- **20-67% faster response times** under load
- **10-173% higher throughput** (especially HTTP transports under heavy load)
- **17-28% lower max memory usage** under heavy load
- **Superior scalability** with increasing concurrency

For detailed benchmark results and analysis, see [benchmark analysis report](https://github.com/cloudera/minimcp/blob/main/benchmarks/reports/MINIMCP_VS_FASTMCP_ANALYSIS.md).

### Test Environment

- **Python Version**: 3.11.9
- **OS**: Linux 6.8.0-87-generic
- **Test Date**: December 9, 2025
- **Total Test Duration**: ~8 hours

## API Reference

This section provides an overview of the key classes, their functions, and the arguments they accept.

### MiniMCP

`from minimcp import MiniMCP` is the key orchestrator for building an MCP server. It requires a server name as its only mandatory argument; all other arguments are optional. You can also specify the type of the scope object, which is passed through the system for static type checking.

MiniMCP provides:

- Tool, Prompt, and Resource managers — used to register message handlers.
- A Context manager — usable inside handlers.

The `MiniMCP.handle()` function processes incoming messages. It accepts a JSON-RPC 2.0 message string and two optional parameters — a send function and a scope object. MiniMCP controls how many handlers can run at the same time and how long each handler can remain idle. By default, idle_timeout is set to 30 seconds and max_concurrency to 100.

```python
# Instantiation
mcp = MiniMCP[ScopeT](name, [version, instructions, idle_timeout, max_concurrency])

# Managers
mcp.tool
mcp.prompt
mcp.resource
mcp.context

# Message handling
response = await mcp.handle(message, [send, scope])
```

### Primitive Managers/Decorators

MiniMCP supports three server primitives, each managed by its own manager class. These managers are available under MiniMCP as a callable instance that can be used as decorators for registering handler functions. They work similar to FastMCP's decorators.

The decorator accepts primitive details as argument (like name, description etc). If not provided, these details are automatically inferred from the handler function.

In addition to decorator usage, all three primitive managers also expose methods to add, list, remove, and invoke handlers programmatically.

#### Tool Manager

```python
# As a decorator
@mcp.tool([name, title, description, annotations, meta])
def handler_func(...):...

# Methods for programmatic access
mcp.tool.add(handler_func, [name, title, description, annotations, meta])  # Register a tool
mcp.tool.remove(name)                                                      # Remove a tool by name
mcp.tool.list()                                                            # List all registered tools
mcp.tool.call(name, args)                                                  # Invoke a tool by name
```

#### Prompt Manager

```python
# As a decorator
@mcp.prompt([name, title, description, meta])
def handler_func(...):...

# Methods for programmatic access
mcp.prompt.add(handler_func, [name, title, description, meta])
mcp.prompt.remove(name)
mcp.prompt.list()
mcp.prompt.get(name, args)
```

#### Resource Manager

```python
# As a decorator
@mcp.resource(uri, [name, title, description, mime_type, annotations, meta])
def handler_func(...):...

# Methods for programmatic access
mcp.resource.add(handler_func, uri, [name, title, description, mime_type, annotations, meta])
mcp.resource.remove(name)
mcp.resource.list()                    # List all static resources
mcp.resource.list_templates()          # List all resource templates (URIs with parameters)
mcp.resource.read(uri)                 # Read a resource by URI, returns ReadResourceResult
mcp.resource.read_by_name(name, args)  # Read a resource by name with template args dict
```

### Context Manager

The Context Manager provides access to request metadata (such as the message, scope, responder, and time_limiter) directly inside the handler function. It tracks the currently active handler context, which you can retrieve using `mcp.context.get()`. If called outside of a handler, this method raises a `ContextError`.

```python
# Context structure
Context(Generic[ScopeT]):
    message: JSONRPCMessage      # The parsed request message
    time_limiter: TimeLimiter    # time_limiter.reset() resets the handler idle timeout
    scope: ScopeT | None         # Scope object passed when calling handle()
    responder: Responder | None  # Allows sending notifications back to the client

# Accessing context
mcp.context.get() -> Context[ScopeT]

# Helper methods for easy access (raise ContextError if not available)
mcp.context.get_scope() -> ScopeT
mcp.context.get_responder() -> Responder
```

**Example - Resetting timeout in long-running operations:**

```python
@mcp.tool()
async def process_large_dataset(dataset_id: str) -> str:
    """Process a large dataset with periodic timeout resets"""
    ctx = mcp.context.get()

    for i in range(1000):
        # Reset timeout to prevent idle timeout during active processing
        ctx.time_limiter.reset()
        await process_item(i)

    return "Processing complete"
```

### Responder

The Responder enables handlers to send notifications back to the client during request processing. It's available via `mcp.context.get_responder()` and automatically resets the idle timeout when sending notifications, ensuring handlers don't time out while actively communicating.

```python
# Accessing responder
responder = mcp.context.get_responder()

# Send progress notifications
await responder.report_progress(progress, total, message)

# Send custom notifications
await responder.send_notification(notification)

# More would be added in the future
```

**Example - Reporting progress during long operations:**

```python
@mcp.tool()
async def process_files(file_paths: list[str]) -> str:
    """Process multiple files with progress updates"""
    responder = mcp.context.get_responder()
    total = len(file_paths)

    for i, path in enumerate(file_paths):
        await responder.report_progress(
            progress=i + 1,
            total=total,
            message=f"Processing {path}"
        )
        await process_file(path)

    return f"Processed {total} files"
```

## Transports

The official MCP specification currently defines two standard transport mechanisms: [stdio](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#stdio) and [Streamable HTTP](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#streamable-http). It also provides flexibility in implementations and also permits custom transports. MiniMCP uses this flexibility to introduce a third option: HTTP transport.

| Transport       | Directionality   | Use Case                                                            |
| --------------- | ---------------- | ------------------------------------------------------------------- |
| Stdio           | Bidirectional    | Local integration (e.g., Claude desktop)                            |
| HTTP            | Request–response | Simple REST-like message handling                                   |
| Streamable HTTP | Bidirectional    | Advanced message handling with notifications, progress updates etc. |

### Stdio Transport

MiniMCP processes each incoming message in a dedicated async task that remains active throughout the entire handler execution. This ensures proper resource management and allows for concurrent message processing while maintaining handler isolation.

### HTTP Transport

HTTP is a subset of Streamable HTTP and does not support bidirectional (server-to-client) communication. However, as shown in the integration example, it can be added as an API endpoint in any Python application to host remote MCP servers. Importantly, it remains compatible with Streamable HTTP MCP clients (Clients can connect using the Streamable HTTP protocol)

### Smart Streamable HTTP Transport

MiniMCP provides a `Smart` Streamable HTTP implementation that uses SSE only when notifications needs to be sent to the client from the server:

- **Simple responses**: If the handler simply returns a message without sending notifications, the server replies with a normal JSON HTTP response.
- **Event streams**: An SSE (Server-Sent Events) stream is opened **only when** the handler calls `responder.send_notification()` or `responder.report_progress()` _(More would be supported in the future)_.
- **Stateless design**: Uses polling provided by Starlette EventSourceResponse to maintain an SSE connection.
- **Future enhancement**: Resumability in case of connection loss could be implemented in a future iteration _(Probably using something like Redis Streams)_, and make polling optional.

Check out [the Math MCP examples](https://github.com/cloudera/minimcp/blob/main/examples/math_mcp/) to see how each transport can be used.

## Testing

MiniMCP comes with a comprehensive test suite of **645 tests** covering unit and integration testing across all components. The test suite validates MCP specification compliance, error handling, edge cases, and real-world scenarios.

For detailed information about the test suite, coverage, and running tests, see the [Testing Guide](https://github.com/cloudera/minimcp/blob/main/docs/testing-guide.md).

## Error Handling

MiniMCP implements a comprehensive error handling system following JSON-RPC 2.0 and MCP specifications. It is designed to bubble up the error information to the client and continue processing. Its architecture cleanly distinguishes between external, client-exposed errors (MiniMCPError subclasses) and internal, MCP-handled errors (InternalMCPError subclasses).

### Protocol-Level Errors

The `MiniMCP.handle()` method provides centralized error handling for all protocol-level errors. Parse errors and JSON-RPC validation errors are re-raised as `InvalidMessageError`, which transport layers must handle explicitly. Other internal errors (invalid parameters, method not found, resource not found, runtime errors etc.) are caught and returned as formatted JSON-RPC error responses with appropriate error codes per the specification.

Tool errors use a dual mechanism as specified by MCP:

1. Tool registration errors, invalid arguments, and runtime failures are returned as JSON-RPC errors.
2. Business logic errors within tool handlers (e.g., API failures, invalid data) are caught by the low-level MCP core and returned in `CallToolResult` with `isError: true`, allowing the client to handle them appropriately.

#### Example - isError: true

```python
@mcp.tool()
def divide(a: float, b: float) -> float:
    """Divide two numbers

    Raises:
        ValueError: If divisor is zero (returned as tool error with isError=true)
    """
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
```

### Transport Error Handling

Each transport implements error handling tailored to its communication model:

- **HTTP transports**: Performs request (header/version) validation, and catches `InvalidMessageError` and other unexpected exceptions. The errors are then formatted as JSON-RPC error messages and return with appropriate HTTP status codes.
- **Stdio transport**: Catches all exceptions including `InvalidMessageError`, formats them as JSON-RPC errors, and writes them to stdout. The connection remains active to continue processing subsequent messages.

## Examples

To run the examples, you’ll need a development setup. After cloning this repository, run the following command from the project root to set up the environment:

```bash
uv sync --frozen --all-extras --dev
```

### 1. Math MCP server

[First set of examples](https://github.com/cloudera/minimcp/blob/main/examples/math_mcp/) include a [Math MCP server](https://github.com/cloudera/minimcp/blob/main/examples/math_mcp/math_mcp.py) with prompts, resources and four tools (add, subtract, multiply, and divide). The examples demonstrate how MiniMCP works with different transport mechanisms and frameworks.

The table below lists the available examples along with the commands to run them.

| # | Transport/Server       | Command                                                               |
|---|------------------------|-----------------------------------------------------------------------|
| 1 | Stdio                  | `uv run -m examples.math_mcp.stdio_server`                    |
| 2 | HTTP Server            | `uv run uvicorn examples.math_mcp.http_server:app`            |
| 3 | Streamable HTTP Server | `uv run uvicorn examples.math_mcp.streamable_http_server:app` |

#### Claude Desktop

Claude desktop can be configured as follows to run the Math MCP stdio example. Replace `/path/to/minimcp` with the actual absolute path to your cloned repository (e.g., `/Users/yourname/projects/minimcp` or `C:\Users\yourname\projects\minimcp`).

```json
{
    "mcpServers":
    {
        "math-server":
        {
            "command": "uv",
            "args":
            [
                "--directory",
                "/path/to/minimcp",
                "run",
                "-m",
                "examples.math_mcp.stdio_server"
            ]
        }
    }
}
```

### 2. Integrating With Web Frameworks

[Second set of examples](https://github.com/cloudera/minimcp/blob/main/examples/web_frameworks/) demonstrate how MiniMCP can be integrated with web frameworks like FastAPI and Django. A dummy [Issue Tracker MCP server](https://github.com/cloudera/minimcp/blob/main/examples/web_frameworks/issue_tracker_mcp.py) was created for the same. It provides tools to create, read, and delete issues.

The table below lists the available examples along with the commands to run them.

| # | Server                         | Command                                                                                            |
|---|--------------------------------|----------------------------------------------------------------------------------------------------|
| 1 | FastAPI HTTP Server with auth | `uv run --with fastapi uvicorn examples.web_frameworks.fastapi_http_server_with_auth:app` |
| 2 | Django WSGI server with auth   | `uv run --with django --with djangorestframework python examples/web_frameworks/django_wsgi_server_with_auth.py runserver` |

Once started, you can use the following curl commands for testing. The examples use HTTP Basic auth to extract the username (for demonstration purposes only - credentials are not validated, any username/password will work):

```bash
# 1. Ping the MCP server
curl -X POST http://127.0.0.1:8000/mcp \
    -u admin:admin \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"jsonrpc": "2.0", "id": "1", "method": "ping"}'

# 2. List tools
curl -X POST http://127.0.0.1:8000/mcp \
    -u admin:admin \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'

# 2. Create an issue
curl -X POST http://127.0.0.1:8000/mcp \
    -u admin:admin \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"jsonrpc":"2.0","id":"1","method":"tools/call",
        "params":{"name":"create_issue","arguments":{"title":"First issue","description":"Issue description"}}}'

# 3. Read the issue
curl -X POST http://127.0.0.1:8000/mcp \
    -u admin:admin \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"jsonrpc":"2.0","id":"1","method":"tools/call",
        "params":{"name":"read_issue","arguments":{"issue_id":"MCP-1"}}}'

# 4. Delete the issue
curl -X POST http://127.0.0.1:8000/mcp \
    -u admin:admin \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"jsonrpc":"2.0","id":"1","method":"tools/call",
        "params":{"name":"delete_issue","arguments":{"issue_id":"MCP-1"}}}'
```

## FAQ

**Q: Why does my handler time out after 30 seconds?**

A: The default idle timeout is 30 seconds. For long-running operations, reset the timeout periodically:

```python
@mcp.tool()
async def long_operation():
    ctx = mcp.context.get()
    for i in range(100):
        # Reset timeout to prevent idle timeout
        ctx.time_limiter.reset()
        await process_item(i)
```

You can also configure the timeout when creating the MiniMCP instance:

```python
mcp = MiniMCP(name="MyServer", idle_timeout=60)  # 60 seconds
```

**Q: How do I adjust the concurrency limit?**

A: By default, MiniMCP allows 100 concurrent handlers. You can adjust this with the `max_concurrency` parameter:

```python
mcp = MiniMCP(name="MyServer", max_concurrency=200)
```

**Q: How do I access the scope in nested functions?**

A: Use `mcp.context.get_scope()` from anywhere within the handler execution context:

```python
@mcp.tool()
def my_tool():
    scope = mcp.context.get_scope()
    helper_function()

def helper_function():
    # Can access scope from nested functions
    scope = mcp.context.get_scope()
    user_id = scope.user_id
```

**Q: Can I use MiniMCP with multiple workers in uvicorn?**

A: Yes! MiniMCP is stateless by design and works perfectly with multiple workers:

```bash
uvicorn my_server:app --workers 4
```

**Q: How do I handle ContextError exceptions?**

A: `ContextError` is raised when accessing context outside of a handler or when required context attributes (scope, responder) are not available:

```python
# Check if scope is available
try:
    scope = mcp.context.get_scope()
except ContextError:
    # Handle case where scope wasn't provided
    pass

# Or check the context directly
ctx = mcp.context.get()
if ctx.scope is not None:
    # Use scope
    pass
```

**Q: What's the difference between HTTP and Streamable HTTP transports?**

A: HTTP is a subset of Streamable HTTP and does not support bidirectional (server-to-client) communication.

- **HTTP**: Simple request-response only. No server-to-client notifications.
- **Streamable HTTP**: Supports bidirectional communication. Opens SSE stream when needed.
- Both are compatible—Streamable HTTP clients can connect to HTTP servers (without bidirectional features).

## Documentation

For detailed information beyond this README, check out the following guides:

- [Testing Guide](https://github.com/cloudera/minimcp/blob/main/docs/testing-guide.md)
- [Transport Specification Compliance](https://github.com/cloudera/minimcp/blob/main/docs/transport-specification-compliance.md)- [Sample MCP Messages](https://github.com/cloudera/minimcp/blob/main/docs/sample-mcp-messages.md)

Additional resources:

- [DeepWiki API Documentation](https://deepwiki.com/cloudera/minimcp)
- [Benchmark Results](https://github.com/cloudera/minimcp/blob/main/benchmarks/reports/MINIMCP_VS_FASTMCP_ANALYSIS.md)

## Contributing

Contributions are welcome! Whether you're fixing bugs, adding features, improving documentation, or reporting issues, we'd love to have your help.

- 🐛 Report bugs or request features via [GitHub Issues](https://github.com/cloudera/minimcp/issues)
- 🔧 Submit pull requests for bug fixes, documentation improvements, or new features

See the [contributing guide](https://github.com/cloudera/minimcp/blob/main/CONTRIBUTING.md) for development setup, workflow, and guidelines.

## License

This project is licensed under [Apache License, Version 2.0](https://github.com/cloudera/minimcp/blob/main/LICENSE)
