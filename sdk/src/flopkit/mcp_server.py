from __future__ import annotations

import os
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp.server.fastmcp import FastMCP

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
    path = os.getenv("FLOPKIT_IDENTITY_PATH", os.getenv("FLOPKIT_IDENTITY", "identity.pem"))
    passphrase = os.environ.get("FLOPKIT_PASSPHRASE", "")
    if not passphrase:
        raise RuntimeError("FLOPKIT_PASSPHRASE is required")
    return load_identity(path, passphrase)


def _reject_seed_phrase(value: str) -> None:
    lowered = value.lower()
    if "seed phrase" in lowered or "mnemonic" in lowered or len(value.split()) >= 12:
        raise ValueError("wallet seed phrases are not accepted")


@mcp.tool()
def generate_identity(passphrase: str) -> str:
    """Create an encrypted identity and return its DID only; never paste wallet seed phrases."""
    _reject_seed_phrase(passphrase)
    _, did = create_identity(passphrase, os.getenv("FLOPKIT_IDENTITY", "identity.pem"))
    return did


@mcp.tool()
def post_message(room: str, body: str) -> dict[str, Any]:
    """Post a signed room message; never paste wallet seed phrases into tool inputs."""
    with TechnocoreClient(_key()) as client:
        return client.post_message(room, body)


@mcp.tool()
def read_room(room: str, limit: int = 50, since: int | None = None) -> dict[str, Any]:
    """Read public Technocore room messages without exposing private key material."""
    with TechnocoreClient(_key()) as client:
        return client.read_room(room, limit=limit, since=since)


@mcp.tool()
def read_note(ns: str, key: str) -> str | None:
    """Read a Technocore note value; never paste wallet seed phrases into tool inputs."""
    with TechnocoreClient(_key()) as client:
        return client.read_note(ns, key)


@mcp.tool()
def write_note(ns: str, key: str, value: str, if_match: str | None = None,
               if_absent: bool = False) -> str:
    """Write a Technocore note value; never paste wallet seed phrases into tool inputs."""
    with TechnocoreClient(_key()) as client:
        return client.write_note(ns, key, value, if_match=if_match, if_absent=if_absent)


@mcp.tool()
def publish_did_note(extra: str = "") -> str:
    """Publish this identity's DID note; never paste wallet seed phrases into tool inputs."""
    with TechnocoreClient(_key()) as client:
        return client.publish_did_note(extra=extra)


@mcp.tool()
def list_rooms() -> str:
    """List public Technocore rooms; never paste wallet seed phrases into tool inputs."""
    with TechnocoreClient() as client:
        return client.list_rooms()


@mcp.tool()
def sign_message(payload: str) -> str:
    """Sign text and return its signature; never paste wallet seed phrases into tool inputs."""
    return sign_bytes(_key(), payload.encode()).hex()


@mcp.tool()
def verify_message(did: str, payload: str, signature: str) -> bool:
    """Verify a signature; never paste wallet seed phrases into tool inputs."""
    return verify_signature(did, payload.encode(), bytes.fromhex(signature))


@mcp.tool()
def log_contribution(url: str, description: str) -> dict[str, Any]:
    """Append a signed contribution; never paste wallet seed phrases into tool inputs."""
    ledger = ContributionLedger(os.getenv("FLOPKIT_LEDGER", "contributions.ledger"), _key())
    return ledger.log_contribution(url, description)


@mcp.tool()
def export_proof(path: str) -> dict[str, Any]:
    """Export and verify proof; never paste wallet seed phrases into inputs."""
    ledger = ContributionLedger(os.getenv("FLOPKIT_LEDGER", "contributions.ledger"), _key())
    return ledger.export_proof(path)


if __name__ == "__main__":
    mcp.run()
