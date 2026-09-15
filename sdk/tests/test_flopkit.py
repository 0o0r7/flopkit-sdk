import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
from mock_technocore import MockTechnocore

from flopkit.config import TechnocoreConfig
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
from flopkit.tclk import TCLKManager
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
            "did": ledger.did,
            "url": "x",
            "description": "y",
            "timestamp": "z",
            "signature": "not-hex",
        })
        + "\n"
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
        "seq": 1,
        "from": result["posted"]["from"],
        "nonce": "123",
        "text": "body",
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
        return httpx.Response(
            200,
            json={
                "room": "room",
                "count": 0,
                "first_seq": 0,
                "last_seq": 0,
                "generation": 0,
                "messages": [],
            },
        )

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
        return httpx.Response(
            200,
            json={
                "room": "room",
                "count": 1,
                "first_seq": 1,
                "last_seq": 1,
                "generation": 0,
                "posted": {"seq": 1, "from": "did:key:wrong", "nonce": "1", "text": "body"},
                "messages": [],
            },
        )

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TechnocoreError, match="mismatched"):
            client.post_message("room", "body", nonce="1")


def test_read_options_and_validation(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update({key: value for key, value in request.url.params.items()})
        return httpx.Response(
            200,
            json={
                "room": "room",
                "count": 0,
                "first_seq": 0,
                "last_seq": 0,
                "generation": 0,
                "messages": [],
            },
        )

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        assert client.read_room("room", since=2, limit=10, wait=1, cache_buster=3)["room"] == "room"
        for kwargs in (
            {"limit": 0},
            {"since": -1},
            {"wait": 11},
            {"cache_buster": -1},
        ):
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
        default_name = client.mint_room_name()
        assert default_name.startswith("p-")
        assert validate_room(default_name) == default_name
        mailbox_name = client.mint_room_name("mb-p")
        assert mailbox_name.startswith("mb-p-")
        assert validate_room(mailbox_name) == mailbox_name
        with pytest.raises(ValueError):
            client.mint_room_name("x")


def test_did_note_fingerprint_and_path() -> None:
    did = "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
    fingerprint = did_note_fingerprint(did)
    assert re.fullmatch(r"[0-9a-f]{16}", fingerprint)
    shard, key = did_note_path(did)
    assert shard == fingerprint[:2]
    assert key == fingerprint[2:]
    assert len(shard) == 2 and len(key) == 14


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
        assert client.resolve_did_note("did:key:z6Mkunknown") is None
        mock.notes[("did", did_note_fingerprint(did))] = did
        mock.notes.pop((f"did-{shard}", note_key))
        assert client.resolve_did_note(did) == did


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
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, headers={"retry-after": "12"})

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RateLimitedError, match="retry after 12"):
            client.post_message("room", "body")
    assert attempts == 1


def test_rate_limited_read_is_not_retried(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, headers={"retry-after": "30"})

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RateLimitedError, match="retry after 30"):
            client.read_room("room")
    assert attempts == 1


