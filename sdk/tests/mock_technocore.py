from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import httpx

from flopkit.identity import verify_signature
from flopkit.technocore import sweep_single_line


class MockTechnocore:
    """HTTPX MockTransport handler for the verified room protocol."""

    def __init__(self, *, reject_signature: bool = False) -> None:
        self.reject_signature = reject_signature
        self.calls: list[str] = []
        self.reads: list[str] = []
        self.messages: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.notes: dict[tuple[str, str], str] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/r/"):
            return self._room(request)
        if request.url.path.startswith("/kv/"):
            return self._note(request)
        if request.url.path == "/rooms":
            res_text = "\n".join(self.messages) + ("\n" if self.messages else "")
            return httpx.Response(200, text=res_text)
        return httpx.Response(404, json={"error": "unknown endpoint"})

    def _room(self, request: httpx.Request) -> httpx.Response:
        room = request.url.path.removeprefix("/r/")
        if request.method == "GET":
            self.reads.append(request.url.path)
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

    def _note(self, request: httpx.Request) -> httpx.Response:
        parts = request.url.path.removeprefix("/kv/").split("/")
        if len(parts) != 2 or request.method not in {"GET", "POST"}:
            return httpx.Response(404, json={"error": "unknown endpoint"})
        ns, key = parts
        current = self.notes.get((ns, key))
        if request.method == "GET":
            if current is None:
                return httpx.Response(404, text="")
            return httpx.Response(200, text=current)
        body = json.loads(request.content)
        if "if" in body and current != body["if"]:
            return httpx.Response(409, text=current or "")
        if body.get("if_absent") is True and current is not None:
            return httpx.Response(409, text=current)
        self.notes[(ns, key)] = sweep_single_line(str(body.get("value", "")))
        return httpx.Response(200, text="ok")


def transport_for(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)
