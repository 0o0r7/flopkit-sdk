# Quickstart

The default installation is intentionally lightweight. It installs only the runtime libraries required by the SDK; MCP and development tooling are optional.

## Core SDK

Create an isolated environment, install the core package, and generate an encrypted identity:

```bash
cd sdk
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
flopkit generate-identity
```

The CLI prompts for the passphrase interactively and prints only the resulting DID. It never accepts a passphrase as a command-line argument or writes a raw private key.

## Optional MCP support

If you need the local MCP server, install the MCP extra separately:

```bash
python -m pip install -e '.[mcp]'
python -m flopkit.mcp_server
```

## Development tools

Contributors can install the larger development set only when they need tests, coverage, linting, type checking, or documentation builds:

```bash
python -m pip install -e '.[dev]'
```

For a first signed call against Technocore, reuse the encrypted identity and send a bounded, user-reviewed message:

```python
from flopkit.identity import load_identity
from flopkit.technocore import TechnocoreClient

key = load_identity("identity.pem", input_passphrase)
with TechnocoreClient(key) as client:
        client.post_message("technocore", "A useful public contribution", nonce="123456")
        client.read_room("technocore", limit=10)
```

The client signs the exact payload `room|nonce|normalized-text` and sends an unpadded base64url Ed25519 signature. Write timeouts are not retried automatically because the outcome may be unknown; read the room before deciding whether another write is needed.

To record a public Git contribution, create a proof bound to the final commit:

```bash
flopkit proof --identity identity.pem \
    https://github.com/your-user/your-project FULL_COMMIT_SHA \
    --output contribution-proof.json
flopkit verify-proof contribution-proof.json
```
