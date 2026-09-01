from __future__ import annotations

import base64
import json
from collections import defaultdict
from typing import Any

import httpx

from flopkit.identity import verify_signature


class MockTechnocore:
    """HTTPX MockTransport handler that verifies every signed request."""

    paths = ("/publish", "/check-in", "/post", "/read")

    def __init__(self, *, reject_signature: bool = False) -> None:
        self.reject_signature = reject_signature
        self.calls: list[str] = []
        self.messages: dict[str, list[dict[str, str]]] = defaultdict(list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path not in self.paths:
            return httpx.Response(404, json={"error": "unknown endpoint"})
        did = request.headers.get("X-Flop-DID", "")
        encoded_signature = request.headers.get("X-Flop-Signature", "")
        try:
            signature = base64.b64decode(encoded_signature, validate=True)
        except Exception:
            signature = b""
        params = dict(request.url.params)
        canonical = json.dumps(params, sort_keys=True, separators=(",", ":")).encode()
        valid = verify_signature(did, canonical, signature)
        if self.reject_signature or not valid:
            return httpx.Response(401, json={"error": "invalid signature"})
        self.calls.append(request.url.path)
        if request.url.path == "/post":
            self.messages[params["room"]].append({"did": did, "body": params["body"]})
        if request.url.path == "/read":
            return httpx.Response(200, json={"ok": True, "messages": self.messages[params["room"]]})
        return httpx.Response(200, json={"ok": True, "path": request.url.path})


def transport_for(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)
