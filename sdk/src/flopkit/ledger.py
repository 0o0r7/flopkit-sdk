from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .identity import public_key_to_did, sign_bytes, verify_signature


class ContributionLedger:
    def __init__(self, path: str | Path, identity: Ed25519PrivateKey) -> None:
        self.path = Path(path)
        self.identity = identity
        self.did = public_key_to_did(identity.public_key())

    def log_contribution(self, url: str, description: str) -> dict[str, Any]:
        event = {"did": self.did, "url": url, "description": description,
                 "timestamp": datetime.now(UTC).isoformat()}
        payload = json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
        event["signature"] = sign_bytes(self.identity, payload).hex()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return event

    def _events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def export_proof(self, path: str | Path) -> dict[str, Any]:
        events = self._events()
        statuses = []
        for event in events:
            signed = {k: v for k, v in event.items() if k != "signature"}
            payload = json.dumps(signed, sort_keys=True, separators=(",", ":")).encode()
            try:
                signature = bytes.fromhex(event.get("signature", ""))
                valid = verify_signature(event.get("did", ""), payload, signature)
            except (TypeError, ValueError):
                valid = False
            statuses.append({"event": event, "valid": valid})
        proof = {
            "did": self.did,
            "events": statuses,
            "valid": all(item["valid"] for item in statuses),
        }
        Path(path).write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return proof
