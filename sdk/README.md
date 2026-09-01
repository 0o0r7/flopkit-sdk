# flopkit

`flopkit` is a security-first Python SDK and MCP server for the experimental Flop Network Technocore layer.

## Quickstart

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
flopkit generate-identity
```

Private keys are stored only as passphrase-encrypted PEM files. Passphrases are prompted interactively by the CLI and are never accepted as command-line arguments. The package intentionally does not implement seed phrases, multi-wallet support, key rotation, or production-network calls.

## Development

```bash
ruff check .
mypy src
pytest
mkdocs build --strict
```

The Technocore endpoint paths and base URL are centralized in `flopkit.config.TechnocoreConfig` and can be overridden with environment variables.

## License

MIT.
