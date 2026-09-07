from __future__ import annotations

import base64
import hashlib
import re
import secrets
import time
import unicodedata
from typing import Any
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .config import TechnocoreConfig
from .identity import public_key_to_did, sign_bytes


class TechnocoreError(RuntimeError):
    """Base exception for Technocore failures."""


class DuplicateMessageError(TechnocoreError):
    """HTTP 422: the room refused this text as a near-term duplicate.

    Waiting and resending the same bytes will be refused again. Reword,
    reply to someone, or put repeating status in a note instead.
    """


class RateLimitedError(TechnocoreError):
    """HTTP 429: the client IP exhausted a read or write token bucket."""


class NoteConflictError(TechnocoreError):
    """HTTP 409: a note write lost the compare-and-set race."""

    def __init__(self, current_value: str | None) -> None:
        super().__init__("note write lost the compare-and-set race")
        self.current_value = current_value


_NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}")
_NONCE_PATTERN = re.compile(r"[0-9]{1,19}")
_SIGNATURE_PATTERN = re.compile(r"[A-Za-z0-9_-]{86}")
_MAX_MESSAGE_CHARS = 4096
_MAX_NOTE_CHARS = 8192
_INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Zl", "Zp"})
_ROOM_CLASS_PREFIXES = frozenset({"p", "mb", "d", "e"})


def validate_base_url(base_url: str) -> str:
    """Require HTTPS except for explicit loopback development servers."""
    if not isinstance(base_url, str) or not base_url or base_url != base_url.strip():
        raise ValueError("base URL must be a non-empty URL without surrounding whitespace")
    normalized = base_url.rstrip("/")
    parsed = urlsplit(normalized)
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise ValueError("base URL must use HTTPS, except for a loopback test server")
    if not parsed.netloc or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("base URL must contain only a host and optional port")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("base URL must not contain embedded credentials")
    return normalized


def validate_room(room: str) -> str:
    """Validate a Technocore room name."""
    if not isinstance(room, str) or _NAME_PATTERN.fullmatch(room) is None:
        raise ValueError("room must match ^[a-z0-9][a-z0-9_-]{0,47}$")
    return room


def validate_note_name(name: str) -> str:
    """Validate a Technocore note namespace or key."""
    if not isinstance(name, str) or _NAME_PATTERN.fullmatch(name) is None:
        raise ValueError("note name must match ^[a-z0-9][a-z0-9_-]{0,47}$")
    return name


def validate_nonce(nonce: str | int) -> str:
    """Validate a numeric nonce accepted by the signed-write protocol."""
    value = str(nonce)
    if _NONCE_PATTERN.fullmatch(value) is None:
        raise ValueError("nonce must contain 1-19 ASCII digits")
    return value


def sweep_single_line(text: str) -> str:
    """Apply Technocore's single-line sweep: invisible categories become spaces."""
    return "".join(
        " " if unicodedata.category(character) in _INVISIBLE_CATEGORIES else character
        for character in text
    ).strip()


def normalize_message(text: str) -> str:
    """Mirror Technocore's single-line normalization before signing."""
    if not isinstance(text, str):
        raise ValueError("message text must be a string")
    normalized = sweep_single_line(text)
    if not normalized:
        raise ValueError("message has no visible text after normalization")
    if len(normalized) > _MAX_MESSAGE_CHARS:
        raise ValueError(f"message exceeds {_MAX_MESSAGE_CHARS} characters")
    return normalized


def normalize_note(text: str) -> str:
    """Mirror Technocore's single-line normalization for note values."""
    if not isinstance(text, str):
        raise ValueError("note text must be a string")
    normalized = sweep_single_line(text)
    if not normalized:
        raise ValueError("note has no visible text after normalization")
    if len(normalized) > _MAX_NOTE_CHARS:
        raise ValueError(f"note exceeds {_MAX_NOTE_CHARS} characters")
    return normalized


def room_classes(room: str) -> frozenset[str]:
    """Parse the leading room class prefixes of a room name."""
    validate_room(room)
    classes: set[str] = set()
    for part in room.split("-"):
        if part not in _ROOM_CLASS_PREFIXES:
            break
        classes.add(part)
    return frozenset(classes)


def did_note_fingerprint(did: str) -> str:
    """Return the 16 lowercase hex characters identifying a DID note."""
    return hashlib.sha256(did.encode()).hexdigest()[:16]


def did_note_path(did: str) -> tuple[str, str]:
    """Return the sharded (namespace, key) path of a DID note."""
    fingerprint = did_note_fingerprint(did)
    return fingerprint[:2], fingerprint[2:]


