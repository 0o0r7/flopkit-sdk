from __future__ import annotations

import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

_PRIVATE_MULTICODEC = b"\xed\x01"
DID_PREFIX = "did:key:z"
PathLike = str | Path


def _reject_seed_phrase(value: str) -> None:
    lowered = value.lower()
    if "seed phrase" in lowered or "mnemonic" in lowered or len(value.split()) >= 12:
        raise ValueError("wallet seed phrases are not accepted")


def generate_identity(
    passphrase: str, path: PathLike = "identity.pem"
) -> tuple[Ed25519PrivateKey, str]:
    if not passphrase:
        raise ValueError("passphrase must not be empty")
    _reject_seed_phrase(passphrase)
    target = Path(path)
    if target.exists():
        raise FileExistsError(path)
    key = Ed25519PrivateKey.generate()
    encrypted = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.BestAvailableEncryption(passphrase.encode()))
    target.write_bytes(encrypted)
    os.chmod(target, 0o600)
    return key, public_key_to_did(key.public_key())


def load_identity(path: PathLike, passphrase: str) -> Ed25519PrivateKey:
    return serialization.load_pem_private_key(Path(path).read_bytes(), password=passphrase.encode())  # type: ignore[return-value]


def _base58_encode(data: bytes) -> str:
    alphabet = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n = int.from_bytes(data, "big")
    out = bytearray()
    while n:
        n, r = divmod(n, 58)
        out.append(alphabet[r])
    pad = len(data) - len(data.lstrip(b"\0"))
    return (alphabet[:1] * pad + bytes(reversed(out))).decode()


def _base58_decode(value: str) -> bytes:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n = 0
    for char in value:
        if char not in alphabet:
            raise ValueError("invalid DID encoding")
        n = n * 58 + alphabet.index(char)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(value) - len(value.lstrip("1"))) + raw


def public_key_to_did(pubkey: Ed25519PublicKey) -> str:
    raw = pubkey.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return DID_PREFIX + _base58_encode(_PRIVATE_MULTICODEC + raw)


def did_to_public_key(did: str) -> Ed25519PublicKey:
    if not did.startswith(DID_PREFIX):
        raise ValueError("unsupported DID")
    decoded = _base58_decode(did[len(DID_PREFIX):])
    if len(decoded) != 34 or decoded[:2] != _PRIVATE_MULTICODEC:
        raise ValueError("invalid Ed25519 DID")
    return Ed25519PublicKey.from_public_bytes(decoded[2:])


def sign_bytes(key: Ed25519PrivateKey, payload: bytes) -> bytes:
    return key.sign(payload)


def verify_signature(did: str, payload: bytes, signature: bytes) -> bool:
    try:
        did_to_public_key(did).verify(signature, payload)
        return True
    except (InvalidSignature, ValueError):
        return False
