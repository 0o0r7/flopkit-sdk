from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from .identity import generate_identity, load_identity
from .ledger import ContributionLedger


def main() -> None:
    parser = argparse.ArgumentParser(prog="flopkit")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate-identity")
    gen.add_argument("--path", default="identity.pem")
    log = sub.add_parser("log")
    log.add_argument("url")
    log.add_argument("description")
    log.add_argument("--identity", default="identity.pem")
    log.add_argument("--ledger", default="contributions.ledger")
    export = sub.add_parser("export-proof")
    export.add_argument("path")
    export.add_argument("--identity", default="identity.pem")
    export.add_argument("--ledger", default="contributions.ledger")
    args = parser.parse_args()
    if args.command == "generate-identity":
        first = getpass.getpass("Passphrase: ")
        second = getpass.getpass("Confirm passphrase: ")
        if first != second:
            raise SystemExit("passphrases do not match")
        _, did = generate_identity(first, args.path)
        print(did)
        return
    key = load_identity(args.identity, getpass.getpass("Passphrase: "))
    ledger = ContributionLedger(args.ledger, key)
    if args.command == "log":
        print(ledger.log_contribution(args.url, args.description))
    elif args.command == "export-proof":
        print(ledger.export_proof(Path(args.path)))
