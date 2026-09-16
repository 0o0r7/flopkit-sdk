"""DID delegation support matching technocore-chat PR #719.

Allows a browser/agent key to delegate signing authority to another agent
DID with scope, expiry, and nonce-based revocation. Delegation records
live in the issuer's DID note as:

    delegate: <agent-did> <scope> <expires> <nonce> <sig>

Higher nonce wins per agent; expired records are rejected.
"""
from __future__ import annotations

import re
import time

from .identity import sign_bytes, verify_signature
from .technocore import TechnocoreClient, did_note_path

_DELEGATE_PREFIX = "delegate:"
_SCOPE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")


class DelegationError(ValueError):
    """Raised when a delegation operation fails."""


class DelegationManager:
    """Manages DID delegation records in Technocore DID notes."""

    def __init__(self, client: TechnocoreClient) -> None:
        self.client = client

    @property
    def did(self) -> str:
        return self.client.did

    def create_delegate(
        self,
        agent_did: str,
        scope: str,
        expires_ms: int,
    ) -> dict[str, str]:
        """Post a signed delegation record to this identity's DID note.

        Args:
            agent_did: the DID of the agent being delegated to.
            scope: the scope of authority (e.g. 'r:lobby', 'tclk1').
            expires_ms: Unix ms after which the delegation expires.
                Use 0 for no expiry.

        Returns:
            Dict with 'agent_did', 'scope', 'nonce', and 'record'.
        """
        if not isinstance(agent_did, str) or not agent_did.startswith("did:key:"):
            raise DelegationError("agent_did must be a valid did:key")
        if not isinstance(scope, str) or _SCOPE_RE.match(scope) is None:
            raise DelegationError("scope must match ^[a-z0-9][a-z0-9_-]{0,47}$")
        if not isinstance(expires_ms, int) or isinstance(expires_ms, bool) or expires_ms < 0:
            raise DelegationError("expires_ms must be a non-negative integer")

        nonce = str(time.time_ns())
        # Sign the delegation record: <issuer-did>|<agent-did>|<scope>|<expires>|<nonce>
        canonical = f"{self.did}|{agent_did}|{scope}|{expires_ms}|{nonce}".encode()
        sig = sign_bytes(self.client.identity, canonical)  # type: ignore[arg-type]
        sig_hex = sig.hex()

        record = f"{_DELEGATE_PREFIX} {agent_did} {scope} {expires_ms} {nonce} {sig_hex}"

        # Read current DID note and append the delegation record
        shard, key = did_note_path(self.did)
        current = self.client.read_note(f"did-{shard}", key) or self.did
        # Remove any existing delegation for this agent (higher nonce replaces)
        updated = self._replace_or_append(current, record, agent_did)
        self.client.write_note(f"did-{shard}", key, updated)

        return {
            "agent_did": agent_did,
            "scope": scope,
            "nonce": nonce,
            "record": record,
        }

    def verify_delegate(
        self,
        issuer_did: str,
        agent_did: str,
    ) -> dict[str, str | bool | int] | None:
        """Verify whether an agent has a valid delegation from an issuer.

        Returns the delegation record if valid, or None if no valid
        delegation exists (expired, revoked, or not found).

        Args:
            issuer_did: the DID of the delegating identity.
            agent_did: the DID of the agent claiming delegation.

        Returns:
            Dict with 'scope', 'expires_ms', 'nonce', 'valid' or None.
        """
        shard, key = did_note_path(issuer_did)
        note = self.client.read_note(f"did-{shard}", key)
        if note is None:
            # Try legacy path
            note = self.client.read_note("did", did_note_path(issuer_did)[1])
        if note is None:
            return None

        # Find all delegation records for this agent, pick highest nonce.
        # Notes are single-line (newlines swept to spaces), so we scan for
        # delegate: tokens in the flattened text.
        best: dict[str, str | int] | None = None
        best_nonce = -1
        tokens = note.split()
        i = 0
        while i < len(tokens):
            if tokens[i] == _DELEGATE_PREFIX and i + 5 <= len(tokens) - 1:
                # delegate: <agent-did> <scope> <expires> <nonce> <sig>
                record_agent = tokens[i + 1]
                scope = tokens[i + 2]
                expires_str = tokens[i + 3]
                nonce_str = tokens[i + 4]
                sig_hex = tokens[i + 5]
                if record_agent == agent_did:
                    try:
                        nonce_int = int(nonce_str)
                    except ValueError:
                        i += 6
                        continue
                    if nonce_int > best_nonce:
                        best_nonce = nonce_int
                        best = {
                            "agent_did": record_agent,
                            "scope": scope,
                            "expires_ms": int(expires_str),
                            "nonce": nonce_str,
                            "sig": sig_hex,
                        }
                i += 6
                continue
            i += 1

        if best is None:
            return None

        # Check expiry
        expires_ms = int(best["expires_ms"])
        if expires_ms > 0:
            now_ms = int(time.time() * 1000)
            if now_ms >= expires_ms:
                return {
                    "scope": str(best["scope"]),
                    "expires_ms": expires_ms,
                    "nonce": str(best["nonce"]),
                    "valid": False,
                    "reason": "expired",
                }

        # Verify signature
        canonical = (
            f"{issuer_did}|{agent_did}|{best['scope']}|{best['expires_ms']}|{best['nonce']}"
        ).encode()
        try:
            sig_bytes = bytes.fromhex(str(best["sig"]))
        except ValueError:
            return None

        valid = verify_signature(issuer_did, canonical, sig_bytes)
        if not valid:
            return None

        # Check if revoked (scope is empty or "revoked")
        if str(best["scope"]) in {"", "revoked"}:
            return {
                "scope": str(best["scope"]),
                "expires_ms": expires_ms,
                "nonce": str(best["nonce"]),
                "valid": False,
                "reason": "revoked",
            }

        return {
            "scope": str(best["scope"]),
            "expires_ms": expires_ms,
            "nonce": str(best["nonce"]),
            "valid": True,
        }

    def revoke_delegate(self, agent_did: str) -> dict[str, str]:
        """Revoke a delegation by posting a record with empty scope and higher nonce.

        Args:
            agent_did: the DID of the agent whose delegation is being revoked.

        Returns:
            Dict with 'agent_did', 'nonce', and 'record'.
        """
        if not isinstance(agent_did, str) or not agent_did.startswith("did:key:"):
            raise DelegationError("agent_did must be a valid did:key")

        nonce = str(time.time_ns())
        # Sign the revocation record
        canonical = f"{self.did}|{agent_did}|revoked|0|{nonce}".encode()
        sig = sign_bytes(self.client.identity, canonical)  # type: ignore[arg-type]
        sig_hex = sig.hex()

        record = f"{_DELEGATE_PREFIX} {agent_did} revoked 0 {nonce} {sig_hex}"

        # Update DID note
        shard, key = did_note_path(self.did)
        current = self.client.read_note(f"did-{shard}", key) or self.did
        updated = self._replace_or_append(current, record, agent_did)
        self.client.write_note(f"did-{shard}", key, updated)

        return {
            "agent_did": agent_did,
            "nonce": nonce,
            "record": record,
        }

    @staticmethod
    def _replace_or_append(note: str, new_record: str, agent_did: str) -> str:
        """Replace any existing delegation for agent_did, or append the new record.

        Notes are single-line (newlines swept to spaces), so we work with
        space-separated tokens and scan for delegate: prefixes.
        """
        tokens = note.split()
        result: list[str] = []
        replaced = False
        i = 0
        while i < len(tokens):
            if tokens[i] == _DELEGATE_PREFIX and i + 5 < len(tokens):
                if tokens[i + 1] == agent_did:
                    # Skip the old record (6 tokens: delegate: agent scope expires nonce sig)
                    i += 6
                    result.append(new_record)
                    replaced = True
                    continue
            result.append(tokens[i])
            i += 1
        if not replaced:
            result.append(new_record)
        return " ".join(result)
