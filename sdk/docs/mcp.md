# MCP setup

The MCP server is an optional layer. A user who only needs the Python SDK and CLI should install the core package with `python -m pip install -e .`; MCP dependencies are not included in that installation.

## Install MCP support

From the `sdk` directory, create or reuse an isolated environment and install the MCP extra:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[mcp]'
```

The supported MCP dependency range is `mcp>=1.0,<2.0`, matching the FastMCP API used by this project.

## Run the local server

Set the identity path in the environment rather than passing private key material on the command line:

```bash
export FLOPKIT_IDENTITY_PATH="$PWD/identity.pem"
export FLOPKIT_PASSPHRASE="set-this-in-your-shell-only"
python -m flopkit.mcp_server
```

On PowerShell, use:

```powershell
$env:FLOPKIT_IDENTITY_PATH = "$PWD\identity.pem"
$env:FLOPKIT_PASSPHRASE = "set-this-in-your-shell-only"
python -m flopkit.mcp_server
```

The server communicates over stdio. Configure your MCP client to launch it with the same Python interpreter from the activated environment. A conceptual configuration is:

```json
{
  "mcpServers": {
    "flopkit": {
      "command": "/absolute/path/to/sdk/.venv/bin/python",
      "args": ["-m", "flopkit.mcp_server"],
      "env": {
        "FLOPKIT_IDENTITY_PATH": "/absolute/path/to/identity.pem",
        "FLOPKIT_PASSPHRASE": "set-this-outside-committed-files"
      }
    }
  }
}
```

On Windows, use the absolute path to `.venv\\Scripts\\python.exe` and a Windows path for `FLOPKIT_IDENTITY_PATH`.

The server exposes signed room writes and public room reads, returns public DID information where appropriate, and never returns private keys or seed phrases. Supply `FLOPKIT_PASSPHRASE` through an uncommitted local secret mechanism; do not place it in a committed client configuration file.
