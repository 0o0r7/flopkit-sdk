"""Opt-in live integration tests against the real Technocore network.

There is no separate Technocore testnet: technocore.chat is the live
network, so this suite is strictly opt-in, self-contained, and polite:

- runs ONLY when the ``FLOPKIT_LIVE`` env var is set (skipped otherwise)
- creates one ephemeral in-memory identity (never persisted)
- issues fewer than a dozen single-line requests with pauses between them
- tags its one offer with ``job={"proto": "flopkit-itest", ...}`` and a
  short ``expiresMs`` so the frame is identifiable and self-expiring
- performs no reads of other parties' private state and no destructive ops

Run manually with::

    FLOPKIT_LIVE=1 pytest tests/test_live_integration.py -v
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

from flopkit.config import TechnocoreConfig
from flopkit.identity import generate_identity
from flopkit.tclk import (
    TCLKManager,
    TranscriptFoldResult,
    deal_room_name,
    fold_transcript,
)
from flopkit.technocore import TechnocoreClient

LIVE = os.environ.get("FLOPKIT_LIVE") == "1"
BASE_URL = os.environ.get("FLOPKIT_LIVE_BASE_URL", "")

pytestmark = pytest.mark.skipif(
    not LIVE, reason="live Technocore integration tests need FLOPKIT_LIVE=1"
)

PAUSE_S = 1.5


def _pause() -> None:
    time.sleep(PAUSE_S)


@pytest.fixture(scope="module")
def client() -> Any:
    """An ephemeral identity client against the live network."""
    with tempfile.TemporaryDirectory() as tmp:
        pem = Path(tmp) / "ephemeral.pem"
        key, _did = generate_identity("flopkit-live-itest", pem)
        config = TechnocoreConfig(base_url=BASE_URL) if BASE_URL else None
        with TechnocoreClient(key, config=config) as c:
            yield c
            _pause()


def test_live_publish_and_resolve_own_note(client: Any) -> None:
    """Publish an ephemeral DID note, then resolve it back from the network."""
    note_path = client.publish_did_note(extra="role:itest")
    _pause()
    assert note_path
    resolved = client.resolve_did_note(client.did)
    assert resolved is not None
    assert "role:itest" in resolved


def test_live_offer_post_read_fold(client: Any) -> None:
    """Post one self-expiring offer, read it back, and fold the transcript."""
    mgr = TCLKManager(client)
    now_ms = int(time.time() * 1000)
    result = mgr.post_offer(
        role="payer",
        amount="1",
        asset="FLOP",
        lock="hash",
        rails=["flop-htlc"],
        claim_by_ms=now_ms + 10 * 60 * 1000,
        refund_after_ms=now_ms + 20 * 60 * 1000,
        expires_ms=now_ms + 5 * 60 * 1000,
        job={"proto": "flopkit-itest", "id": "live-suite"},
    )
    _pause()
    assert result["id"].startswith("0x")

    room_data = client.read_room("tclk-offers", limit=50)
    _pause()
    records = [
        {
            "room": "tclk-offers",
            "seq": msg.get("seq"),
            "ts": msg.get("ts"),
            "from": msg.get("from"),
            "nonce": msg.get("nonce"),
            "sig": msg.get("sig", ""),
            "text": msg.get("text", ""),
        }
        for msg in room_data.get("messages", [])
    ]
    folded: TranscriptFoldResult = fold_transcript(records)
    mine = [o for o in folded.offers if o.get("id") == result["id"]]
    assert mine, "posted offer must be readable and conformantly folded"
    assert deal_room_name(mine[0]["id"]).startswith("mb-p-tclk-")
    assert mine[0]["job"]["proto"] == "flopkit-itest"


def test_live_state_pointer_roundtrip(client: Any) -> None:
    """Write and read back a tclk state pointer note for a scratch contract."""
    from flopkit.tclk import state_pointer_path

    scratch = "0x" + "ec" * 32
    ns, key = state_pointer_path(scratch)
    payload = "tclk1 state offered"
    client.write_note(ns, key, payload)
    _pause()
    back = client.read_note(ns, key)
    assert back == payload
