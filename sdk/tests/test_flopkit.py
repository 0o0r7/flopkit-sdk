import base64
import json
from pathlib import Path

import httpx

from flopkit.identity import (
    did_to_public_key,
    generate_identity,
    load_identity,
    public_key_to_did,
    sign_bytes,
    verify_signature,
)
from flopkit.ledger import ContributionLedger
from flopkit.technocore import TechnocoreClient


def test_identity_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "identity.pem"
    key, did = generate_identity("correct horse", path)
    loaded = load_identity(path, "correct horse")
    assert public_key_to_did(loaded.public_key()) == did
    assert did_to_public_key(did).public_bytes_raw() == key.public_key().public_bytes_raw()
    sig = sign_bytes(loaded, b"hello")
    assert verify_signature(did, b"hello", sig)
    assert not verify_signature(did, b"bad", sig)


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


def test_technocore_flow(tmp_path: Path) -> None:
    key, did = generate_identity("secret", tmp_path / "identity.pem")
    seen = []
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Flop-DID"] == did
        assert base64.b64decode(request.headers["X-Flop-Signature"])
        seen.append(request.url.path)
        return httpx.Response(200, json={"ok": True, "path": request.url.path})
    with TechnocoreClient(key, transport=httpx.MockTransport(handler)) as client:
        assert client.publish_did()["ok"]
        assert client.check_in()["ok"]
        assert client.post_message("room", "body")["ok"]
        assert client.read_room("room")["ok"]
    assert seen == ["/publish", "/check-in", "/post", "/read"]
