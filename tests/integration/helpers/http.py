import anyio
import httpx


async def url_available(url: str) -> bool:
    """Check if a URL is available (server is responding).

    Returns True if the server responds with any status code (including 405 Method Not Allowed),
    which indicates the server is running. Returns False only on connection errors.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            await client.get(url, timeout=2.0)
            # Any response (including 405, 404, etc.) means the server is running
            return True
    except Exception:
        # Connection refused, timeout, etc. - server not available
        return False


async def until_available(url: str, max_attempts: int = 60, sleep_interval: float = 0.5) -> None:
    """Wait for a URL to become available.

    Default timeout is 30 seconds (60 attempts * 0.5 seconds).
    This gives the server enough time to start even under heavy system load.
    """
    for _ in range(max_attempts):
        if await url_available(url):
            return None
        await anyio.sleep(sleep_interval)

    raise RuntimeError(f"URL {url} is not available after {max_attempts * sleep_interval} seconds")
