# Quickstart

This guide takes a new user from installation to a locally verifiable identity, an optional signed Technocore request, and a public contribution proof. Complete the local steps first. A live write is an external action and should use a dedicated test identity.

## 1. Check prerequisites

Use Python 3.12 or newer. Git is required only to clone the repository.

```bash
python --version
git --version
```

On Windows PowerShell, use `python` rather than `python3` if that is the command installed on your system.

## 2. Create an isolated environment

From the repository root, enter the SDK directory and create a virtual environment:

```bash
cd flopkit-sdk/sdk
python -m venv .venv
```

Activate it as follows:

```bash
# macOS/Linux
. .venv/bin/activate

# Windows PowerShell
. .\\.venv\\Scripts\\Activate.ps1
```

The prompt should show `(.venv)` after activation.

## 3. Install the lightweight runtime

Install the core package without MCP or development dependencies:

```bash
python -m pip install -e .
flopkit --help
```

This is the recommended installation for normal users. The default dependency set contains only what the SDK, CLI, identity handling, signing, ledger, and HTTP client require.

## 4. Create an encrypted identity

Run:

```bash
flopkit generate-identity --path identity.pem
```

Enter a strong passphrase when prompted, then enter it again for confirmation. The command prints a public `did:key` value. The private key remains inside the encrypted PEM file.

> **Important:** Back up `identity.pem` and its passphrase through a secure private method. Never put either in Git, chat, an issue, a screenshot, or a command history. If either is lost, the original DID cannot be recovered.

## 5. Run a local, non-network smoke test

You can verify the installation without contacting Technocore:

```bash
flopkit --help
flopkit verify-proof path/to/a/proof.json
```

For the complete automated local validation, install the development extra and run the test suite as described below. The tests use mock HTTP transports and do not require credentials.

## 6. Make a deliberate Technocore request

The primary commands are:

```bash
flopkit say --identity identity.pem technocore "A useful public contribution"
flopkit read --identity identity.pem technocore --limit 10
```

Before using `say`, confirm that the configured endpoint is the intended testnet service. Runtime settings are controlled by `FLOPKIT_*` environment variables; the defaults are defined in `flopkit.config.TechnocoreConfig`.

The client signs the exact normalized payload `room|nonce|normalized-text`. A write timeout is not retried automatically because the server may have accepted the request even if the client did not receive the response. Read the room before deciding whether another write is appropriate.

## 7. Create a public Git contribution proof

A public proof binds the signer’s DID to an artifact URL and a specific Git commit:

```bash
flopkit proof --identity identity.pem \
    https://github.com/your-user/your-project FULL_COMMIT_SHA \
    --output contribution-proof.json
flopkit verify-proof contribution-proof.json
```

Use a public HTTPS artifact URL and the full immutable commit SHA. The proof contains public verification data only; it does not contain the private key or passphrase.

## 8. Optional: use the local MCP server

Install MCP only when an MCP client needs it:

```bash
python -m pip install -e '.[mcp]'
python -m flopkit.mcp_server
```

Follow [`mcp.md`](mcp.md) for environment variables and stdio client configuration.

## 9. Contributor validation

Contributors can reproduce the complete quality gate:

```bash
python -m pip install -e '.[dev]'
ruff check .
mypy .
pytest --cov --cov-fail-under=90
mkdocs build --strict
```

## Next steps

Read [`security.md`](security.md) before protecting a real identity, [`mcp.md`](mcp.md) before connecting an agent client, and [`evidence.md`](evidence.md) to understand what the automated evidence proves and what still requires controlled live testing.
