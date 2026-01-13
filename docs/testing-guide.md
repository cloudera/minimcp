# MiniMCP Testing Guide

## Overview

The MiniMCP test suite contains **645 tests** ensuring reliability and MCP specification compliance.

- **Unit Tests**: 514 (80%)
- **Integration Tests**: 131 (20%)

## Test Structure

```text
tests/
├── unit/                          # Component-level tests
│   ├── managers/                  # Tool, Resource, Prompt, Context managers
│   ├── transports/                # HTTP, Streamable HTTP, Stdio transports
│   ├── utils/                     # JSON-RPC, function wrappers
│   ├── test_minimcp.py            # Core MiniMCP class
│   ├── test_responder.py          # Response building
│   └── test_limiter.py            # Rate limiting
│
└── integration/                   # End-to-end tests
    ├── test_http_server.py
    ├── test_streamable_http_server.py
    └── test_stdio_server.py
```

## Key Test Coverage

### Core Components

- **MiniMCP Core** (50 tests): Server initialization, message handling, lifecycle management, protocol negotiation
- **JSON-RPC Protocol** (41 tests): JSON-RPC 2.0 compliance, error codes, message validation
- **Responder** (35 tests): Response building, error handling, progress notifications
- **Rate Limiting** (39 tests): Timeout enforcement, concurrent request limiting

### Managers

- **Tool Manager** (46 tests): Tool registration/execution, schema generation, Pydantic validation
- **Resource Manager** (63 tests): Static/dynamic resources, URI templates, subscriptions
- **Prompt Manager** (51 tests): Prompt registration/execution, argument schemas
- **Context Manager** (17 tests): Context lifecycle, state isolation

### Transports

- **HTTP Transport** (39 tests): POST handling, header validation, error responses
- **Streamable HTTP** (43 tests): SSE support, stream lifecycle, concurrent handling
- **Stdio Transport** (15 tests): Line-based messaging, newline compliance
- **Base HTTP** (22 tests): Core HTTP functionality, protocol version validation

### Utilities

- **MCP Function Wrapper** (53 tests): Function wrapping, schema generation, type hints, Pydantic support

### Integration Tests

- **HTTP Server** (39 tests): Full server lifecycle with real MCP client
- **Streamable HTTP Server** (55 tests): SSE streaming, progress notifications
- **Stdio Server** (37 tests): Process-based communication, graceful shutdown

## Running Tests

### Basic Commands

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=minimcp --cov-report=html

# Unit tests only
uv run pytest tests/unit/

# Integration tests only
uv run pytest tests/integration/

# Specific component
uv run pytest tests/unit/test_minimcp.py
```

### Test Options

```bash
# Verbose output
uv run pytest -v

# Show print statements
uv run pytest -s

# Stop on first failure
uv run pytest -x

# Run only failed tests
uv run pytest --lf

# Specific test class/method
uv run pytest tests/unit/test_minimcp.py::TestMiniMCP::test_init_creates_minimcp_instance
```

## MCP Specification Compliance

The test suite validates:

- ✅ Protocol negotiation and version checking
- ✅ JSON-RPC 2.0 message format
- ✅ Transport protocols (HTTP, Streamable HTTP, Stdio)
- ✅ Lifecycle management (initialize, ping, shutdown)
- ✅ MCP primitives (Tools, Resources, Prompts)
- ✅ Error codes and handling
- ✅ Pagination and subscriptions

## Contributing Tests

When adding new features, include:

1. **Unit tests** for component logic
2. **Integration tests** for end-to-end scenarios (if applicable)
3. **Edge case coverage** for error conditions
4. **Type hints** for all test code

### Test Template

```python
import pytest

pytestmark = pytest.mark.anyio


class TestMyFeature:
    """Test suite for MyFeature class."""

    @pytest.fixture
    def my_fixture(self):
        """Create a test fixture."""
        return MyObject()

    async def test_feature_success(self, my_fixture):
        """Test successful feature execution."""
        result = await my_fixture.do_something()
        assert result == expected_value

    async def test_feature_error_handling(self, my_fixture):
        """Test error handling in feature."""
        with pytest.raises(ExpectedError):
            await my_fixture.do_invalid_thing()
```

## Test Dependencies

- `pytest` - Test framework
- `pytest-cov` - Coverage reporting

---

_Last updated: January 13, 2026_
