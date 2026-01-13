"""
A dummy issue tracker MCP server.
It provides tools to create, read, and delete issues.
"""

import time

from pydantic import BaseModel

from minimcp import HTTPTransport, MiniMCP

# --- Schemas ---


class Issue(BaseModel):
    id: str
    title: str
    description: str
    owner_user_name: str
    created_at: int


# MiniMCP provides a powerful scope object mechanism. Its generic and can be typed by the user. It can be used
# to pass any type of extra information to the handler functions. In this example, we use it to pass the current
# user name to the handler functions.
class Scope(BaseModel):
    user_name: str


# --- MCP ---

mcp = MiniMCP[Scope](
    name="IssueTrackerMCP",
    version="0.1.0",
    instructions="An issue tracker MCP server that provides tools to create, read and delete issues.",
)
mcp_transport = HTTPTransport(mcp)

issues: dict[str, Issue] = {}


@mcp.tool()
def create_issue(title: str, description: str) -> Issue:
    # Get the current user id from the scope
    current_user_name = mcp.context.get_scope().user_name

    # Create a new issue
    id = f"MCP-{len(issues) + 1}"
    new_issue = Issue(
        id=id,
        title=title,
        description=description,
        owner_user_name=current_user_name,
        created_at=int(time.time()),
    )
    issues[id] = new_issue

    return new_issue


@mcp.tool()
def read_issue(issue_id: str) -> Issue:
    if issue_id not in issues:
        raise ValueError(f"Issue {issue_id} not found")

    return issues[issue_id]


@mcp.tool()
def delete_issue(issue_id: str) -> str:
    if issue_id not in issues:
        raise ValueError(f"Issue {issue_id} not found")

    # User check - Only the owner of the issue can delete it
    current_user_name = mcp.context.get_scope().user_name
    if issues[issue_id].owner_user_name != current_user_name:
        raise ValueError(f"You are not the owner of issue {issue_id}")

    # Delete the issue
    del issues[issue_id]

    return "Issue deleted successfully"
