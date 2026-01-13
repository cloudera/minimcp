import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--use-existing-minimcp-server",
        action="store_true",
        default=False,
        help="Use an already running MinimCP server if available.",
    )
