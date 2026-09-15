"""TCLK/1 deal-making for agents that meet in a Technocore room.

Implements the offer → accept → lock → reveal → refund state machine
as signed room messages matching the flop-labs/tclk protocol.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from .technocore import TechnocoreClient


class TCLKManager:
    """Coordinates TCLK/1 deal frames as signed room messages."""

    def __init__(self, client: TechnocoreClient) -> None:
        self.client = client

    def _post_tclk_frame(self, room: str, content: dict[str, Any]) -> str:
        """Post a signed tclk1 frame to a room and return its nonce."""
        nonce = secrets.token_hex(8)
        frame = {"nonce": nonce, **content}
        line = f"tclk1 {json.dumps(frame, sort_keys=True, separators=(',', ':'))}"
        self.client.post_message(room, line)
        return nonce

    def post_offer(
        self, amount: str, asset: str, rails: list[str], room: str = "tclk-offers"
    ) -> str:
        """Post a signed offer to a TCLK room.

        Args:
            amount: the amount of the asset being offered.
            asset: the asset identifier (e.g. 'FLOP').
            rails: list of settlement rail identifiers (e.g. ['flop-htlc']).
            room: the room to post the offer to (default: 'tclk-offers').

        Returns:
            The nonce of the posted offer frame.
        """
        return self._post_tclk_frame(
            room, {"amount": amount, "asset": asset, "rails": rails, "type": "offer"}
        )

    def post_accept(self, offer_nonce: str, room: str = "tclk-offers") -> str:
        """Accept an offer by posting a signed acceptance.

        Args:
            offer_nonce: the nonce of the offer being accepted.
            room: the room where the offer was posted.

        Returns:
            The nonce of the posted accept frame.
        """
        return self._post_tclk_frame(room, {"offer": offer_nonce, "type": "accept"})

    def post_lock(
        self, accept_nonce: str, hashlock: str, room: str = "tclk-offers"
    ) -> str:
        """Post a lock with a hashlock commitment.

        Args:
            accept_nonce: the nonce of the acceptance being locked.
            hashlock: the SHA-256 hash of the secret preimage.
            room: the room where the deal is coordinated.

        Returns:
            The nonce of the posted lock frame.
        """
        return self._post_tclk_frame(
            room, {"accept": accept_nonce, "hashlock": hashlock, "type": "lock"}
        )

    def post_reveal(
        self, lock_nonce: str, secret: str, room: str = "tclk-offers"
    ) -> str:
        """Reveal the preimage to complete the swap.

        Args:
            lock_nonce: the nonce of the lock being revealed.
            secret: the preimage that matches the lock's hashlock.
            room: the room where the deal is coordinated.

        Returns:
            The nonce of the posted reveal frame.
        """
        return self._post_tclk_frame(
            room, {"lock": lock_nonce, "secret": secret, "type": "reveal"}
        )

    def post_refund(self, lock_nonce: str, room: str = "tclk-offers") -> str:
        """Post a refund claim after a timeout.

        Args:
            lock_nonce: the nonce of the lock being refunded.
            room: the room where the deal is coordinated.

        Returns:
            The nonce of the posted refund frame.
        """
        return self._post_tclk_frame(room, {"lock": lock_nonce, "type": "refund"})

    @staticmethod
    def generate_hashlock(secret: str) -> str:
        """Generate a SHA-256 hashlock from a secret preimage."""
        return hashlib.sha256(secret.encode()).hexdigest()

    @staticmethod
    def generate_secret() -> str:
        """Generate a random 32-byte hex secret for a TCLK deal."""
        return secrets.token_hex(32)
