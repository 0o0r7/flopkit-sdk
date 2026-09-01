from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .config import TechnocoreConfig
from .identity import public_key_to_did, sign_bytes


class TechnocoreError(RuntimeError):
    """Base exception for Technocore failures."""


class TechnocoreClient:
    def __init__(self, identity: Ed25519PrivateKey, config: TechnocoreConfig | None = None,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.identity = identity
        self.config = config or TechnocoreConfig()
        self._client = httpx.Client(base_url=self.config.base_url, timeout=self.config.timeout,
                                    transport=transport)
        self.did = public_key_to_did(identity.public_key())

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TechnocoreClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
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
                value = response.json()
                return value if isinstance(value, dict) else {"data": value}
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last = exc
                if attempt >= self.config.retries:
                    break
                time.sleep(0.05 * (2 ** attempt))
        raise TechnocoreError("Technocore request failed after retries") from last

    def publish_did(self) -> dict[str, Any]:
        return self._request(self.config.publish_path, {"did": self.did})

    def check_in(self) -> dict[str, Any]:
        return self._request(self.config.check_in_path, {"did": self.did})

    def post_message(self, room: str, body: str) -> dict[str, Any]:
        return self._request(self.config.post_path, {"did": self.did, "room": room, "body": body})

    def read_room(self, room: str) -> dict[str, Any]:
        return self._request(self.config.read_path, {"did": self.did, "room": room})
