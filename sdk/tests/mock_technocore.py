from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import httpx

from flopkit.identity import verify_signature


class MockTechnocore:
    """HTTPX MockTransport handler for the verified room protocol."""

    def __init__(self, *, reject_signature: bool = False) -> None:
        self.reject_signature = reject_signature
        self.calls: list[str] = []
        self.messages: dict[str, list[dict[str, str]]] = defaultdict(list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if not request.url.path.startswith("/r/"):
            return httpx.Response(404, json={"error": "unknown endpoint"})
        room = request.url.path.removeprefix("/r/")
        if request.method == "GET":
            messages = self.messages[room]
            return httpx.Response(
                200,
                json={
                    "room": room,
                    "count": len(messages),
                    "first_seq": 1 if messages else 0,
                    "last_seq": len(messages),
                    "generation": 0,
                    "messages": messages,
                },
            )
        if request.method != "POST":
            return httpx.Response(405, json={"error": "method not allowed"})
        body = json.loads(request.content)
        did = body.get("did", "")
        nonce = str(body.get("nonce", ""))
        text = body.get("text", "")
        signature = body.get("sig", "")
        canonical = f"{room}|{nonce}|{text}".encode()
        try:
            import base64

            decoded_signature = base64.urlsafe_b64decode(signature + "==")
        except Exception:
            decoded_signature = b""
        valid = verify_signature(did, canonical, decoded_signature)
        if self.reject_signature or not valid:
            return httpx.Response(401, json={"error": "invalid signature"})
        self.calls.append(request.url.path)
        seq = len(self.messages[room]) + 1
        posted = {"seq": seq, "from": did, "nonce": nonce, "text": text}
        self.messages[room].append(posted)
        return httpx.Response(
            200,
            json={
                "room": room,
                "count": len(self.messages[room]),
                "first_seq": 1,
                "last_seq": seq,
                "generation": 0,
                "posted": posted,
                "messages": self.messages[room],
            },
        )


def transport_for(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)
