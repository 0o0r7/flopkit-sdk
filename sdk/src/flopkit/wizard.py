"""Dependency-free interactive onboarding for the FlopKit CLI."""

from __future__ import annotations

import getpass
from collections.abc import Callable
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .identity import generate_identity, load_identity, public_key_to_did
from .technocore import TechnocoreClient

Input = Callable[[str], str]
Output = Callable[[str], None]


def run(input_fn: Input = input, output: Output = print) -> None:
    """Run the interactive menu without introducing a runtime dependency."""
    while True:
        output("\nFlopKit")
        output("1. Create identity")
        output("2. Show my DID")
        output("3. Send a signed message")
        output("4. Read a Technocore room")
        output("5. Exit")
        choice = input_fn("Select an option: ").strip()
        if choice == "1":
            path = Path(input_fn("Identity path [identity.pem]: ").strip() or "identity.pem")
            _create_identity_with(path, output)
        elif choice == "2":
            path = Path(input_fn("Identity path [identity.pem]: ").strip() or "identity.pem")
            key = _load_identity_key_with(path)
            output(public_key_to_did(key.public_key()))
        elif choice == "3":
            path = Path(input_fn("Identity path [identity.pem]: ").strip() or "identity.pem")
            room = input_fn("Room [technocore]: ").strip() or "technocore"
            text = input_fn("Message: ")
            output(f"Room: {room}")
            output(f"Message: {text}")
            if input_fn("Send signed message? [y/N]: ").strip().lower() != "y":
                output("Cancelled.")
                continue
            key = _load_identity_key_with(path)
            with TechnocoreClient(key) as client:
                result = client.post_message(room, text)
            output(str(result))
        elif choice == "4":
            path = Path(input_fn("Identity path [identity.pem]: ").strip() or "identity.pem")
            room = input_fn("Room [technocore]: ").strip() or "technocore"
            key = _load_identity_key_with(path)
            with TechnocoreClient(key) as client:
                result = client.read_room(room)
            output(str(result))
        elif choice == "5":
            return
        else:
            output("Choose an option from 1 to 5.")


def _create_identity_with(path: Path, output: Output) -> None:
    first = getpass.getpass("Passphrase: ")
    second = getpass.getpass("Confirm passphrase: ")
    if first != second:
        raise ValueError("passphrases do not match")
    _, did = generate_identity(first, path)
    output(f"Created DID: {did}")
    output("Back up the encrypted identity file and its passphrase separately.")


def _load_identity_key_with(path: Path) -> Ed25519PrivateKey:
    return load_identity(path, getpass.getpass("Passphrase: "))
