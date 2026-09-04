# Security notes

flopkit stores private keys only as passphrase-encrypted PKCS8 PEM files using `cryptography`’s `BestAvailableEncryption`. New identity files are created with owner-only `0600` permissions, and an existing target path raises `FileExistsError` rather than overwriting a key. The same identity file must be reused to preserve the same public DID across sessions.

The SDK rejects wallet seed-phrase and mnemonic-style input. The CLI prompts for passphrases interactively; passphrases are never accepted as CLI arguments, printed, or committed. MCP identity generation returns the DID only, never private key material.

The project intentionally supports one identity per user. It does not implement seed phrases, browser key storage, token claiming, or airdrop automation. Signed writes use a nonce and are never automatically retried after an ambiguous timeout. Public contribution proofs contain only a DID, public HTTPS artifact URL, Git commit, and signature; they never contain private key material.

The repository ignores `*.pem`, `*.seed`, `.env`, and `*.jsonl` files. Before publishing changes, verify with `git ls-files '*.pem' '*.key' '*.seed'` that no private material is tracked.
