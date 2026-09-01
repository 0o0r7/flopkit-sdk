# flopkit monorepo

This repository contains the flopkit developer website and the original Python SDK.

- `client/` — React/Vite website for flopkit.
- `sdk/` — secure Python SDK and MCP server for Technocore.

## Run the website

```bash
pnpm install
pnpm dev
```

## Run the SDK

```bash
cd sdk
python -m pip install -e '.[dev]'
pytest
```

See [`SDK.md`](SDK.md) for the SDK verification commands and [`sdk/README.md`](sdk/README.md) for SDK usage.
