from __future__ import annotations

import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp.server.fastmcp import FastMCP  # type: ignore[attr-defined]

from .identity import (
    generate_identity,
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


@mcp.tool()  # type: ignore[untyped-decorator]
def generate_identity_tool(passphrase: str) -> str:
    _, did = generate_identity(passphrase, os.getenv("FLOPKIT_IDENTITY", "identity.pem"))
    return did


@mcp.tool()  # type: ignore[untyped-decorator]
def publish_did() -> dict[str, object]:
    with TechnocoreClient(_key()) as client:
        return client.publish_did()


@mcp.tool()  # type: ignore[untyped-decorator]
def check_in() -> dict[str, object]:
    with TechnocoreClient(_key()) as client:
        return client.check_in()


@mcp.tool()  # type: ignore[untyped-decorator]
def post_message(room: str, body: str) -> dict[str, object]:
    with TechnocoreClient(_key()) as client:
        return client.post_message(room, body)


@mcp.tool()  # type: ignore[untyped-decorator]
def sign_message(payload: str) -> str:
    return sign_bytes(_key(), payload.encode()).hex()


@mcp.tool()  # type: ignore[untyped-decorator]
def verify_message(did: str, payload: str, signature: str) -> bool:
    return verify_signature(did, payload.encode(), bytes.fromhex(signature))


@mcp.tool()  # type: ignore[untyped-decorator]
def log_contribution(url: str, description: str) -> dict[str, object]:
    ledger = ContributionLedger(os.getenv("FLOPKIT_LEDGER", "contributions.ledger"), _key())
    return ledger.log_contribution(url, description)


@mcp.tool()  # type: ignore[untyped-decorator]
def export_proof(path: str) -> dict[str, object]:
    ledger = ContributionLedger(os.getenv("FLOPKIT_LEDGER", "contributions.ledger"), _key())
    return ledger.export_proof(path)


if __name__ == "__main__":
    mcp.run()
