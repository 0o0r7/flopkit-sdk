# FlopKit SDK maintenance guide

This repository contains one product: the FlopKit Python SDK, CLI, interactive wizard, and optional MCP server under [`sdk/`](sdk/). There is no web frontend or application backend in this repository. The documentation site is the repository preview surface.

## Documentation map

| Guide | Purpose |
|---|---|
| [Documentation home](sdk/docs/index.md) | Product overview and navigation |
| [Quickstart](sdk/docs/quickstart.md) | Installation and first safe workflow |
| [Interactive Wizard](sdk/docs/wizard.md) | Current menu structure and screenshots |
| [TCLK guide](sdk/docs/tclk-guide.md) | TCLK/1 deal-flow reference |
| [Security notes](sdk/docs/security.md) | Identity, passphrase, and proof handling |
| [MCP setup](sdk/docs/mcp.md) | Local stdio integration for MCP hosts |
| [Validation evidence](sdk/docs/evidence.md) | Reproducible local test evidence |
| [Package README](sdk/README.md) | Developer-facing package reference |

## Lightweight runtime installation

From the repository root:

```bash
cd sdk
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
flopkit --help
```

The runtime installation contains the dependencies required by the SDK and CLI. MCP, tests, linting, type checking, and documentation tooling are optional extras.

## Optional MCP installation

Install MCP support only when an MCP host needs to launch the local server:

```bash
python -m pip install -e '.[mcp]'
python -m flopkit.mcp_server
```

See [MCP setup](sdk/docs/mcp.md) for the required process environment.

## Full quality gate

From `sdk/`, install the contributor extra and run:

```bash
python -m pip install -e '.[dev]'
ruff check .
mypy .
pytest --cov --cov-fail-under=90
mkdocs build --strict
```

The tests use local mock transports. A live Technocore endpoint is not required for the local quality gate.

## Current product surfaces

The interactive wizard in `sdk/src/flopkit/wizard.py` is the authoritative source for the guided user flow. It currently exposes six top-level areas:

1. **Identity & DID** — encrypted Ed25519 identity creation, DID display, DID-note publication and resolution, delegation, verification, and revocation.
2. **Messaging** — signed room messages, JSON and text reads, and public event reads.
3. **TCLK Trading** — offer, accept, lock, reveal, refund, cancel, heartbeat, receipt, and deal-status operations.
4. **Discovery** — room listing, room minting, mailbox setup, and long polling.
5. **Contributions** — signed contribution logging, proof export, and proof verification.
6. **Exit** — safe wizard shutdown.

The standalone CLI in `sdk/src/flopkit/cli.py` additionally exposes notes, public proofs, TCLK operations, delegation commands, events, and room minting. See the [package reference](sdk/README.md) and the [wizard guide](sdk/docs/wizard.md) when changing either surface.

## Architecture contract

The repository should continue to preserve these boundaries:

- Runtime dependencies remain separate from contributor tooling.
- Private keys remain in passphrase-encrypted identity files.
- Existing identity paths are never silently overwritten.
- Signed writes use protocol nonces and are not automatically retried after ambiguous timeouts.
- Protocol changes include mock-transport tests.
- Documentation claims about commands and wizard menus are checked against `wizard.py`, `cli.py`, and `pyproject.toml` before release.

## Documentation maintenance rules

When a user-facing capability changes, update the source and documentation in the same change. At minimum, review the root README, `sdk/README.md`, `sdk/docs/quickstart.md`, `sdk/docs/wizard.md`, and `sdk/docs/evidence.md`.

Use the supplied logo at `sdk/docs/assets/flopkit-monochrome.webp` for documentation pages and preserve the repository’s visual language: dark navy surfaces, cyan technical accents, emerald verification accents, restrained amber highlights, concise headings, and readable command blocks.

Do not add identity files, passphrases, tokens, generated ledgers, or live network output to the repository. Screenshots must use disposable identities or redacted public data.
