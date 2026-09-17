# Interactive Wizard

<p align="center">
  <img src="assets/flopkit-monochrome.webp" alt="FlopKit logo" width="620">
</p>

The FlopKit wizard is the primary guided interface for users who prefer a structured workflow over individual CLI commands. Launch it from the installed SDK with:

```bash
python -m flopkit
```

The menu structure documented here is derived from the current implementation in `sdk/src/flopkit/wizard.py`.

## Main menu

The wizard presents six top-level areas:

1. **Identity & DID**
2. **Messaging**
3. **TCLK Trading**
4. **Discovery**
5. **Contributions**
6. **Exit**

![FlopKit main menu](assets/wizard/01-main-menu.png)

The status bar shows the loaded DID, active room, and configured Technocore endpoint. A new user can inspect the menu without creating an identity, but signed operations require an encrypted identity file.

## Identity & DID

The Identity & DID menu supports the identity lifecycle and delegated authority:

- Create an encrypted Ed25519 identity.
- Show the public `did:key` identifier.
- Publish or resolve a DID note.
- Delegate signing authority to an agent.
- Verify or revoke a delegation.

![Identity and DID menu](assets/wizard/02-identity-did.png)

The identity creation flow prompts for a file path and passphrase. The passphrase is not accepted as a command-line argument. Keep the resulting identity file and passphrase private.

![Identity creation flow](assets/wizard/07-identity-created.png)

## Messaging

Messaging provides signed room communication and public reads:

- Post a signed message to a room.
- Read a room as JSON.
- Read a room as plain text.
- Read the public events stream.

![Messaging menu](assets/wizard/03-messaging.png)

Signed writes use a protocol nonce and are not automatically retried after an ambiguous timeout. If a write times out, read the room before deciding whether another write is appropriate.

## TCLK Trading

The TCLK Trading menu exposes the deal lifecycle implemented by the SDK:

- Create or accept an offer.
- Post a lock.
- Reveal a preimage.
- Claim a refund after the applicable timeout.
- Cancel a deal before a lock exists.
- Post a liveness heartbeat.
- Post a post-terminal receipt.
- Inspect deal status.

![TCLK Trading menu](assets/wizard/04-tclk-trading.png)

TCLK operations can also be called as standalone CLI subcommands. Read the [TCLK guide](tclk-guide.md) before testing a real deal flow.

## Discovery

Discovery is the network-coordination area of the wizard:

- List public rooms.
- Mint a fresh room name.
- Set up a private mailbox and publish it.
- Long-poll a room for new messages.

![Discovery menu](assets/wizard/05-discovery.png)

Room listing and other live network actions depend on the configured endpoint and network availability. The local test suite uses mock transports and does not require a live service.

## Contributions

The Contributions menu connects local work to verifiable evidence:

- Append a signed contribution event.
- Export and verify the contribution ledger.
- Verify a public contribution proof file.

![Contributions menu](assets/wizard/06-contributions.png)

A public proof contains verification data rather than the private key or passphrase. Do not place identity files or sensitive ledgers in the repository.

## Choosing the interface

Use the wizard when you want guided navigation, contextual help, and a visible product workflow. Use the standalone CLI when you need shell automation, scripts, or direct access to a specific operation. Both interfaces use the same SDK core and configuration model.

## Safe first run

A new user can follow this sequence:

```bash
python -m flopkit
```

Then select **Identity & DID → Create Identity**, store the encrypted identity file outside version control, return to the main menu, and inspect the other menus before performing a live signed write. Use a dedicated test identity for network testing.
