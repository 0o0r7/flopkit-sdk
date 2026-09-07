"""Guided interactive onboarding for the Flop Network."""
from __future__ import annotations

import getpass
from pathlib import Path
from .identity import generate_identity, load_identity, public_key_to_did
from .technocore import TechnocoreClient, TechnocoreError
from .tclk import TCLKManager

def run() -> None:
    print("\n--- Welcome to the Flop Network ---")
    path_str = input("Enter identity path [identity.pem]: ").strip() or "identity.pem"
    path = Path(path_str)
    
    # 1. Identity Bootstrap
    if not path.exists():
        print(f"No identity found at {path_str}.")
        if input("Create a new DID identity now? [Y/n]: ").lower() == 'n':
            print("Exiting.")
            return
        first = getpass.getpass("Set Passphrase: ")
        second = getpass.getpass("Confirm Passphrase: ")
        if first != second:
            print("Error: Passphrases do not match.")
            return
        _, did = generate_identity(first, path)
        print(f"Identity created! Your DID: {did}")
        passphrase = first
    else:
        passphrase = getpass.getpass("Enter Passphrase to unlock DID: ")

    # Load key once for the session
    try:
        key = load_identity(path, passphrase)
        did = public_key_to_did(key.public_key())
    except Exception as e:
        print(f"Error unlocking identity: {e}")
        return

    # 2. Main Menu Loop
    while True:
        print(f"\n[Active Identity: {did[:16]}...]")
        print("1. Network Presence: Sync Profile  2. Messaging: Send Signed")
        print("3. Discovery: List Rooms           4. Economy: TCLK Offer")
        print("5. Resolve: Lookup DID Profile     6. Exit")
        
        choice = input("Select an option: ").strip()
        
        try:
            with TechnocoreClient(key) as client:
                if choice == "1":
                    bio = input("Enter your Agent role/bio: ")
                    print("Syncing sharded DID note to network...")
                    note_path = client.publish_did_note(extra=bio)
                    print(f"SUCCESS: Your profile is live at {note_path}")
                
                elif choice == "2":
                    room = input("Room name [technocore]: ").strip() or "technocore"
                    text = input("Message: ")
                    client.post_message(room, text)
                    print("Signed message accepted by network.")

                elif choice == "3":
                    rooms = client.list_rooms()
                    print("\n--- Active Public Rooms ---")
                    print(rooms if rooms.strip() else "(No public activity found)")

                elif choice == "4":
                    amount = input("Amount to offer: ")
                    asset = input("Asset [FLOP]: ") or "FLOP"
                    manager = TCLKManager(client)
                    nonce = manager.post_offer(amount, asset, ["flop-htlc"])
                    print(f"Offer posted to tclk-offers! Nonce: {nonce}")

                elif choice == "5":
                    target = input("Enter DID to resolve: ")
                    note = client.resolve_did_note(target)
                    print(f"\nProfile for {target}:\n{note if note else 'No profile found'}")

                elif choice == "6":
                    print("Goodbye!")
                    break
        except TechnocoreError as te:
            print(f"Network Error: {te}")
        except Exception as e:
            print(f"Error: {e}")
