# Security notes

flopkit stores private keys only as passphrase-encrypted PKCS8 PEM files using `cryptography`’s `BestAvailableEncryption`. New identity files are created with owner-only `0600` permissions, and an existing target path raises `FileExistsError` rather than overwriting a key.

The SDK rejects wallet seed-phrase and mnemonic-style input. The CLI prompts for passphrases interactively; passphrases are never accepted as CLI arguments, printed, or committed. MCP identity generation returns the DID only, never private key material.

The project intentionally supports one identity per user. It does not implement key rotation, multi-wallet features, or production Technocore calls. The repository ignores `*.pem`, `*.seed`, `.env`, and `*.jsonl` files.
