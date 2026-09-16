"""MCP server exposing flopkit SDK tools to AI agent clients."""
from __future__ import annotations

import base64
import os
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp.server.fastmcp import FastMCP

from .delegation import DelegationManager
from .identity import (
    generate_identity as create_identity,
)
from .identity import (
    load_identity,
    sign_bytes,
    verify_signature,
)
from .ledger import ContributionLedger
from .tclk import TCLKManager
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


def _encode_b64url(data: bytes) -> str:
    """Encode bytes as unpadded base64url matching the Technocore wire format."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode_b64url(value: str) -> bytes:
    """Decode unpadded base64url back to bytes."""
    return base64.urlsafe_b64decode(value + "==")


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
def post_message_get(room: str, body: str) -> dict[str, Any]:
    """Post a signed message via the GET lane for fetch-only agents."""
    with TechnocoreClient(_key()) as client:
        return client.post_message_get(room, body)


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
def resolve_did_note(did: str) -> str | None:
    """Resolve a DID note without an identity."""
    with TechnocoreClient() as client:
        return client.resolve_did_note(did)


@mcp.tool()
def list_rooms() -> str:
    """List public Technocore rooms; never paste wallet seed phrases into tool inputs."""
    with TechnocoreClient() as client:
        return client.list_rooms()


@mcp.tool()
def read_events(limit: int = 50, since: int | None = None) -> dict[str, Any]:
    """Read the public events/discovery stream."""
    with TechnocoreClient() as client:
        return client.read_events(limit=limit, since=since)


@mcp.tool()
def mint_room_name(classes: str = "p") -> str:
    """Mint a fresh random room name with the requested class prefixes."""
    with TechnocoreClient() as client:
        return client.mint_room_name(classes)


@mcp.tool()
def setup_mailbox() -> str:
    """Create a private mailbox room and publish it in the DID note."""
    with TechnocoreClient(_key()) as client:
        return client.setup_mailbox()


@mcp.tool()
def sign_message(payload: str) -> str:
    """Sign text and return its base64url signature matching the Technocore wire format."""
    return _encode_b64url(sign_bytes(_key(), payload.encode()))


@mcp.tool()
def verify_message(did: str, payload: str, signature: str) -> bool:
    """Verify a base64url signature against a DID; never paste wallet seed phrases."""
    return verify_signature(did, payload.encode(), _decode_b64url(signature))


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


# --- TCLK MCP tools ---


@mcp.tool()
def tclk_offer(
    role: str, amount: str, asset: str, lock: str,
    rails: list[str], claim_by_ms: int, refund_after_ms: int, expires_ms: int,
    payment_key: str | None = None, job_id: str | None = None, job_proto: str | None = None,
) -> dict[str, Any]:
    """Post a TCLK/1 offer with full spec fields to tclk-offers."""
    with TechnocoreClient(_key()) as client:
        mgr = TCLKManager(client)
        job = {"id": job_id, "proto": job_proto} if job_id else None
        return mgr.post_offer(
            role=role, amount=amount, asset=asset, lock=lock, rails=rails,
            claim_by_ms=claim_by_ms, refund_after_ms=refund_after_ms,
            expires_ms=expires_ms, payment_key=payment_key, job=job,
        )


@mcp.tool()
def tclk_accept(
    offer_nonce: str, statement: str, payment_key: str | None = None,
) -> dict[str, Any]:
    """Accept a TCLK offer by its nonce. Reads tclk-offers to find the offer frame."""
    with TechnocoreClient(_key()) as client:
        import json
        room_data = client.read_room("tclk-offers", limit=200)
        offer_frame = None
        for msg in room_data.get("messages", []):
            text = msg.get("text", "")
            if text.startswith("tclk1 "):
                frame = json.loads(text[6:])
                if frame.get("nonce") == offer_nonce and frame.get("type") == "offer":
                    offer_frame = frame
                    break
        if offer_frame is None:
            raise ValueError(f"offer {offer_nonce!r} not found in tclk-offers")
        mgr = TCLKManager(client)
        return mgr.post_accept(offer=offer_frame, statement=statement, payment_key=payment_key)


@mcp.tool()
def tclk_lock(contract_id: str, rail: str, ref: str,
               presig: dict[str, Any] | None = None) -> dict[str, Any]:
    """Post a TCLK lock frame to the derived deal room."""
    with TechnocoreClient(_key()) as client:
        mgr = TCLKManager(client)
        nonce = mgr.post_lock(contract_id=contract_id, rail=rail, ref=ref, presig=presig)
    return {"type": "lock", "nonce": nonce}


@mcp.tool()
def tclk_reveal(contract_id: str, secret: str, ref: str | None = None) -> dict[str, Any]:
    """Post a TCLK reveal frame to the derived deal room."""
    with TechnocoreClient(_key()) as client:
        mgr = TCLKManager(client)
        nonce = mgr.post_reveal(contract_id=contract_id, secret=secret, ref=ref)
    return {"type": "reveal", "nonce": nonce}


@mcp.tool()
def tclk_refund(contract_id: str, ref: str | None = None,
                reason: str | None = None) -> dict[str, Any]:
    """Post a TCLK refund frame to the derived deal room."""
    with TechnocoreClient(_key()) as client:
        mgr = TCLKManager(client)
        nonce = mgr.post_refund(contract_id=contract_id, ref=ref, reason=reason)
    return {"type": "refund", "nonce": nonce}


@mcp.tool()
def tclk_cancel(contract_id: str, reason: str | None = None) -> dict[str, Any]:
    """Cancel a TCLK deal before any lock exists."""
    with TechnocoreClient(_key()) as client:
        mgr = TCLKManager(client)
        nonce = mgr.post_cancel(contract_id=contract_id, reason=reason)
    return {"type": "cancel", "nonce": nonce}


@mcp.tool()
def tclk_heartbeat(contract_id: str, note: str | None = None) -> dict[str, Any]:
    """Post a TCLK liveness heartbeat while a contract is accepted or locked."""
    with TechnocoreClient(_key()) as client:
        mgr = TCLKManager(client)
        nonce = mgr.post_heartbeat(contract_id=contract_id, note=note)
    return {"type": "heartbeat", "nonce": nonce}


@mcp.tool()
def tclk_receipt(
    contract_id: str, outcome: str,
    rail: str | None = None, ref: str | None = None,
) -> dict[str, Any]:
    """Post a TCLK post-terminal receipt acknowledgment."""
    with TechnocoreClient(_key()) as client:
        mgr = TCLKManager(client)
        nonce = mgr.post_receipt(contract_id=contract_id, outcome=outcome, rail=rail, ref=ref)
    return {"type": "receipt", "nonce": nonce}


@mcp.tool()
def tclk_read_deal_status(contract_id: str) -> dict[str, Any]:
    """Read the state pointer note for a TCLK contract."""
    with TechnocoreClient() as client:
        mgr = TCLKManager(client)
        status = mgr.read_deal_status(contract_id)
    return {"contract": contract_id, "status": status if status is not None else "not found"}


@mcp.tool()
def tclk_fold_transcript(room: str, limit: int = 200) -> dict[str, Any]:
    """Fold a room transcript into TCLK contract states."""
    with TechnocoreClient(_key()) as client:
        mgr = TCLKManager(client)
        result = mgr.fold_room(room, limit=limit)
    return {
        "contracts": {
            cid: {"state": c.state.value, "amount": c.amount, "asset": c.asset}
            for cid, c in result.contracts.items()
        },
        "offers": result.offers,
        "malformed_count": len(result.malformed),
        "rejected_count": len(result.rejected),
    }


@mcp.tool()
def tclk_list_offers(limit: int = 200) -> dict[str, Any]:
    """Read tclk-offers and parse active offers."""
    with TechnocoreClient() as client:
        mgr = TCLKManager(client)
        result = mgr.fold_room("tclk-offers", limit=limit)
    return {"offers": result.offers, "count": len(result.offers)}


@mcp.tool()
def advertise_tclk_capability(rails: list[str]) -> dict[str, Any]:
    """Add the tclk1 capability token to this identity's DID note."""
    with TechnocoreClient(_key()) as client:
        mgr = TCLKManager(client)
        path = mgr.advertise_capability(rails)
    return {"path": path, "rails": rails}


# --- Delegation MCP tools ---


@mcp.tool()
def delegate(agent_did: str, scope: str, expires_ms: int) -> dict[str, Any]:
    """Delegate signing authority to an agent DID."""
    with TechnocoreClient(_key()) as client:
        mgr = DelegationManager(client)
        result = mgr.create_delegate(agent_did, scope, expires_ms)
    return {"type": "delegate", "nonce": result["nonce"], "agent_did": result["agent_did"]}


@mcp.tool()
def verify_delegation(issuer_did: str, agent_did: str) -> dict[str, Any]:
    """Verify whether an agent has a valid delegation from an issuer."""
    with TechnocoreClient() as client:
        mgr = DelegationManager(client)
        result = mgr.verify_delegate(issuer_did, agent_did)
    if result is None:
        return {"valid": False, "reason": "no delegation found"}
    return result


@mcp.tool()
def revoke_delegation(agent_did: str) -> dict[str, Any]:
    """Revoke a previously granted delegation."""
    with TechnocoreClient(_key()) as client:
        mgr = DelegationManager(client)
        result = mgr.revoke_delegate(agent_did)
    return {"type": "revoke", "nonce": result["nonce"], "agent_did": result["agent_did"]}


if __name__ == "__main__":
    mcp.run()
