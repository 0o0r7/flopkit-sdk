"""Guided interactive onboarding for the Flop Network Technocore layer."""
from __future__ import annotations

import getpass
from collections.abc import Callable
from pathlib import Path

from .identity import generate_identity, load_identity, public_key_to_did
from .technocore import TechnocoreClient, TechnocoreError

# --- ANSI styling helpers (zero external dependencies) ---


def _dim(text: str) -> str:
    """Return text in a subtle dimmed style."""
    return f"\033[2m{text}\033[0m"


def _bold(text: str) -> str:
    """Return text in bold."""
    return f"\033[1m{text}\033[0m"


def _green(text: str) -> str:
    """Return text in green."""
    return f"\033[32m{text}\033[0m"


def _red(text: str) -> str:
    """Return text in red."""
    return f"\033[31m{text}\033[0m"


def _yellow(text: str) -> str:
    """Return text in yellow."""
    return f"\033[33m{text}\033[0m"


def run(
    prompt_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    """Run the interactive wizard with injectable I/O for testing.

    Args:
        prompt_fn: callable that takes a prompt string and returns user input.
        output_fn: callable that takes a display string and presents it.
    """
    display = output_fn
    prompt = prompt_fn

    display("\nFlopKit")
    display(_dim("Secure Technocore SDK — guided onboarding"))

    while True:
        display(_bold("\n--- Main Menu ---"))
        display("1. Create Identity")
        display("2. Show DID")
        display("3. Post Message")
        display("4. List Rooms")
        display("5. Exit")

        choice = prompt("\nSelect (1-5): ").strip()

        if choice == "1":
            path_str = (
                prompt(_dim("Identity path (Press Enter for 'identity.pem'): ")).strip()
                or "identity.pem"
            )
            path = Path(path_str)
            if path.exists():
                display(_yellow(f"File already exists: {path_str}"))
                continue
            first = getpass.getpass("Passphrase: ")
            second = getpass.getpass("Confirm passphrase: ")
            if first != second:
                display(_red("Error: Passphrases do not match."))
                continue
            try:
                _, did = generate_identity(first, path)
                display(f"Created DID: {did}")
                display(_dim("Your did:key is your public name on the network."))
            except Exception as exc:
                display(_red(f"Error: {exc}"))

        elif choice == "2":
            path_str = (
                prompt(_dim("Identity path (Press Enter for 'identity.pem'): ")).strip()
                or "identity.pem"
            )
            passphrase = getpass.getpass("Passphrase: ")
            try:
                key = load_identity(path_str, passphrase)
                did = public_key_to_did(key.public_key())
                display(did)
            except Exception:
                display(_red("Error: Could not load identity. Check path and passphrase."))

        elif choice == "3":
            path_str = (
                prompt(_dim("Identity path (Press Enter for 'identity.pem'): ")).strip()
                or "identity.pem"
            )
            room = prompt(_dim("Room (Press Enter for 'technocore'): ")).strip() or "technocore"
            text = prompt("Message: ")
            confirm = prompt("Send? (y/n): ").strip().lower()
            if confirm != "y":
                display("Cancelled.")
                continue
            try:
                passphrase = getpass.getpass("Passphrase: ")
                key = load_identity(path_str, passphrase)
                with TechnocoreClient(key) as client:
                    client.post_message(room, text)
                    display(_green("Message sent."))
            except TechnocoreError as te:
                display(_red(f"Network error: {te}"))
            except Exception as exc:
                display(_red(f"Error: {exc}"))

        elif choice == "4":
            try:
                with TechnocoreClient() as client:
                    rooms = client.list_rooms()
                    display(rooms if rooms.strip() else _dim("(No active rooms)"))
            except TechnocoreError as te:
                display(_red(f"Network error: {te}"))

        elif choice == "5":
            return
