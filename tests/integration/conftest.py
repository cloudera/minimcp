"""
Shared fixtures for MCP integration tests.
"""

from collections.abc import AsyncGenerator

import anyio
import pytest
import servers.http_server as http_test_server
from helpers.http import until_available, url_available
from helpers.process import run_module
from servers.http_server import SERVER_HOST, SERVER_PORT

pytestmark = pytest.mark.anyio

BASE_URL: str = f"http://{SERVER_HOST}:{SERVER_PORT}"


def pytest_configure(config: pytest.Config) -> None:
    use_existing_minimcp_server = config.getoption("--use-existing-minimcp-server")
    server_is_running = anyio.run(url_available, BASE_URL)

    if server_is_running and not use_existing_minimcp_server:
        raise RuntimeError(
            f"Server is already running at {BASE_URL}. "
            "Run pytest with the --use-existing-minimcp-server option to use it."
        )


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def http_test_server_process() -> AsyncGenerator[None, None]:
    """
    Session-scoped fixture that starts the HTTP test server once across all workers.

    With pytest-xdist, multiple workers may call this fixture. The first worker starts the server,
    and subsequent workers detect and reuse it.
    """

    if await url_available(BASE_URL):
        # Server is available, use that.
        yield None
    else:
        try:
            async with run_module(http_test_server):
                await until_available(BASE_URL)
                yield None
                await anyio.sleep(1)  # Wait a bit for safe shutdown
        except Exception:
            # If server started between our check and start attempt, that's OK
            # Another worker got there first
            yield None
