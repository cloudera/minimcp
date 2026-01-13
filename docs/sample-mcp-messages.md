# Sample MCP Messages

Sample JSON-RPC 2.0 messages - request and expected response.

The messages below can be tested using an HTTP client such as Postman or curl. Make sure to set the Accept and Content-Type headers to `application/json`. Use the following command to start the MiniMCP server.

```bash
uv run uvicorn examples.math_mcp.http_server:app --reload
```

## Ping

Request

```json
{
  "jsonrpc": "2.0",
  "id": "123",
  "method": "ping"
}
```

Response

```json
{
    "jsonrpc": "2.0",
    "id": "123",
    "result": {}
}
```

## Initialize

Request

```json
{
    "jsonrpc": "2.0",
    "id": "init-1",
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "roots": {"listChanged": true}
        },
        "clientInfo": {
            "name": "mcp-client",
            "version": "1.0.0"
        }
    }
}
```

Response

```json
{
    "jsonrpc": "2.0",
    "id": "init-1",
    "result": {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "experimental": {},
            "tools": {
                "listChanged": false
            }
        },
        "serverInfo": {
            "name": "math-server",
            "version": "1.0.0"
        }
    }
}
```

## Tools

### List Tools

Request

```json
{
    "jsonrpc": "2.0",
    "id": "tools-1",
    "method": "tools/list",
    "params": {}
}
```

Response

```json
{
    "jsonrpc": "2.0",
    "id": "tools-1",
    "result": {
        "tools": [
            {
                "name": "add",
                "description": "Add two numbers",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "a": {
                            "type": "number"
                        },
                        "b": {
                            "type": "number"
                        }
                    },
                    "required": [
                        "a",
                        "b"
                    ],
                    "additionalProperties": false
                }
            }
        ]
    }
}
```

### Tool Calling

Request

```json
{
    "jsonrpc": "2.0",
    "id": "tool-call-1",
    "method": "tools/call",
    "params": {
        "name": "add",
        "arguments": {
            "a": 5,
            "b": 3
        }
    }
}
```

Response

```json
{
    "jsonrpc": "2.0",
    "id": "tool-call-1",
    "result": {
        "content": [
            {
                "type": "text",
                "text": "8"
            }
        ],
        "isError": false
    }
}
```

### Tool Calling With Progress

MiniMCP server must be started with streamable HTTP transport.

```bash
uv run uvicorn examples.math_mcp.streamable_http_server:app --reload
```

Request

```json
{
    "jsonrpc": "2.0",
    "id": "tool-call-2",
    "method": "tools/call",
    "params": {
        "name": "add",
        "arguments": {
            "a": 5,
            "b": 3
        },
        "_meta": {
            "progressToken": "pg_10"
        }
    }
}
```

Responses

```json
{
    "method": "notifications/progress",
    "params": {
        "progressToken": "pg_10",
        "progress": 0.3,
        "message": "Adding numbers"
    },
    "jsonrpc": "2.0"
}

{
    "method": "notifications/progress",
    "params": {
        "progressToken": "pg_10",
        "progress": 0.7,
        "message": "Adding numbers"
    },
    "jsonrpc": "2.0"
}

{
    "jsonrpc": "2.0",
    "id": "tool-call-2",
    "result": {
        "content": [
            {
                "type": "text",
                "text": "8.0"
            }
        ],
        "structuredContent": {
            "result": 8.0
        },
        "isError": false
    }
}
```

## Prompt

### List Prompts

Request

```json
{
    "jsonrpc": "2.0",
    "id": "prompt-1",
    "method": "prompts/list",
    "params": {}
}
```

Response

```json
{
    "jsonrpc": "2.0",
    "id": "prompt-1",
    "result": {
        "prompts": [
            {
                "name": "problem_solving",
                "description": "General Prompt to systematically solve math problems.",
                "arguments": [
                    {
                        "name": "problem_description",
                        "description": "Description of the problem to solve",
                        "required": true
                    }
                ]
            }
        ]
    }
}
```

### Get Prompt

Request

```json
{
    "jsonrpc": "2.0",
    "id": "prompt-3",
    "method": "prompts/get",
    "params": {
        "name": "problem_solving",
        "arguments": {
            "problem_description": "Find the area of a circle with radius 5 meters"
        }
    }
}
```

Response

```json
{
    "jsonrpc": "2.0",
    "id": "prompt-3",
    "result": {
        "description": "General prompt to systematically solve math problems.",
        "messages": [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": "You are a math problem solver.\nSolve the following problem step by step and provide the final simplified answer.\n\nProblem: Find the area of a circle with radius 5 meters\n\nOutput:\n1. Step-by-step reasoning\n2. Final answer in simplest form\n"
                }
            }
        ]
    }
}
```

## Resource

### List Resources

Request

```json
{
    "jsonrpc": "2.0",
    "id": "resource-1",
    "method": "resources/list",
    "params": {}
}
```

Response

```json
{
    "jsonrpc": "2.0",
    "id": "resource-1",
    "result": {
        "resources": [
            {
                "name": "get_geometry_formulas",
                "uri": "math://formulas/geometry",
                "description": "Geometry formulas reference for all types"
            }
        ]
    }
}
```

### List Resource Templates

Request

```json
{
    "jsonrpc": "2.0",
    "id": "resource-2",
    "method": "resources/templates/list",
    "params": {}
}
```

Response

```json
{
    "jsonrpc": "2.0",
    "id": "resource-2",
    "result": {
        "resourceTemplates": [
            {
                "name": "get_geometry_formula",
                "uriTemplate": "math://formulas/geometry/{formula_type}",
                "description": "Get a geometry formula by type (Area, Volume, etc.)"
            }
        ]
    }
}
```

### Read Resource

Request

```json
{
    "jsonrpc": "2.0",
    "id": "resource-3",
    "method": "resources/read",
    "params": {
        "uri": "math://formulas/geometry"
    }
}
```

Response

```json
{
    "jsonrpc": "2.0",
    "id": "resource-3",
    "result": {
        "contents": [
            {
                "uri": "math://formulas/geometry",
                "mimeType": "text/plain",
                "text": "{\n  \"Area\": {\n    \"rectangle\": \"A = length * width\",\n    \"triangle\": \"A = (1/2) * base * height\",\n    \"circle\": \"A = πr²\",\n    \"trapezoid\": \"A = (1/2)(b₁ + b₂)h\"\n  },\n  \"Volume\": {\n    \"cube\": \"V = s³\",\n    \"rectangular_prism\": \"V = length * width * height\",\n    \"cylinder\": \"V = πr²h\",\n    \"sphere\": \"V = (4/3)πr³\"\n  }\n}"
            }
        ]
    }
}
```

### Read Resource Template

Request

```json
{
    "jsonrpc": "2.0",
    "id": "resource-4",
    "method": "resources/read",
    "params": {
        "uri": "math://formulas/geometry/Volume"
    }
}
```

Response

```json
{
    "jsonrpc": "2.0",
    "id": "resource-4",
    "result": {
        "contents": [
            {
                "uri": "math://formulas/geometry/Volume",
                "mimeType": "text/plain",
                "text": "{\n  \"cube\": \"V = s³\",\n  \"rectangular_prism\": \"V = length * width * height\",\n  \"cylinder\": \"V = πr²h\",\n  \"sphere\": \"V = (4/3)πr³\"\n}"
            }
        ]
    }
}
```