def test_nonce_monotonicity_is_enforced_locally(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.post_message("room", "first", nonce="500")
        with pytest.raises(ValueError, match="greater than 500"):
            client.post_message("room", "second", nonce="500")
        with pytest.raises(ValueError, match="greater than 500"):
            client.post_message("room", "second", nonce="499")
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


# --- Wizard tests (P0: fixed to use injectable I/O) ---


def test_interactive_menu_can_exit_without_side_effects() -> None:
    output: list[str] = []
    choices = iter(["5"])
    run_wizard(lambda _prompt: next(choices), output.append)
    assert output[0] == "\nFlopKit"
    assert output[-1] == "5. Exit"


def test_interactive_menu_creates_and_shows_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("flopkit.wizard.getpass.getpass", lambda _prompt: "wizard-secret")
    identity = tmp_path / "identity.pem"
    choices = iter(["1", str(identity), "2", str(identity), "5"])
    output: list[str] = []
    run_wizard(lambda _prompt: next(choices), output.append)
    assert identity.exists()
    assert any(line.startswith("Created DID: did:key:z6Mk") for line in output)
    assert sum(line.startswith("did:key:z6Mk") for line in output) == 1


def test_interactive_menu_can_cancel_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("flopkit.wizard.getpass.getpass", lambda _prompt: "unused")
    identity = tmp_path / "identity.pem"
    choices = iter(["3", str(identity), "technocore", "draft", "n", "5"])
    output: list[str] = []
    run_wizard(lambda _prompt: next(choices), output.append)
    assert "Cancelled." in output
    assert not identity.exists()


# --- GET signed-write lane tests (P1) ---


def test_get_signed_write_lane(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        result = client.post_message_get("room", "hello world", nonce="100")
    assert result["posted"]["text"] == "hello world"
    assert result["posted"]["nonce"] == "100"
    assert mock.calls == ["/r/room/say-signed/"] or any("say-signed" in c for c in mock.calls)


def test_get_signed_write_nonce_monotonicity(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.post_message_get("room", "first", nonce="500")
        with pytest.raises(ValueError, match="greater than 500"):
            client.post_message_get("room", "second", nonce="500")


# --- GET note-write lane tests (P1) ---


def test_get_note_write_lane(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        result = client.write_note_get("notes", "key1", "test value")
        assert result == "ok"
        assert client.read_note("notes", "key1") == "test value"


def test_get_note_write_with_if_absent(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.write_note_get("notes", "key1", "v1")
        with pytest.raises(NoteConflictError):
            client.write_note_get("notes", "key1", "v2", if_absent=True)


# --- Text read test (P1) ---


def test_read_room_text(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.post_message("room", "hello", nonce="1")
        text = client.read_room_text("room")
        assert "hello" in text or "room" in text


# --- TCLK tests (P2) ---


def test_tclk_offer(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        manager = TCLKManager(client)
        nonce = manager.post_offer("100", "FLOP", ["flop-htlc"])
    assert len(nonce) == 16  # 8 bytes hex
    assert any("tclk1" in msg["text"] for msg in mock.messages["tclk-offers"])


def test_tclk_full_state_machine(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        manager = TCLKManager(client)
        offer_nonce = manager.post_offer("100", "FLOP", ["flop-htlc"])
        accept_nonce = manager.post_accept(offer_nonce)
        secret = TCLKManager.generate_secret()
        hashlock = TCLKManager.generate_hashlock(secret)
        lock_nonce = manager.post_lock(accept_nonce, hashlock)
        manager.post_reveal(lock_nonce, secret)
        manager.post_refund(lock_nonce)
    messages = mock.messages["tclk-offers"]
    types = [json.loads(m["text"].removeprefix("tclk1 "))["type"] for m in messages]
    assert types == ["offer", "accept", "lock", "reveal", "refund"]


def test_tclk_hashlock_and_secret() -> None:
    secret = TCLKManager.generate_secret()
    assert len(secret) == 64  # 32 bytes hex
    hashlock = TCLKManager.generate_hashlock("test-secret")
    assert re.fullmatch(r"[0-9a-f]{64}", hashlock)


# --- Ecosystem helper tests (P3) ---


def test_parse_rooms(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.post_message("lobby", "hello", nonce="1")
        client.post_message("technocore", "world", nonce="1")
        rooms = client.parse_rooms()
    assert len(rooms) >= 2
    assert any(r["room"] == "lobby" for r in rooms)
    assert any(r["room"] == "technocore" for r in rooms)


def test_parse_budget_footer() -> None:
    text_with = "# budget: 15 of 25 reads left\nsome content"
    result = TechnocoreClient.parse_budget(text_with)
    assert result == {"remaining": 15, "total": 25}

    text_without = "just some content"
    assert TechnocoreClient.parse_budget(text_without) is None


def test_setup_mailbox(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        room = client.setup_mailbox()
    assert room.startswith("mb-p-")
    # DID note should contain mailbox reference
    shard, note_key = did_note_path(client.did)
    note = mock.notes.get((f"did-{shard}", note_key))
    assert note is not None and f"mailbox:{room}" in note


def test_long_poll(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        client.post_message("room", "hello", nonce="1")
        result = client.long_poll("room", since=0, wait=1)
    assert result["room"] == "room"
    assert isinstance(result["messages"], list)


# --- Package exports test (P2) ---


def test_package_exports() -> None:
    import flopkit

    expected = {
        "ContributionLedger", "DuplicateMessageError", "NoteConflictError",
        "RateLimitedError", "TCLKManager", "TechnocoreClient", "TechnocoreConfig",
        "TechnocoreError", "create_contribution_proof", "did_to_public_key",
        "generate_identity", "public_key_to_did", "sign_bytes",
        "verify_contribution_proof", "verify_signature", "write_proof",
    }
    assert expected <= set(flopkit.__all__)
    for name in expected:
        assert hasattr(flopkit, name)


# --- Coverage: GET lane error paths ---


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


def test_get_signed_write_400_error(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400)

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TechnocoreError, match="HTTP 400"):
            client.post_message_get("room", "body")


def test_get_signed_write_timeout(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TechnocoreError, match="outcome is unknown"):
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


def test_get_note_write_400_error(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400)

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TechnocoreError, match="HTTP 400"):
            client.write_note_get("ns", "key", "value")


def test_get_note_write_rejects_if_match_and_if_absent(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    with TechnocoreClient(key, transport=httpx.MockTransport(MockTechnocore())) as client:
        with pytest.raises(ValueError, match="only one of if_match and if_absent"):
            client.write_note_get("ns", "key", "value", if_match="x", if_absent=True)


def test_read_room_text_validation(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    with TechnocoreClient(key, transport=httpx.MockTransport(MockTechnocore())) as client:
        for kwargs in ({"limit": 0}, {"since": -1}, {"wait": 11}, {"cache_buster": -1}):
            with pytest.raises(ValueError):
                client.read_room_text("room", **kwargs)


def test_parse_rooms_empty(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore()
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        rooms = client.parse_rooms()
    assert rooms == []


def test_setup_mailbox_no_identity() -> None:
    with TechnocoreClient() as client:
        with pytest.raises(TechnocoreError, match="identity is required"):
            client.setup_mailbox()


def test_post_message_get_mismatched_response(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "room": "room", "count": 1, "first_seq": 1, "last_seq": 1,
                "generation": 0,
                "posted": {"seq": 1, "from": "did:key:wrong", "nonce": "1", "text": "body"},
                "messages": [],
            },
        )

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TechnocoreError, match="mismatched"):
            client.post_message_get("room", "body", nonce="1")


# --- Coverage: wizard interactive paths ---


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
    choices = iter(["4", "5"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("lobby" in line for line in output)


def test_wizard_post_message_success(
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
    choices = iter(["3", str(identity), "technocore", "hello world", "y", "5"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("sent" in line.lower() for line in output)


def test_wizard_create_identity_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = tmp_path / "identity.pem"
    identity.write_text("existing")
    output: list[str] = []
    choices = iter(["1", str(identity), "5"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("already exists" in line for line in output)


def test_wizard_show_did_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("flopkit.wizard.getpass.getpass", lambda _p: "wrong")
    identity = tmp_path / "nonexistent.pem"
    output: list[str] = []
    choices = iter(["2", str(identity), "5"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("Could not load" in line or "Error" in line for line in output)


def test_wizard_passphrase_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = tmp_path / "identity.pem"
    answers = iter(["correct", "wrong"])
    monkeypatch.setattr("flopkit.wizard.getpass.getpass", lambda _p: next(answers))
    output: list[str] = []
    choices = iter(["1", str(identity), "5"])
    run_wizard(lambda _p: next(choices), output.append)
    assert any("do not match" in line for line in output)
    assert not identity.exists()
