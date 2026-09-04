import json
from pathlib import Path

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
from flopkit.technocore import (
    TechnocoreClient,
    TechnocoreError,
    encode_wire_signature,
    message_payload,
    normalize_message,
    validate_base_url,
    validate_nonce,
    validate_room,
)
from flopkit.wizard import run as run_wizard


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


def test_invalid_json_response_is_rejected(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"[]")

    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TechnocoreError, match="not an object"):
            client.read_room("room")


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


def test_interactive_menu_can_exit_without_side_effects() -> None:
    output: list[str] = []
    choices = iter(["5"])
    run_wizard(lambda _prompt: next(choices), output.append)
    assert output[0] == "\nFlopKit"
    assert output[-1] == "5. Exit"


def test_interactive_menu_creates_and_shows_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = tmp_path / "identity.pem"
    monkeypatch.setattr("flopkit.wizard.getpass.getpass", lambda _prompt: "wizard-secret")
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
