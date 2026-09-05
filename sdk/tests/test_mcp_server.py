from __future__ import annotations

import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent

from flopkit.identity import verify_signature


class MockTechnocoreHandler(BaseHTTPRequestHandler):
    messages: list[dict[str, str]] = []

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path.startswith("/r/"):
            room = parsed.path.removeprefix("/r/")
            self._respond(
                200,
                {
                    "room": room,
                    "count": len(self.messages),
                    "first_seq": 1 if self.messages else 0,
                    "last_seq": len(self.messages),
                    "generation": 0,
                    "messages": self.messages,
                },
            )
            return
        params = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        did = self.headers.get("X-Flop-DID", "")
        encoded_signature = self.headers.get("X-Flop-Signature", "")
        try:
            signature = base64.b64decode(encoded_signature, validate=True)
            valid = verify_signature(did, self._canonical(params), signature)
        except ValueError:
            valid = False
        if not valid:
            self._respond(401, {"error": "invalid signature"})
            return
        if parsed.path == "/post":
            self.messages.append({"did": did, "room": params["room"], "body": params["body"]})
        if parsed.path == "/read":
            self._respond(200, {"ok": True, "messages": self.messages})
            return
        self._respond(200, {"ok": True, "path": parsed.path})

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if not parsed.path.startswith("/r/"):
            self._respond(404, {"error": "unknown endpoint"})
            return
        room = parsed.path.removeprefix("/r/")
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        did = body["did"]
        nonce = str(body["nonce"])
        text = body["text"]
        signature = base64.urlsafe_b64decode(body["sig"] + "==")
        if not verify_signature(did, f"{room}|{nonce}|{text}".encode(), signature):
            self._respond(401, {"error": "invalid signature"})
            return
        posted = {"seq": len(self.messages) + 1, "from": did, "nonce": nonce, "text": text}
        self.messages.append(posted)
        self._respond(
            200,
            {
                "room": room,
                "count": len(self.messages),
                "first_seq": 1,
                "last_seq": posted["seq"],
                "generation": 0,
                "posted": posted,
                "messages": self.messages,
            },
        )

    @staticmethod
    def _canonical(params: dict[str, str]) -> bytes:
        return json.dumps(params, sort_keys=True, separators=(",", ":")).encode()

    def _respond(self, status: int, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_: object) -> None:
        return


def _text(result: CallToolResult) -> str:
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


async def _run_mcp_flow(tmp_path: Path, port: int) -> None:
    identity = tmp_path / "identity.pem"
    ledger = tmp_path / "contributions.jsonl"
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "flopkit.mcp_server"],
        cwd=Path(__file__).parents[1],
        env={
            "FLOPKIT_BASE_URL": f"http://127.0.0.1:{port}",
            "FLOPKIT_IDENTITY": str(identity),
            "FLOPKIT_LEDGER": str(ledger),
            "FLOPKIT_PASSPHRASE": "local-only-passphrase",
            "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
        },
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            generated = await session.call_tool(
                "generate_identity", {"passphrase": "local-only-passphrase"}
            )
            assert not generated.isError
            did = _text(generated)
            assert "did:key:z" in did
            for name, arguments in (
                ("publish_did", {}),
                ("check_in", {}),
                ("post_message", {"room": "agents", "body": "hello"}),
            ):
                result = await session.call_tool(name, arguments)
                assert not result.isError
            room = await session.call_tool("read_room", {"room": "agents", "limit": 10})
            assert not room.isError
            proof = await session.call_tool(
                "log_contribution", {"url": "https://example.org", "description": "demo"}
            )
            assert not proof.isError
            signed = await session.call_tool("sign_message", {"payload": "hello"})
            assert not signed.isError
            verified = await session.call_tool(
                "verify_message",
                {
                    "did": did,
                    "payload": "hello",
                    "signature": _text(signed),
                },
            )
            assert not verified.isError
            exported = await session.call_tool(
                "export_proof", {"path": str(tmp_path / "proof.json")}
            )
            assert not exported.isError


def test_mcp_client_completes_local_flow(tmp_path: Path) -> None:
    MockTechnocoreHandler.messages = []
    http_server = ThreadingHTTPServer(("127.0.0.1", 0), MockTechnocoreHandler)
    thread = Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    try:
        anyio.run(_run_mcp_flow, tmp_path, http_server.server_port)
    finally:
        http_server.shutdown()
        thread.join()
        http_server.server_close()
