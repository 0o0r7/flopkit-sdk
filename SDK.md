# flopkit Python SDK

The original secure Python SDK and MCP server now live in [`sdk/`](sdk/). The website remains in [`client/`](client/).

From the repository root, run the SDK checks with:

```bash
cd sdk
python -m pip install -e '.[dev]'
pytest
ruff check .
mypy src
mkdocs build --strict
```
