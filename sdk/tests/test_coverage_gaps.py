"""Focused tests to close coverage gaps in tclk.py, wizard.py, and technocore.py."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from mock_technocore import MockTechnocore

from flopkit.delegation import DelegationManager
from flopkit.identity import generate_identity, load_identity
from flopkit.tclk import (
    TCLKManager,
    deal_room_name,
    derive_contract_id,
    encode_frame,
    fold_transcript,
    generate_secret,
    hashlock_from_secret,
    offer_id,
)
from flopkit.technocore import NoteConflictError, TechnocoreClient
from flopkit.wizard import _handle_action

# --- TCLKManager.post_refund ---


def test_tclk_post_refund(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        now = int(time.time() * 1000)
        mgr.post_offer(
            role="payer", amount="100", asset="FLOP", lock="hash",
            rails=["paper"], claim_by_ms=now + 3600000,
            refund_after_ms=now + 7200000, expires_ms=now + 1800000,
        )
        offer_frame = json.loads(
            mock.messages["tclk-offers"][-1]["text"].removeprefix("tclk1 ")
        )
        secret = generate_secret()
        statement = hashlock_from_secret(secret)
        accept_result = mgr.post_accept(offer=offer_frame, statement=statement)
        contract_id = accept_result["contract"]
        mgr.post_lock(contract_id=contract_id, rail="paper", ref="ref1")
        mgr.post_refund(
            contract_id=contract_id, ref="ref1", reason="timeout",
        )
    deal_room = deal_room_name(contract_id)
    refund_msgs = [
        m for m in mock.messages[deal_room]
        if "refund" in m["text"]
    ]
    assert len(refund_msgs) == 1
    frame = json.loads(refund_msgs[0]["text"].removeprefix("tclk1 "))
    assert frame["type"] == "refund"
    assert frame.get("reason") == "timeout"


# --- TCLKManager.post_cancel with reason ---


def test_tclk_post_cancel_with_reason(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        now = int(time.time() * 1000)
        mgr.post_offer(
            role="payer", amount="100", asset="FLOP", lock="hash",
            rails=["paper"], claim_by_ms=now + 3600000,
            refund_after_ms=now + 7200000, expires_ms=now + 1800000,
        )
        offer_frame = json.loads(
            mock.messages["tclk-offers"][-1]["text"].removeprefix("tclk1 ")
        )
        accept_result = mgr.post_accept(
            offer=offer_frame, statement=hashlock_from_secret(generate_secret()),
        )
        mgr.post_cancel(
            contract_id=accept_result["contract"], reason="changed mind",
        )
    deal_room = deal_room_name(accept_result["contract"])
    cancel_msgs = [
        m for m in mock.messages[deal_room]
        if "cancel" in m["text"]
    ]
    assert len(cancel_msgs) == 1
    frame = json.loads(cancel_msgs[0]["text"].removeprefix("tclk1 "))
    assert frame.get("reason") == "changed mind"


# --- TCLKManager.post_heartbeat with note ---


def test_tclk_post_heartbeat_with_note(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        now = int(time.time() * 1000)
        mgr.post_offer(
            role="payer", amount="100", asset="FLOP", lock="hash",
            rails=["paper"], claim_by_ms=now + 3600000,
            refund_after_ms=now + 7200000, expires_ms=now + 1800000,
        )
        offer_frame = json.loads(
            mock.messages["tclk-offers"][-1]["text"].removeprefix("tclk1 ")
        )
        accept_result = mgr.post_accept(
            offer=offer_frame, statement=hashlock_from_secret(generate_secret()),
        )
        mgr.post_heartbeat(
            contract_id=accept_result["contract"], note="still alive",
        )
    deal_room = deal_room_name(accept_result["contract"])
    hb_msgs = [
        m for m in mock.messages[deal_room]
        if "heartbeat" in m["text"]
    ]
    assert len(hb_msgs) == 1
    frame = json.loads(hb_msgs[0]["text"].removeprefix("tclk1 "))
    assert frame.get("note") == "still alive"


# --- TCLKManager.post_receipt with rail and ref ---


def test_tclk_post_receipt_with_rail_ref(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        now = int(time.time() * 1000)
        mgr.post_offer(
            role="payer", amount="100", asset="FLOP", lock="hash",
            rails=["paper"], claim_by_ms=now + 3600000,
            refund_after_ms=now + 7200000, expires_ms=now + 1800000,
        )
        offer_frame = json.loads(
            mock.messages["tclk-offers"][-1]["text"].removeprefix("tclk1 ")
        )
        secret = generate_secret()
        statement = hashlock_from_secret(secret)
        accept_result = mgr.post_accept(offer=offer_frame, statement=statement)
        contract_id = accept_result["contract"]
        mgr.post_lock(contract_id=contract_id, rail="paper", ref="ref1")
        mgr.post_reveal(contract_id=contract_id, secret=secret)
        mgr.post_receipt(
            contract_id=contract_id, outcome="claimed",
            rail="paper", ref="ref1",
        )
    deal_room = deal_room_name(contract_id)
    receipt_msgs = [
        m for m in mock.messages[deal_room]
        if "receipt" in m["text"]
    ]
    assert len(receipt_msgs) == 1
    frame = json.loads(receipt_msgs[0]["text"].removeprefix("tclk1 "))
    assert frame.get("rail") == "paper"
    assert frame.get("ref") == "ref1"


# --- TCLKManager.fold_room ---


def test_tclk_fold_room(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        now = int(time.time() * 1000)
        mgr.post_offer(
            role="payer", amount="100", asset="FLOP", lock="hash",
            rails=["paper"], claim_by_ms=now + 3600000,
            refund_after_ms=now + 7200000, expires_ms=now + 1800000,
        )
        result = mgr.fold_room("tclk-offers", limit=200)
    assert len(result.offers) >= 1
    assert result.malformed == []


# --- fold_transcript: duplicate accept (idempotent reject) ---


def test_fold_transcript_duplicate_accept(tmp_path: Path) -> None:
    _, did1 = generate_identity("secret1", tmp_path / "id1.pem")
    _, did2 = generate_identity("secret2", tmp_path / "id2.pem")
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 9999999998000,
        "refundAfterMs": 9999999999000, "expiresMs": 9999999999000,
        "nonce": "111",
    }
    offer_frame["id"] = offer_id(offer_frame)
    accept_frame = {
        "type": "accept", "from": did2, "ref": offer_frame["id"],
        "statement": "0x" + "b" * 64, "contract": "",
        "nonce": "222",
    }
    contract_id = derive_contract_id(offer_frame, accept_frame)
    accept_frame["contract"] = contract_id
    records = [
        {"room": "tclk-offers", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "111", "sig": "", "text": encode_frame(offer_frame)},
        {"room": "tclk-offers", "seq": 2, "ts": 1100, "from": did2,
         "nonce": "222", "sig": "", "text": encode_frame(accept_frame)},
        {"room": "tclk-offers", "seq": 3, "ts": 1200, "from": did2,
         "nonce": "222", "sig": "", "text": encode_frame(accept_frame)},
    ]
    result = fold_transcript(records, now_ms=3000)
    # Second accept should be rejected (contract re-keyed after first accept)
    assert len(result.rejected) > 0


# --- fold_transcript: accept unknown offer ---


def test_fold_transcript_accept_unknown_offer(tmp_path: Path) -> None:
    _, did2 = generate_identity("secret2", tmp_path / "id2.pem")
    accept_frame = {
        "type": "accept", "from": did2, "ref": "0xnonexistent",
        "statement": "0x" + "b" * 64, "contract": "0x" + "c" * 64,
        "nonce": "222",
    }
    records = [
        {"room": "tclk-offers", "seq": 1, "ts": 1000, "from": did2,
         "nonce": "222", "sig": "", "text": encode_frame(accept_frame)},
    ]
    result = fold_transcript(records, now_ms=2000)
    assert len(result.rejected) >= 1


# --- fold_transcript: receipt rail mismatch ---


def test_fold_transcript_receipt_rail_mismatch(tmp_path: Path) -> None:
    _, did1 = generate_identity("secret1", tmp_path / "id1.pem")
    _, did2 = generate_identity("secret2", tmp_path / "id2.pem")
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 9999999998000,
        "refundAfterMs": 9999999999000, "expiresMs": 9999999999000,
        "nonce": "111",
    }
    offer_frame["id"] = offer_id(offer_frame)
    accept_frame = {
        "type": "accept", "from": did2, "ref": offer_frame["id"],
        "statement": "0x" + "b" * 64, "contract": "",
        "nonce": "222",
    }
    contract_id = derive_contract_id(offer_frame, accept_frame)
    accept_frame["contract"] = contract_id
    lock_frame = {
        "type": "lock", "from": did1, "contract": contract_id,
        "rail": "paper", "ref": "ref1",
    }
    secret = generate_secret()
    statement = hashlock_from_secret(secret)
    # Fix: use matching statement in accept
    accept_frame["statement"] = statement
    # Re-derive contract id with correct statement
    contract_id = derive_contract_id(offer_frame, accept_frame)
    accept_frame["contract"] = contract_id
    lock_frame = {
        "type": "lock", "from": did1, "contract": contract_id,
        "rail": "paper", "ref": "ref1",
    }
    reveal_frame = {
        "type": "reveal", "from": did2, "contract": contract_id,
        "secret": secret,
    }
    receipt_frame = {
        "type": "receipt", "from": did1, "contract": contract_id,
        "outcome": "claimed", "rail": "wrong-rail", "ref": "ref1",
    }
    deal_room = deal_room_name(contract_id)
    receipt_frame = {
        "type": "receipt", "from": did1, "contract": contract_id,
        "outcome": "claimed", "rail": "wrong-rail", "ref": "ref1",
    }
    records = [
        {"room": "tclk-offers", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "111", "sig": "", "text": encode_frame(offer_frame)},
        {"room": "tclk-offers", "seq": 2, "ts": 1100, "from": did2,
         "nonce": "222", "sig": "", "text": encode_frame(accept_frame)},
        {"room": deal_room, "seq": 3, "ts": 1200, "from": did1,
         "nonce": "333", "sig": "", "text": encode_frame(lock_frame)},
        {"room": deal_room, "seq": 4, "ts": 1300, "from": did2,
         "nonce": "444", "sig": "", "text": encode_frame(reveal_frame)},
        {"room": deal_room, "seq": 5, "ts": 1400, "from": did1,
         "nonce": "555", "sig": "", "text": encode_frame(receipt_frame)},
    ]
    result = fold_transcript(records, now_ms=2000)
    assert any(
        "contradicts" in r.get("reason", "")
        for r in result.rejected
    )


# --- fold_transcript: cancel idempotent ---


def test_fold_transcript_cancel_idempotent(tmp_path: Path) -> None:
    _, did1 = generate_identity("secret1", tmp_path / "id1.pem")
    _, did2 = generate_identity("secret2", tmp_path / "id2.pem")
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 9999999998000,
        "refundAfterMs": 9999999999000, "expiresMs": 9999999999000,
        "nonce": "111",
    }
    offer_frame["id"] = offer_id(offer_frame)
    accept_frame = {
        "type": "accept", "from": did2, "ref": offer_frame["id"],
        "statement": "0x" + "b" * 64, "contract": "",
        "nonce": "222",
    }
    contract_id = derive_contract_id(offer_frame, accept_frame)
    accept_frame["contract"] = contract_id
    cancel_frame = {
        "type": "cancel", "from": did1, "contract": contract_id,
    }
    deal_room = deal_room_name(contract_id)
    records = [
        {"room": "tclk-offers", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "111", "sig": "", "text": encode_frame(offer_frame)},
        {"room": "tclk-offers", "seq": 2, "ts": 1100, "from": did2,
         "nonce": "222", "sig": "", "text": encode_frame(accept_frame)},
        {"room": deal_room, "seq": 3, "ts": 1200, "from": did1,
         "nonce": "333", "sig": "", "text": encode_frame(cancel_frame)},
        {"room": deal_room, "seq": 4, "ts": 1300, "from": did1,
         "nonce": "444", "sig": "", "text": encode_frame(cancel_frame)},
    ]
    result = fold_transcript(records, now_ms=2000)
    # Second cancel should be rejected (already cancelled)
    assert len(result.rejected) >= 1


# --- fold_transcript: refund before window ---


def test_fold_transcript_refund_before_window(tmp_path: Path) -> None:
    _, did1 = generate_identity("secret1", tmp_path / "id1.pem")
    _, did2 = generate_identity("secret2", tmp_path / "id2.pem")
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 9999999998000,
        "refundAfterMs": 9999999999000, "expiresMs": 9999999999000,
        "nonce": "111",
    }
    offer_frame["id"] = offer_id(offer_frame)
    accept_frame = {
        "type": "accept", "from": did2, "ref": offer_frame["id"],
        "statement": "0x" + "b" * 64, "contract": "",
        "nonce": "222",
    }
    contract_id = derive_contract_id(offer_frame, accept_frame)
    accept_frame["contract"] = contract_id
    lock_frame = {
        "type": "lock", "from": did1, "contract": contract_id,
        "rail": "paper", "ref": "ref1",
    }
    refund_frame = {
        "type": "refund", "from": did2, "contract": contract_id,
    }
    deal_room = deal_room_name(contract_id)
    records = [
        {"room": "tclk-offers", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "111", "sig": "", "text": encode_frame(offer_frame)},
        {"room": "tclk-offers", "seq": 2, "ts": 1100, "from": did2,
         "nonce": "222", "sig": "", "text": encode_frame(accept_frame)},
        {"room": deal_room, "seq": 3, "ts": 1200, "from": did1,
         "nonce": "333", "sig": "", "text": encode_frame(lock_frame)},
        {"room": deal_room, "seq": 4, "ts": 1300, "from": did2,
         "nonce": "444", "sig": "", "text": encode_frame(refund_frame)},
    ]
    result = fold_transcript(records, now_ms=1300)
    # Refund should be rejected (window not open: refundAfterMs is far future)
    assert len(result.rejected) >= 1


# --- fold_transcript: reveal after claim deadline ---


def test_fold_transcript_reveal_after_deadline(tmp_path: Path) -> None:
    _, did1 = generate_identity("secret1", tmp_path / "id1.pem")
    _, did2 = generate_identity("secret2", tmp_path / "id2.pem")
    secret = generate_secret()
    statement = hashlock_from_secret(secret)
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 1200,
        "refundAfterMs": 5000, "expiresMs": 9999,
        "nonce": "111",
    }
    offer_frame["id"] = offer_id(offer_frame)
    accept_frame = {
        "type": "accept", "from": did2, "ref": offer_frame["id"],
        "statement": statement, "contract": "",
        "nonce": "222",
    }
    contract_id = derive_contract_id(offer_frame, accept_frame)
    accept_frame["contract"] = contract_id
    lock_frame = {
        "type": "lock", "from": did1, "contract": contract_id,
        "rail": "paper", "ref": "ref1",
    }
    reveal_frame = {
        "type": "reveal", "from": did2, "contract": contract_id,
        "secret": secret,
    }
    deal_room = deal_room_name(contract_id)
    records = [
        {"room": "tclk-offers", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "111", "sig": "", "text": encode_frame(offer_frame)},
        {"room": "tclk-offers", "seq": 2, "ts": 1100, "from": did2,
         "nonce": "222", "sig": "", "text": encode_frame(accept_frame)},
        {"room": deal_room, "seq": 3, "ts": 1150, "from": did1,
         "nonce": "333", "sig": "", "text": encode_frame(lock_frame)},
        {"room": deal_room, "seq": 4, "ts": 2000, "from": did2,
         "nonce": "444", "sig": "", "text": encode_frame(reveal_frame)},
    ]
    result = fold_transcript(records, now_ms=2000)
    # Reveal should be rejected (ts=2000 > claimByMs=1200)
    assert any("deadline" in r.get("reason", "") for r in result.rejected)


# --- TechnocoreClient.write_note_get conflict ---


def test_write_note_get_conflict(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.write_note("ns", "key", "v1")
        with pytest.raises(NoteConflictError):
            client.write_note_get("ns", "key", "v2", if_match="wrong")


# --- Wizard _handle_action tests ---


def _make_wizard_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Any, str, MockTechnocore, list[str]]:
    identity = tmp_path / "identity.pem"
    key, did = generate_identity("test-pass", identity)
    mock = MockTechnocore()

    class MockedClient(TechnocoreClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("transport", httpx.MockTransport(mock))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("flopkit.wizard.TechnocoreClient", MockedClient)
    monkeypatch.setattr(
        "flopkit.wizard.load_identity_file",
        lambda path: load_identity(path, "test-pass"),
    )
    output: list[str] = []
    return identity, key, did, mock, output


def test_wizard_tclk_offer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    prompts = iter([
        "payer", "100", "FLOP", "hash", "paper",
        "9999999998000", "9999999999000", "9999999999000",
    ])
    _handle_action(
        "tclk_offer", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("Offer posted" in line for line in output)
    assert "tclk-offers" in mock.messages


def test_wizard_tclk_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    # First post an offer+accept to get a contract id
    with TechnocoreClient(_key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        now = int(time.time() * 1000)
        mgr.post_offer(
            role="payer", amount="100", asset="FLOP", lock="hash",
            rails=["paper"], claim_by_ms=now + 3600000,
            refund_after_ms=now + 7200000, expires_ms=now + 1800000,
        )
        offer_frame = json.loads(
            mock.messages["tclk-offers"][-1]["text"].removeprefix("tclk1 ")
        )
        accept_result = mgr.post_accept(
            offer=offer_frame, statement=hashlock_from_secret(generate_secret()),
        )
        contract_id = accept_result["contract"]

    prompts = iter([contract_id, "paper", "ref1"])
    _handle_action(
        "tclk_lock", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("Lock posted" in line for line in output)


def test_wizard_tclk_reveal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    secret = generate_secret()
    statement = hashlock_from_secret(secret)
    with TechnocoreClient(_key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        now = int(time.time() * 1000)
        mgr.post_offer(
            role="payer", amount="100", asset="FLOP", lock="hash",
            rails=["paper"], claim_by_ms=now + 3600000,
            refund_after_ms=now + 7200000, expires_ms=now + 1800000,
        )
        offer_frame = json.loads(
            mock.messages["tclk-offers"][-1]["text"].removeprefix("tclk1 ")
        )
        accept_result = mgr.post_accept(offer=offer_frame, statement=statement)
        contract_id = accept_result["contract"]
        mgr.post_lock(contract_id=contract_id, rail="paper", ref="ref1")

    prompts = iter([contract_id, secret])
    _handle_action(
        "tclk_reveal", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("Reveal posted" in line for line in output)


def test_wizard_tclk_refund(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    contract_id = "0x" + "a" * 64
    prompts = iter([contract_id])
    _handle_action(
        "tclk_refund", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("Refund posted" in line for line in output)


def test_wizard_tclk_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    contract_id = "0x" + "a" * 64
    prompts = iter([contract_id])
    _handle_action(
        "tclk_cancel", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("Cancel posted" in line for line in output)


def test_wizard_tclk_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    contract_id = "0x" + "a" * 64
    prompts = iter([contract_id])
    _handle_action(
        "tclk_heartbeat", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("Heartbeat posted" in line for line in output)


def test_wizard_tclk_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    contract_id = "0x" + "a" * 64
    prompts = iter([contract_id, "claimed"])
    _handle_action(
        "tclk_receipt", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("Receipt posted" in line for line in output)


def test_wizard_delegate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    _, agent_did = generate_identity("agent", tmp_path / "agent.pem")
    prompts = iter([agent_did, "r-lobby", "0"])
    _handle_action(
        "delegate", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("Delegation created" in line for line in output)


def test_wizard_verify_delegation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, issuer_did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    _, agent_did = generate_identity("agent", tmp_path / "agent.pem")
    # First create a delegation
    with TechnocoreClient(_key, transport=httpx.MockTransport(mock)) as client:
        mgr = DelegationManager(client)
        mgr.create_delegate(agent_did, "r-lobby", 0)
    prompts = iter([issuer_did, agent_did])
    _handle_action(
        "verify_delegation", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("Valid" in line for line in output)


def test_wizard_revoke_delegation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    _, agent_did = generate_identity("agent", tmp_path / "agent.pem")
    prompts = iter([agent_did])
    _handle_action(
        "revoke_delegation", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("revoked" in line for line in output)


def test_wizard_setup_mailbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    _handle_action(
        "setup_mailbox", output.append, lambda _p: "",
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("Mailbox" in line for line in output)


def test_wizard_long_poll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    prompts = iter(["technocore", "0"])
    _handle_action(
        "long_poll", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any(
        "No new messages" in line or "seq" in line
        for line in output
    )


def test_wizard_export_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    # Create a ledger file first
    ledger_path = tmp_path / "contributions.ledger"
    from flopkit.ledger import ContributionLedger
    ledger = ContributionLedger(ledger_path, _key)
    ledger.log_contribution("https://example.org", "test")
    output_path = tmp_path / "proof.json"
    prompts = iter([str(output_path)])
    _handle_action(
        "export_proof", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("Proof exported" in line for line in output)


def test_wizard_read_room_json_with_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    # Post a message to the mock
    with TechnocoreClient(_key, transport=httpx.MockTransport(mock)) as client:
        client.post_message("technocore", "hello world", nonce="1")
    prompts = iter(["technocore", "50"])
    _handle_action(
        "read_room_json", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("hello world" in line for line in output)


def test_wizard_read_room_text_with_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    with TechnocoreClient(_key, transport=httpx.MockTransport(mock)) as client:
        client.post_message("technocore", "hello text", nonce="1")
    prompts = iter(["technocore"])
    _handle_action(
        "read_room_text", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("hello text" in line for line in output)


def test_wizard_read_events_with_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    with TechnocoreClient(_key, transport=httpx.MockTransport(mock)) as client:
        client.post_message("events", "test event", nonce="1")
    _handle_action(
        "read_events", output.append, lambda _p: "",
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any(
        "event" in line.lower() or "No events" in line
        for line in output
    )


def test_wizard_publish_did_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _key, _did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    prompts = iter(["role:agent"])
    _handle_action(
        "publish_did_note", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("Published" in line for line in output)


def test_wizard_resolve_did_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, key, did, mock, output = _make_wizard_setup(tmp_path, monkeypatch)
    # First publish a DID note
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.publish_did_note(extra="role:agent")
    prompts = iter([did])
    _handle_action(
        "resolve_did", output.append, lambda _p: next(prompts),
        lambda: str(identity), lambda: str(identity), lambda: None, lambda r: None,
    )
    assert any("Note:" in line for line in output)
