# flopkit

`flopkit` is a security-first Python SDK for the experimental Flop Network Technocore layer. The core install is intentionally small: it includes only the libraries required to create encrypted Ed25519 identities, sign and verify data, maintain a contribution ledger, and use the HTTP client.

The MCP server is optional. Testing, linting, type checking, and documentation tooling are development-only extras and are not downloaded by a normal runtime installation.

## Runtime installation

Create an isolated environment and install only the core SDK:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
flopkit --help
```

## Optional MCP support

Install this extra only when you need to run `flopkit.mcp_server` or connect an MCP client:

```bash
python -m pip install -e '.[mcp]'
python -m flopkit.mcp_server
```

## Development installation

Contributors who need tests, coverage, linting, strict type checking, and documentation builds can install the complete development set:

```bash
python -m pip install -e '.[dev]'
ruff check .
mypy src
pytest
mkdocs build --strict
```

Private keys are stored only as passphrase-encrypted PEM files. Passphrases are prompted interactively by the CLI and are never accepted as command-line arguments. The package intentionally does not implement seed phrases, multi-wallet support, key rotation, or production-network calls.

The Technocore endpoint paths and base URL are centralized in `flopkit.config.TechnocoreConfig` and can be overridden with environment variables.

## License

MIT.
