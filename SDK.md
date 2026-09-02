# flopkit SDK

The Python SDK and MCP server live in [`sdk/`](sdk/). The introductory website remains in [`client/`](client/).

## Lightweight runtime install

From the repository root:

```bash
cd sdk
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
flopkit --help
```

This installs only the runtime dependencies required by the SDK and CLI.

## Optional MCP install

Install MCP support only when you need to launch the local MCP server:

```bash
python -m pip install -e '.[mcp]'
python -m flopkit.mcp_server
```

## Full development checks

Contributors can install the complete development toolchain:

```bash
python -m pip install -e '.[dev]'
pytest --cov --cov-fail-under=90
ruff check .
mypy .
mkdocs build --strict
```

See the [SDK Quickstart](sdk/docs/quickstart.md), [Security notes](sdk/docs/security.md), and [MCP setup](sdk/docs/mcp.md) for the full guides.
