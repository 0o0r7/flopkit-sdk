from __future__ import annotations

import os
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp.server.fastmcp import FastMCP  # type: ignore[attr-defined]

from .identity import (
    generate_identity as create_identity,
)
from .identity import (
    load_identity,
    sign_bytes,
    verify_signature,
)
from .ledger import ContributionLedger
from .technocore import TechnocoreClient

mcp = FastMCP("flopkit")


def _key() -> Ed25519PrivateKey:
    path = os.getenv("FLOPKIT_IDENTITY", "identity.pem")
    passphrase = os.environ.get("FLOPKIT_PASSPHRASE", "")
    if not passphrase:
        raise RuntimeError("FLOPKIT_PASSPHRASE is required")
    return load_identity(path, passphrase)


def _reject_seed_phrase(value: str) -> None:
    lowered = value.lower()
    if "seed phrase" in lowered or "mnemonic" in lowered or len(value.split()) >= 12:
        raise ValueError("wallet seed phrases are not accepted")


@mcp.tool()  # type: ignore[untyped-decorator]
def generate_identity(passphrase: str) -> str:
    """Create an encrypted identity and return its DID only; never paste wallet seed phrases."""
    _reject_seed_phrase(passphrase)
    _, did = create_identity(passphrase, os.getenv("FLOPKIT_IDENTITY", "identity.pem"))
    return did


@mcp.tool()  # type: ignore[untyped-decorator]
def publish_did() -> dict[str, Any]:
    """Publish the current DID; never paste wallet seed phrases into tool inputs."""
    with TechnocoreClient(_key()) as client:
        return client.publish_did()


@mcp.tool()  # type: ignore[untyped-decorator]
def check_in() -> dict[str, Any]:
    """Check in the current DID; never paste wallet seed phrases into tool inputs."""
    with TechnocoreClient(_key()) as client:
        return client.check_in()


@mcp.tool()  # type: ignore[untyped-decorator]
def post_message(room: str, body: str) -> dict[str, Any]:
    """Post a signed room message; never paste wallet seed phrases into tool inputs."""
    with TechnocoreClient(_key()) as client:
        return client.post_message(room, body)


@mcp.tool()  # type: ignore[untyped-decorator]
def sign_message(payload: str) -> str:
    """Sign text and return its signature; never paste wallet seed phrases into tool inputs."""
    return sign_bytes(_key(), payload.encode()).hex()


@mcp.tool()  # type: ignore[untyped-decorator]
def verify_message(did: str, payload: str, signature: str) -> bool:
    """Verify a signature; never paste wallet seed phrases into tool inputs."""
    return verify_signature(did, payload.encode(), bytes.fromhex(signature))


@mcp.tool()  # type: ignore[untyped-decorator]
def log_contribution(url: str, description: str) -> dict[str, Any]:
    """Append a signed contribution; never paste wallet seed phrases into tool inputs."""
    ledger = ContributionLedger(os.getenv("FLOPKIT_LEDGER", "contributions.ledger"), _key())
    return ledger.log_contribution(url, description)


@mcp.tool()  # type: ignore[untyped-decorator]
def export_proof(path: str) -> dict[str, Any]:
    """Export and verify proof; never paste wallet seed phrases into inputs."""
    ledger = ContributionLedger(os.getenv("FLOPKIT_LEDGER", "contributions.ledger"), _key())
    return ledger.export_proof(path)


if __name__ == "__main__":
    mcp.run()
