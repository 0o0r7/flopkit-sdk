# flopkit documentation

`flopkit` is a small, security-first Python SDK for the Flop Network Technocore layer. It gives applications and AI agents a local Ed25519 identity, signed protocol requests, an append-only contribution ledger, and public proofs that can be verified without access to the private key.

## Choose a path

| You want to… | Read |
|---|---|
| Install the SDK and create your first identity | [Quickstart](quickstart.md) |
| Protect identities, passphrases, and proof files | [Security notes](security.md) |
| Connect an MCP-compatible agent client | [MCP setup](mcp.md) |
| Review reproducible local execution evidence | [Performance evidence](evidence.md) |

The default installation contains only runtime dependencies. MCP and the contributor toolchain are optional, so users do not need to download the full development stack merely to run the SDK.

> **Trust boundary:** Share a public DID or a verified public proof when appropriate. Keep the encrypted identity file, its passphrase, private keys, tokens, and sensitive ledger data local.
