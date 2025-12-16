# Contributing to MiniMCP

Thank you for your interest in supporting the MiniMCP project! This document outlines the guidelines and instructions for making contributions.

## Development Setup

1. Make sure you have Python 3.10+ installed
2. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
3. Fork the repository
4. Clone your fork
5. Install dependencies:

```bash
uv sync --frozen --all-extras --dev
```

6. Sets up the Git hook so it runs automatically on each git commit

```bash
uv run pre-commit install
```

## Development Workflow

1. In your fork, create a new branch from main or your chosen base branch.
2. Make your changes
3. Ensure tests pass:

```bash
# Run both unit and integration tests
uv run pytest
```

4. Run type checking:

```bash
uv run pyright
```

5. Run linting:

```bash
uv run ruff check .
```

Fix and format

```bash
uv run ruff check . --fix
uv run ruff format .
```

6. Update README if you modified example code:
7. (Optional) Run pre-commit hooks on all files:

```bash
uv run pre-commit run --all-files
```

8. Submit a pull request to the same branch you branched from

### Code Style

- We use `ruff` for linting and formatting
- Follow PEP 8 style guidelines
- Add type hints to all functions
- Include docstrings for public APIs

## Build & Publish

```bash
rm -rf dist
uv run -m build
uv run twine check dist/*
uv run twine upload dist/*
```

## Validate pyproject.toml

To validate changes after manually editing pyproject.toml, run:

```bash
uvx --from 'validate-pyproject[all]' validate-pyproject pyproject.toml
```

## License

By contributing, you agree that your contributions will be licensed under [Apache License, Version 2.0](https://github.com/cloudera/minimcp/blob/main/LICENSE)
