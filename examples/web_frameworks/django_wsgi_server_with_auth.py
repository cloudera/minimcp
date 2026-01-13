#!/usr/bin/env python3

"""
Django WSGI HTTP MCP Server with Basic Authentication
This example demonstrates how to create a minimal MCP server with Django using HTTP transport. It shows
how to interface MiniMCP with Django, and shows how to use scope to pass authenticated user details that
can be accessed inside the handler functions.

MiniMCP provides a powerful scope object mechanism that can be used to pass any type of extra information
to be used in the handler functions.

How to run:
    # Start the server (default: http://127.0.0.1:8000)
    uv run --with django --with djangorestframework \
        python examples/minimcp/web_frameworks/django_wsgi_server_with_auth.py runserver
"""

from collections.abc import Mapping
from http import HTTPStatus
from typing import cast

import django  # pyright: ignore[reportMissingImports]
from django.conf import settings  # pyright: ignore[reportMissingImports]
from django.core.management import execute_from_command_line  # pyright: ignore[reportMissingImports]
from django.http import HttpRequest, HttpResponse  # pyright: ignore[reportMissingImports]
from django.urls import path  # pyright: ignore[reportMissingImports]
from rest_framework.authentication import BasicAuthentication  # pyright: ignore[reportMissingImports]
from rest_framework.exceptions import AuthenticationFailed  # pyright: ignore[reportMissingImports]

from minimcp.types import MESSAGE_ENCODING

from .issue_tracker_mcp import Scope, mcp_transport

# --- Minimal Django Setup ---
settings.configure(
    SECRET_KEY="dev",
    ROOT_URLCONF=__name__,
    ALLOWED_HOSTS=["*"],
    MIDDLEWARE=["django.middleware.common.CommonMiddleware"],
    INSTALLED_APPS=["rest_framework"],
)

django.setup()


class DemoAuth(BasicAuthentication):
    """Basic authentication that extracts username."""

    def authenticate_credentials(self, userid, password, request=None):
        return (userid, None)

    def get_username(self, request: HttpRequest) -> str | None:
        try:
            auth_result = self.authenticate(request)
            if auth_result:
                return auth_result[0]
        except AuthenticationFailed:
            return None


# --- MCP View ---
async def mcp_view(request: HttpRequest) -> HttpResponse:
    """Handle MCP requests with scope containing authenticated user."""

    username = DemoAuth().get_username(request)
    if not username:
        return HttpResponse(b"Authentication required", status=HTTPStatus.UNAUTHORIZED)

    # Prepare request for MCP transport
    body_str = request.body.decode(MESSAGE_ENCODING) if request.body else ""
    headers = cast(Mapping[str, str], request.headers)
    method = request.method or "POST"

    # Dispatch to MCP transport
    scope = Scope(user_name=username)
    response = await mcp_transport.dispatch(method, headers=headers, body=body_str, scope=scope)

    # Prepare response for Django
    content = response.content.encode(MESSAGE_ENCODING) if response.content else b""
    return HttpResponse(content, status=response.status_code, headers=response.headers)


# --- Start Server ---
urlpatterns = [
    path("mcp", mcp_view),
]

if __name__ == "__main__":
    execute_from_command_line()
