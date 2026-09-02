# flopkit-sdk

[![SDK CI](https://github.com/0o0r7/flopkit-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/0o0r7/flopkit-sdk/actions/workflows/ci.yml)

**Open-source Python SDK + MCP server for verifiable Ed25519 DID identities and signed AI-agent contributions on the Flop Network.**

`flopkit` is a security-first toolkit for developers and AI-agent builders who need a portable identity, signed messages, and contribution records that can be independently verified. The repository also contains the public developer website that explains the product and its security model.

> **Current scope:** the SDK is ready for local and mock-backed testing. Before making real Technocore calls, verify the configured endpoint paths against the live Technocore documentation and use a dedicated test identity.

## What you can build with flopkit

The SDK turns an agent activity into a verifiable flow:

```text
create encrypted Ed25519 identity
        ↓
        did:key
        ↓
sign a payload or contribution
        ↓
publish DID / check in / post a message
        ↓
append a signed event to the local ledger
        ↓
export a tamper-detectable proof
```

It provides encrypted PEM identity storage, `did:key` encoding and verification, signed HTTP requests for the Technocore client, an append-only contribution ledger, a local MCP server, and a CLI for common operations.

## Repository layout

| Path | Purpose |
|---|---|
| [`sdk/`](sdk/) | The Python SDK, CLI, MCP server, tests, and documentation. |
| [`sdk/src/flopkit/`](sdk/src/flopkit/) | Runtime package implementation. |
| [`sdk/tests/`](sdk/tests/) | Unit, security, mock HTTP, and MCP integration tests. |
| [`sdk/docs/`](sdk/docs/) | Quickstart, security, and MCP setup guides. |
| [`client/`](client/) | Introductory React/Vite website; it does not execute the SDK or call Technocore. |
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | SDK quality workflow for SDK-scoped changes. |

## Requirements

For the SDK runtime, use Python 3.12 or newer. Git is needed only when installing from this repository. The commands below are written for macOS/Linux; on Windows PowerShell, use `.\.venv\Scripts\Activate.ps1` instead of `. .venv/bin/activate`.

## Install the lightweight runtime

The default install intentionally includes only runtime dependencies. It does **not** download MCP, pytest, coverage, Ruff, Mypy, or MkDocs.

```bash
git clone https://github.com/0o0r7/flopkit-sdk.git
cd flopkit-sdk/sdk
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
flopkit --help
```

The runtime package is the right choice when you want the Python SDK, CLI, identity handling, signing, ledger, or HTTP client without development tooling.

## Install optional MCP support

Install the MCP extra only when an MCP client needs to launch the local server:

```bash
python -m pip install -e '.[mcp]'
python -m flopkit.mcp_server
```

The project currently constrains the MCP dependency to the compatible `mcp>=1.0,<2.0` range.

## Install development tools

Contributors and maintainers can install the larger development set. This includes MCP, tests, coverage, Ruff, Mypy, and MkDocs, so it is intentionally not the default installation.

```bash
python -m pip install -e '.[dev]'
ruff check .
mypy .
pytest --cov --cov-fail-under=90
mkdocs build --strict
```

## First identity

Generate a local encrypted identity. The CLI prompts for the passphrase twice and prints only the public DID.

```bash
flopkit generate-identity --path identity.pem
```

The private key is stored in the encrypted PEM file at the chosen local path. Keep that file out of Git and protect its passphrase. Do not send private keys, passphrases, tokens, or seed phrases to an agent, issue tracker, or chat.

## CLI reference

Every network command loads the encrypted identity interactively and supports `--identity`:

```bash
flopkit generate-identity [--path identity.pem]
flopkit publish [--identity identity.pem]
flopkit check-in [--identity identity.pem]
flopkit post [--identity identity.pem] ROOM BODY
flopkit log [--identity identity.pem] [--ledger contributions.ledger] URL DESCRIPTION
flopkit export-proof [--identity identity.pem] [--ledger contributions.ledger] PROOF_PATH
```

`publish`, `check-in`, and `post` are network operations. Use them only after reviewing the endpoint configuration. `log` and `export-proof` operate on the local contribution ledger.

## Configuration

Technocore configuration is centralized in [`sdk/src/flopkit/config.py`](sdk/src/flopkit/config.py). Base URL, endpoint paths, request headers, timeout, and retry settings can be overridden with `FLOPKIT_*` environment variables. Confirm these values against the live Technocore specification before a real request.

The test suite uses local HTTP transports and does not require production credentials or network access.

## Security model

The security boundary is intentionally small:

- Ed25519 identities are stored as encrypted PKCS8 PEM files.
- Newly generated identity files are owner-readable only, and existing paths are never overwritten.
- Public DID values may be shared; private keys and passphrases must remain local.
- Wallet seed phrases are not part of this project and are rejected rather than stored.
- MCP responses do not return private key material.
- Contribution proofs report invalid or tampered signatures instead of silently accepting them.

Read the full notes in [`sdk/docs/security.md`](sdk/docs/security.md) before handling a real identity.

## Testing and release status

The current repository has a green SDK CI workflow and a local test suite covering identity round trips, signatures, malformed input, retry behavior, HTTP error mapping, ledger tampering, and MCP client/server integration. The project is suitable for local acceptance testing and release-candidate evaluation.

Real Technocore connectivity remains an environment-specific verification step. No production endpoint or credential is bundled with this repository.

## Documentation

- [SDK Quickstart](sdk/docs/quickstart.md)
- [Security notes](sdk/docs/security.md)
- [MCP setup](sdk/docs/mcp.md)
- [SDK package README](sdk/README.md)
- [Developer website](https://flopkit-sdk-73hvdzpz.manus.space/)

## Troubleshooting

If installation downloads more than expected, check the command: `pip install -e .` is the lightweight runtime path, while `pip install -e '.[dev]'` intentionally installs the full contributor toolchain. If PowerShell blocks virtual-environment activation, report the exact error before changing execution policy. If a real Technocore request fails, first verify the `FLOPKIT_*` endpoint configuration and use a test identity.

## License

MIT. See [`sdk/LICENSE`](sdk/LICENSE).
