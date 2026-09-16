"""Wizard flow tests: drive the two-level TUI via injectable I/O.

These cover the interactive action handlers in wizard.py, which the
unit tests in test_flopkit.py only touch indirectly. All network I/O
goes through MockTechnocore; identities live in a tmp cwd so the
CWD-relative default 'identity.pem' and 'contributions.ledger' are
isolated per test.
"""
from __future__ import annotations

import getpass
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
from mock_technocore import MockTechnocore

from flopkit.identity import generate_identity
from flopkit.tclk import TCLKManager, generate_secret, hashlock_from_secret
from flopkit.technocore import TechnocoreClient
from flopkit.wizard import run as run_wizard


@pytest.fixture()
def identity_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Identity file at the CWD default, patched getpass + client transport."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: "secret")
    key, did = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()

    class MockedClient(TechnocoreClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("transport", httpx.MockTransport(mock))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("flopkit.wizard.TechnocoreClient", MockedClient)
    return {"key": key, "did": did, "mock": mock, "tmp": tmp_path}


def drive(choices: list[str]) -> list[str]:
    output: list[str] = []
    it = iter(choices)
    run_wizard(lambda _p: next(it), output.append)
    return output


def test_wizard_create_and_show_identity(identity_env: dict[str, Any]) -> None:
    out = drive([
        "1", "1", "fresh.pem", "",     # create identity at a NEW path (getpass x2)
        "2", "", "",                    # show DID (default identity.pem from fixture)
        "0", "6",
    ])
    assert any("Created DID:" in line for line in out)
    assert any("DID:" in line and "z6Mk" in line for line in out)


def test_wizard_post_and_read_messages(identity_env: dict[str, Any]) -> None:
    out = drive([
        "2", "1", "", "", "hello from the wizard test", "y", "",  # path, room, text, send
        "3", "", "",                                              # read text
        "4", "",                                                  # read events
        "0", "6",
    ])
    assert any("Message sent." in line for line in out)
    assert any("hello from the wizard test" in line for line in out)
    assert any("No events" in line for line in out)


def test_wizard_post_message_cancelled(identity_env: dict[str, Any]) -> None:
    out = drive([
        "2", "1", "", "", "draft that never ships", "n", "",
        "0", "6",
    ])
    assert any("Cancelled." in line for line in out)


def test_wizard_publish_resolve_delegate(identity_env: dict[str, Any]) -> None:
    did = identity_env["did"]
    _, agent_did = generate_identity("secret", identity_env["tmp"] / "agent.pem")
    out = drive([
        "1", "3", "", "", "",                # publish DID note (path, extra, enter)
        "4", did, "",                         # resolve own note
        "5", "", agent_did, "r-lobby", "0", "",  # delegate (path, agent, scope, expiry, enter)
        "6", did, agent_did, "",              # verify delegation
        "7", "", agent_did, "",               # revoke delegation (path, agent, enter)
        "0", "6",
    ])
    assert any("Published DID note at:" in line for line in out)
    assert any("Note:" in line for line in out)
    assert any("Delegation created." in line for line in out)
    assert any("Valid delegation." in line for line in out)
    assert any("Delegation revoked." in line for line in out)


def test_wizard_discovery_actions(identity_env: dict[str, Any]) -> None:
    out = drive([
        "4", "1", "",              # list rooms (enter)
        "2", "", "",               # mint room (classes, enter)
        "3", "", "",               # setup mailbox (path, enter)
        "4", "", "", "",           # long poll (room, since, enter)
        "0", "6",
    ])
    assert any("Room: " in line for line in out)
    assert any("Mailbox: " in line for line in out)
    assert any("No new messages" in line for line in out)


def test_wizard_tclk_offer_and_status(identity_env: dict[str, Any]) -> None:
    out = drive([
        "3", "1", "", "payer", "100", "FLOP", "hash", "paper",
        "9999999998000", "9999999999000", "9999999999000", "",
        "9", "0x" + "a" * 64, "",
        "0", "6",
    ])
    assert any("Offer posted." in line and "ID: 0x" in line for line in out)
    assert any("No state pointer found." in line for line in out)


def test_wizard_tclk_accept_through_receipt(identity_env: dict[str, Any]) -> None:
    env = identity_env
    mock: MockTechnocore = env["mock"]
    # Seed a real, spec-conformant offer through the same mock transport.
    with TechnocoreClient(
        env["key"], transport=httpx.MockTransport(mock)
    ) as client:
        secret = generate_secret()
        offer = TCLKManager(client).post_offer(
            role="payer", amount="100", asset="FLOP", lock="hash",
            rails=["paper"], claim_by_ms=9999999998000,
            refund_after_ms=9999999999000, expires_ms=9999999999000,
        )
    statement = hashlock_from_secret(secret)

    out = drive([
        "3", "2", "", offer["id"], statement, "",   # accept
        "0", "6",
    ])
    assert any("Accept posted." in line for line in out)
    joined = "\n".join(out)
    match = re.search(r"0x[0-9a-f]{64}", joined)
    assert match is not None
    contract_id = match.group(0)

    out = drive([
        "3", "3", "", contract_id, "paper", "ref-1", "",     # lock: path, cid, rail, ref
        "4", "", contract_id, secret, "",                    # reveal
        "5", "", contract_id, "",                            # refund
        "6", "", contract_id, "",                            # cancel
        "7", "", contract_id, "",                            # heartbeat
        "8", "", contract_id, "claimed", "",                 # receipt
        "0", "6",
    ])
    joined = "\n".join(out)
    for marker in ("Lock posted.", "Reveal posted.", "Refund posted.",
                   "Cancel posted.", "Heartbeat posted.", "Receipt posted."):
        assert marker in joined


def test_wizard_contributions_log_export_verify(
    identity_env: dict[str, Any],
) -> None:
    out = drive([
        "5", "1", "", "https://example.com/artifact", "did the thing", "",
        "2", "", "proof.json", "",
        "3", "proof.json", "",
        "0", "6",
    ])
    assert any("Logged. Signature:" in line for line in out)
    assert any("Proof exported to: proof.json" in line for line in out)
    assert any("Valid: True" in line for line in out)
    assert any("Ledger export: 1/1 events valid." in line for line in out)


def test_wizard_invalid_choices_recover(identity_env: dict[str, Any]) -> None:
    out = drive(["9", "", "6"])          # invalid main choice, then exit
    assert any("Invalid choice" in line for line in out)
    out = drive(["2", "9", "", "0", "6"])  # invalid submenu choice, back, exit
    assert any("Invalid choice." in line for line in out)
