"""Command-line interface for the flopkit SDK."""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import Any

from .delegation import DelegationManager
from .identity import generate_identity, load_identity
from .ledger import ContributionLedger
from .proofs import create_contribution_proof, verify_contribution_proof, write_proof
from .tclk import TCLKManager
from .technocore import TechnocoreClient
from .wizard import run as run_wizard


def _identity_path(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--identity", default="identity.pem", help="encrypted PEM identity path")


def _load_key(path: str) -> Any:
    return load_identity(path, getpass.getpass("Passphrase: "))


def _post(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        return client.post_message(args.room, args.body, nonce=args.nonce)


def _read(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        return client.read_room(
            args.room,
            since=args.since,
            limit=args.limit,
            wait=args.wait,
            cache_buster=args.cache_buster,
        )


def _events(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient() as client:
        return client.read_events(since=args.since, limit=args.limit)


def _mint_room(args: argparse.Namespace) -> dict[str, str]:
    with TechnocoreClient() as client:
        name = client.mint_room_name(args.classes)
    return {"room": name}


def _note_read(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        value = client.read_note(args.ns, args.key)
    return {"ns": args.ns, "key": args.key, "value": value if value is not None else "not found"}


def _note_write(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        result = client.write_note(
            args.ns, args.key, args.value, if_match=args.if_match, if_absent=args.if_absent
        )
    return {"path": f"/kv/{args.ns}/{args.key}", "result": result}


def _did_publish(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        path = client.publish_did_note(extra=args.extra or "", if_absent=args.if_absent)
    return {"path": path}


def _did_resolve(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient() as client:
        note = client.resolve_did_note(args.did)
    return {"did": args.did, "note": note if note is not None else "not found"}


def _rooms(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient() as client:
        return {"rooms": client.list_rooms()}


def _log(args: argparse.Namespace) -> dict[str, Any]:
    ledger = ContributionLedger(args.ledger, _load_key(args.identity))
    return ledger.log_contribution(args.url, args.description)


def _export_proof(args: argparse.Namespace) -> dict[str, Any]:
    ledger = ContributionLedger(args.ledger, _load_key(args.identity))
    return ledger.export_proof(Path(args.path))


def _create_public_proof(args: argparse.Namespace) -> dict[str, Any]:
    proof = create_contribution_proof(
        _load_key(args.identity), args.artifact_url, args.commit
    )
    write_proof(args.path, proof)
    return proof


def _verify_public_proof(args: argparse.Namespace) -> dict[str, Any]:
    payload = json.loads(Path(args.path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("proof JSON must contain an object")
    verify_contribution_proof(payload)
    return {"path": str(args.path), "valid": True}


# --- TCLK handlers ---


def _tclk_offer(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        manager = TCLKManager(client)
        result = manager.post_offer(
            role=args.role,
            amount=args.amount,
            asset=args.asset,
            lock=args.lock_type,
            rails=args.rails,
            claim_by_ms=args.claim_by_ms,
            refund_after_ms=args.refund_after_ms,
            expires_ms=args.expires_ms,
            payment_key=args.payment_key,
            job={"id": args.job_id, "proto": args.job_proto} if args.job_id else None,
        )
    return {"type": "offer", "nonce": result["nonce"], "id": result["id"]}


def _tclk_accept(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        manager = TCLKManager(client)
        # Read the offer from tclk-offers
        room_data = client.read_room("tclk-offers", limit=200)
        offer_frame = None
        for msg in room_data.get("messages", []):
            text = msg.get("text", "")
            if text.startswith("tclk1 "):
                frame = json.loads(text[6:])
                if frame.get("nonce") == args.offer_nonce and frame.get("type") == "offer":
                    offer_frame = frame
                    break
        if offer_frame is None:
            raise ValueError(f"offer {args.offer_nonce!r} not found in tclk-offers")
        result = manager.post_accept(
            offer=offer_frame,
            statement=args.statement,
            payment_key=args.payment_key,
        )
    return {"type": "accept", "nonce": result["nonce"], "contract": result["contract"]}


def _tclk_lock(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        manager = TCLKManager(client)
        nonce = manager.post_lock(
            contract_id=args.contract,
            rail=args.rail,
            ref=args.ref,
            presig=json.loads(args.presig) if args.presig else None,
        )
    return {"type": "lock", "nonce": nonce}


def _tclk_reveal(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        manager = TCLKManager(client)
        nonce = manager.post_reveal(
            contract_id=args.contract,
            secret=args.secret,
            ref=args.ref,
        )
    return {"type": "reveal", "nonce": nonce}


def _tclk_refund(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        manager = TCLKManager(client)
        nonce = manager.post_refund(
            contract_id=args.contract,
            ref=args.ref,
            reason=args.reason,
        )
    return {"type": "refund", "nonce": nonce}


def _tclk_cancel(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        manager = TCLKManager(client)
        nonce = manager.post_cancel(
            contract_id=args.contract,
            reason=args.reason,
        )
    return {"type": "cancel", "nonce": nonce}


def _tclk_heartbeat(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        manager = TCLKManager(client)
        nonce = manager.post_heartbeat(
            contract_id=args.contract,
            note=args.note,
        )
    return {"type": "heartbeat", "nonce": nonce}


def _tclk_receipt(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        manager = TCLKManager(client)
        nonce = manager.post_receipt(
            contract_id=args.contract,
            outcome=args.outcome,
            rail=args.rail,
            ref=args.ref,
        )
    return {"type": "receipt", "nonce": nonce}


def _tclk_status(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient() as client:
        manager = TCLKManager(client)
        status = manager.read_deal_status(args.contract)
    return {"contract": args.contract, "status": status if status is not None else "not found"}


def _tclk_fold(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        manager = TCLKManager(client)
        result = manager.fold_room(args.room, limit=args.limit)
    return {
        "contracts": {
            cid: {"state": c.state.value, "amount": c.amount, "asset": c.asset}
            for cid, c in result.contracts.items()
        },
        "offers": result.offers,
        "malformed_count": len(result.malformed),
        "rejected_count": len(result.rejected),
    }


def _tclk_advertise(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        manager = TCLKManager(client)
        path = manager.advertise_capability(args.rails)
    return {"path": path, "rails": args.rails}


# --- Delegation handlers ---


def _delegate(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        mgr = DelegationManager(client)
        result = mgr.create_delegate(args.agent_did, args.scope, args.expires_ms)
    return {"type": "delegate", "nonce": result["nonce"], "agent_did": result["agent_did"]}


def _verify_delegate(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient() as client:
        mgr = DelegationManager(client)
        result = mgr.verify_delegate(args.issuer_did, args.agent_did)
    if result is None:
        return {"valid": False, "reason": "no delegation found"}
    return result  # type: ignore[return-value]


def _revoke_delegate(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        mgr = DelegationManager(client)
        result = mgr.revoke_delegate(args.agent_did)
    return {"type": "revoke", "nonce": result["nonce"], "agent_did": result["agent_did"]}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flopkit", description="Secure Technocore SDK CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate-identity", help="create an encrypted Ed25519 identity")
    gen.add_argument("--path", default="identity.pem", help="destination encrypted PEM path")
    for name in ("say", "post"):
        post = sub.add_parser(name, help="post a signed message to a Technocore room")
        _identity_path(post)
        post.add_argument("--nonce", help="optional 1-19 digit nonce")
        post.add_argument("room")
        post.add_argument("body")
        post.set_defaults(handler=_post)
    read = sub.add_parser("read", help="read public messages from a Technocore room")
    _identity_path(read)
    read.add_argument("room")
    read.add_argument("--since", type=int)
    read.add_argument("--limit", type=int, default=50)
    read.add_argument("--wait", type=float)
    read.add_argument("--cache-buster", type=int)
    read.set_defaults(handler=_read)
    events = sub.add_parser("events", help="read the public events/discovery stream")
    events.add_argument("--since", type=int)
    events.add_argument("--limit", type=int, default=50)
    events.set_defaults(handler=_events)
    mint = sub.add_parser("mint-room", help="mint a fresh random room name")
    mint.add_argument("--classes", default="p", help="room class prefixes (e.g. 'p', 'mb-p')")
    mint.set_defaults(handler=_mint_room)
    log = sub.add_parser("log", help="append a signed contribution event")
    _identity_path(log)
    log.add_argument("--ledger", default="contributions.ledger")
    log.add_argument("url")
    log.add_argument("description")
    log.set_defaults(handler=_log)
    export = sub.add_parser("export-proof", help="export and verify the contribution ledger")
    _identity_path(export)
    export.add_argument("--ledger", default="contributions.ledger")
    export.add_argument("path")
    export.set_defaults(handler=_export_proof)
    proof = sub.add_parser("proof", help="create a signed proof for a public Git contribution")
    _identity_path(proof)
    proof.add_argument("artifact_url")
    proof.add_argument("commit")
    proof.add_argument("--output", dest="path", required=True)
    proof.set_defaults(handler=_create_public_proof)
    verify = sub.add_parser("verify-proof", help="verify a public contribution proof")
    verify.add_argument("path")
    verify.set_defaults(handler=_verify_public_proof)
    rooms = sub.add_parser("rooms", help="list public Technocore rooms without an identity")
    rooms.set_defaults(handler=_rooms)
    note_read = sub.add_parser("note-read", help="read a Technocore note value")
    _identity_path(note_read)
    note_read.add_argument("ns")
    note_read.add_argument("key")
    note_read.set_defaults(handler=_note_read)
    note_write = sub.add_parser("note-write", help="write a Technocore note value")
    _identity_path(note_write)
    note_write.add_argument("--if-match", help="only write when the current value matches")
    note_write.add_argument(
        "--if-absent", action="store_true", help="only write when the note is missing"
    )
    note_write.add_argument("ns")
    note_write.add_argument("key")
    note_write.add_argument("value")
    note_write.set_defaults(handler=_note_write)
    did_publish = sub.add_parser("did-publish", help="publish this identity's DID note")
    _identity_path(did_publish)
    did_publish.add_argument("--extra", default="", help="extra space-separated tokens")
    did_publish.add_argument("--if-absent", action="store_true", help="only publish when absent")
    did_publish.set_defaults(handler=_did_publish)
    did_resolve = sub.add_parser("did-resolve", help="resolve a DID note without an identity")
    did_resolve.add_argument("did")
    did_resolve.set_defaults(handler=_did_resolve)
    # TCLK subcommands (full spec)
    tclk_offer = sub.add_parser("tclk-offer", help="post a TCLK/1 trade offer")
    _identity_path(tclk_offer)
    tclk_offer.add_argument("role", choices=["payer", "payee"], help="sender's role")
    tclk_offer.add_argument("amount", help="amount in rail-native minimal units")
    tclk_offer.add_argument("asset", help="asset identifier (e.g. FLOP)")
    tclk_offer.add_argument("--lock-type", default="hash", choices=["hash", "point"],
                            help="lock kind (default: hash)")
    tclk_offer.add_argument("--rails", nargs="+", default=["flop-htlc"],
                            help="settlement rail identifiers")
    tclk_offer.add_argument("--claim-by-ms", type=int, required=True,
                            help="Unix ms deadline for claiming")
    tclk_offer.add_argument("--refund-after-ms", type=int, required=True,
                            help="Unix ms after which refund is allowed")
    tclk_offer.add_argument("--expires-ms", type=int, required=True,
                            help="Unix ms after which the offer expires")
    tclk_offer.add_argument("--payment-key", help="optional hash/point payment key statement")
    tclk_offer.add_argument("--job-id", help="optional job id")
    tclk_offer.add_argument("--job-proto", help="optional job protocol (e.g. a2a)")
    tclk_offer.set_defaults(handler=_tclk_offer)
    tclk_accept = sub.add_parser("tclk-accept", help="accept a TCLK offer")
    _identity_path(tclk_accept)
    tclk_accept.add_argument("offer_nonce", help="nonce of the offer to accept")
    tclk_accept.add_argument("--statement", required=True, help="hash/point statement for the lock")
    tclk_accept.add_argument("--payment-key", help="optional payment key statement")
    tclk_accept.set_defaults(handler=_tclk_accept)
    tclk_lock = sub.add_parser("tclk-lock", help="post a TCLK lock to the derived deal room")
    _identity_path(tclk_lock)
    tclk_lock.add_argument("contract", help="contract id (0x + 64 hex)")
    tclk_lock.add_argument("rail", help="settlement rail identifier")
    tclk_lock.add_argument("ref", help="rail-specific lock reference")
    tclk_lock.add_argument("--presig", help="optional adaptor pre-signature JSON")
    tclk_lock.set_defaults(handler=_tclk_lock)
    tclk_reveal = sub.add_parser("tclk-reveal", help="reveal a TCLK preimage")
    _identity_path(tclk_reveal)
    tclk_reveal.add_argument("contract", help="contract id (0x + 64 hex)")
    tclk_reveal.add_argument("secret", help="preimage (hash) or scalar (point)")
    tclk_reveal.add_argument("--ref", help="optional rail reference matching the lock")
    tclk_reveal.set_defaults(handler=_tclk_reveal)
    tclk_refund = sub.add_parser("tclk-refund", help="post a TCLK refund claim")
    _identity_path(tclk_refund)
    tclk_refund.add_argument("contract", help="contract id (0x + 64 hex)")
    tclk_refund.add_argument("--ref", help="optional rail reference matching the lock")
    tclk_refund.add_argument("--reason", help="optional human-readable reason")
    tclk_refund.set_defaults(handler=_tclk_refund)
    tclk_cancel = sub.add_parser("tclk-cancel", help="cancel a TCLK deal before any lock")
    _identity_path(tclk_cancel)
    tclk_cancel.add_argument("contract", help="contract id (0x + 64 hex)")
    tclk_cancel.add_argument("--reason", help="optional human-readable reason")
    tclk_cancel.set_defaults(handler=_tclk_cancel)
    tclk_heartbeat = sub.add_parser("tclk-heartbeat", help="post a TCLK liveness heartbeat")
    _identity_path(tclk_heartbeat)
    tclk_heartbeat.add_argument("contract", help="contract id (0x + 64 hex)")
    tclk_heartbeat.add_argument("--note", help="optional liveness note")
    tclk_heartbeat.set_defaults(handler=_tclk_heartbeat)
    tclk_receipt = sub.add_parser("tclk-receipt", help="post a TCLK post-terminal receipt")
    _identity_path(tclk_receipt)
    tclk_receipt.add_argument("contract", help="contract id (0x + 64 hex)")
    tclk_receipt.add_argument("outcome", help="outcome string (claimed/refunded/cancelled)")
    tclk_receipt.add_argument("--rail", help="optional rail id matching locked terms")
    tclk_receipt.add_argument("--ref", help="optional rail reference matching locked terms")
    tclk_receipt.set_defaults(handler=_tclk_receipt)
    tclk_status = sub.add_parser("tclk-status", help="read the TCLK state pointer for a contract")
    tclk_status.add_argument("contract", help="contract id (0x + 64 hex)")
    tclk_status.set_defaults(handler=_tclk_status)
    tclk_fold = sub.add_parser("tclk-fold", help="fold a room transcript into deal states")
    _identity_path(tclk_fold)
    tclk_fold.add_argument("room", help="room to read and fold")
    tclk_fold.add_argument("--limit", type=int, default=200, help="max messages to read")
    tclk_fold.set_defaults(handler=_tclk_fold)
    tclk_advertise = sub.add_parser("tclk-advertise", help="advertise TCLK capability in DID note")
    _identity_path(tclk_advertise)
    tclk_advertise.add_argument("--rails", nargs="+", default=["flop-htlc"],
                                help="settlement rail identifiers to advertise")
    tclk_advertise.set_defaults(handler=_tclk_advertise)
    # Delegation subcommands
    delegate = sub.add_parser("delegate", help="delegate signing authority to an agent")
    _identity_path(delegate)
    delegate.add_argument("agent_did", help="DID of the agent to delegate to")
    delegate.add_argument("scope", help="scope of authority (e.g. r:lobby)")
    delegate.add_argument("expires_ms", type=int, help="expiry in Unix ms (0 for no expiry)")
    delegate.set_defaults(handler=_delegate)
    verify_delegate = sub.add_parser("verify-delegate", help="verify an agent's delegation")
    verify_delegate.add_argument("issuer_did", help="DID of the delegating issuer")
    verify_delegate.add_argument("agent_did", help="DID of the agent claiming delegation")
    verify_delegate.set_defaults(handler=_verify_delegate)
    revoke_delegate = sub.add_parser("revoke-delegate", help="revoke a delegation")
    _identity_path(revoke_delegate)
    revoke_delegate.add_argument("agent_did", help="DID of the agent to revoke")
    revoke_delegate.set_defaults(handler=_revoke_delegate)
    return parser


def main() -> None:
    if len(sys.argv) == 1:
        run_wizard()
        return
    args = _parser().parse_args()
    if args.command == "generate-identity":
        first = getpass.getpass("Passphrase: ")
        second = getpass.getpass("Confirm passphrase: ")
        if first != second:
            raise SystemExit("passphrases do not match")
        _, did = generate_identity(first, args.path)
        print(did)
        return
    try:
        print(json.dumps(args.handler(args), ensure_ascii=True, sort_keys=True))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