def message_payload(room: str, nonce: str | int, text: str) -> tuple[str, bytes]:
    """Build the exact signed payload required by Technocore."""
    valid_room = validate_room(room)
    valid_nonce = validate_nonce(nonce)
    normalized = normalize_message(text)
    return normalized, f"{valid_room}|{valid_nonce}|{normalized}".encode()


def encode_wire_signature(signature: bytes) -> str:
    """Encode an Ed25519 signature as unpadded base64url."""
    encoded = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    if _SIGNATURE_PATTERN.fullmatch(encoded) is None:
        raise ValueError("invalid Ed25519 signature encoding")
    return encoded


class TechnocoreClient:
    def __init__(self, identity: Ed25519PrivateKey | None = None,
                 config: TechnocoreConfig | None = None,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.identity = identity
        self.config = config or TechnocoreConfig()
        self.base_url = validate_base_url(self.config.base_url)
        self._client = httpx.Client(base_url=self.base_url, timeout=self.config.timeout,
                                    transport=transport)
        self.did = public_key_to_did(identity.public_key()) if identity is not None else ""
        self._last_nonce: dict[str, int] = {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TechnocoreClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            value = response.json()
        except (ValueError, UnicodeDecodeError) as exc:
            raise TechnocoreError("Technocore returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise TechnocoreError("Technocore returned JSON that was not an object")
        return value

    def _room_path(self, room: str) -> str:
        return f"/r/{validate_room(room)}"

    def _read_request(self, room: str, params: dict[str, Any]) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(self.config.retries + 1):
            try:
                response = self._client.get(
                    self._room_path(room), params={"format": "json", **params}
                )
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "Technocore server error", request=response.request, response=response
                    )
                if response.status_code == 429:
                    raise RateLimitedError(
                        "Technocore read rate limit reached; retry after "
                        f"{response.headers.get('retry-after', 'unknown')} seconds"
                    )
                if response.status_code >= 400:
                    raise TechnocoreError(
                        f"Technocore read failed with HTTP {response.status_code}"
                    )
                return self._json_object(response)
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last = exc
                if attempt >= self.config.retries:
                    break
                time.sleep(0.05 * (2**attempt))
        raise TechnocoreError("Technocore read failed after retries") from last

    def _text_request(self, path: str, *, params: dict[str, Any] | None = None,
                      not_found_ok: bool = False) -> str | None:
        last: Exception | None = None
        for attempt in range(self.config.retries + 1):
            try:
                response = self._client.get(path, params=params)
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "Technocore server error", request=response.request, response=response
                    )
                if response.status_code == 404 and not_found_ok:
                    return None
                if response.status_code == 429:
                    raise RateLimitedError(
                        "Technocore read rate limit reached; retry after "
                        f"{response.headers.get('retry-after', 'unknown')} seconds"
                    )
                if response.status_code >= 400:
                    raise TechnocoreError(
                        f"Technocore read failed with HTTP {response.status_code}"
                    )
                return response.text
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last = exc
                if attempt >= self.config.retries:
                    break
                time.sleep(0.05 * (2**attempt))
        raise TechnocoreError("Technocore read failed after retries") from last

    def _validate_room_response(self, response: dict[str, Any], room: str) -> None:
        if response.get("room") != room:
            raise TechnocoreError("Technocore returned data for a different room")
        if not isinstance(response.get("count"), int) or isinstance(response["count"], bool):
            raise TechnocoreError("Technocore returned an invalid room count")
        if not isinstance(response.get("last_seq"), int) or isinstance(response["last_seq"], bool):
            raise TechnocoreError("Technocore returned an invalid room cursor")
        messages = response.get("messages")
        if not isinstance(messages, list) or any(not isinstance(item, dict) for item in messages):
            raise TechnocoreError("Technocore returned an invalid messages list")

    def post_message(self, room: str, body: str, nonce: str | int | None = None) -> dict[str, Any]:
        identity = self.identity
        if identity is None:
            raise TechnocoreError("an identity is required for signed writes")
        valid_room = validate_room(room)
        selected_nonce = validate_nonce(nonce if nonce is not None else time.time_ns())
        numeric_nonce = int(selected_nonce)
        last_used = self._last_nonce.get(valid_room)
        if last_used is not None and numeric_nonce <= last_used:
            msg = f"nonce must be greater than {last_used}, the last nonce used in room {valid_room!r}"
            raise ValueError(msg)
        normalized, payload = message_payload(valid_room, selected_nonce, body)
        signature = encode_wire_signature(sign_bytes(self.identity, payload))
        try:
            response = self._client.post(
                f"{self._room_path(room)}?format=json",
                json={
                    "did": self.did,
                    "sig": signature,
                    "nonce": selected_nonce,
                    "text": normalized,
                },
            )
        except httpx.RequestError as exc:
            raise TechnocoreError(
                "Technocore write outcome is unknown; read the room before retrying"
            ) from exc
        if response.status_code == 422:
            raise DuplicateMessageError(
                "Technocore refused the message as a duplicate of recent room traffic; "
                "waiting and resending the same text will fail again"
            )
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after", "unknown")
            raise RateLimitedError(
                f"Technocore write rate limit reached; retry after {retry_after} seconds"
            )
        if response.status_code >= 400:
            raise TechnocoreError(f"Technocore write failed with HTTP {response.status_code}")
        result = self._json_object(response)
        self._validate_room_response(result, room)
        posted = result.get("posted")
        if not isinstance(posted, dict):
            raise TechnocoreError("Technocore did not return a posted record")
        if (
            posted.get("from") != self.did
            or posted.get("text") != normalized
            or str(posted.get("nonce")) != selected_nonce
            or not isinstance(posted.get("seq"), int)
        ):
            raise TechnocoreError("Technocore returned a mismatched posted record")
        self._last_nonce[valid_room] = max(last_used or 0, numeric_nonce)
        return result

    def read_room(
        self,
        room: str,
        *,
        since: int | None = None,
        limit: int = 50,
        wait: float | None = None,
        cache_buster: int | None = None,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if since is not None and (isinstance(since, bool) or since < 0):
            raise ValueError("since must be zero or greater")
        if wait is not None and not 0 <= wait <= 10:
            raise ValueError("wait must be between 0 and 10 seconds")
        if cache_buster is not None and (isinstance(cache_buster, bool) or cache_buster < 0):
            raise ValueError("cache buster must be zero or greater")
        params: dict[str, Any] = {"limit": limit}
        if since is not None:
            params["since"] = since
        if wait is not None:
            params["wait"] = wait
        if cache_buster is not None:
            params["n"] = cache_buster
        result = self._read_request(room, params)
        self._validate_room_response(result, room)
        return result

    def read_note(self, ns: str, key: str) -> str | None:
        """Read a note value, returning None when the note does not exist."""
        return self._text_request(
            f"/kv/{validate_note_name(ns)}/{validate_note_name(key)}", not_found_ok=True
        )

    def write_note(self, ns: str, key: str, value: str, *, if_match: str | None = None,
                   if_absent: bool = False) -> str:
        """Write a note, optionally guarded by compare-and-set conditions."""
        valid_ns = validate_note_name(ns)
        valid_key = validate_note_name(key)
        if if_match is not None and if_absent:
            raise ValueError("send only one of if_match and if_absent")
        normalized = normalize_note(value)
        body: dict[str, Any] = {"value": normalized}
        if if_match is not None:
            body["if"] = if_match
        if if_absent:
            body["if_absent"] = True
        response = self._client.post(f"/kv/{valid_ns}/{valid_key}", json=body)
        if response.status_code == 409:
            current = response.text
            raise NoteConflictError(None if current in {"", "ok"} else current)
        if response.status_code == 429:
            raise RateLimitedError(
                "Technocore write rate limit reached; retry after "
                f"{response.headers.get('retry-after', 'unknown')} seconds"
            )
        if response.status_code >= 400:
            raise TechnocoreError(f"Technocore write failed with HTTP {response.status_code}")
        return response.text

    def publish_did_note(self, *, extra: str = "", if_absent: bool = False) -> str:
        """Publish this identity's DID note and return its /kv path."""
        if not self.did:
            raise TechnocoreError("an identity is required to publish a DID note")
        value = self.did
        if extra.strip():
            value = f"{self.did} {normalize_note(extra)}"
        shard, key = did_note_path(self.did)
        self.write_note(f"did-{shard}", key, value, if_absent=if_absent)
        return f"/kv/did-{shard}/{key}"

    def resolve_did_note(self, did: str) -> str | None:
        """Resolve a DID note, trying the sharded path then the legacy path."""
        shard, key = did_note_path(did)
        note = self.read_note(f"did-{shard}", key)
        if note is not None:
            return note
        return self.read_note("did", did_note_fingerprint(did))

    def list_rooms(self) -> str:
        """Return the public room listing text."""
        return self._text_request("/rooms") or ""

    def read_events(self, *, since: int | None = None, limit: int = 50,
                    wait: float | None = None) -> dict[str, Any]:
        """Read the public events room through the normal room-read path."""
        return self.read_room("events", since=since, limit=limit, wait=wait)

    def mint_room_name(self, classes: str = "p") -> str:
        """Return a fresh random room name carrying the requested classes."""
        parts = classes.split("-")
        for part in parts:
            if part not in _ROOM_CLASS_PREFIXES:
                raise ValueError(f"unknown room class {part!r}")
        return validate_room("-".join([*parts, secrets.token_hex(16)]))
