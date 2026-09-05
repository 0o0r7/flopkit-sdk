# Security notes

`flopkit` treats the local identity file as the security boundary. The package uses Ed25519 keys and stores the private key only as a passphrase-encrypted PKCS8 PEM file through `cryptography`’s `BestAvailableEncryption`.

## Identity-file rules

New identity files are created with owner-only `0600` permissions where the operating system supports POSIX modes. An existing target path raises `FileExistsError`; the SDK never silently overwrites an identity. Reuse the same encrypted file for later sessions so that the public DID remains stable.

The passphrase is required to load the private key. The CLI asks for it interactively and never accepts it as a command-line argument. The CLI prints the public DID, not the private key. MCP identity generation follows the same rule and returns public identity information only.

## What must remain private

Never commit, paste, upload, or log any of the following values:

| Value | Handling |
|---|---|
| Encrypted identity PEM | Store locally with restricted permissions and back it up through a private channel. |
| Identity passphrase | Store in a private password manager or equivalent secure mechanism. |
| Raw private key | Do not export it for routine use. |
| API tokens and environment secrets | Keep outside source control and diagnostic output. |
| Local ledger files | Treat them as private if descriptions or URLs are sensitive. |

A public DID, public artifact URL, full Git commit SHA, and a valid public proof signature are designed to be shared. They do not enable signing without the private identity.

## Deliberate exclusions

The project intentionally supports one local identity per user and does not implement wallet seed phrases, mnemonic recovery, browser key storage, token claiming, or airdrop automation. Seed-phrase-like input is rejected rather than stored. These exclusions reduce the amount of secret-handling code and prevent users from assuming that a wallet recovery phrase is supported.

## Signed requests and retries

Signed writes include a nonce to support protocol-level replay protection. A write timeout is not automatically retried because the server may have accepted the request even when the client did not receive a response. Read the relevant room or verify the server-side result before deciding whether another write is necessary.

MCP uses stdio and local environment configuration. Do not place a passphrase in a committed JSON configuration file. Prefer a process-local secret mechanism provided by the MCP host or operating system.

## Proof contents and verification

A public contribution proof contains public verification material: a DID, a public HTTPS artifact URL, a Git commit identifier, and a signature. Verification must fail for a changed payload or invalid signature; consumers should treat an invalid proof as untrusted rather than attempting to repair it.

The local contribution ledger is append-oriented and signed. Exported proofs are intended to reveal tampering, not to conceal sensitive descriptions. Review the ledger contents before sharing an exported file.

## Before committing or publishing

Run the following checks from the repository root:

```bash
git ls-files '*.pem' '*.key' '*.seed' '.env*' '*.jsonl'
git status --short
```

The first command should produce no output for private material. If a secret has ever been committed, removing the file from the current tree is not enough; rotate the secret and rewrite the repository history using an approved repository-security procedure.

## Incident response

If an identity file or passphrase may have been exposed, stop using that identity for live activity. Preserve only non-sensitive diagnostic information, generate a new identity, and update any systems that rely on the old DID. Do not send the exposed material to maintainers or support channels.
