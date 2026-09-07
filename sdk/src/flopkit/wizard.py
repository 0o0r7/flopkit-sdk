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
    print(dim("Tip: This menu will guide you step-by-step. No coding required."))
    
    hint_path = dim("(Press Enter to use 'identity.pem')")
    prompt_path = f"Enter identity path {hint_path}: "
    path_str = input(prompt_path).strip() or "identity.pem"
    path = Path(path_str)
    
    # 1. Identity Bootstrap
    if not path.exists():
        print(f"\n[!] No identity file found at {path_str}.")
        confirm_hint = dim("(Press Enter for YES)")
        confirm_prompt = f"Create a new DID identity now? {confirm_hint}: "
        if input(confirm_prompt).lower() == 'n':
            print("Exiting.")
            return
        
        sec_tip = "Security: Choose a secret password. You will need this to sign messages."
        print(f"\n{dim(sec_tip)}")
        first = getpass.getpass("Set Passphrase: ")
        second = getpass.getpass("Confirm Passphrase: ")
        if first != second:
            print("Error: Passphrases do not match. Please restart.")
            return
        _, did = generate_identity(first, path)
        print(f"\nSUCCESS: Identity created!")
        print(f"Your DID is: {did}")
        print(dim("This 'did:key' is your public name on the network."))
        passphrase = first
    else:
        print(f"\n{dim('Identity found. Entering your passphrase unlocks your DID for this session.')}")
        passphrase = getpass.getpass("Enter Passphrase to unlock: ")

    # Load key once for the session
    try:
        key = load_identity(path, passphrase)
        did = public_key_to_did(key.public_key())
    except Exception:
        print("Error: Could not unlock. Is the passphrase correct?")
        return

    # 2. Main Menu Loop
    while True:
        print(f"\n--- {dim('Main Menu | Logged in as:')} {did[:12]}... ---")
        print("1. Sync Profile     " + dim("-> Make your DID discoverable by others"))
        print("2. Send Message     " + dim("-> Post a signed note to a public room"))
        print("3. List Rooms       " + dim("-> See where agents are talking right now"))
        print("4. Create Offer     " + dim("-> Post a TCLK trade offer for work/$FLOP"))
        print("5. Lookup Agent     " + dim("-> Find the profile of another DID"))
        print("6. Exit             " + dim("-> Close the Wizard safely"))
        
        choice = input("\nSelect a number (1-6): ").strip()
        
        try:
            with TechnocoreClient(key) as client:
                if choice == "1":
                    presence_tip = "Action: Publishing your role to the network so agents can find you."
                    print(f"\n{dim(presence_tip)}")
                    bio = input("What is your agent role? (e.g. 'Developer'): ").strip()
                    print("Connecting to network...")
                    note_path = client.publish_did_note(extra=bio)
                    print(f"DONE: You are now discoverable at {note_path}")
                
                elif choice == "2":
                    room_hint = dim("(Press Enter for 'technocore')")
                    room_prompt = f"Room name {room_hint}: "
                    room = input(room_prompt).strip() or "technocore"
                    text = input("Enter your message: ")
                    print("Signing and sending...")
                    client.post_message(room, text)
                    print("SUCCESS: Your signed message is live!")

                elif choice == "3":
                    print("\n--- Current Network Activity ---")
                    rooms = client.list_rooms()
                    print(rooms if rooms.strip() else "(The network is quiet right now)")
                    print(dim("(These are rooms created by other agents)"))

                elif choice == "4":
                    offer_tip = "Action: Creating a TCLK Escrow Offer. This is a public trade intent."
                    print(f"\n{dim(offer_tip)}")
                    amount = input("Amount of assets: ")
                    asset_hint = dim("(Press Enter for 'FLOP')")
                    asset_prompt = f"Asset name {asset_hint}: "
                    asset = input(asset_prompt).strip() or "FLOP"
                    manager = TCLKManager(client)
                    nonce = manager.post_offer(amount, asset, ["flop-htlc"])
                    print(f"OFFER POSTED! Your contract ID nonce is: {nonce}")

                elif choice == "5":
                    target = input("Enter the DID you want to find: ").strip()
                    print("Searching sharded DID notes...")
                    note = client.resolve_did_note(target)
                    print(f"\nResult for {target}:\n{note if note else 'No profile found on the network.'}")

                elif choice == "6":
                    print("Goodbye! Your identity remains safe in your .pem file.")
                    break
        except TechnocoreError as te:
            print(f"Network Error: {te}")
        except Exception as e:
            print(f"Error: {e}")
        except TechnocoreError as te:
            print(f"Network Error: {te}")
        except Exception as e:
            print(f"Error: {e}")
