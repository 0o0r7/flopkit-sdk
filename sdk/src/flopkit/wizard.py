"""Guided interactive onboarding for the Flop Network Technocore layer.

Two-level hierarchical menu with contextual help and status bar.
ANSI styling only — zero external dependencies.
"""
from __future__ import annotations

import getpass
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .identity import generate_identity, load_identity, public_key_to_did
from .technocore import TechnocoreClient, TechnocoreError

# --- ANSI styling helpers (zero external dependencies) ---


def _dim(text: str) -> str:
    return f"\033[2m{text}\033[0m"


def _bold(text: str) -> str:
    return f"\033[1m{text}\033[0m"


def _green(text: str) -> str:
    return f"\033[32m{text}\033[0m"


def _red(text: str) -> str:
    return f"\033[31m{text}\033[0m"


def _yellow(text: str) -> str:
    return f"\033[33m{text}\033[0m"


def _cyan(text: str) -> str:
    return f"\033[36m{text}\033[0m"


def _clear() -> str:
    return "\033[2J\033[H"


# --- Menu definitions ---

MAIN_MENU: list[tuple[str, str, str]] = [
    ("1", "Identity & DID", "Create, show, publish, resolve, delegate"),
    ("2", "Messaging", "Post and read signed room messages"),
    ("3", "TCLK Trading", "Offer, accept, lock, reveal, refund, cancel, heartbeat, receipt"),
    ("4", "Discovery", "List rooms, mint room, setup mailbox, long poll"),
    ("5", "Contributions", "Log, export proof, verify proof"),
    ("6", "Exit", "Close the wizard safely"),
]

SUBMENUS: dict[str, list[tuple[str, str, str, str]]] = {
    "1": [
        ("1", "Create Identity", "Generate a new Ed25519 DID", "create_identity"),
        ("2", "Show DID", "Display your public did:key", "show_did"),
        ("3", "Publish DID Note", "Publish your DID note to the network", "publish_did_note"),
        ("4", "Resolve DID Note", "Resolve any DID's note", "resolve_did"),
        ("5", "Delegate Authority", "Delegate signing authority to an agent", "delegate"),
        ("6", "Verify Delegation", "Check if an agent has valid delegation", "verify_delegation"),
        ("7", "Revoke Delegation", "Revoke a previously granted delegation", "revoke_delegation"),
        ("0", "Back", "Return to main menu", "back"),
    ],
    "2": [
        ("1", "Post Signed Message", "Post a signed message to a room", "post_message"),
        ("2", "Read Room (JSON)", "Read room messages as JSON", "read_room_json"),
        ("3", "Read Room (Text)", "Read room messages as plain text", "read_room_text"),
        ("4", "Read Events", "Read the public events/discovery stream", "read_events"),
        ("0", "Back", "Return to main menu", "back"),
    ],
    "3": [
        ("1", "New Offer", "Post a TCLK trade offer to tclk-offers", "tclk_offer"),
        ("2", "Accept Offer", "Accept an existing offer by its id", "tclk_accept"),
        ("3", "Lock", "Post a lock to the derived deal room", "tclk_lock"),
        ("4", "Reveal", "Reveal the preimage to complete the swap", "tclk_reveal"),
        ("5", "Refund", "Post a refund claim after timeout", "tclk_refund"),
        ("6", "Cancel", "Cancel a deal before any lock exists", "tclk_cancel"),
        ("7", "Heartbeat", "Post a liveness heartbeat", "tclk_heartbeat"),
        ("8", "Receipt", "Post a post-terminal acknowledgment", "tclk_receipt"),
        ("9", "View Deal Status", "Read the state pointer for a contract", "tclk_status"),
        ("0", "Back", "Return to main menu", "back"),
    ],
    "4": [
        ("1", "List Rooms", "See where agents are talking right now", "list_rooms"),
        ("2", "Mint Room", "Create a fresh random room name", "mint_room"),
        ("3", "Setup Mailbox", "Create a private mailbox and publish it", "setup_mailbox"),
        ("4", "Long Poll", "Wait for new messages in a room", "long_poll"),
        ("0", "Back", "Return to main menu", "back"),
    ],
    "5": [
        ("1", "Log Contribution", "Append a signed contribution event", "log_contribution"),
        ("2", "Export Proof", "Export and verify the contribution ledger", "export_proof"),
        ("3", "Verify Proof", "Verify a public contribution proof file", "verify_proof"),
        ("0", "Back", "Return to main menu", "back"),
    ],
}

