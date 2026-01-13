from minimcp import StreamableHTTPTransport

from .math_mcp import math_mcp

transport = StreamableHTTPTransport[None](math_mcp)
app = transport.as_starlette("/mcp")
