from minimcp import HTTPTransport

from .math_mcp import math_mcp

transport = HTTPTransport[None](math_mcp)
app = transport.as_starlette("/mcp")
