# MiniMCP Transport Specification Compliance

The official MCP specification currently defines two standard transport mechanisms for client-server communication - [stdio](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#stdio) and [Streamable HTTP](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#streamable-http). It also provides flexibility for different implementations and also permits custom transports. However, implementers must ensure the following which MiniMCP adheres to:

- All messages MUST use JSON-RPC 2.0 format and be UTF-8 encoded.
- Lifecycle requirements during both initialization and operation phases are met.
- Each message represents an individual request, notification, or response.

MiniMCP makes use of the flexibility to provide a third HTTP transport.

## 1. Stdio Transport

Consistent with the standard, stdio enables bidirectional communication and is commonly employed for developing local MCP servers.

- The server reads messages from its standard input (stdin) and sends messages to its standard output (stdout).
- Messages are delimited by newlines.
- Only valid MCP messages should be written into stdin and stdout.

## 2. HTTP Transport

HTTP is a subset of Streamable HTTP and doesn't provide bidirectional communication. On the flip side, it can be easily added as a RESTful API endpoint in any Python application for developing remote MCP servers.

- The transport SHOULD check the accept header, content type, protocol version, and request body.
- Every message sent from the client MUST be a new HTTP POST request to the MCP endpoint.
- The body of the POST request MUST be a single JSON-RPC request or notification.
- If the input is a request: The server MUST return Content-Type: application/json, to return one response JSON object.
- If the input is a notification: If the server accepts, the server MUST return HTTP status code 202 Accepted with no body.
- If the server cannot accept, it MUST return an HTTP error status code (e.g., 400 Bad Request). The HTTP response body MAY comprise a JSON-RPC error response that has no id.
- Multiple POST requests must be served concurrently by the server.

## 3. Smart Streamable HTTP Transport

MiniMCP comes with a Smart Streamable HTTP implementation. It keeps track of the usage pattern and sends back a normal JSON HTTP response if the handler just returns a response. In other words, the event stream is used only if a notification needs to be sent from the server to the client. For simplicity, it uses polling to keep the stream open, and fully resumable Streamable HTTP can be supported in the future.

- The transport SHOULD check the accept header, content type, protocol version, and request body.
- Every message sent from the client MUST be a new HTTP POST request to the MCP endpoint.
- The body of the POST request MUST be a single JSON-RPC request or notification.
- If the input is a request:
  - To return one response JSON object: The server MUST return Content-Type: application/json.
  - To return notifications followed by a response JSON object: The server MUST return an SSE stream with Content-Type: text/event-stream.
  - The SSE stream SHOULD eventually include a JSON-RPC response for the JSON-RPC request sent in the POST body.
- If the input is a notification: If the server accepts, the server MUST return HTTP status code 202 Accepted with no body.
- If the server cannot accept, it MUST return an HTTP error status code (e.g., 400 Bad Request). The HTTP response body MAY comprise a JSON-RPC error response that has no id.
- Multiple POST requests must be served concurrently by the server.
