# FlopKit documentation

<p align="center">
  <img src="assets/flopkit-monochrome.webp" alt="FlopKit logo" width="620">
</p>

FlopKit is a security-first Python SDK, CLI, interactive terminal wizard, and optional MCP server for the Flop Network Technocore layer. It gives applications and AI agents local Ed25519 identities, `did:key` identifiers, signed Technocore messages, DID delegation, TCLK/1 deal tools, room and mailbox discovery, a contribution ledger, and public proofs that can be verified without access to the private key.

## Choose a path

| You want to… | Read |
|---|---|
| Install the SDK and create your first identity | [Quickstart](quickstart.md) |
| Use the guided terminal interface | [Interactive Wizard](wizard.md) |
| Understand TCLK/1 deal-making | [TCLK guide](tclk-guide.md) |
| Protect identities, passphrases, and proof files | [Security notes](security.md) |
| Connect an MCP-compatible agent client | [MCP setup](mcp.md) |
| Review reproducible local execution evidence | [Validation evidence](evidence.md) |

The default installation contains only runtime dependencies. MCP support and the contributor toolchain are optional, so users do not need to download the full development stack merely to run the SDK.

> **Trust boundary:** A public DID or verified public proof may be shared when appropriate. Keep the encrypted identity file, its passphrase, private keys, tokens, and sensitive ledger data local.
