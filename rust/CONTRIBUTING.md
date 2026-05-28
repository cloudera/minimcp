# Contributing to MiniMCP (Rust)

This document covers the Rust workspace under `rust/`. For the Python package, see the [top-level CONTRIBUTING.md](../CONTRIBUTING.md).

The Rust checks mirror the Python ones:

| Python | Rust |
|---|---|
| `ruff format` | `cargo fmt` |
| `ruff check` | `cargo clippy` |
| `pytest` | `cargo test` |

## Development Setup

1. Install [rustup](https://rustup.rs/). The toolchain and required components
   (`rustfmt`, `clippy`) are pinned in `rust-toolchain.toml`, so rustup installs
   them automatically the first time you run a cargo command in this directory.
2. Fork and clone the repository.
3. Build the workspace:

```bash
cd rust
cargo build
```

## Development Workflow

All commands are run from the `rust/` directory.

1. Create a branch from your chosen base branch.
2. Make your changes.
3. Run the tests:

```bash
cargo test
```

4. Format the code (and verify formatting):

```bash
cargo fmt           # apply formatting
cargo fmt --check   # verify only (used by the hook and CI)
```

5. Run the linter. Warnings are treated as errors to match the pre-commit hook:

```bash
cargo clippy --all-targets -- -D warnings
```

6. Build only the stdio transport (no HTTP / axum) when relevant:

```bash
cargo build -p minimcp --no-default-features
```

7. Submit a pull request to the branch you based your work on.

## Pre-commit Hooks

The Rust hooks live in `rust/.pre-commit-config.yaml`, kept separate from the
repository-root `.pre-commit-config.yaml` so the Python and Rust toolchains stay
decoupled. They run `cargo fmt --check`, `cargo clippy -D warnings`, and
`cargo test` whenever staged `.rs` files change.

Run them on demand (from the repository root):

```bash
pre-commit run --all-files --config rust/.pre-commit-config.yaml
```

To run them automatically on each commit, install them as the git hook:

```bash
pre-commit install --config rust/.pre-commit-config.yaml
```

> Caveat: `pre-commit install` writes a single `.git/hooks/pre-commit` script, so
> installing this config replaces the one from the repository-root config (and
> vice versa). If you work on both the Python and Rust sides and want both
> enforced automatically, run the Rust hooks manually with the
> `pre-commit run --config rust/.pre-commit-config.yaml` command above, or wire
> both configs into a single hook of your choosing.

[pre-commit](https://pre-commit.com/) itself is a Python tool; it is already
available via the Python dev environment (`uv run pre-commit ...`) or any global
install.

## Continuous Integration

The same three checks run in CI on every pull request that touches `rust/`, via
`.github/workflows/rust.yml` (`cargo fmt --check`, `cargo clippy -D warnings`,
`cargo test`). Running the pre-commit hooks locally keeps you green in CI.

## Code Style

- Format with `cargo fmt` (rustfmt defaults).
- Keep `cargo clippy --all-targets` warning-free.
- Document public modules, types, and functions with `///` doc comments.

## License

By contributing, you agree that your contributions will be licensed under [Apache License, Version 2.0](https://github.com/cloudera/minimcp/blob/main/LICENSE).
