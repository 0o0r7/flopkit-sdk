# MCP setup

Run the local server with an encrypted identity and passphrase supplied through the process environment:

```bash
FLOPKIT_IDENTITY=identity.pem FLOPKIT_PASSPHRASE='set-outside-source-control' python -m flopkit.mcp_server
```

A local MCP client can register the server with a stdio command configuration:

```json
{
  "mcpServers": {
    "flopkit": {
      "command": "python",
      "args": ["-m", "flopkit.mcp_server"],
      "cwd": "/path/to/flopkit/sdk",
      "env": {
        "FLOPKIT_IDENTITY": "/path/to/identity.pem",
        "FLOPKIT_PASSPHRASE": "provided-by-your-secret-manager"
      }
    }
  }
}
```

The server exposes identity generation, Technocore onboarding, message signing and verification, contribution logging, and proof export. Never paste a wallet seed phrase into any tool input.
