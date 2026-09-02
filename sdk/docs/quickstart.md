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

For a first signed call against a local mock, configure the endpoint through the centralized settings:

```python
from flopkit.identity import load_identity
from flopkit.technocore import TechnocoreClient

key = load_identity("identity.pem", input_passphrase)
with TechnocoreClient(key) as client:
    client.publish_did()
    client.check_in()
```

The client uses GET requests, signs the canonical query payload, and sends the DID and signature in configurable headers. Before any real call, confirm the endpoint paths and base URL against the live Technocore documentation.
