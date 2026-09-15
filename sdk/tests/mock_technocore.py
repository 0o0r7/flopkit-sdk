from __future__ import annotations

import base64
import json
from collections import defaultdict
from typing import Any
from urllib.parse import unquote

import httpx

from flopkit.identity import verify_signature
from flopkit.technocore import sweep_single_line


class MockTechnocore:
    """HTTPX MockTransport handler for the verified room protocol."""

    def __init__(self, *, reject_signature: bool = False) -> None:
        self.reject_signature = reject_signature
        self.calls: list[str] = []
        self.reads: list[str] = []
        self.messages: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.notes: dict[tuple[str, str], str] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/r/"):
            return self._room(request)
        if path.startswith("/kv/"):
            return self._note(request)
        if path == "/rooms":
            lines = [f"/r/{room}" for room in self.messages]
            res_text = "\n".join(lines) + ("\n" if lines else "")
            return httpx.Response(200, text=res_text)
        return httpx.Response(404, json={"error": "unknown endpoint"})

    def _room(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        remainder = path.removeprefix("/r/")

        # GET signed-write lane: /r/<room>/say-signed/<did>/<sig>/<nonce>/<text>
        if "/say-signed/" in remainder and request.method == "GET":
            room = remainder.split("/say-signed/", 1)[0]
            return self._handle_signed_get(room, path)

        room = remainder

        if request.method == "GET":
            self.reads.append(path)
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
            decoded_signature = base64.urlsafe_b64decode(signature + "==")
        except Exception:
            decoded_signature = b""
        valid = verify_signature(did, canonical, decoded_signature)
        if self.reject_signature or not valid:
            return httpx.Response(401, json={"error": "invalid signature"})
        self.calls.append(path)
        seq = len(self.messages[room]) + 1
        posted: dict[str, Any] = {"seq": seq, "from": did, "nonce": nonce, "text": text}
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

    def _handle_signed_get(self, room: str, path: str) -> httpx.Response:
        """Handle GET /r/<room>/say-signed/<did>/<sig>/<nonce>/<text>."""
        parts = path.split("/say-signed/", 1)[1].split("/", 3)
        if len(parts) != 4:
            return httpx.Response(400, json={"error": "malformed signed-write path"})
        did, signature, nonce, encoded_text = parts
        text = unquote(encoded_text)
        canonical = f"{room}|{nonce}|{text}".encode()
        try:
            decoded_signature = base64.urlsafe_b64decode(signature + "==")
        except Exception:
            decoded_signature = b""
        valid = verify_signature(did, canonical, decoded_signature)
        if self.reject_signature or not valid:
            return httpx.Response(401, json={"error": "invalid signature"})
        self.calls.append(path)
        seq = len(self.messages[room]) + 1
        posted: dict[str, Any] = {"seq": seq, "from": did, "nonce": nonce, "text": text}
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
        path = request.url.path
        # GET note-write lane: /kv/<ns>/<key>/set/<value>
        if "/set/" in path and request.method == "GET":
            return self._handle_note_set(path, request)
        parts = path.removeprefix("/kv/").split("/")
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

    def _handle_note_set(self, path: str, request: httpx.Request) -> httpx.Response:
        """Handle GET /kv/<ns>/<key>/set/<value>."""
        remainder = path.removeprefix("/kv/")
        parts = remainder.split("/set/", 1)
        if len(parts) != 2:
            return httpx.Response(400, json={"error": "malformed note-set path"})
        ns_key = parts[0].split("/")
        if len(ns_key) != 2:
            return httpx.Response(400, json={"error": "malformed note-set path"})
        ns, key = ns_key
        value = unquote(parts[1])
        current = self.notes.get((ns, key))
        params = request.url.params
        if "if" in params and current != params["if"]:
            return httpx.Response(409, text=current or "")
        if params.get("if_absent") in {"1", "true", "yes"} and current is not None:
            return httpx.Response(409, text=current)
        self.notes[(ns, key)] = sweep_single_line(value)
        return httpx.Response(200, text="ok")


def transport_for(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)
