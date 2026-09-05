"""Public contribution proofs bound to an immutable Git revision."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .identity import did_to_public_key, public_key_to_did

_COMMIT_PATTERN = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")
_SIGNATURE_PATTERN = re.compile(r"[A-Za-z0-9_-]{86}")
SCHEMA = "technocore-contribution-proof-v1"


def _validate_artifact_url(artifact_url: str) -> str:
    if not isinstance(artifact_url, str) or artifact_url != artifact_url.strip():
        raise ValueError("artifact URL must not contain surrounding whitespace")
    parsed = urlsplit(artifact_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.fragment:
        raise ValueError("artifact URL must be an absolute HTTPS URL without a fragment")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("artifact URL must not contain embedded credentials")
    return artifact_url


def _validate_commit(commit: str) -> str:
    if _COMMIT_PATTERN.fullmatch(commit) is None:
        raise ValueError("commit must be a complete 40- or 64-character hexadecimal revision")
    return commit.lower()


def contribution_payload(artifact_url: str, commit: str) -> bytes:
    """Build the deterministic signed payload for a public contribution."""
    record = {
        "artifact_url": _validate_artifact_url(artifact_url),
        "commit": _validate_commit(commit),
        "schema": SCHEMA,
    }
    return json.dumps(record, sort_keys=True, separators=(",", ":")).encode()


def _encode_signature(signature: bytes) -> str:
    encoded = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    if _SIGNATURE_PATTERN.fullmatch(encoded) is None:
        raise ValueError("invalid contribution signature")
    return encoded


def create_contribution_proof(
    identity: Ed25519PrivateKey, artifact_url: str, commit: str
) -> dict[str, str]:
    """Create a signed proof without writing it to disk."""
    payload = contribution_payload(artifact_url, commit)
    return {
        "schema": SCHEMA,
        "did": public_key_to_did(identity.public_key()),
        "artifact_url": _validate_artifact_url(artifact_url),
        "commit": _validate_commit(commit),
        "signature": _encode_signature(identity.sign(payload)),
    }


def verify_contribution_proof(proof: dict[str, Any]) -> None:
    """Raise ValueError unless a public contribution proof is valid."""
    required = ("schema", "did", "artifact_url", "commit", "signature")
    if proof.get("schema") != SCHEMA or any(
        not isinstance(proof.get(key), str) for key in required
    ):
        raise ValueError("unsupported or incomplete contribution proof")
    signature = proof["signature"]
    if _SIGNATURE_PATTERN.fullmatch(signature) is None:
        raise ValueError("invalid contribution signature encoding")
    try:
        raw_signature = base64.urlsafe_b64decode(signature + "==")
        did_to_public_key(proof["did"]).verify(
            raw_signature, contribution_payload(proof["artifact_url"], proof["commit"])
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("contribution proof signature is invalid") from exc


def write_proof(path: str | Path, proof: dict[str, str]) -> None:
    """Write a proof without overwriting an existing file."""
    target = Path(path)
    if target.exists():
        raise FileExistsError(path)
    target.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")