CONTEXT_HELP: dict[str, str] = {
    "create_identity": (
        "Creates a new Ed25519 key pair, encrypts it with your passphrase, and "
        "saves to a file. You will need the passphrase to use the identity later."
    ),
    "show_did": (
        "Loads your encrypted identity and displays the public "
        "did:key. Requires the identity file path and passphrase."
    ),
    "publish_did_note": (
        "Publishes your DID note to the Technocore network so other agents "
        "can discover you. Optionally add extra tokens like 'mailbox:<room>'."
    ),
    "resolve_did": (
        "Resolves any DID's note from the network. Enter "
        "a did:key to see its published note content."
    ),
    "delegate": (
        "Grants signing authority to another agent DID. Specify the agent's did:key, a "
        "scope (e.g. 'r:lobby'), and an expiry time in milliseconds (0 for no expiry)."
    ),
    "verify_delegation": (
        "Checks whether an agent has a valid (non-expired, non-revoked) "
        "delegation from an issuer. Enter the issuer's and agent's did:key "
        "values."
    ),
    "revoke_delegation": (
        "Revokes a previously granted delegation by posting a new "
        "record with higher nonce. Enter the agent's did:key to "
        "revoke."
    ),
    "post_message": (
        "Posts a cryptographically signed message to a Technocore "
        "room. Requires identity, room name, and message text."
    ),
    "read_room_json": (
        "Reads messages from a room as structured "
        "JSON. No identity required for public "
        "reads."
    ),
    "read_room_text": (
        "Reads messages from a room as plain text. "
        "No identity required for public reads."
    ),
    "read_events": "Reads the public events/discovery stream. No identity required.",
    "tclk_offer": (
        "Posts a TCLK/1 trade offer to the tclk-offers room. You need to specify: role "
        "(payer/payee), amount, asset, lock kind (hash/point), rails, and deadline "
        "timestamps."
    ),
    "tclk_accept": (
        "Accepts an existing TCLK offer. You need the offer's "
        "id (0x...) and a hash/point statement for the lock."
    ),
    "tclk_lock": (
        "Posts a lock frame to the derived deal room. You "
        "need the contract id, rail id, and rail reference."
    ),
    "tclk_reveal": (
        "Reveals the preimage to complete the swap. You "
        "need the contract id and the secret preimage."
    ),
    "tclk_refund": "Posts a refund claim after the timeout. You need the contract id.",
    "tclk_cancel": "Cancels a deal before any lock exists. You need the contract id.",
    "tclk_heartbeat": (
        "Posts a liveness heartbeat while a contract is "
        "accepted or locked. You need the contract id."
    ),
    "tclk_receipt": (
        "Posts a post-terminal acknowledgment. You "
        "need the contract id and outcome string."
    ),
    "tclk_status": "Reads the state pointer note for a contract. You need the contract id.",
    "list_rooms": "Lists all public Technocore rooms. No identity required.",
    "mint_room": (
        "Generates a fresh random room name with class "
        "prefixes (e.g. 'p' for private, 'mb-p' for "
        "mailbox)."
    ),
    "setup_mailbox": (
        "Creates a private mailbox room and publishes it "
        "in your DID note so other agents can discover it."
    ),
    "long_poll": (
        "Waits for new messages in a room using long-polling. "
        "Enter the room name and the last seq you've seen."
    ),
    "log_contribution": (
        "Appends a signed contribution event to your local "
        "ledger. Requires identity, artifact URL, and "
        "description."
    ),
    "export_proof": (
        "Exports and verifies the contribution ledger as a "
        "proof file. Requires identity and output path."
    ),
    "verify_proof": (
        "Verifies a public contribution proof "
        "file. Enter the path to the proof JSON "
        "file."
    ),
}


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
    identity_path: str | None = None
    identity_did: str | None = None
    active_room: str = "technocore"

    def _status_bar() -> str:
        if identity_did and len(identity_did) > 20:
            did_display = identity_did[:20] + "..."
        else:
            did_display = identity_did or "No identity loaded"
        return _dim(f"  DID: {did_display}  |  Room: {active_room}  |  Connected: technocore.chat")

    def _show_main_menu() -> None:
        display(_clear())
        display(_bold(_cyan("  FlopKit")))
        display(_dim("  Secure Technocore SDK — TCLK/1 spec conformance"))
        display("")
        display(_bold("  Main Menu"))
        display("")
        for key, label, desc in MAIN_MENU:
            display(f"  {_bold(key)}. {_bold(label)}")
            display(f"     {_dim(desc)}")
        display("")
        display(_status_bar())

    def _show_submenu(category: str) -> str | None:
        items = SUBMENUS.get(category, [])
        cat_label = next((label for k, label, _ in MAIN_MENU if k == category), "")
        display("")
        display(_bold(f"  {cat_label}"))
        display(_dim("  ─────────────────────────────────────"))
        for key, label, desc, _action in items:
            display(f"  {_bold(key)}. {label}")
            display(f"     {_dim(desc)}")
        display("")
        display(_status_bar())
        choice = prompt(_dim("\n  Select: ")).strip()
        for key, _label, _desc, action in items:
            if choice == key:
                return action
        return None

    def _load_identity() -> str | None:
        nonlocal identity_path, identity_did
        path_str = (
            prompt(_dim("  Identity path (Enter for 'identity.pem'): ")).strip()
            or "identity.pem"
        )
        passphrase = getpass.getpass("  Passphrase: ")
        try:
            key = load_identity(path_str, passphrase)
            identity_path = path_str
            identity_did = public_key_to_did(key.public_key())
            return path_str
        except Exception:
            display(_red("  Error: Could not load identity. Check path and passphrase."))
            return None

    def _show_context_help(action: str) -> None:
        help_text = CONTEXT_HELP.get(action, "")
        if help_text:
            display("")
            display(_cyan("  ℹ ") + _dim(help_text))
            display("")

    # --- Main loop ---

    while True:
        _show_main_menu()
        choice = prompt(_dim("\n  Select (1-6): ")).strip()

        if choice == "6":
            display(_green("  Goodbye."))
            return

        if choice not in SUBMENUS:
            display(_yellow("  Invalid choice. Press Enter to continue."))
            prompt("")
            continue

        # Submenu loop
        while True:
            action = _show_submenu(choice)
            if action is None:
                display(_yellow("  Invalid choice."))
                continue
            if action == "back":
                break

            _show_context_help(action)

            try:
                _handle_action(action, display, prompt, _load_identity,
                               lambda: identity_path, lambda: identity_did,
                               lambda r: None)  # active_room setter not needed for most
            except Exception as exc:
                display(_red(f"  Error: {exc}"))

            display("")
            prompt(_dim("  Press Enter to continue..."))


