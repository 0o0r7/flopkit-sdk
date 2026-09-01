from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .identity import generate_identity, load_identity
from .ledger import ContributionLedger
from .technocore import TechnocoreClient


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
        return client.post_message(args.room, args.body)


def _log(args: argparse.Namespace) -> dict[str, Any]:
    ledger = ContributionLedger(args.ledger, _load_key(args.identity))
    return ledger.log_contribution(args.url, args.description)


def _export_proof(args: argparse.Namespace) -> dict[str, Any]:
    ledger = ContributionLedger(args.ledger, _load_key(args.identity))
    return ledger.export_proof(Path(args.path))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flopkit", description="Secure Technocore SDK CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate-identity", help="create an encrypted Ed25519 identity")
    gen.add_argument("--path", default="identity.pem", help="destination encrypted PEM path")
    _add_network_command(sub, "publish", _publish)
    _add_network_command(sub, "check-in", _check_in)
    post = sub.add_parser("post", help="post a signed message to a Technocore room")
    _identity_path(post)
    post.add_argument("room")
    post.add_argument("body")
    post.set_defaults(handler=_post)
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
    return parser


def main() -> None:
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
        print(args.handler(args))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
