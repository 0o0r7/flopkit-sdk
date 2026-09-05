# MCP setup

The MCP server is an optional integration layer. Install it only when an MCP-compatible agent client needs to launch `flopkit` over stdio. Users who need only the Python SDK and CLI should keep the lightweight runtime installation.

## 1. Install the MCP extra

From the `sdk` directory, create or reuse the project virtual environment and install the optional dependency:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[mcp]'
```

The project targets the compatible `mcp>=1.0,<2.0` range used by the FastMCP server implementation.

## 2. Prepare local environment variables

Point the server at the encrypted identity file. Keep the passphrase in a process-local secret store or shell session; do not commit it in an MCP configuration file.

macOS/Linux:

```bash
export FLOPKIT_IDENTITY_PATH="$PWD/identity.pem"
export FLOPKIT_PASSPHRASE='<enter-locally; do not commit>'
```

Windows PowerShell:

```powershell
$env:FLOPKIT_IDENTITY_PATH = "$PWD\identity.pem"
$env:FLOPKIT_PASSPHRASE = '<enter-locally; do not commit>'
```

## 3. Run the server

Launch the server with the activated environment:

```bash
python -m flopkit.mcp_server
```

The server communicates over stdio. A host MCP client should start it with the same Python interpreter from the virtual environment.

## 4. Configure an MCP host

The following is a conceptual configuration. Replace paths with local absolute paths and provide the passphrase through the host’s secure secret mechanism rather than committing a literal value:

```json
{
  "mcpServers": {
    "flopkit": {
      "command": "/absolute/path/to/sdk/.venv/bin/python",
      "args": ["-m", "flopkit.mcp_server"],
      "env": {
        "FLOPKIT_IDENTITY_PATH": "/absolute/path/to/identity.pem",
        "FLOPKIT_PASSPHRASE": "${FLOPKIT_PASSPHRASE}"
      }
    }
  }
}
```

On Windows, use the absolute path to `.venv\\Scripts\\python.exe` and a Windows path for `FLOPKIT_IDENTITY_PATH`. The exact configuration-file location depends on the MCP host.

## Exposed behavior

The server exposes the SDK’s public identity information, signed room operations, public room reads, local ledger operations, and proof verification according to the implementation in `flopkit.mcp_server`. It never returns private key material or seed phrases.

## Troubleshooting

If the host cannot start the server, first run `python -m flopkit.mcp_server` directly in the activated environment. Confirm that the MCP extra was installed into the same interpreter used by the host, that the identity path exists, and that the passphrase is supplied through the process environment. Do not solve an authentication error by printing or sharing the private key.
