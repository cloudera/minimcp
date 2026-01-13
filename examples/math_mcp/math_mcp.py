"""
A simple MCP server for mathematical operations.
"""

from typing import Any

import anyio
from pydantic import Field

from minimcp import MiniMCP

math_mcp = MiniMCP[Any](
    name="MathServer", version="0.1.0", instructions="This is a simple MCP server for mathematical operations."
)


# -- Prompts --
@math_mcp.prompt()
def problem_solving(problem_description: str = Field(description="Description of the problem to solve")) -> str:
    "General prompt to systematically solve math problems."

    return f"""You are a math problem solver.
Solve the following problem step by step and provide the final simplified answer.

Problem: {problem_description}

Output:
1. Step-by-step reasoning
2. Final answer in simplest form
"""


# -- Resources --
GEOMETRY_FORMULAS = {
    "Area": {
        "rectangle": "A = length * width",
        "triangle": "A = (1/2) * base * height",
        "circle": "A = πr²",
        "trapezoid": "A = (1/2)(b₁ + b₂)h",
    },
    "Volume": {
        "cube": "V = s³",
        "rectangular_prism": "V = length * width * height",
        "cylinder": "V = πr²h",
        "sphere": "V = (4/3)πr³",
    },
}


@math_mcp.resource("math://formulas/geometry")
def get_geometry_formulas() -> dict[str, dict[str, str]]:
    """Geometry formulas reference for all types"""
    return GEOMETRY_FORMULAS


@math_mcp.resource("math://formulas/geometry/{formula_type}")
def get_geometry_formula(formula_type: str) -> dict[str, str]:
    "Get a geometry formula by type (Area, Volume, etc.)"
    if formula_type not in GEOMETRY_FORMULAS:
        raise ValueError(f"Invalid formula type: {formula_type}")
    return GEOMETRY_FORMULAS[formula_type]


# -- Tools --
@math_mcp.tool()
def add(
    a: float = Field(description="The first float number"), b: float = Field(description="The second float number")
) -> float:
    "Add two numbers"
    return a + b


@math_mcp.tool(description="Add two numbers with progress reporting")
async def add_with_progress(
    a: float = Field(description="The first float number"), b: float = Field(description="The second float number")
) -> float:
    responder = math_mcp.context.get_responder()
    await responder.report_progress(0.1, message="Adding numbers")
    await anyio.sleep(1)
    await responder.report_progress(0.4, message="Adding numbers")
    await anyio.sleep(1)
    await responder.report_progress(0.7, message="Adding numbers")
    await anyio.sleep(1)
    return a + b


@math_mcp.tool(description="Subtract two numbers")
def subtract(
    a: float = Field(description="The first float number"), b: float = Field(description="The second float number")
) -> float:
    return a - b


@math_mcp.tool(name="multiply")  # Different name from function name
def product(
    a: float = Field(description="The first float number"), b: float = Field(description="The second float number")
) -> float:
    "Multiply two numbers"

    return a * b


@math_mcp.tool(description="Divide two numbers")
def divide(
    a: float = Field(description="The first float number"), b: float = Field(description="The second float number")
) -> float:
    return a / b
