"""Comprehensive tests for the flopkit SDK — TCLK spec conformance, delegation, wizard TUI."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from mock_technocore import MockTechnocore

from flopkit.config import TechnocoreConfig
from flopkit.delegation import DelegationError, DelegationManager
from flopkit.identity import (
    did_to_public_key,
    generate_identity,
    load_identity,
    public_key_to_did,
    sign_bytes,
    verify_signature,
)
from flopkit.ledger import ContributionLedger
from flopkit.proofs import (
    create_contribution_proof,
    verify_contribution_proof,
    write_proof,
)
from flopkit.tclk import (
    FrameType,
    PaperRail,
    TCLKContract,
    TCLKError,
    TCLKManager,
    TCLKState,
    TranscriptFoldResult,
    capability_token,
    deal_room_name,
    decode_frame,
    derive_contract_id,
    encode_frame,
    fold_transcript,
    generate_secret,
    hashlock_from_secret,
    parse_capability_token,
    state_pointer_path,
    validate_point_statement,
    verify_hashlock,
    generate_point_lock,
)
from flopkit.technocore import (
    DuplicateMessageError,
    NoteConflictError,
    RateLimitedError,
    TechnocoreClient,
    TechnocoreError,
    did_note_fingerprint,
    did_note_path,
    encode_wire_signature,
    message_payload,
    normalize_message,
    normalize_note,
    room_classes,
    validate_base_url,
    validate_nonce,
    validate_room,
)
from flopkit.wizard import run as run_wizard

# --- Identity tests ---


def test_identity_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "identity.pem"
    key, did = generate_identity("correct horse", path)
    loaded = load_identity(path, "correct horse")
    assert public_key_to_did(loaded.public_key()) == did
    assert did_to_public_key(did).public_bytes_raw() == key.public_key().public_bytes_raw()
    sig = sign_bytes(loaded, b"hello")
    assert verify_signature(did, b"hello", sig)
    assert not verify_signature(did, b"bad", sig)


def test_seed_phrase_is_rejected(tmp_path: Path) -> None:
    seed = "one two three four five six seven eight nine ten eleven twelve"
    with pytest.raises(ValueError, match="wallet seed phrases"):
        generate_identity(seed, tmp_path / "identity.pem")


def test_existing_identity_path_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "identity.pem"
    path.write_text("existing")
    with pytest.raises(FileExistsError):
        generate_identity("secret", path)
    assert path.read_text() == "existing"


def test_wrong_passphrase(tmp_path: Path) -> None:
    path = tmp_path / "identity.pem"
    generate_identity("secret", path)
    try:
        load_identity(path, "wrong")
    except ValueError:
        pass
    else:
        raise AssertionError("wrong passphrase accepted")


# --- Ledger tests ---


def test_ledger_and_tamper_detection(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "key.pem")
    ledger_path = tmp_path / "events.ledger"
    ledger = ContributionLedger(ledger_path, key)
    ledger.log_contribution("https://example.org", "description")
    proof = ledger.export_proof(tmp_path / "proof.json")
    assert proof["valid"] is True
    event = json.loads(ledger_path.read_text())
    event["description"] = "tampered"
    ledger_path.write_text(json.dumps(event) + "\n")
    assert ledger.export_proof(tmp_path / "bad.json")["valid"] is False


def test_malformed_ledger_signature_is_invalid(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    ledger_path = tmp_path / "events.ledger"
    ledger = ContributionLedger(ledger_path, key)
    ledger_path.write_text(
        json.dumps({
            "did": ledger.did, "url": "x", "description": "y",
            "timestamp": "z", "signature": "not-hex",
        }) + "\n"
    )
    assert ledger.export_proof(tmp_path / "bad.json")["valid"] is False


# --- Technocore client tests ---


def test_technocore_flow(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        result = client.post_message("room", "body", nonce="123")
        read_result = client.read_room("room", limit=1)
    assert result["posted"] == {
        "seq": 1, "from": result["posted"]["from"], "nonce": "123", "text": "body",
    }
    assert read_result["messages"] == [result["posted"]]
    assert mock.calls == ["/r/room"]


def test_bad_signature_is_rejected(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore(reject_signature=True)
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        with pytest.raises(TechnocoreError, match="HTTP 401"):
            client.post_message("room", "body")


def test_retry_on_5xx(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={
            "room": "room", "count": 0, "first_seq": 0,
            "last_seq": 0, "generation": 0, "messages": [],
        })

    config = TechnocoreConfig(retries=2)
    with TechnocoreClient(key, config=config, transport=httpx.MockTransport(handler)) as client:
        assert client.read_room("room")["messages"] == []
    assert attempts == 3


def test_4xx_is_not_retried(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400)

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TechnocoreError, match="HTTP 400"):
            client.read_room("room")
    assert attempts == 1


# --- Protocol helper tests ---


def test_protocol_helpers_validate_and_normalize() -> None:
    assert validate_base_url("https://technocore.chat") == "https://technocore.chat"
    assert validate_base_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"
    assert validate_room("room_1") == "room_1"
    assert validate_nonce(123) == "123"
    assert normalize_message("  hello\nworld  ") == "hello world"
    normalized, payload = message_payload("room", "123", " hello ")
    assert normalized == "hello"
    assert payload == b"room|123|hello"
    with pytest.raises(ValueError):
        validate_base_url("http://example.org")
    with pytest.raises(ValueError):
        validate_base_url("https://example.org/path")
    with pytest.raises(ValueError):
        validate_base_url("https://user:pass@example.org")
    with pytest.raises(ValueError):
        validate_room("Room")
    with pytest.raises(ValueError):
        validate_nonce("not-a-number")
    with pytest.raises(ValueError):
        normalize_message("\n\t")
    with pytest.raises(ValueError):
        normalize_message("x" * 4097)
    with pytest.raises(ValueError):
        encode_wire_signature(b"short")


def test_wire_signature_is_unpadded_base64url(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    encoded = encode_wire_signature(key.sign(b"payload"))
    assert "=" not in encoded
    assert len(encoded) == 86


def test_write_timeout_is_not_retried(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("write timeout")

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TechnocoreError, match="outcome is unknown"):
            client.post_message("room", "body")
    assert attempts == 1


def test_mismatched_post_response_is_rejected(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "room": "room", "count": 1, "first_seq": 1, "last_seq": 1,
            "generation": 0,
            "posted": {"seq": 1, "from": "did:key:wrong", "nonce": "1", "text": "body"},
            "messages": [],
        })

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TechnocoreError, match="mismatched"):
            client.post_message("room", "body", nonce="1")


def test_read_options_and_validation(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update({k: v for k, v in request.url.params.items()})
        return httpx.Response(200, json={
            "room": "room", "count": 0, "first_seq": 0,
            "last_seq": 0, "generation": 0, "messages": [],
        })

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        assert client.read_room("room", since=2, limit=10, wait=1, cache_buster=3)["room"] == "room"
        for kwargs in ({"limit": 0}, {"since": -1}, {"wait": 11}, {"cache_buster": -1}):
            with pytest.raises(ValueError):
                client.read_room("room", **kwargs)
    assert seen == {"format": "json", "limit": "10", "since": "2", "wait": "1", "n": "3"}


# --- Note tests ---


def test_note_roundtrip_and_missing_note(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.write_note("notes", "greeting", "hello world")
        assert client.read_note("notes", "greeting") == "hello world"
        assert client.read_note("notes", "missing") is None


def test_note_cas_conflicts_and_success(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.write_note("notes", "state", "v1")
        with pytest.raises(NoteConflictError) as match:
            client.write_note("notes", "state", "v2", if_match="wrong")
        assert match.value.current_value == "v1"
        with pytest.raises(NoteConflictError):
            client.write_note("notes", "state", "v2", if_absent=True)
        client.write_note("notes", "state", "v2", if_match="v1")
        assert client.read_note("notes", "state") == "v2"


def test_note_rejects_if_match_with_if_absent(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    with TechnocoreClient(key, transport=httpx.MockTransport(MockTechnocore())) as client:
        with pytest.raises(ValueError, match="only one of if_match and if_absent"):
            client.write_note("notes", "key", "value", if_match="x", if_absent=True)


def test_normalize_note_sweeps_and_bounds() -> None:
    assert normalize_note("  a\nb\tc  ") == "a b c"
    with pytest.raises(ValueError):
        normalize_note("\n\t")
    with pytest.raises(ValueError):
        normalize_note("x" * 8193)


# --- Room and DID tests ---


def test_room_classes_parse_prefixes() -> None:
    assert room_classes("e-commerce") == {"e"}
    assert room_classes("mb-p-tclk-abc") == {"mb", "p"}
    assert room_classes("lobby") == frozenset()


def test_mint_room_name_uses_classes(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    with TechnocoreClient(key, transport=httpx.MockTransport(MockTechnocore())) as client:
        assert client.mint_room_name().startswith("p-")
        assert client.mint_room_name("mb-p").startswith("mb-p-")
        with pytest.raises(ValueError):
            client.mint_room_name("x")


def test_did_note_fingerprint_and_path() -> None:
    did = "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
    fingerprint = did_note_fingerprint(did)
    assert re.fullmatch(r"[0-9a-f]{16}", fingerprint)
    shard, key = did_note_path(did)
    assert shard == fingerprint[:2]
    assert key == fingerprint[2:]


def test_publish_and_resolve_did_note(tmp_path: Path) -> None:
    key, did = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        path = client.publish_did_note(extra="mailbox:mb-p-tclk-abc")
        shard, note_key = did_note_path(did)
        assert path == f"/kv/did-{shard}/{note_key}"
        note = client.resolve_did_note(did)
        assert note is not None and note.startswith(did)
        assert "mailbox:mb-p-tclk-abc" in note


def test_list_rooms_returns_mock_text(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.post_message("lobby", "hello", nonce="1")
        assert "lobby" in client.list_rooms()


def test_read_events_reads_events_room(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        assert client.read_events(limit=10)["room"] == "events"
    assert "/r/events" in mock.reads


# --- Error handling tests ---


def test_invalid_json_response_is_rejected(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"[]")

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TechnocoreError, match="not an object"):
            client.read_room("room")


def test_duplicate_message_422_is_distinct(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": "duplicate"})

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DuplicateMessageError, match="duplicate"):
            client.post_message("room", "body")


def test_rate_limited_write_is_not_retried(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "12"})

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RateLimitedError, match="retry after 12"):
            client.post_message("room", "body")


def test_rate_limited_read_is_not_retried(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "30"})

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RateLimitedError, match="retry after 30"):
            client.read_room("room")


def test_nonce_monotonicity_is_enforced_locally(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.post_message("room", "first", nonce="500")
        with pytest.raises(ValueError, match="greater than 500"):
            client.post_message("room", "second", nonce="500")
        client.post_message("room", "second", nonce="501")
    assert mock.calls == ["/r/room", "/r/room"]


# --- Contribution proof tests ---


def test_official_contribution_proof_roundtrip(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    commit = "a" * 40
    proof = create_contribution_proof(key, "https://example.org/project", commit)
    verify_contribution_proof(proof)
    output = tmp_path / "contribution-proof.json"
    write_proof(output, proof)
    assert json.loads(output.read_text()) == proof
    with pytest.raises(FileExistsError):
        write_proof(output, proof)
    proof["commit"] = "b" * 40
    with pytest.raises(ValueError, match="invalid"):
        verify_contribution_proof(proof)


# --- TCLK frame encoding/decoding tests ---


def test_encode_decode_frame_roundtrip() -> None:
    frame = {"type": "offer", "amount": "100", "nonce": "12345"}
    line = encode_frame(frame)
    assert line.startswith("tclk1 ")
    decoded = decode_frame(line)
    assert decoded == frame


def test_decode_frame_rejects_non_tclk() -> None:
    with pytest.raises(TCLKError, match="must start with"):
        decode_frame("not a frame")
    with pytest.raises(TCLKError, match="unknown frame type"):
        decode_frame('tclk1 {"type":"bogus"}')


def test_decode_frame_rejects_oversized() -> None:
    big = "tclk1 " + '{"type":"offer","text":"' + "x" * 4100 + '"}'
    with pytest.raises(TCLKError, match="exceeds"):
        decode_frame(big)


def test_frame_type_enum_has_all_8() -> None:
    types = {ft.value for ft in FrameType}
    assert types == {"offer", "accept", "lock", "reveal", "refund",
                     "cancel", "heartbeat", "receipt"}


def test_tclk_state_enum_has_all_states() -> None:
    states = {s.value for s in TCLKState}
    assert states == {"offered", "accepted", "locked", "revealed",
                      "refunded", "cancelled", "receipted"}


# --- Contract ID derivation tests ---


def test_contract_id_derivation_is_deterministic() -> None:
    offer = {"type": "offer", "from": "did:key:z6Mktest1", "amount": "100",
             "nonce": "111", "id": "0xabc"}
    accept = {"type": "accept", "from": "did:key:z6Mktest2", "ref": "111",
              "statement": "0xdef", "contract": "", "nonce": "222"}
    id1 = derive_contract_id(offer, accept)
    id2 = derive_contract_id(offer, accept)
    assert id1 == id2
    assert id1.startswith("0x")
    assert len(id1) == 66  # 0x + 64 hex


def test_contract_id_changes_with_different_offers() -> None:
    accept = {"type": "accept", "from": "did:key:z6Mktest2", "ref": "111",
              "statement": "0xdef", "contract": "", "nonce": "222"}
    offer1 = {"type": "offer", "nonce": "111", "id": "0xabc", "amount": "100"}
    offer2 = {"type": "offer", "nonce": "111", "id": "0xabc", "amount": "200"}
    assert derive_contract_id(offer1, accept) != derive_contract_id(offer2, accept)


def test_deal_room_name() -> None:
    contract_id = "0x" + "a" * 64
    room = deal_room_name(contract_id)
    assert room == "mb-p-tclk-aaaaaaaaaaaaaaaa"


def test_state_pointer_path() -> None:
    contract_id = "0x" + "a" * 64
    ns, key = state_pointer_path(contract_id)
    assert ns == "tclk-aa"
    assert key == "a" * 14


def test_capability_token_and_parse() -> None:
    token = capability_token(["flop-htlc", "paper"])
    assert token == "tclk1:flop-htlc,paper"
    parsed = parse_capability_token(f"did:key:z6Mktest {token} extra")
    assert parsed == ["flop-htlc", "paper"]
    assert parse_capability_token("no token here") is None


# --- HTLC tests ---


def test_generate_secret_format() -> None:
    secret = generate_secret()
    assert secret.startswith("0x")
    assert len(secret) == 66  # 0x + 64 hex


def test_hashlock_from_secret() -> None:
    secret = generate_secret()
    hashlock = hashlock_from_secret(secret)
    assert hashlock.startswith("0x")
    assert len(hashlock) == 66
    assert verify_hashlock(secret, hashlock)
    assert not verify_hashlock(generate_secret(), hashlock)


def test_hashlock_rejects_non_hex() -> None:
    with pytest.raises(TCLKError, match="must be 0x-prefixed"):
        hashlock_from_secret("not-hex")


# --- PTLC interface tests ---


def test_validate_point_statement() -> None:
    valid = "0x02" + "a" * 64
    assert validate_point_statement(valid) == valid
    with pytest.raises(TCLKError, match="point statement"):
        validate_point_statement("0x01" + "a" * 64)
    with pytest.raises(TCLKError, match="point statement"):
        validate_point_statement("not-a-point")


def test_generate_point_lock_format() -> None:
    point = generate_point_lock()
    assert point.startswith("0x")
    assert len(point) == 68  # 0x + 66 hex
    assert point[2:4] in {"02", "03"}


# --- TCLK Manager tests ---


def test_tclk_post_offer(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        result = mgr.post_offer(
            role="payer", amount="100", asset="FLOP", lock="hash",
            rails=["flop-htlc"], claim_by_ms=9999999999000,
            refund_after_ms=9999999999000, expires_ms=9999999999000,
        )
    assert "nonce" in result
    assert "id" in result
    assert result["id"].startswith("0x")
    messages = mock.messages["tclk-offers"]
    assert any("tclk1" in m["text"] for m in messages)
    frame = json.loads(messages[0]["text"].removeprefix("tclk1 "))
    assert frame["type"] == "offer"
    assert frame["role"] == "payer"
    assert frame["lock"] == "hash"
    assert frame["claimByMs"] == 9999999999000


def test_tclk_post_offer_rejects_bad_role(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        with pytest.raises(TCLKError, match="role"):
            mgr.post_offer(
                role="invalid", amount="100", asset="FLOP", lock="hash",
                rails=["flop-htlc"], claim_by_ms=1000, refund_after_ms=2000,
                expires_ms=3000,
            )


def test_tclk_full_deal_cycle(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        now = int(time.time() * 1000)
        # Post offer
        offer_result = mgr.post_offer(
            role="payer", amount="100", asset="FLOP", lock="hash",
            rails=["paper"], claim_by_ms=now + 3600000,
            refund_after_ms=now + 7200000, expires_ms=now + 1800000,
        )
        # Read offer back
        offer_frame = json.loads(
            mock.messages["tclk-offers"][-1]["text"].removeprefix("tclk1 ")
        )
        # Post accept
        secret = generate_secret()
        statement = hashlock_from_secret(secret)
        accept_result = mgr.post_accept(offer=offer_frame, statement=statement)
        contract_id = accept_result["contract"]
        # Post lock to derived deal room
        lock_nonce = mgr.post_lock(
            contract_id=contract_id, rail="paper", ref="paper-ref-1",
        )
        # Post reveal
        reveal_nonce = mgr.post_reveal(contract_id=contract_id, secret=secret)
        # Post receipt
        receipt_nonce = mgr.post_receipt(
            contract_id=contract_id, outcome="claimed", rail="paper", ref="paper-ref-1",
        )
    # Verify all frame types were posted
    all_messages = []
    for room_msgs in mock.messages.values():
        all_messages.extend(room_msgs)
    types = [json.loads(m["text"].removeprefix("tclk1 "))["type"] for m in all_messages]
    assert "offer" in types
    assert "accept" in types
    assert "lock" in types
    assert "reveal" in types
    assert "receipt" in types


def test_tclk_cancel_before_lock(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        now = int(time.time() * 1000)
        offer_result = mgr.post_offer(
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
        cancel_nonce = mgr.post_cancel(contract_id=accept_result["contract"])
    # Verify cancel was posted to the deal room
    deal_room = deal_room_name(accept_result["contract"])
    cancel_msgs = [m for m in mock.messages[deal_room] if "cancel" in m["text"]]
    assert len(cancel_msgs) == 1


def test_tclk_heartbeat(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        now = int(time.time() * 1000)
        offer_result = mgr.post_offer(
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
        hb_nonce = mgr.post_heartbeat(
            contract_id=accept_result["contract"], note="still here",
        )
    deal_room = deal_room_name(accept_result["contract"])
    hb_msgs = [m for m in mock.messages[deal_room] if "heartbeat" in m["text"]]
    assert len(hb_msgs) == 1


def test_tclk_advertise_capability(tmp_path: Path) -> None:
    key, did = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        path = mgr.advertise_capability(["flop-htlc", "paper"])
    shard, note_key = did_note_path(did)
    note = mock.notes.get((f"did-{shard}", note_key))
    assert note is not None
    assert "tclk1:flop-htlc,paper" in note


def test_tclk_read_write_deal_status(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    contract_id = "0x" + "a" * 64
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        mgr.write_deal_status(contract_id, "locked")
        status = mgr.read_deal_status(contract_id)
    assert status == "locked"


# --- Transcript folding tests ---


def test_fold_transcript_basic(tmp_path: Path) -> None:
    """Test that fold_transcript processes offer and accept frames."""
    key1, did1 = generate_identity("secret1", tmp_path / "id1.pem")
    key2, did2 = generate_identity("secret2", tmp_path / "id2.pem")
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 9999999999000,
        "refundAfterMs": 9999999999000, "expiresMs": 9999999999000,
        "nonce": "111", "id": "0x" + "a" * 64,
    }
    accept_frame = {
        "type": "accept", "from": did2, "ref": "111",
        "statement": "0x" + "b" * 64, "contract": "",
        "nonce": "222",
    }
    # The accept's contract field references the offer's id
    accept_frame["contract"] = offer_frame["id"]
    # The derived contract id is hash(offer+accept)
    contract_id = derive_contract_id(offer_frame, accept_frame)

    records = [
        {"room": "tclk-offers", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "111", "sig": "", "text": encode_frame(offer_frame)},
        {"room": "tclk-offers", "seq": 2, "ts": 2000, "from": did2,
         "nonce": "222", "sig": "", "text": encode_frame(accept_frame)},
    ]
    result = fold_transcript(records, now_ms=3000)
    assert contract_id in result.contracts
    contract = result.contracts[contract_id]
    assert contract.state == TCLKState.ACCEPTED


def test_fold_transcript_rejects_wrong_room(tmp_path: Path) -> None:
    _, did1 = generate_identity("secret1", tmp_path / "id1.pem")
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 9999999999000,
        "refundAfterMs": 9999999999000, "expiresMs": 9999999999000,
        "nonce": "111", "id": "0x" + "a" * 64,
    }
    records = [
        {"room": "wrong-room", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "111", "sig": "", "text": encode_frame(offer_frame)},
    ]
    result = fold_transcript(records, now_ms=3000)
    assert len(result.rejected) == 1


def test_fold_transcript_malformed_time() -> None:
    records = [
        {"room": "tclk-offers", "seq": 1, "ts": None, "from": "", "nonce": "",
         "sig": "", "text": "tclk1 {}"},
    ]
    result = fold_transcript(records)
    assert len(result.malformed) == 1
    assert "timestamp" in result.malformed[0]["reason"]


def test_fold_transcript_skips_non_tclk(tmp_path: Path) -> None:
    _, did1 = generate_identity("secret1", tmp_path / "id1.pem")
    records = [
        {"room": "lobby", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "1", "sig": "", "text": "hello world"},
    ]
    result = fold_transcript(records)
    assert len(result.contracts) == 0
    assert len(result.malformed) == 0


def test_fold_transcript_expired_offer_cancelled(tmp_path: Path) -> None:
    _, did1 = generate_identity("secret1", tmp_path / "id1.pem")
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 2000,
        "refundAfterMs": 3000, "expiresMs": 1500,
        "nonce": "111", "id": "0x" + "a" * 64,
    }
    records = [
        {"room": "tclk-offers", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "111", "sig": "", "text": encode_frame(offer_frame)},
    ]
    result = fold_transcript(records, now_ms=5000)
    contract = result.contracts[offer_frame["id"]]
    assert contract.state == TCLKState.CANCELLED


# --- Settlement rail tests ---


def test_paper_rail_lock_claim_refund(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    contract_id = "0x" + "a" * 64
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        rail = PaperRail(client)
        ref = rail.lock_funds(contract_id, "0x" + "b" * 64, "100", "FLOP", 9999999999000)
        assert ref.startswith("paper-")
        assert rail.claim_funds(contract_id, "0x" + "c" * 64, ref)
        assert rail.refund_funds(contract_id, ref)
    # Verify notes were written
    ns, k = state_pointer_path(contract_id)
    note = mock.notes.get((ns, k))
    assert note is not None
    assert "refunded" in note


def test_paper_rail_no_client() -> None:
    rail = PaperRail()
    ref = rail.lock_funds("0x" + "a" * 64, "0x" + "b" * 64, "100", "FLOP", 1000)
    assert ref.startswith("paper-")
    assert rail.claim_funds("0x" + "a" * 64, "secret", ref)
    assert rail.refund_funds("0x" + "a" * 64, ref)


# --- Delegation tests ---


def test_delegation_create_and_verify(tmp_path: Path) -> None:
    key, issuer_did = generate_identity("secret", tmp_path / "identity.pem")
    _, agent_did = generate_identity("agent", tmp_path / "agent.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = DelegationManager(client)
        result = mgr.create_delegate(agent_did, "r-lobby", 0)
        assert result["agent_did"] == agent_did
        assert result["scope"] == "r-lobby"
        # Verify
        verified = mgr.verify_delegate(issuer_did, agent_did)
        assert verified is not None
        assert verified["valid"] is True
        assert verified["scope"] == "r-lobby"


def test_delegation_revoke(tmp_path: Path) -> None:
    key, issuer_did = generate_identity("secret", tmp_path / "identity.pem")
    _, agent_did = generate_identity("agent", tmp_path / "agent.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = DelegationManager(client)
        mgr.create_delegate(agent_did, "r-lobby", 0)
        mgr.revoke_delegate(agent_did)
        verified = mgr.verify_delegate(issuer_did, agent_did)
        assert verified is not None
        assert verified["valid"] is False
        assert verified["reason"] == "revoked"


def test_delegation_expired(tmp_path: Path) -> None:
    key, issuer_did = generate_identity("secret", tmp_path / "identity.pem")
    _, agent_did = generate_identity("agent", tmp_path / "agent.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = DelegationManager(client)
        # Expired in the past
        mgr.create_delegate(agent_did, "r-lobby", 1)
        verified = mgr.verify_delegate(issuer_did, agent_did)
        assert verified is not None
        assert verified["valid"] is False
        assert verified["reason"] == "expired"


def test_delegation_no_note_found(tmp_path: Path) -> None:
    _, issuer_did = generate_identity("issuer", tmp_path / "issuer.pem")
    _, agent_did = generate_identity("agent", tmp_path / "agent.pem")
    mock = MockTechnocore()
    with TechnocoreClient(transport=httpx.MockTransport(mock)) as client:
        mgr = DelegationManager(client)
        result = mgr.verify_delegate(issuer_did, agent_did)
        assert result is None


def test_delegation_rejects_bad_agent_did(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = DelegationManager(client)
        with pytest.raises(DelegationError, match="agent_did"):
            mgr.create_delegate("not-a-did", "r-lobby", 0)


def test_delegation_rejects_bad_scope(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    _, agent_did = generate_identity("agent", tmp_path / "agent.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = DelegationManager(client)
        with pytest.raises(DelegationError, match="scope"):
            mgr.create_delegate(agent_did, "BAD SCOPE!", 0)


# --- Wizard TUI tests ---


def test_wizard_exit() -> None:
    output: list[str] = []
    choices = iter(["6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("FlopKit" in line for line in output)
    assert any("Goodbye" in line for line in output)


def test_wizard_invalid_then_exit() -> None:
    output: list[str] = []
    choices = iter(["9", "", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("Invalid" in line for line in output)


def test_wizard_create_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("flopkit.wizard.getpass.getpass", lambda _p: "wizard-secret")
    identity = tmp_path / "identity.pem"
    choices = iter(["1", "1", str(identity), "", "0", "6"])
    output: list[str] = []
    run_wizard(lambda _p: next(choices), output.append)
    assert identity.exists()
    assert any("Created DID" in line for line in output)


def test_wizard_create_identity_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = tmp_path / "identity.pem"
    identity.write_text("existing")
    output: list[str] = []
    choices = iter(["1", "1", str(identity), "", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("already exists" in line for line in output)


def test_wizard_passphrase_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = tmp_path / "identity.pem"
    answers = iter(["correct", "wrong"])
    monkeypatch.setattr("flopkit.wizard.getpass.getpass", lambda _p: next(answers))
    output: list[str] = []
    choices = iter(["1", "1", str(identity), "", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("do not match" in line for line in output)
    assert not identity.exists()


def test_wizard_list_rooms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock = MockTechnocore()

    class MockedClient(TechnocoreClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("transport", httpx.MockTransport(mock))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("flopkit.wizard.TechnocoreClient", MockedClient)
    mock.messages["lobby"] = []
    output: list[str] = []
    choices = iter(["4", "1", "", "", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("lobby" in line for line in output)


def test_wizard_post_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = tmp_path / "identity.pem"
    key, did = generate_identity("test-pass", identity)
    mock = MockTechnocore()

    class MockedClient(TechnocoreClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("transport", httpx.MockTransport(mock))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("flopkit.wizard.TechnocoreClient", MockedClient)
    monkeypatch.setattr("flopkit.wizard.getpass.getpass", lambda _p: "test-pass")
    output: list[str] = []
    choices = iter(["2", "1", str(identity), "technocore", "hello world", "y", "", "", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("sent" in line.lower() for line in output)


# --- Package exports test ---


def test_package_exports() -> None:
    import flopkit

    expected = {
        "ContributionLedger", "DelegationError", "DelegationManager",
        "DuplicateMessageError", "FrameType", "NoteConflictError",
        "PaperRail", "RateLimitedError", "SettlementRail",
        "TCLKContract", "TCLKError", "TCLKManager", "TCLKState",
        "TechnocoreClient", "TechnocoreConfig", "TechnocoreError",
        "TranscriptFoldResult", "capability_token", "create_contribution_proof",
        "deal_room_name", "decode_frame", "derive_contract_id",
        "did_to_public_key", "encode_frame", "fold_transcript",
        "generate_identity", "generate_secret", "hashlock_from_secret",
        "parse_capability_token", "public_key_to_did", "sign_bytes",
        "state_pointer_path", "validate_point_statement",
        "verify_contribution_proof", "verify_hashlock", "verify_signature",
        "write_proof",
    }
    assert expected <= set(flopkit.__all__)
    for name in expected:
        assert hasattr(flopkit, name), f"missing export: {name}"


# --- Ecosystem helper tests ---


def test_parse_rooms(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.post_message("lobby", "hello", nonce="1")
        client.post_message("technocore", "world", nonce="1")
        rooms = client.parse_rooms()
    assert len(rooms) >= 2
    assert any(r["room"] == "lobby" for r in rooms)


def test_parse_budget_footer() -> None:
    text_with = "# budget: 15 of 25 reads left\nsome content"
    result = TechnocoreClient.parse_budget(text_with)
    assert result == {"remaining": 15, "total": 25}
    assert TechnocoreClient.parse_budget("just content") is None


def test_setup_mailbox(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        room = client.setup_mailbox()
    assert room.startswith("mb-p-")


def test_long_poll(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.post_message("room", "hello", nonce="1")
        result = client.long_poll("room", since=0, wait=1)
    assert result["room"] == "room"


# --- GET lane tests ---


def test_get_signed_write_lane(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        result = client.post_message_get("room", "hello world", nonce="100")
    assert result["posted"]["text"] == "hello world"


def test_get_note_write_lane(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        assert client.write_note_get("notes", "key1", "test value") == "ok"
        assert client.read_note("notes", "key1") == "test value"


def test_read_room_text(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.post_message("room", "hello", nonce="1")
        text = client.read_room_text("room")
        assert "hello" in text or "room" in text


# --- Wizard action coverage tests ---


def test_wizard_show_did(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = tmp_path / "identity.pem"
    generate_identity("test-pass", identity)
    monkeypatch.setattr("flopkit.wizard.getpass.getpass", lambda _p: "test-pass")
    output: list[str] = []
    choices = iter(["1", "2", str(identity), "", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("DID:" in line for line in output)


def test_wizard_show_did_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("flopkit.wizard.getpass.getpass", lambda _p: "wrong")
    identity = tmp_path / "nonexistent.pem"
    output: list[str] = []
    choices = iter(["1", "2", str(identity), "", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("Error" in line or "Could not load" in line for line in output)


def test_wizard_resolve_did(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock = MockTechnocore()

    class MockedClient(TechnocoreClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("transport", httpx.MockTransport(mock))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("flopkit.wizard.TechnocoreClient", MockedClient)
    output: list[str] = []
    choices = iter(["1", "4", "did:key:z6Mktest", "", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("No note found" in line or "Note:" in line for line in output)


def test_wizard_mint_room(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock = MockTechnocore()

    class MockedClient(TechnocoreClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("transport", httpx.MockTransport(mock))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("flopkit.wizard.TechnocoreClient", MockedClient)
    output: list[str] = []
    choices = iter(["4", "2", "", "", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("Room:" in line for line in output)


def test_wizard_read_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock = MockTechnocore()

    class MockedClient(TechnocoreClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("transport", httpx.MockTransport(mock))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("flopkit.wizard.TechnocoreClient", MockedClient)
    output: list[str] = []
    choices = iter(["2", "4", "", "", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("No events" in line or "events" in line.lower() for line in output)


def test_wizard_read_room_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock = MockTechnocore()

    class MockedClient(TechnocoreClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("transport", httpx.MockTransport(mock))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("flopkit.wizard.TechnocoreClient", MockedClient)
    output: list[str] = []
    choices = iter(["2", "2", "", "", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("No messages" in line or "lobby" in line for line in output)


def test_wizard_read_room_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock = MockTechnocore()

    class MockedClient(TechnocoreClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("transport", httpx.MockTransport(mock))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("flopkit.wizard.TechnocoreClient", MockedClient)
    output: list[str] = []
    choices = iter(["2", "3", "", "", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    # Should show some text output
    assert len(output) > 5


def test_wizard_tclk_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock = MockTechnocore()

    class MockedClient(TechnocoreClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("transport", httpx.MockTransport(mock))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("flopkit.wizard.TechnocoreClient", MockedClient)
    output: list[str] = []
    choices = iter(["3", "9", "0x" + "a" * 64, "", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("No state pointer" in line or "Status:" in line for line in output)


def test_wizard_subcategory_back_and_exit() -> None:
    output: list[str] = []
    choices = iter(["1", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("Goodbye" in line for line in output)


def test_wizard_invalid_submenu_choice() -> None:
    output: list[str] = []
    choices = iter(["1", "99", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("Invalid" in line for line in output)


def test_wizard_log_contribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = tmp_path / "identity.pem"
    generate_identity("test-pass", identity)
    monkeypatch.setattr("flopkit.wizard.getpass.getpass", lambda _p: "test-pass")
    output: list[str] = []
    choices = iter(["5", "1", str(identity), "https://example.org", "test desc", "", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("Logged" in line for line in output)


def test_wizard_verify_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock = MockTechnocore()

    class MockedClient(TechnocoreClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("transport", httpx.MockTransport(mock))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("flopkit.wizard.TechnocoreClient", MockedClient)
    output: list[str] = []
    choices = iter(["5", "3", "/nonexistent/proof.json", "", "0", "6"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("Error" in line for line in output)


# --- TCLK state machine guard tests ---


def test_tclk_lock_after_refund_window_rejected(tmp_path: Path) -> None:
    key, did1 = generate_identity("secret", tmp_path / "id1.pem")
    _, did2 = generate_identity("secret2", tmp_path / "id2.pem")
    now = 1000
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 2000,
        "refundAfterMs": 1500, "expiresMs": 5000,
        "nonce": "111", "id": "0x" + "a" * 64,
    }
    accept_frame = {
        "type": "accept", "from": did2, "ref": "111",
        "statement": "0x" + "b" * 64, "contract": "0x" + "a" * 64,
        "nonce": "222",
    }
    contract_id = derive_contract_id(offer_frame, accept_frame)
    lock_frame = {
        "type": "lock", "from": did1, "contract": contract_id,
        "rail": "paper", "ref": "ref1",
    }
    # Lock after refund window (ts=2000 > refundAfterMs=1500)
    records = [
        {"room": "tclk-offers", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "111", "sig": "", "text": encode_frame(offer_frame)},
        {"room": "tclk-offers", "seq": 2, "ts": 1100, "from": did2,
         "nonce": "222", "sig": "", "text": encode_frame(accept_frame)},
        {"room": deal_room_name(contract_id), "seq": 3, "ts": 2000, "from": did1,
         "nonce": "333", "sig": "", "text": encode_frame(lock_frame)},
    ]
    result = fold_transcript(records, now_ms=2000)
    # The lock should be rejected
    assert any("refund window" in r.get("reason", "") for r in result.rejected)


def test_tclk_heartbeat_on_wrong_state_rejected(tmp_path: Path) -> None:
    key, did1 = generate_identity("secret", tmp_path / "id1.pem")
    _, did2 = generate_identity("secret2", tmp_path / "id2.pem")
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 9999999999000,
        "refundAfterMs": 9999999999000, "expiresMs": 9999999999000,
        "nonce": "111", "id": "0x" + "a" * 64,
    }
    accept_frame = {
        "type": "accept", "from": did2, "ref": "111",
        "statement": "0x" + "b" * 64, "contract": "0x" + "a" * 64,
        "nonce": "222",
    }
    contract_id = derive_contract_id(offer_frame, accept_frame)
    heartbeat_frame = {
        "type": "heartbeat", "from": did1, "contract": contract_id,
        "nonce": "333",
    }
    # Heartbeat on offered state (not accepted/locked)
    records = [
        {"room": "tclk-offers", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "111", "sig": "", "text": encode_frame(offer_frame)},
        {"room": deal_room_name(contract_id), "seq": 2, "ts": 1100, "from": did1,
         "nonce": "333", "sig": "", "text": encode_frame(heartbeat_frame)},
    ]
    result = fold_transcript(records, now_ms=2000)
    assert any("heartbeat" in r.get("reason", "").lower() for r in result.rejected)


def test_tclk_cancel_after_lock_rejected(tmp_path: Path) -> None:
    key, did1 = generate_identity("secret", tmp_path / "id1.pem")
    _, did2 = generate_identity("secret2", tmp_path / "id2.pem")
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 9999999999000,
        "refundAfterMs": 9999999999000, "expiresMs": 9999999999000,
        "nonce": "111", "id": "0x" + "a" * 64,
    }
    accept_frame = {
        "type": "accept", "from": did2, "ref": "111",
        "statement": "0x" + "b" * 64, "contract": "0x" + "a" * 64,
        "nonce": "222",
    }
    contract_id = derive_contract_id(offer_frame, accept_frame)
    lock_frame = {
        "type": "lock", "from": did1, "contract": contract_id,
        "rail": "paper", "ref": "ref1",
    }
    cancel_frame = {
        "type": "cancel", "from": did1, "contract": contract_id,
    }
    records = [
        {"room": "tclk-offers", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "111", "sig": "", "text": encode_frame(offer_frame)},
        {"room": "tclk-offers", "seq": 2, "ts": 1100, "from": did2,
         "nonce": "222", "sig": "", "text": encode_frame(accept_frame)},
        {"room": deal_room_name(contract_id), "seq": 3, "ts": 1200, "from": did1,
         "nonce": "333", "sig": "", "text": encode_frame(lock_frame)},
        {"room": deal_room_name(contract_id), "seq": 4, "ts": 1300, "from": did1,
         "nonce": "444", "sig": "", "text": encode_frame(cancel_frame)},
    ]
    result = fold_transcript(records, now_ms=2000)
    assert any("cancel" in r.get("reason", "").lower() for r in result.rejected)


def test_tclk_receipt_on_non_terminal_rejected(tmp_path: Path) -> None:
    key, did1 = generate_identity("secret", tmp_path / "id1.pem")
    _, did2 = generate_identity("secret2", tmp_path / "id2.pem")
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 9999999999000,
        "refundAfterMs": 9999999999000, "expiresMs": 9999999999000,
        "nonce": "111", "id": "0x" + "a" * 64,
    }
    accept_frame = {
        "type": "accept", "from": did2, "ref": "111",
        "statement": "0x" + "b" * 64, "contract": "0x" + "a" * 64,
        "nonce": "222",
    }
    contract_id = derive_contract_id(offer_frame, accept_frame)
    receipt_frame = {
        "type": "receipt", "from": did1, "contract": contract_id,
        "outcome": "claimed",
    }
    # Receipt on accepted state (not terminal)
    records = [
        {"room": "tclk-offers", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "111", "sig": "", "text": encode_frame(offer_frame)},
        {"room": "tclk-offers", "seq": 2, "ts": 1100, "from": did2,
         "nonce": "222", "sig": "", "text": encode_frame(accept_frame)},
        {"room": deal_room_name(contract_id), "seq": 3, "ts": 1200, "from": did1,
         "nonce": "333", "sig": "", "text": encode_frame(receipt_frame)},
    ]
    result = fold_transcript(records, now_ms=2000)
    assert any("receipt" in r.get("reason", "").lower() for r in result.rejected)


def test_tclk_reveal_wrong_secret_rejected(tmp_path: Path) -> None:
    key, did1 = generate_identity("secret", tmp_path / "id1.pem")
    _, did2 = generate_identity("secret2", tmp_path / "id2.pem")
    secret = generate_secret()
    statement = hashlock_from_secret(secret)
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 9999999999000,
        "refundAfterMs": 9999999999000, "expiresMs": 9999999999000,
        "nonce": "111", "id": "0x" + "a" * 64,
    }
    accept_frame = {
        "type": "accept", "from": did2, "ref": "111",
        "statement": statement, "contract": "0x" + "a" * 64,
        "nonce": "222",
    }
    contract_id = derive_contract_id(offer_frame, accept_frame)
    lock_frame = {
        "type": "lock", "from": did1, "contract": contract_id,
        "rail": "paper", "ref": "ref1",
    }
    wrong_secret = generate_secret()
    reveal_frame = {
        "type": "reveal", "from": did2, "contract": contract_id,
        "secret": wrong_secret,
    }
    records = [
        {"room": "tclk-offers", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "111", "sig": "", "text": encode_frame(offer_frame)},
        {"room": "tclk-offers", "seq": 2, "ts": 1100, "from": did2,
         "nonce": "222", "sig": "", "text": encode_frame(accept_frame)},
        {"room": deal_room_name(contract_id), "seq": 3, "ts": 1200, "from": did1,
         "nonce": "333", "sig": "", "text": encode_frame(lock_frame)},
        {"room": deal_room_name(contract_id), "seq": 4, "ts": 1300, "from": did2,
         "nonce": "444", "sig": "", "text": encode_frame(reveal_frame)},
    ]
    result = fold_transcript(records, now_ms=2000)
    assert any("does not match" in r.get("reason", "") for r in result.rejected)


def test_tclk_full_lifecycle_with_fold(tmp_path: Path) -> None:
    """Test full offer→accept→lock→reveal→receipt lifecycle via fold."""
    key, did1 = generate_identity("secret", tmp_path / "id1.pem")
    _, did2 = generate_identity("secret2", tmp_path / "id2.pem")
    secret = generate_secret()
    statement = hashlock_from_secret(secret)
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 9999999999000,
        "refundAfterMs": 9999999999000, "expiresMs": 9999999999000,
        "nonce": "111", "id": "0x" + "a" * 64,
    }
    accept_frame = {
        "type": "accept", "from": did2, "ref": "111",
        "statement": statement, "contract": "0x" + "a" * 64,
        "nonce": "222",
    }
    contract_id = derive_contract_id(offer_frame, accept_frame)
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
        "outcome": "claimed", "rail": "paper", "ref": "ref1",
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
         "nonce": "444", "sig": "", "text": encode_frame(reveal_frame)},
        {"room": deal_room, "seq": 5, "ts": 1400, "from": did1,
         "nonce": "555", "sig": "", "text": encode_frame(receipt_frame)},
    ]
    result = fold_transcript(records, now_ms=2000)
    assert contract_id in result.contracts
    contract = result.contracts[contract_id]
    assert contract.state == TCLKState.RECEIPTED
    assert contract.amount == "100"
    assert contract.asset == "FLOP"


def test_tclk_refund_after_deadline(tmp_path: Path) -> None:
    """Test refund works after refund window opens."""
    key, did1 = generate_identity("secret", tmp_path / "id1.pem")
    _, did2 = generate_identity("secret2", tmp_path / "id2.pem")
    secret = generate_secret()
    statement = hashlock_from_secret(secret)
    offer_frame = {
        "type": "offer", "from": did1, "role": "payer",
        "amount": "100", "asset": "FLOP", "lock": "hash",
        "rails": ["paper"], "claimByMs": 2000,
        "refundAfterMs": 1500, "expiresMs": 5000,
        "nonce": "111", "id": "0x" + "a" * 64,
    }
    accept_frame = {
        "type": "accept", "from": did2, "ref": "111",
        "statement": statement, "contract": "0x" + "a" * 64,
        "nonce": "222",
    }
    contract_id = derive_contract_id(offer_frame, accept_frame)
    lock_frame = {
        "type": "lock", "from": did1, "contract": contract_id,
        "rail": "paper", "ref": "ref1",
    }
    refund_frame = {
        "type": "refund", "from": did1, "contract": contract_id,
        "ref": "ref1",
    }
    deal_room = deal_room_name(contract_id)
    records = [
        {"room": "tclk-offers", "seq": 1, "ts": 1000, "from": did1,
         "nonce": "111", "sig": "", "text": encode_frame(offer_frame)},
        {"room": "tclk-offers", "seq": 2, "ts": 1100, "from": did2,
         "nonce": "222", "sig": "", "text": encode_frame(accept_frame)},
        {"room": deal_room, "seq": 3, "ts": 1200, "from": did1,
         "nonce": "333", "sig": "", "text": encode_frame(lock_frame)},
        {"room": deal_room, "seq": 4, "ts": 1600, "from": did1,
         "nonce": "444", "sig": "", "text": encode_frame(refund_frame)},
    ]
    result = fold_transcript(records, now_ms=2000)
    assert contract_id in result.contracts
    assert result.contracts[contract_id].state == TCLKState.REFUNDED


def test_tclk_fold_room_with_manager(tmp_path: Path) -> None:
    """Test TCLKManager.fold_room reads and folds a room."""
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        result = mgr.fold_room("tclk-offers", limit=50)
    assert isinstance(result, TranscriptFoldResult)
    assert result.contracts == {}


def test_tclk_post_offer_with_payment_key_and_job(tmp_path: Path) -> None:
    """Test post_offer with optional payment_key and job fields."""
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        result = mgr.post_offer(
            role="payer", amount="100", asset="FLOP", lock="hash",
            rails=["flop-htlc"], claim_by_ms=9999999999000,
            refund_after_ms=9999999999000, expires_ms=9999999999000,
            payment_key="0x" + "a" * 64,
            job={"id": "task-1", "proto": "a2a"},
        )
    messages = mock.messages["tclk-offers"]
    frame = json.loads(messages[-1]["text"].removeprefix("tclk1 "))
    assert "paymentKey" in frame
    assert frame["job"]["id"] == "task-1"


def test_tclk_offer_rejects_bad_lock_kind(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        with pytest.raises(TCLKError, match="lock must be"):
            mgr.post_offer(
                role="payer", amount="100", asset="FLOP", lock="bogus",
                rails=["flop-htlc"], claim_by_ms=1000, refund_after_ms=2000,
                expires_ms=3000,
            )


def test_tclk_offer_rejects_empty_rails(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        with pytest.raises(TCLKError, match="rails"):
            mgr.post_offer(
                role="payer", amount="100", asset="FLOP", lock="hash",
                rails=[], claim_by_ms=1000, refund_after_ms=2000,
                expires_ms=3000,
            )


def test_tclk_accept_rejects_non_offer(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = TCLKManager(client)
        with pytest.raises(TCLKError, match="offer must be"):
            mgr.post_accept(offer={"type": "not_offer"}, statement="0x" + "a" * 64)


# --- Additional delegation tests ---


def test_delegation_higher_nonce_wins(tmp_path: Path) -> None:
    key, issuer_did = generate_identity("secret", tmp_path / "identity.pem")
    _, agent_did = generate_identity("agent", tmp_path / "agent.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = DelegationManager(client)
        # Create with scope r-lobby
        mgr.create_delegate(agent_did, "r-lobby", 0)
        # Create again with scope r-all (higher nonce)
        mgr.create_delegate(agent_did, "r-all", 0)
        # Verify the higher nonce wins
        verified = mgr.verify_delegate(issuer_did, agent_did)
        assert verified is not None
        assert verified["valid"] is True
        assert verified["scope"] == "r-all"


def test_delegation_rejects_bad_expires(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    _, agent_did = generate_identity("agent", tmp_path / "agent.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = DelegationManager(client)
        with pytest.raises(DelegationError, match="expires_ms"):
            mgr.create_delegate(agent_did, "r-lobby", -1)


def test_delegation_revoke_rejects_bad_did(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        mgr = DelegationManager(client)
        with pytest.raises(DelegationError, match="agent_did"):
            mgr.revoke_delegate("not-a-did")


# --- GET lane coverage tests ---


def test_get_signed_write_422_duplicate(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": "duplicate"})

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DuplicateMessageError, match="duplicate"):
            client.post_message_get("room", "body")


def test_get_signed_write_429_rate_limited(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "5"})

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RateLimitedError, match="retry after 5"):
            client.post_message_get("room", "body")


def test_get_signed_write_no_identity(tmp_path: Path) -> None:
    with TechnocoreClient() as client:
        with pytest.raises(TechnocoreError, match="identity is required"):
            client.post_message_get("room", "body")


def test_get_note_write_409_conflict(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.write_note_get("ns", "key", "v1")
        with pytest.raises(NoteConflictError):
            client.write_note_get("ns", "key", "v2", if_absent=True)


def test_setup_mailbox_no_identity() -> None:
    with TechnocoreClient() as client:
        with pytest.raises(TechnocoreError, match="identity is required"):
            client.setup_mailbox()


def test_parse_rooms_empty(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        assert client.parse_rooms() == []
