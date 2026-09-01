# Quickstart

Create an isolated environment, install the package, and generate an identity:

```bash
pip install -e '.[dev]'
flopkit generate-identity
```

Use the generated encrypted PEM with the SDK or configure `FLOPKIT_IDENTITY` and `FLOPKIT_PASSPHRASE` for the MCP server.
