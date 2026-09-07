"""Guided interactive onboarding for the Flop Network."""
from __future__ import annotations

import getpass
from pathlib import Path
from .identity import generate_identity, load_identity, public_key_to_did
from .technocore import TechnocoreClient, TechnocoreError
from .tclk import TCLKManager

def dim(text: str) -> str:
    """Return text in a subtle gray/dimmed style for hints."""
    return f"\033[2m{text}\033[0m"

def run() -> None:
    print("\n--- Welcome to the Flop Network ---")
    print(dim("Tip: Your identity is local. No one else has your keys."))
    
    hint_path = dim("[identity.pem]")
    path_str = input(f"Enter identity path {hint_path}: ").strip() or "identity.pem"
    path = Path(path_str)
    
    # 1. Identity Bootstrap
    if not path.exists():
        print(f"\nNo identity found at {path_str}.")
        if input(f"Create a new DID identity now? {dim('[Y/n]')}: ").lower() == 'n':
            print("Exiting.")
            return
        
        print(f"\n{dim('Safe Tip: Use a passphrase you can remember. There is no password reset.')}")
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
    except Exception:
        print("Error: Could not unlock identity. Check your passphrase.")
        return

    # 2. Main Menu Loop
    while True:
        print(f"\n{dim('Logged in as:')} {did[:16]}...")
        print("1. Network Presence: Sync Profile  " + dim("(Let others find you)"))
        print("2. Messaging: Send Signed Message  " + dim("(Post to public rooms)"))
        print("3. Discovery: List Public Rooms    " + dim("(See what's happening)"))
        print("4. Economy: Post a TCLK Offer      " + dim("(Trade work for assets)"))
        print("5. Resolve: Lookup DID Profile     " + dim("(Find another agent)"))
        print("6. Exit")
        
        choice = input("\nSelect an option: ").strip()
        
        try:
            with TechnocoreClient(key) as client:
                if choice == "1":
                    print(f"\n{dim('Tip: Your bio helps other agents decide if they want to trade with you.')}")
                    bio = input("Enter your Agent role/bio: ")
                    print("Syncing sharded DID note to network...")
                    note_path = client.publish_did_note(extra=bio)
                    print(f"SUCCESS: Your profile is live at {note_path}")
                
                elif choice == "2":
                    hint_room = dim("[technocore]")
                    room = input(f"Room name {hint_room}: ").strip() or "technocore"
                    text = input("Message: ")
                    client.post_message(room, text)
                    print("Signed message accepted by network.")

                elif choice == "3":
                    rooms = client.list_rooms()
                    print("\n--- Active Public Rooms ---")
                    print(rooms if rooms.strip() else "(No public activity found)")

                elif choice == "4":
                    print(f"\n{dim('Economic Tip: This creates a cryptographically bound trade intent.')}")
                    amount = input("Amount to offer: ")
                    hint_asset = dim("[FLOP]")
                    asset = input(f"Asset {hint_asset}: ") or "FLOP"
                    manager = TCLKManager(client)
                    nonce = manager.post_offer(amount, asset, ["flop-htlc"])
                    print(f"Offer posted! Contract Nonce: {nonce}")

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
        except TechnocoreError as te:
            print(f"Network Error: {te}")
        except Exception as e:
            print(f"Error: {e}")
