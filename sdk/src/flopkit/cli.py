from __future__ import annotations

import argparse
import getpass
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .identity import generate_identity, load_identity
from .ledger import ContributionLedger
from .proofs import create_contribution_proof, verify_contribution_proof, write_proof
from .technocore import TechnocoreClient
from .wizard import run as run_wizard


def _identity_path(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--identity", default="identity.pem", help="encrypted PEM identity path")


def _load_key(path: str) -> Any:
    return load_identity(path, getpass.getpass("Passphrase: "))


def _add_network_command(
    sub: argparse._SubParsersAction[Any], name: str, handler: Callable[..., Any]
) -> None:
    command = sub.add_parser(name, help=f"{name.replace('-', ' ')} on Technocore")
    _identity_path(command)
    command.set_defaults(handler=handler)


def _publish(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        return client.publish_did()


def _check_in(args: argparse.Namespace) -> dict[str, Any]:
    with TechnocoreClient(_load_key(args.identity)) as client:
        return client.check_in()


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flopkit", description="Secure Technocore SDK CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate-identity", help="create an encrypted Ed25519 identity")
    gen.add_argument("--path", default="identity.pem", help="destination encrypted PEM path")
    _add_network_command(sub, "publish", _publish)
    _add_network_command(sub, "check-in", _check_in)
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
