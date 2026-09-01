# Security notes

Private keys are written only as PEM encrypted with `BestAvailableEncryption`. The code does not accept seed phrases, and the CLI never accepts passphrases as arguments. `.gitignore` excludes PEM, seed, environment, and ledger files. MCP identity generation returns only a DID.
