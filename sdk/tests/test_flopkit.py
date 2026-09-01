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
from flopkit.technocore import TechnocoreClient, TechnocoreError


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
        assert client.publish_did()["ok"]
        assert client.check_in()["ok"]
        assert client.post_message("room", "body")["ok"]
        result = client.read_room("room")
    assert result["messages"] == [{"did": result["messages"][0]["did"], "body": "body"}]
    assert mock.calls == ["/publish", "/check-in", "/post", "/read"]


def test_bad_signature_is_rejected(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    mock = MockTechnocore(reject_signature=True)
    with TechnocoreClient(key, transport=httpx.MockTransport(mock)) as client:
        with pytest.raises(TechnocoreError, match="HTTP 401"):
            client.check_in()


def test_retry_on_5xx(tmp_path: Path) -> None:
    key, _ = generate_identity("secret", tmp_path / "identity.pem")
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    config = TechnocoreConfig(retries=2)
    with TechnocoreClient(key, config=config, transport=httpx.MockTransport(handler)) as client:
        assert client.check_in()["ok"]
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
            client.check_in()
    assert attempts == 1
