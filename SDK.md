# SDK maintenance guide

This repository contains one product: the Python SDK, CLI, and optional MCP server under [`sdk/`](sdk/). All source, tests, and documentation are organized around that product.

## Lightweight runtime install

From the repository root:

```bash
cd sdk
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
flopkit --help
```

This installs only the runtime dependencies needed by the SDK and CLI.

## Optional MCP install

Install MCP support only when a local MCP server is required:

```bash
python -m pip install -e '.[mcp]'
python -m flopkit.mcp_server
```

## Full development checks

Contributors can install the complete quality toolchain:

```bash
python -m pip install -e '.[dev]'
ruff check .
mypy .
pytest --cov --cov-fail-under=90
mkdocs build --strict
```

The user-facing guides are [Quickstart](sdk/docs/quickstart.md), [Security notes](sdk/docs/security.md), [MCP setup](sdk/docs/mcp.md), and [Performance evidence](sdk/docs/evidence.md).

## Design constraints

Keep runtime dependencies separate from contributor tooling. Do not add secrets, identity files, passphrases, seed phrases, or generated runtime ledgers to the repository. Protocol changes must include mock-transport tests and preserve the rule that ambiguous signed writes are not retried automatically.
