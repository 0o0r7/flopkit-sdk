from __future__ import annotations
import json
import secrets
from typing import Any

class TCLKManager:
    """Manages the state machine and coordination for TCLK/1 deals."""
    def __init__(self, client):
        self.client = client

    def post_offer(self, amount: str, asset: str, rails: list[str]) -> str:
        """Post a signed offer to the public tclk-offers room."""
        content = {
            "amount": amount,
            "asset": asset,
            "rails": rails,
            "nonce": secrets.token_hex(8),
            "type": "offer"
        }
        line = f"tclk1 {json.dumps(content, sort_keys=True, separators=(',', ':'))}"
        self.client.post_message("tclk-offers", line)
        return content["nonce"]
