from __future__ import annotations

import base64
import json
import re
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


_NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}")
_NONCE_PATTERN = re.compile(r"[0-9]{1,19}")
_SIGNATURE_PATTERN = re.compile(r"[A-Za-z0-9_-]{86}")
_MAX_MESSAGE_CHARS = 4096
_INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Zl", "Zp"})


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


def validate_nonce(nonce: str | int) -> str:
    """Validate a numeric nonce accepted by the signed-write protocol."""
    value = str(nonce)
    if _NONCE_PATTERN.fullmatch(value) is None:
        raise ValueError("nonce must contain 1-19 ASCII digits")
    return value


def normalize_message(text: str) -> str:
    """Mirror Technocore's single-line normalization before signing."""
    if not isinstance(text, str):
        raise ValueError("message text must be a string")
    normalized = "".join(
        " " if unicodedata.category(character) in _INVISIBLE_CATEGORIES else character
        for character in text
    ).strip()
    if not normalized:
        raise ValueError("message has no visible text after normalization")
    if len(normalized) > _MAX_MESSAGE_CHARS:
        raise ValueError(f"message exceeds {_MAX_MESSAGE_CHARS} characters")
    return normalized


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
    def __init__(self, identity: Ed25519PrivateKey, config: TechnocoreConfig | None = None,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.identity = identity
        self.config = config or TechnocoreConfig()
        self.base_url = validate_base_url(self.config.base_url)
        self._client = httpx.Client(base_url=self.base_url, timeout=self.config.timeout,
                                    transport=transport)
        self.did = public_key_to_did(identity.public_key())

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

    def _legacy_request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        canonical = json.dumps(params, sort_keys=True, separators=(",", ":")).encode()
        headers = {
            self.config.did_header: self.did,
            self.config.signature_header: base64.b64encode(
                sign_bytes(self.identity, canonical)
            ).decode(),
        }
        last: Exception | None = None
        for attempt in range(self.config.retries + 1):
            try:
                response = self._client.get(path, params=params, headers=headers)
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "server error", request=response.request, response=response
                    )
                if response.status_code >= 400:
                    raise TechnocoreError(
                        f"Technocore request failed with HTTP {response.status_code}"
                    )
                return self._json_object(response)
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last = exc
                if attempt >= self.config.retries:
                    break
                time.sleep(0.05 * (2 ** attempt))
        raise TechnocoreError("Technocore request failed after retries") from last

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

    def publish_did(self) -> dict[str, Any]:
        return self._legacy_request(self.config.publish_path, {"did": self.did})

    def check_in(self) -> dict[str, Any]:
        return self._legacy_request(self.config.check_in_path, {"did": self.did})

    def post_message(self, room: str, body: str, nonce: str | int | None = None) -> dict[str, Any]:
        selected_nonce = validate_nonce(nonce if nonce is not None else time.time_ns())
        normalized, payload = message_payload(room, selected_nonce, body)
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