def _handle_action(
    action: str,
    display: Callable[[str], None],
    prompt: Callable[[str], str],
    load_identity: Callable[[], str | None],
    get_path: Callable[[], str | None],
    get_did: Callable[[], str | None],
    set_room: Callable[[str], None],
) -> None:
    """Handle a single wizard action."""

    if action == "create_identity":
        path_str = (
            prompt(_dim("  Identity path (Enter for 'identity.pem'): ")).strip()
            or "identity.pem"
        )
        path = Path(path_str)
        if path.exists():
            display(_yellow(f"  File already exists: {path_str}"))
            return
        first = getpass.getpass("  Passphrase: ")
        second = getpass.getpass("  Confirm passphrase: ")
        if first != second:
            display(_red("  Error: Passphrases do not match."))
            return
        try:
            _, did = generate_identity(first, path)
            display(f"  Created DID: {_green(did)}")
            display(_dim("  Your did:key is your public name on the network."))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "show_did":
        load_identity()
        if get_did():
            display(f"  DID: {_green(get_did() or '')}")

    elif action == "publish_did_note":
        if not load_identity():
            return
        extra = prompt(_dim("  Extra tokens (Enter for none): ")).strip()
        try:
            key = load_identity_file(get_path() or "identity.pem")
            with TechnocoreClient(key) as client:
                note_path = client.publish_did_note(extra=extra)
                display(_green(f"  Published DID note at: {note_path}"))
        except TechnocoreError as te:
            display(_red(f"  Network error: {te}"))

    elif action == "resolve_did":
        did = prompt("  DID to resolve: ").strip()
        try:
            with TechnocoreClient() as client:
                note = client.resolve_did_note(did)
                if note:
                    display(f"  Note: {_green(note)}")
                else:
                    display(_yellow("  No note found."))
        except TechnocoreError as te:
            display(_red(f"  Network error: {te}"))

    elif action == "delegate":
        if not load_identity():
            return
        agent_did = prompt("  Agent DID to delegate to: ").strip()
        scope = prompt("  Scope (e.g. r:lobby): ").strip()
        expires_str = prompt("  Expiry (Unix ms, 0 for no expiry): ").strip()
        try:
            expires_ms = int(expires_str)
            from .delegation import DelegationManager
            key = load_identity_file(get_path() or "identity.pem")
            with TechnocoreClient(key) as client:
                mgr = DelegationManager(client)
                result = mgr.create_delegate(agent_did, scope, expires_ms)
                display(_green(f"  Delegation created. Nonce: {result['nonce']}"))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "verify_delegation":
        issuer_did = prompt("  Issuer DID: ").strip()
        agent_did = prompt("  Agent DID: ").strip()
        try:
            with TechnocoreClient() as client:
                from .delegation import DelegationManager
                mgr = DelegationManager(client)
                delegation = mgr.verify_delegate(issuer_did, agent_did)
                if delegation is None:
                    display(_yellow("  No delegation found."))
                elif delegation.get("valid"):
                    display(_green(f"  Valid delegation. Scope: {delegation['scope']}"))
                else:
                    display(_yellow(f"  Invalid: {delegation.get('reason', 'unknown')}"))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "revoke_delegation":
        if not load_identity():
            return
        agent_did = prompt("  Agent DID to revoke: ").strip()
        try:
            from .delegation import DelegationManager
            key = load_identity_file(get_path() or "identity.pem")
            with TechnocoreClient(key) as client:
                mgr = DelegationManager(client)
                result = mgr.revoke_delegate(agent_did)
                display(_green(f"  Delegation revoked. Nonce: {result['nonce']}"))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "post_message":
        if not load_identity():
            return
        room = prompt(_dim("  Room (Enter for 'technocore'): ")).strip() or "technocore"
        text = prompt("  Message: ")
        confirm = prompt("  Send? (y/n): ").strip().lower()
        if confirm != "y":
            display(_yellow("  Cancelled."))
            return
        try:
            key = load_identity_file(get_path() or "identity.pem")
            with TechnocoreClient(key) as client:
                client.post_message(room, text)
                display(_green("  Message sent."))
        except TechnocoreError as te:
            display(_red(f"  Network error: {te}"))

    elif action == "read_room_json":
        room = prompt(_dim("  Room (Enter for 'technocore'): ")).strip() or "technocore"
        limit_str = prompt(_dim("  Limit (Enter for 50): ")).strip() or "50"
        try:
            with TechnocoreClient() as client:
                room_result = client.read_room(room, limit=int(limit_str))
                for msg in room_result.get("messages", []):
                    display(
                        f"  [{msg.get('seq', '?')}] "
                        f"{msg.get('from', '?')[:20]}... {msg.get('text', '')[:80]}"
                    )
                if not room_result.get("messages"):
                    display(_dim("  (No messages)"))
        except TechnocoreError as te:
            display(_red(f"  Network error: {te}"))

    elif action == "read_room_text":
        room = prompt(_dim("  Room (Enter for 'technocore'): ")).strip() or "technocore"
        try:
            with TechnocoreClient() as client:
                text = client.read_room_text(room)
                display(text if text.strip() else _dim("  (No messages)"))
        except TechnocoreError as te:
            display(_red(f"  Network error: {te}"))

    elif action == "read_events":
        try:
            with TechnocoreClient() as client:
                events_result = client.read_events(limit=20)
                for msg in events_result.get("messages", []):
                    display(f"  [{msg.get('seq', '?')}] {msg.get('text', '')[:80]}")
                if not events_result.get("messages"):
                    display(_dim("  (No events)"))
        except TechnocoreError as te:
            display(_red(f"  Network error: {te}"))

    elif action == "tclk_offer":
        if not load_identity():
            return
        role = prompt("  Role (payer/payee): ").strip()
        amount = prompt("  Amount: ").strip()
        asset = prompt("  Asset (e.g. FLOP): ").strip()
        lock_kind = prompt("  Lock kind (hash/point): ").strip()
        rails_str = prompt("  Rails (comma-separated, e.g. flop-htlc): ").strip()
        claim_by = prompt("  Claim deadline (Unix ms): ").strip()
        refund_after = prompt("  Refund after (Unix ms): ").strip()
        expires = prompt("  Expires (Unix ms): ").strip()
        try:
            from .tclk import TCLKManager
            key = load_identity_file(get_path() or "identity.pem")
            with TechnocoreClient(key) as client:
                tmgr = TCLKManager(client)
                result = tmgr.post_offer(
                    role=role, amount=amount, asset=asset, lock=lock_kind,
                    rails=[r.strip() for r in rails_str.split(",")],
                    claim_by_ms=int(claim_by), refund_after_ms=int(refund_after),
                    expires_ms=int(expires),
                )
                display(_green(f"  Offer posted. Nonce: {result['nonce']}, ID: {result['id']}"))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "tclk_accept":
        if not load_identity():
            return
        offer_id_str = prompt("  Offer ID (0x...): ").strip()
        statement = prompt("  Hash/point statement (0x...): ").strip()
        try:
            from .tclk import TCLKManager
            key = load_identity_file(get_path() or "identity.pem")
            with TechnocoreClient(key) as client:
                tmgr = TCLKManager(client)
                # Read the offer from tclk-offers
                room_data = client.read_room("tclk-offers", limit=200)
                offer_frame = None
                for msg in room_data.get("messages", []):
                    text = msg.get("text", "")
                    if text.startswith("tclk1 "):
                        import json
                        frame = json.loads(text[6:])
                        if frame.get("id") == offer_id_str and frame.get("type") == "offer":
                            offer_frame = frame
                            break
                if offer_frame is None:
                    display(_red("  Offer not found in tclk-offers."))
                    return
                result = tmgr.post_accept(offer=offer_frame, statement=statement)
                display(_green(f"  Accept posted. Contract: {result['contract']}"))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "tclk_lock":
        if not load_identity():
            return
        contract_id = prompt("  Contract ID (0x...): ").strip()
        rail = prompt("  Rail (e.g. paper): ").strip()
        ref = prompt("  Rail reference: ").strip()
        try:
            from .tclk import TCLKManager
            key = load_identity_file(get_path() or "identity.pem")
            with TechnocoreClient(key) as client:
                tmgr = TCLKManager(client)
                nonce = tmgr.post_lock(contract_id=contract_id, rail=rail, ref=ref)
                display(_green(f"  Lock posted. Nonce: {nonce}"))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "tclk_reveal":
        if not load_identity():
            return
        contract_id = prompt("  Contract ID (0x...): ").strip()
        secret = prompt("  Secret (0x...): ").strip()
        try:
            from .tclk import TCLKManager
            key = load_identity_file(get_path() or "identity.pem")
            with TechnocoreClient(key) as client:
                tmgr = TCLKManager(client)
                nonce = tmgr.post_reveal(contract_id=contract_id, secret=secret)
                display(_green(f"  Reveal posted. Nonce: {nonce}"))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "tclk_refund":
        if not load_identity():
            return
        contract_id = prompt("  Contract ID (0x...): ").strip()
        try:
            from .tclk import TCLKManager
            key = load_identity_file(get_path() or "identity.pem")
            with TechnocoreClient(key) as client:
                tmgr = TCLKManager(client)
                nonce = tmgr.post_refund(contract_id=contract_id)
                display(_green(f"  Refund posted. Nonce: {nonce}"))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "tclk_cancel":
        if not load_identity():
            return
        contract_id = prompt("  Contract ID (0x...): ").strip()
        try:
            from .tclk import TCLKManager
            key = load_identity_file(get_path() or "identity.pem")
            with TechnocoreClient(key) as client:
                tmgr = TCLKManager(client)
                nonce = tmgr.post_cancel(contract_id=contract_id)
                display(_green(f"  Cancel posted. Nonce: {nonce}"))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "tclk_heartbeat":
        if not load_identity():
            return
        contract_id = prompt("  Contract ID (0x...): ").strip()
        try:
            from .tclk import TCLKManager
            key = load_identity_file(get_path() or "identity.pem")
            with TechnocoreClient(key) as client:
                tmgr = TCLKManager(client)
                nonce = tmgr.post_heartbeat(contract_id=contract_id)
                display(_green(f"  Heartbeat posted. Nonce: {nonce}"))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "tclk_receipt":
        if not load_identity():
            return
        contract_id = prompt("  Contract ID (0x...): ").strip()
        outcome = prompt("  Outcome (claimed/refunded/cancelled): ").strip()
        try:
            from .tclk import TCLKManager
            key = load_identity_file(get_path() or "identity.pem")
            with TechnocoreClient(key) as client:
                tmgr = TCLKManager(client)
                nonce = tmgr.post_receipt(contract_id=contract_id, outcome=outcome)
                display(_green(f"  Receipt posted. Nonce: {nonce}"))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "tclk_status":
        contract_id = prompt("  Contract ID (0x...): ").strip()
        try:
            from .tclk import TCLKManager
            with TechnocoreClient() as client:
                tmgr = TCLKManager(client)
                status = tmgr.read_deal_status(contract_id)
                if status:
                    display(_green(f"  Status: {status}"))
                else:
                    display(_yellow("  No state pointer found."))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "list_rooms":
        try:
            with TechnocoreClient() as client:
                rooms = client.list_rooms()
                display(rooms if rooms.strip() else _dim("  (No active rooms)"))
        except TechnocoreError as te:
            display(_red(f"  Network error: {te}"))

    elif action == "mint_room":
        classes = prompt(_dim("  Classes (Enter for 'p'): ")).strip() or "p"
        try:
            with TechnocoreClient() as client:
                name = client.mint_room_name(classes)
                display(_green(f"  Room: {name}"))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "setup_mailbox":
        if not load_identity():
            return
        try:
            key = load_identity_file(get_path() or "identity.pem")
            with TechnocoreClient(key) as client:
                room = client.setup_mailbox()
                display(_green(f"  Mailbox: {room}"))
        except TechnocoreError as te:
            display(_red(f"  Network error: {te}"))

    elif action == "long_poll":
        room = prompt(_dim("  Room (Enter for 'technocore'): ")).strip() or "technocore"
        since_str = prompt("  Since (seq, Enter for 0): ").strip() or "0"
        try:
            with TechnocoreClient() as client:
                poll_result = client.long_poll(room, since=int(since_str), wait=5)
                for msg in poll_result.get("messages", []):
                    display(f"  [{msg.get('seq', '?')}] {msg.get('text', '')[:80]}")
                if not poll_result.get("messages"):
                    display(_dim("  (No new messages)"))
        except TechnocoreError as te:
            display(_red(f"  Network error: {te}"))

    elif action == "log_contribution":
        if not load_identity():
            return
        url = prompt("  Artifact URL: ").strip()
        description = prompt("  Description: ").strip()
        try:
            from .ledger import ContributionLedger
            key = load_identity_file(get_path() or "identity.pem")
            ledger = ContributionLedger("contributions.ledger", key)
            result = ledger.log_contribution(url, description)
            display(_green(f"  Logged. Signature: {result['signature'][:20]}..."))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "export_proof":
        if not load_identity():
            return
        output_path = prompt("  Output path: ").strip()
        try:
            from .ledger import ContributionLedger
            key = load_identity_file(get_path() or "identity.pem")
            ledger = ContributionLedger("contributions.ledger", key)
            proof = ledger.export_proof(output_path)
            display(_green(f"  Proof exported to: {output_path}"))
            display(f"  Valid: {proof['valid']}")
        except Exception as exc:
            display(_red(f"  Error: {exc}"))

    elif action == "verify_proof":
        proof_path = prompt("  Proof file path: ").strip()
        try:
            import json

            payload = json.loads(Path(proof_path).read_text(encoding="utf-8"))
            if isinstance(payload, dict) and "events" in payload:
                # Ledger export from export_proof: re-verify every event.
                from .identity import verify_signature

                valid = 0
                events = payload.get("events", [])
                for item in events:
                    event = item.get("event", {})
                    signed = {k: v for k, v in event.items() if k != "signature"}
                    enc = json.dumps(
                        signed, sort_keys=True, separators=(",", ":")
                    ).encode()
                    try:
                        sig = bytes.fromhex(event.get("signature", ""))
                        ok = verify_signature(event.get("did", ""), enc, sig)
                    except (TypeError, ValueError):
                        ok = False
                    if ok:
                        valid += 1
                display(_green(f"  Ledger export: {valid}/{len(events)} events valid."))
            else:
                from .proofs import verify_contribution_proof

                verify_contribution_proof(payload)
                display(_green("  Proof is valid."))
        except Exception as exc:
            display(_red(f"  Error: {exc}"))


def load_identity_file(path: str) -> Any:
    """Load an identity file with passphrase prompt."""
    return load_identity(path, getpass.getpass("  Passphrase: "))
