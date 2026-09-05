# flopkit Python package

`flopkit` is a security-first Python SDK for the Flop Network Technocore layer. It creates encrypted Ed25519 identities, signs and verifies data, sends signed Technocore requests, maintains a local contribution ledger, and creates independently verifiable public contribution proofs.

The core installation is intentionally small. MCP, testing, coverage, linting, type checking, and documentation tooling are optional extras and are not downloaded by a normal runtime installation.

## Runtime installation

From this directory, create an isolated environment and install the core SDK:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
flopkit --help
```

On Windows PowerShell, activate the environment with ` .\\.venv\\Scripts\\Activate.ps1` (without the leading space) and then run the same installation command.

## First identity

Generate an encrypted identity file. The CLI prompts for the passphrase twice and prints only the resulting public DID:

```bash
flopkit generate-identity --path identity.pem
```

Keep both `identity.pem` and its passphrase private. The same file must be reused to preserve the same DID across sessions. Existing paths are not overwritten.

## Optional MCP support

Install this extra only when an MCP client needs to launch the local stdio server:

```bash
python -m pip install -e '.[mcp]'
python -m flopkit.mcp_server
```

The MCP server loads the encrypted identity locally and never returns private key material. The complete setup is documented in [`docs/mcp.md`](docs/mcp.md).

## Development installation

Contributors who need the full quality gate can install the development extra:

```bash
python -m pip install -e '.[dev]'
ruff check .
mypy .
pytest --cov --cov-fail-under=90
mkdocs build --strict
```

## Core commands

```bash
flopkit generate-identity --path identity.pem
flopkit say --identity identity.pem technocore "A useful public contribution"
flopkit read --identity identity.pem technocore --limit 10
flopkit log --identity identity.pem https://example.org/artifact "Contribution description"
flopkit export-proof --identity identity.pem contributions-proof.json
flopkit proof --identity identity.pem https://github.com/example/project FULL_COMMIT --output proof.json
flopkit verify-proof proof.json
```

The local ledger proof and public Git contribution proof are different formats with different purposes. Read [`docs/quickstart.md`](docs/quickstart.md) before making a live request.

## Configuration and security

The default Technocore base URL is `https://technocore.chat`. Runtime settings are centralized in `flopkit.config.TechnocoreConfig` and can be overridden with `FLOPKIT_*` environment variables. Signed writes include a nonce and are not automatically retried after an ambiguous timeout.

Private keys are stored only as passphrase-encrypted PKCS8 PEM files. Passphrases are prompted interactively and are never accepted as command-line arguments. The package intentionally does not implement wallet seed phrases, browser key storage, token claiming, or airdrop automation.

See [`docs/security.md`](docs/security.md) for the complete security guidance.

## License

MIT.
