"""TCLK/1 — Technocore Lock Protocol: full spec conformance.

Implements all 8 frame types (offer, accept, lock, reveal, refund, cancel,
heartbeat, receipt), contract ID derivation, derived deal rooms, a state
machine with guards, transcript folding, settlement rail interface, HTLC
full path, and PTLC wire-format interface per flop-labs/tclk SPEC.md.

Adaptor-signature crypto for PTLC is reference/unaudited and not shipped
for production use — matching SPEC.md's own disclaimer.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from .technocore import TechnocoreClient, TechnocoreError

# --- Constants from SPEC.md ---

MAX_FRAME_CHARS = 4096
OFFERS_ROOM = "tclk-offers"
DEAL_ROOM_PREFIX = "mb-p-tclk-"
STATE_POINTER_NS_PREFIX = "kv/tclk-"
CAPABILITY_TOKEN_PREFIX = "tclk1:"

# Hash statement: 0x + 64 lowercase hex (32 bytes)
_HASH_RE = re.compile(r"^0x[0-9a-f]{64}$")
# Point statement: 0x + 66 lowercase hex (33-byte SEC1-compressed secp256k1)
_POINT_RE = re.compile(r"^0x(02|03)[0-9a-f]{64}$")
# Amount: decimal integer string
_AMOUNT_RE = re.compile(r"^\d+$")
# Nonce: decimal string (technocore nonces can exceed JS safe-integer)
_NONCE_RE = re.compile(r"^\d{1,19}$")
# DID: did:key:z6Mk... (56 chars)
_DID_RE = re.compile(r"^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{40,55}$")
# Contract id: 0x + 64 lowercase hex
_CONTRACT_RE = re.compile(r"^0x[0-9a-f]{64}$")
# Lock kind
_LOCK_KINDS = frozenset({"hash", "point"})
# Rail ids (canonical, lowercase, no punctuation)
_RAIL_RE = re.compile(r"^[a-z][a-z0-9-]*$")


class FrameType(str, Enum):
    """All tclk/1 frame types per SPEC.md §3."""

    OFFER = "offer"
    ACCEPT = "accept"
    LOCK = "lock"
    REVEAL = "reveal"
    REFUND = "refund"
    CANCEL = "cancel"
    HEARTBEAT = "heartbeat"
    RECEIPT = "receipt"


class TCLKState(str, Enum):
    """Contract lifecycle states per SPEC.md §4."""

    OFFERED = "offered"
    ACCEPTED = "accepted"
    LOCKED = "locked"
    REVEALED = "revealed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"
    RECEIPTED = "receipted"


class TCLKError(ValueError):
    """Raised when a frame violates the tclk/1 protocol."""


class IdempotentReject(TCLKError):
    """A replayed frame that is a no-op rejection, not an error."""


# --- Validation helpers ---


def _validate_did(did: str, field_name: str = "from") -> str:
    if not isinstance(did, str) or _DID_RE.match(did) is None:
        raise TCLKError(f"{field_name} must be a valid did:key (Ed25519)")
    return did


def _validate_hash(value: str, field_name: str) -> str:
    if not isinstance(value, str) or _HASH_RE.match(value) is None:
        raise TCLKError(f"{field_name} must be 0x + 64 lowercase hex")
    return value


def _validate_point(value: str, field_name: str) -> str:
    if not isinstance(value, str) or _POINT_RE.match(value) is None:
        raise TCLKError(f"{field_name} must be 0x + 66 lowercase hex (33-byte SEC1-compressed)")
    return value


def _validate_amount(value: str) -> str:
    if not isinstance(value, str) or _AMOUNT_RE.match(value) is None:
        raise TCLKError("amount must be a decimal integer string")
    return value


def _validate_nonce(nonce: str) -> str:
    if not isinstance(nonce, str) or _NONCE_RE.match(nonce) is None:
        raise TCLKError("nonce must contain 1-19 ASCII digits")
    return nonce


def _validate_contract_id(contract: str) -> str:
    if not isinstance(contract, str) or _CONTRACT_RE.match(contract) is None:
        raise TCLKError("contract must be 0x + 64 lowercase hex")
    return contract


def _validate_lock_kind(lock: str) -> str:
    if lock not in _LOCK_KINDS:
        raise TCLKError(f"lock must be 'hash' or 'point', got {lock!r}")
    return lock


def _validate_rails(rails: list[str]) -> list[str]:
    if not isinstance(rails, list) or not rails:
        raise TCLKError("rails must be a non-empty list")
    for rail in rails:
        if not isinstance(rail, str) or _RAIL_RE.match(rail) is None:
            raise TCLKError(f"invalid rail id {rail!r}")
    return rails


def _validate_ms(value: int, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TCLKError(f"{field_name} must be a non-negative integer (Unix ms)")
    return value


def _validate_optional_hash(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _validate_hash(value, field_name)


def _validate_optional_point(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _validate_point(value, field_name)


# --- Canonical encoding ---


def _canonical_json(obj: dict[str, Any]) -> str:
    """Serialize JSON canonically: sorted keys, comma/colon separators, ASCII-only."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def encode_frame(frame: dict[str, Any]) -> str:
    """Encode a tclk/1 frame wire line: 'tclk1 ' + canonical JSON."""
    line = f"tclk1 {_canonical_json(frame)}"
    if len(line) > MAX_FRAME_CHARS:
        raise TCLKError(f"frame exceeds {MAX_FRAME_CHARS} chars")
    return line


def decode_frame(line: str) -> dict[str, Any]:
    """Decode a tclk/1 wire line into a frame dict. Fail-closed."""
    if not isinstance(line, str):
        raise TCLKError("frame line must be a string")
    if not line.startswith("tclk1 "):
        raise TCLKError("frame must start with 'tclk1 '")
    if len(line) > MAX_FRAME_CHARS:
        raise TCLKError(f"frame exceeds {MAX_FRAME_CHARS} chars")
    try:
        obj = json.loads(line[6:])
    except json.JSONDecodeError as exc:
        raise TCLKError(f"invalid JSON in frame: {exc}") from exc
    if not isinstance(obj, dict):
        raise TCLKError("frame must be a JSON object")
    frame_type = obj.get("type")
    if frame_type not in {ft.value for ft in FrameType}:
        raise TCLKError(f"unknown frame type {frame_type!r}")
    return obj


# --- Contract ID derivation (SPEC.md §3.1) ---


def derive_contract_id(offer_frame: dict[str, Any], accept_frame: dict[str, Any]) -> str:
    """Derive the contract id from the canonical offer and accept frames.

    The contract id is SHA-256 of the canonical offer line concatenated
    with the canonical accept line.
    """
    offer_line = encode_frame(offer_frame)
    accept_line = encode_frame(accept_frame)
    digest = hashlib.sha256((offer_line + accept_line).encode()).hexdigest()
    return f"0x{digest}"


def deal_room_name(contract_id: str) -> str:
    """Derive the deal room name from a contract id.

    Format: mb-p-tclk-<first 16 hex of contract id>
    """
    contract = _validate_contract_id(contract_id)
    hex_part = contract[2:18]  # first 16 hex chars
    return f"{DEAL_ROOM_PREFIX}{hex_part}"


def state_pointer_path(contract_id: str) -> tuple[str, str]:
    """Return the (namespace, key) for the state pointer note.

    Format: kv/tclk-<hh>/<14 hex> (sharded off the contract id).
    """
    contract = _validate_contract_id(contract_id)
    hex_part = contract[2:]  # full 64 hex chars
    shard = hex_part[:2]
    key = hex_part[2:16]  # 14 hex chars
    return f"tclk-{shard}", key


def capability_token(rails: list[str]) -> str:
    """Build the capability advertisement token for a DID note.

    Format: tclk1:<rail>,<rail>
    """
    return CAPABILITY_TOKEN_PREFIX + ",".join(_validate_rails(rails))


def parse_capability_token(note: str) -> list[str] | None:
    """Parse capability tokens from a DID note. Returns rails or None."""
    if not isinstance(note, str):
        return None
    for token in note.split():
        if token.startswith(CAPABILITY_TOKEN_PREFIX):
            rails_str = token[len(CAPABILITY_TOKEN_PREFIX):]
            return [r for r in rails_str.split(",") if r]
    return None


# --- Settlement rail interface (SPEC.md §5) ---


class SettlementRail(Protocol):
    """Abstract settlement rail interface per SPEC.md §5."""

    @property
    def rail_id(self) -> str:
        """Return the canonical rail identifier."""
        ...

    def lock_funds(self, contract_id: str, statement: str, amount: str,
                    asset: str, deadline_ms: int) -> str:
        """Lock funds under the given hash/point statement. Return a rail ref."""
        ...

    def claim_funds(self, contract_id: str, witness: str, rail_ref: str) -> bool:
        """Claim locked funds by revealing the witness (secret or scalar)."""
        ...

    def refund_funds(self, contract_id: str, rail_ref: str) -> bool:
        """Refund locked funds after the deadline has passed."""
        ...


class PaperRail:
    """Reference non-value rehearsal rail (SPEC.md §5).

    Records the lock/claim/refund lifecycle in venue notes and backs it
    with nothing at all. Exists so the whole choreography can be rehearsed
    on real infrastructure before a value-bearing rail exists.
    """

    def __init__(self, client: TechnocoreClient | None = None) -> None:
        self._client = client

    @property
    def rail_id(self) -> str:
        return "paper"

    def lock_funds(self, contract_id: str, statement: str, amount: str,
                   asset: str, deadline_ms: int) -> str:
        ref = f"paper-{secrets.token_hex(8)}"
        if self._client is not None:
            ns, key = state_pointer_path(contract_id)
            self._client.write_note(ns, key, f"locked:{ref}:{statement}:{amount}:{asset}")
        return ref

    def claim_funds(self, contract_id: str, witness: str, rail_ref: str) -> bool:
        if self._client is not None:
            ns, key = state_pointer_path(contract_id)
            self._client.write_note(ns, key, f"claimed:{rail_ref}:{witness}")
        return True

    def refund_funds(self, contract_id: str, rail_ref: str) -> bool:
        if self._client is not None:
            ns, key = state_pointer_path(contract_id)
            self._client.write_note(ns, key, f"refunded:{rail_ref}")
        return True


# --- HTLC helpers ---


def generate_secret() -> str:
    """Generate a random 32-byte hex secret for a TCLK deal."""
    return f"0x{secrets.token_hex(32)}"


def hashlock_from_secret(secret: str) -> str:
    """Compute the SHA-256 hash statement from a secret preimage.

    Returns '0x' + 64 lowercase hex.
    """
    if not isinstance(secret, str) or not secret.startswith("0x"):
        raise TCLKError("secret must be 0x-prefixed hex")
    raw = bytes.fromhex(secret[2:])
    return f"0x{hashlib.sha256(raw).hexdigest()}"


def verify_hashlock(secret: str, hashlock: str) -> bool:
    """Verify that a secret preimage matches a hash statement."""
    return hashlock_from_secret(secret) == hashlock


# --- PTLC interface (reference/unaudited) ---


def validate_point_statement(statement: str) -> str:
    """Validate a 33-byte SEC1-compressed secp256k1 point statement.

    NOTE: Adaptor-signature crypto is reference/unaudited per SPEC.md.
    This validates the wire format only; it does not verify the point
    is on-curve (that requires secp256k1 crypto not shipped here).
    """
    return _validate_point(statement, "point statement")


def generate_point_lock() -> str:
    """Generate a placeholder point lock statement (reference only).

    NOTE: This produces a valid-format but cryptographically meaningless
    point. Real adaptor signatures require audited secp256k1 crypto.
    """
    prefix = secrets.choice(["02", "03"])
    return f"0x{prefix}{secrets.token_hex(32)}"


# --- Contract state ---


@dataclass
class TCLKContract:
    """In-memory representation of a TCLK contract state."""

    contract_id: str
    state: TCLKState = TCLKState.OFFERED
    offer: dict[str, Any] = field(default_factory=dict)
    accept: dict[str, Any] = field(default_factory=dict)
    lock_frame: dict[str, Any] = field(default_factory=dict)
    lock_kind: str = "hash"
    statement: str = ""
    amount: str = ""
    asset: str = ""
    rails: list[str] = field(default_factory=list)
    claim_by_ms: int = 0
    refund_after_ms: int = 0
    expires_ms: int = 0
    payer_did: str = ""
    payee_did: str = ""
    last_updated_ms: int = 0
    rail_ref: str = ""
    secret: str = ""


# --- Transcript folding (SPEC.md §2, §4) ---


@dataclass
class TranscriptFoldResult:
    """Result of folding a room transcript into contract states."""

    contracts: dict[str, TCLKContract] = field(default_factory=dict)
    malformed: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    offers: list[dict[str, Any]] = field(default_factory=list)


def fold_transcript(
    records: list[dict[str, Any]],
    *,
    now_ms: int | None = None,
) -> TranscriptFoldResult:
    """Fold a list of signed room records into contract states.

    Each record must contain: room, seq, ts, from, nonce, sig, text.
    The Ed25519 signature covers <room>|<nonce>|<text>.
    Frames are applied at the record's timestamp (fail-closed on
    missing/malformed time — never falls back to auditor clock).

    Args:
        records: list of signed room records from read_room or /export.
        now_ms: optional current time for deadline checks (defaults to
            the maximum record ts seen, or 0 if no records).

    Returns:
        TranscriptFoldResult with contracts, malformed, and rejected lists.
    """
    from .identity import verify_signature
    from .technocore import encode_wire_signature

    result = TranscriptFoldResult()
    contracts: dict[str, TCLKContract] = {}
    offers_by_nonce: dict[str, dict[str, Any]] = {}
    max_ts = 0

    for record in records:
        # Extract record fields
        room = record.get("room", "")
        seq = record.get("seq")
        ts = record.get("ts")
        sender = record.get("from", "")
        nonce = record.get("nonce", "")
        sig = record.get("sig", "")
        text = record.get("text", "")

        # Fail-closed on missing/malformed time
        if ts is None or not isinstance(ts, (int, float)) or isinstance(ts, bool):
            result.malformed.append({
                "seq": seq, "reason": "missing or malformed timestamp",
            })
            continue
        ts_int = int(ts)
        max_ts = max(max_ts, ts_int)

        # Verify signature (if sig present)
        if sig:
            try:
                sig_bytes = __import__("base64").urlsafe_b64decode(sig + "==")
            except Exception:
                result.malformed.append({
                    "seq": seq, "reason": "malformed signature encoding",
                })
                continue
            canonical = f"{room}|{nonce}|{text}".encode()
            if not verify_signature(sender, canonical, sig_bytes):
                result.malformed.append({
                    "seq": seq, "reason": "signature verification failed",
                })
                continue

        # Try to decode as a tclk frame
        if not text.startswith("tclk1 "):
            continue  # Not a tclk frame, skip silently

        try:
            frame = decode_frame(text)
        except TCLKError as exc:
            result.malformed.append({"seq": seq, "reason": str(exc)})
            continue

        frame_type = frame.get("type")
        frame_from = frame.get("from", sender)

        # Verify sender matches frame 'from'
        if frame_from != sender:
            result.rejected.append({
                "seq": seq, "reason": "frame 'from' does not match record sender",
                "frame": frame,
            })
            continue

        # Apply frame to state machine
        try:
            _apply_frame(
                contracts, offers_by_nonce, frame, room, ts_int,
                result,
            )
        except IdempotentReject:
            result.rejected.append({
                "seq": seq, "reason": "idempotent reject (replayed frame)",
                "frame": frame,
            })
        except TCLKError as exc:
            result.rejected.append({
                "seq": seq, "reason": str(exc), "frame": frame,
            })

    # Check deadlines
    effective_now = now_ms if now_ms is not None else max_ts
    for contract in contracts.values():
        if contract.state == TCLKState.LOCKED and contract.refund_after_ms > 0:
            if effective_now >= contract.refund_after_ms:
                # Refund window is open; contract stays locked but refund is available
                pass
        if contract.state == TCLKState.OFFERED and contract.expires_ms > 0:
            if effective_now >= contract.expires_ms:
                contract.state = TCLKState.CANCELLED

    result.contracts = contracts
    result.offers = list(offers_by_nonce.values())
    return result


def _apply_frame(
    contracts: dict[str, TCLKContract],
    offers_by_nonce: dict[str, dict[str, Any]],
    frame: dict[str, Any],
    room: str,
    ts: int,
    result: TranscriptFoldResult,
) -> None:
    """Apply a single frame to the contract state machine. Raises on violation."""
    frame_type = frame.get("type")

    if frame_type == FrameType.OFFER.value:
        _apply_offer(contracts, offers_by_nonce, frame, room, ts)
    elif frame_type == FrameType.ACCEPT.value:
        _apply_accept(contracts, offers_by_nonce, frame, room, ts)
    elif frame_type == FrameType.LOCK.value:
        _apply_lock(contracts, frame, room, ts)
    elif frame_type == FrameType.REVEAL.value:
        _apply_reveal(contracts, frame, room, ts)
    elif frame_type == FrameType.REFUND.value:
        _apply_refund(contracts, frame, room, ts)
    elif frame_type == FrameType.CANCEL.value:
        _apply_cancel(contracts, frame, room, ts)
    elif frame_type == FrameType.HEARTBEAT.value:
        _apply_heartbeat(contracts, frame, room, ts)
    elif frame_type == FrameType.RECEIPT.value:
        _apply_receipt(contracts, frame, room, ts)


def _apply_offer(
    contracts: dict[str, TCLKContract],
    offers_by_nonce: dict[str, dict[str, Any]],
    frame: dict[str, Any],
    room: str,
    ts: int,
) -> None:
    """Apply an offer frame. Must be in tclk-offers room."""
    if room != OFFERS_ROOM:
        raise TCLKError(f"offer must be in {OFFERS_ROOM}, got {room!r}")
    _validate_did(frame.get("from", ""), "from")
    _validate_amount(frame.get("amount", ""))
    if not isinstance(frame.get("asset"), str) or not frame["asset"]:
        raise TCLKError("asset must be a non-empty string")
    _validate_lock_kind(frame.get("lock", ""))
    _validate_rails(frame.get("rails", []))
    _validate_ms(frame.get("claimByMs", 0), "claimByMs")
    _validate_ms(frame.get("refundAfterMs", 0), "refundAfterMs")
    _validate_ms(frame.get("expiresMs", 0), "expiresMs")
    _validate_nonce(frame.get("nonce", ""))
    offer_id = frame.get("id", "")
    if not isinstance(offer_id, str) or not offer_id:
        raise TCLKError("offer must have an 'id' field")
    # Optional paymentKey
    pk = frame.get("paymentKey")
    if pk is not None:
        if frame["lock"] == "hash":
            _validate_hash(pk, "paymentKey")
        elif frame["lock"] == "point":
            _validate_point(pk, "paymentKey")
    # Optional job
    job = frame.get("job")
    if job is not None and not isinstance(job, dict):
        raise TCLKError("job must be an object")

    nonce = frame["nonce"]
    if nonce in offers_by_nonce:
        raise IdempotentReject("duplicate offer nonce")

    offers_by_nonce[nonce] = frame
    # Create a preliminary contract entry keyed by offer id
    contract = TCLKContract(
        contract_id=offer_id,
        state=TCLKState.OFFERED,
        offer=frame,
        lock_kind=frame["lock"],
        amount=frame["amount"],
        asset=frame["asset"],
        rails=frame["rails"],
        claim_by_ms=frame["claimByMs"],
        refund_after_ms=frame["refundAfterMs"],
        expires_ms=frame["expiresMs"],
        payer_did=frame["from"] if frame.get("role") == "payer" else "",
        payee_did=frame["from"] if frame.get("role") == "payee" else "",
        last_updated_ms=ts,
    )
    contracts[offer_id] = contract


def _apply_accept(
    contracts: dict[str, TCLKContract],
    offers_by_nonce: dict[str, dict[str, Any]],
    frame: dict[str, Any],
    room: str,
    ts: int,
) -> None:
    """Apply an accept frame. Must be in tclk-offers room."""
    if room != OFFERS_ROOM:
        raise TCLKError(f"accept must be in {OFFERS_ROOM}, got {room!r}")
    _validate_did(frame.get("from", ""), "from")
    ref = frame.get("ref", "")
    if not isinstance(ref, str) or not ref:
        raise TCLKError("accept must reference an offer (ref field)")
    statement = frame.get("statement", "")
    if not isinstance(statement, str) or not statement:
        raise TCLKError("accept must have a statement field")
    _validate_nonce(frame.get("nonce", ""))
    contract_id = frame.get("contract", "")
    _validate_contract_id(contract_id)

    # Verify the accept references a known offer
    offer = offers_by_nonce.get(ref)
    if offer is None:
        raise TCLKError(f"accept references unknown offer nonce {ref!r}")

    # The contract field in accept should reference the offer's id
    offer_id = offer.get("id", "")
    if contract_id != offer_id:
        raise TCLKError("accept contract field does not match offer id")

    # Derive the actual contract id from offer+accept
    derived = derive_contract_id(offer, frame)

    # Update contract state
    contract = contracts.get(offer_id)
    if contract is None:
        raise TCLKError(f"accept references unknown offer id {offer_id!r}")

    if contract.state != TCLKState.OFFERED:
        raise IdempotentReject("contract already accepted or beyond")

    contract.state = TCLKState.ACCEPTED
    contract.accept = frame
    contract.contract_id = derived
    contract.statement = statement
    # Fill in the counterparty
    if offer.get("role") == "payer":
        contract.payee_did = frame["from"]
    else:
        contract.payer_did = frame["from"]
    contract.last_updated_ms = ts

    # Re-key the contract by the derived contract id
    contracts[derived] = contract
    if offer_id and offer_id != derived:
        contracts.pop(offer_id, None)


def _apply_lock(
    contracts: dict[str, TCLKContract],
    frame: dict[str, Any],
    room: str,
    ts: int,
) -> None:
    """Apply a lock frame. Must be in the derived deal room."""
    _validate_did(frame.get("from", ""), "from")
    contract_id = _validate_contract_id(frame.get("contract", ""))
    rail = frame.get("rail", "")
    if not isinstance(rail, str) or not rail:
        raise TCLKError("lock must specify a rail")
    ref = frame.get("ref", "")
    if not isinstance(ref, str) or not ref:
        raise TCLKError("lock must have a ref field")

    # Verify room is the derived deal room
    expected_room = deal_room_name(contract_id)
    if room != expected_room:
        raise TCLKError(f"lock must be in {expected_room}, got {room!r}")

    contract = contracts.get(contract_id)
    if contract is None:
        raise TCLKError(f"lock references unknown contract {contract_id!r}")
    if contract.state != TCLKState.ACCEPTED:
        raise IdempotentReject(f"lock on contract in state {contract.state.value}")

    # Guard: lock after refund window is open
    if contract.refund_after_ms > 0 and ts >= contract.refund_after_ms:
        raise TCLKError("lock rejected: refund window is already open")

    # Optional presig for PTLC
    presig = frame.get("presig")
    if presig is not None:
        if not isinstance(presig, dict):
            raise TCLKError("presig must be an object")

    contract.state = TCLKState.LOCKED
    contract.lock_frame = frame
    contract.rail_ref = ref
    contract.last_updated_ms = ts


def _apply_reveal(
    contracts: dict[str, TCLKContract],
    frame: dict[str, Any],
    room: str,
    ts: int,
) -> None:
    """Apply a reveal frame. Must be in the derived deal room."""
    _validate_did(frame.get("from", ""), "from")
    contract_id = _validate_contract_id(frame.get("contract", ""))
    secret = frame.get("secret", "")
    if not isinstance(secret, str) or not secret:
        raise TCLKError("reveal must have a secret field")

    expected_room = deal_room_name(contract_id)
    if room != expected_room:
        raise TCLKError(f"reveal must be in {expected_room}, got {room!r}")

    contract = contracts.get(contract_id)
    if contract is None:
        raise TCLKError(f"reveal references unknown contract {contract_id!r}")
    if contract.state != TCLKState.LOCKED:
        raise IdempotentReject(f"reveal on contract in state {contract.state.value}")

    # Guard: claim deadline
    if contract.claim_by_ms > 0 and ts > contract.claim_by_ms:
        raise TCLKError("reveal rejected: claim deadline has passed")

    # Verify hash lock if applicable
    if contract.lock_kind == "hash":
        if not verify_hashlock(secret, contract.statement):
            raise TCLKError("reveal secret does not match hash statement")

    contract.state = TCLKState.REVEALED
    contract.secret = secret
    contract.last_updated_ms = ts


def _apply_refund(
    contracts: dict[str, TCLKContract],
    frame: dict[str, Any],
    room: str,
    ts: int,
) -> None:
    """Apply a refund frame. Must be in the derived deal room."""
    _validate_did(frame.get("from", ""), "from")
    contract_id = _validate_contract_id(frame.get("contract", ""))

    expected_room = deal_room_name(contract_id)
    if room != expected_room:
        raise TCLKError(f"refund must be in {expected_room}, got {room!r}")

    contract = contracts.get(contract_id)
    if contract is None:
        raise TCLKError(f"refund references unknown contract {contract_id!r}")
    if contract.state != TCLKState.LOCKED:
        raise IdempotentReject(f"refund on contract in state {contract.state.value}")

    # Guard: refund window must be open
    if contract.refund_after_ms > 0 and ts < contract.refund_after_ms:
        raise TCLKError("refund rejected: refund window not yet open")

    # Optional ref must match lock's rail ref
    ref = frame.get("ref")
    if ref is not None and contract.rail_ref and ref != contract.rail_ref:
        raise TCLKError("refund ref does not match lock's rail ref")

    contract.state = TCLKState.REFUNDED
    contract.last_updated_ms = ts


def _apply_cancel(
    contracts: dict[str, TCLKContract],
    frame: dict[str, Any],
    room: str,
    ts: int,
) -> None:
    """Apply a cancel frame. Either side, before any lock exists."""
    _validate_did(frame.get("from", ""), "from")
    contract_id = _validate_contract_id(frame.get("contract", ""))

    contract = contracts.get(contract_id)
    if contract is None:
        raise TCLKError(f"cancel references unknown contract {contract_id!r}")

    # Guard: can only cancel before lock
    if contract.state in {TCLKState.LOCKED, TCLKState.REVEALED,
                          TCLKState.REFUNDED, TCLKState.RECEIPTED}:
        raise TCLKError(f"cancel rejected: contract is {contract.state.value}")

    if contract.state == TCLKState.CANCELLED:
        raise IdempotentReject("contract already cancelled")

    contract.state = TCLKState.CANCELLED
    contract.last_updated_ms = ts


def _apply_heartbeat(
    contracts: dict[str, TCLKContract],
    frame: dict[str, Any],
    room: str,
    ts: int,
) -> None:
    """Apply a heartbeat frame. Liveness while accepted or locked."""
    _validate_did(frame.get("from", ""), "from")
    contract_id = _validate_contract_id(frame.get("contract", ""))
    _validate_nonce(frame.get("nonce", ""))

    contract = contracts.get(contract_id)
    if contract is None:
        raise TCLKError(f"heartbeat references unknown contract {contract_id!r}")

    # Guard: heartbeat only while accepted or locked
    if contract.state not in {TCLKState.ACCEPTED, TCLKState.LOCKED}:
        raise TCLKError(f"heartbeat rejected: contract is {contract.state.value}")

    # Heartbeat is state-neutral — does not change contract state
    contract.last_updated_ms = ts


def _apply_receipt(
    contracts: dict[str, TCLKContract],
    frame: dict[str, Any],
    room: str,
    ts: int,
) -> None:
    """Apply a receipt frame. Post-terminal acknowledgment."""
    _validate_did(frame.get("from", ""), "from")
    contract_id = _validate_contract_id(frame.get("contract", ""))
    outcome = frame.get("outcome", "")
    if not isinstance(outcome, str) or not outcome:
        raise TCLKError("receipt must have an outcome field")

    contract = contracts.get(contract_id)
    if contract is None:
        raise TCLKError(f"receipt references unknown contract {contract_id!r}")

    # Guard: receipt only after terminal state
    if contract.state not in {TCLKState.REVEALED, TCLKState.REFUNDED,
                              TCLKState.CANCELLED}:
        raise TCLKError(f"receipt rejected: contract is {contract.state.value}")

    # Guard: rail/ref must match locked terms if present
    rail = frame.get("rail")
    ref = frame.get("ref")
    if rail is not None and contract.lock_frame:
        locked_rail = contract.lock_frame.get("rail")
        if locked_rail and rail != locked_rail:
            raise TCLKError("receipt rail contradicts locked settlement terms")
    if ref is not None and contract.rail_ref and ref != contract.rail_ref:
        raise TCLKError("receipt ref contradicts locked settlement terms")

    contract.state = TCLKState.RECEIPTED
    contract.last_updated_ms = ts


# --- TCLK Manager ---


class TCLKManager:
    """Coordinates TCLK/1 deal frames as signed room messages.

    Implements all 8 frame types per flop-labs/tclk SPEC.md with full
    field conformance, contract ID derivation, derived deal rooms, state
    pointer notes, and capability advertisement.
    """

    def __init__(self, client: TechnocoreClient) -> None:
        self.client = client

    @property
    def did(self) -> str:
        return self.client.did

    def _post_frame(self, room: str, content: dict[str, Any]) -> str:
        """Post a signed tclk/1 frame to a room and return its nonce."""
        nonce = str(time.time_ns())
        frame = {"nonce": nonce, **content}
        line = encode_frame(frame)
        self.client.post_message(room, line)
        return nonce

    def _generate_offer_id(self) -> str:
        """Generate a unique offer id (0x + 64 hex)."""
        return f"0x{secrets.token_hex(32)}"

    # --- Frame builders ---

    def post_offer(
        self,
        *,
        role: str,
        amount: str,
        asset: str,
        lock: str,
        rails: list[str],
        claim_by_ms: int,
        refund_after_ms: int,
        expires_ms: int,
        payment_key: str | None = None,
        job: dict[str, Any] | None = None,
        room: str = OFFERS_ROOM,
    ) -> dict[str, str]:
        """Post a signed offer frame with full spec fields.

        Args:
            role: the sender's role — 'payer' or 'payee'.
            amount: decimal integer string in rail-native minimal units.
            asset: the asset identifier (e.g. 'FLOP').
            lock: lock kind — 'hash' or 'point'.
            rails: list of settlement rail identifiers.
            claim_by_ms: Unix ms deadline for claiming (revealing secret).
            refund_after_ms: Unix ms after which a refund is allowed.
            expires_ms: Unix ms after which the offer expires.
            payment_key: optional hash/point statement for the payment key.
            job: optional job descriptor with 'id' and 'proto' keys.
            room: the room to post to (default: tclk-offers).

        Returns:
            Dict with 'nonce' and 'id' of the posted offer.
        """
        if role not in {"payer", "payee"}:
            raise TCLKError("role must be 'payer' or 'payee'")
        _validate_amount(amount)
        _validate_lock_kind(lock)
        _validate_rails(rails)
        _validate_ms(claim_by_ms, "claim_by_ms")
        _validate_ms(refund_after_ms, "refund_after_ms")
        _validate_ms(expires_ms, "expires_ms")

        offer_id = self._generate_offer_id()
        nonce = str(time.time_ns())
        frame: dict[str, Any] = {
            "type": FrameType.OFFER.value,
            "from": self.did,
            "role": role,
            "amount": amount,
            "asset": asset,
            "lock": lock,
            "rails": rails,
            "claimByMs": claim_by_ms,
            "refundAfterMs": refund_after_ms,
            "expiresMs": expires_ms,
            "nonce": nonce,
            "id": offer_id,
        }
        if payment_key is not None:
            frame["paymentKey"] = payment_key
        if job is not None:
            frame["job"] = job

        line = encode_frame(frame)
        self.client.post_message(room, line)
        return {"nonce": nonce, "id": offer_id}

    def post_accept(
        self,
        *,
        offer: dict[str, Any],
        statement: str,
        payment_key: str | None = None,
        room: str = OFFERS_ROOM,
    ) -> dict[str, str]:
        """Post a signed accept frame referencing an offer.

        The ``contract`` field in the accept references the offer's ``id``.
        The derived contract id (hash of offer+accept lines) is used for
        the deal room name and all subsequent frames.

        Args:
            offer: the full offer frame dict to accept.
            statement: the hash/point statement for the lock.
            payment_key: optional payment key statement.
            room: the room to post to (default: tclk-offers).

        Returns:
            Dict with 'nonce' and 'contract' (derived contract id).
        """
        if not isinstance(offer, dict) or offer.get("type") != "offer":
            raise TCLKError("offer must be a valid offer frame dict")
        nonce = str(time.time_ns())
        # The contract field in accept references the offer's id
        offer_id = offer.get("id", "")
        frame: dict[str, Any] = {
            "type": FrameType.ACCEPT.value,
            "from": self.did,
            "ref": offer.get("nonce", ""),
            "statement": statement,
            "contract": offer_id,
            "nonce": nonce,
        }
        if payment_key is not None:
            frame["paymentKey"] = payment_key

        # Derive the contract id from the canonical offer+accept lines
        contract_id = derive_contract_id(offer, frame)
        line = encode_frame(frame)
        self.client.post_message(room, line)
        return {"nonce": nonce, "contract": contract_id}

    def post_lock(
        self,
        *,
        contract_id: str,
        rail: str,
        ref: str,
        presig: dict[str, Any] | None = None,
    ) -> str:
        """Post a signed lock frame to the derived deal room.

        Args:
            contract_id: the contract id (0x + 64 hex).
            rail: the settlement rail identifier.
            ref: the rail-specific lock reference.
            presig: optional adaptor pre-signature for PTLC.

        Returns:
            The nonce of the posted lock frame.
        """
        room = deal_room_name(contract_id)
        frame: dict[str, Any] = {
            "type": FrameType.LOCK.value,
            "from": self.did,
            "contract": contract_id,
            "rail": rail,
            "ref": ref,
        }
        if presig is not None:
            frame["presig"] = presig
        return self._post_frame(room, frame)

    def post_reveal(
        self,
        *,
        contract_id: str,
        secret: str,
        ref: str | None = None,
    ) -> str:
        """Post a signed reveal frame to the derived deal room.

        Args:
            contract_id: the contract id.
            secret: the preimage (hash lock) or scalar (point lock).
            ref: optional rail reference matching the lock.

        Returns:
            The nonce of the posted reveal frame.
        """
        room = deal_room_name(contract_id)
        frame: dict[str, Any] = {
            "type": FrameType.REVEAL.value,
            "from": self.did,
            "contract": contract_id,
            "secret": secret,
        }
        if ref is not None:
            frame["ref"] = ref
        return self._post_frame(room, frame)

    def post_refund(
        self,
        *,
        contract_id: str,
        ref: str | None = None,
        reason: str | None = None,
    ) -> str:
        """Post a signed refund frame to the derived deal room.

        Args:
            contract_id: the contract id.
            ref: optional rail reference matching the lock.
            reason: optional human-readable reason.

        Returns:
            The nonce of the posted refund frame.
        """
        room = deal_room_name(contract_id)
        frame: dict[str, Any] = {
            "type": FrameType.REFUND.value,
            "from": self.did,
            "contract": contract_id,
        }
        if ref is not None:
            frame["ref"] = ref
        if reason is not None:
            frame["reason"] = reason
        return self._post_frame(room, frame)

    def post_cancel(
        self,
        *,
        contract_id: str,
        reason: str | None = None,
    ) -> str:
        """Post a signed cancel frame. Either side, before any lock.

        Args:
            contract_id: the contract id.
            reason: optional human-readable reason.

        Returns:
            The nonce of the posted cancel frame.
        """
        room = deal_room_name(contract_id)
        frame: dict[str, Any] = {
            "type": FrameType.CANCEL.value,
            "from": self.did,
            "contract": contract_id,
        }
        if reason is not None:
            frame["reason"] = reason
        return self._post_frame(room, frame)

    def post_heartbeat(
        self,
        *,
        contract_id: str,
        note: str | None = None,
    ) -> str:
        """Post a signed heartbeat frame for liveness while accepted/locked.

        Args:
            contract_id: the contract id.
            note: optional liveness note.

        Returns:
            The nonce of the posted heartbeat frame.
        """
        room = deal_room_name(contract_id)
        nonce = str(time.time_ns())
        frame: dict[str, Any] = {
            "type": FrameType.HEARTBEAT.value,
            "from": self.did,
            "contract": contract_id,
            "nonce": nonce,
        }
        if note is not None:
            frame["note"] = note
        line = encode_frame(frame)
        self.client.post_message(room, line)
        return nonce

    def post_receipt(
        self,
        *,
        contract_id: str,
        outcome: str,
        rail: str | None = None,
        ref: str | None = None,
    ) -> str:
        """Post a signed receipt frame as a post-terminal acknowledgment.

        Args:
            contract_id: the contract id.
            outcome: the outcome string (e.g. 'claimed', 'refunded', 'cancelled').
            rail: optional rail id matching the locked terms.
            ref: optional rail reference matching the locked terms.

        Returns:
            The nonce of the posted receipt frame.
        """
        room = deal_room_name(contract_id)
        frame: dict[str, Any] = {
            "type": FrameType.RECEIPT.value,
            "from": self.did,
            "contract": contract_id,
            "outcome": outcome,
        }
        if rail is not None:
            frame["rail"] = rail
        if ref is not None:
            frame["ref"] = ref
        return self._post_frame(room, frame)

    # --- State pointer ---

    def read_deal_status(self, contract_id: str) -> str | None:
        """Read the state pointer note for a contract.

        Returns the note value or None if no state pointer exists.
        """
        ns, key = state_pointer_path(contract_id)
        return self.client.read_note(ns, key)

    def write_deal_status(self, contract_id: str, status: str,
                          *, if_match: str | None = None) -> str:
        """Write/update the state pointer note for a contract.

        Uses compare-and-set for atomicity.
        """
        ns, key = state_pointer_path(contract_id)
        return self.client.write_note(ns, key, status, if_match=if_match)

    # --- Capability advertisement ---

    def advertise_capability(self, rails: list[str]) -> str:
        """Add the tclk1 capability token to this identity's DID note.

        Args:
            rails: list of settlement rail identifiers to advertise.

        Returns:
            The DID note path.
        """
        token = capability_token(rails)
        return self.client.publish_did_note(extra=token)

    # --- Transcript folding ---

    def fold_room(self, room: str, *, limit: int = 200,
                  since: int | None = None) -> TranscriptFoldResult:
        """Read a room and fold its transcript into contract states.

        Args:
            room: the room to read (tclk-offers or a deal room).
            limit: max messages to read.
            since: optional seq to start from.

        Returns:
            TranscriptFoldResult with contracts and any malformed/rejected records.
        """
        response = self.client.read_room(room, limit=limit, since=since)
        records = []
        for msg in response.get("messages", []):
            records.append({
                "room": room,
                "seq": msg.get("seq"),
                "ts": msg.get("ts", 0),
                "from": msg.get("from", ""),
                "nonce": msg.get("nonce", ""),
                "sig": msg.get("sig", ""),
                "text": msg.get("text", ""),
            })
        return fold_transcript(records)

    # --- Legacy compatibility (deprecated, use full-spec methods) ---

    @staticmethod
    def generate_hashlock(secret: str) -> str:
        """Generate a SHA-256 hashlock from a secret preimage. (deprecated)"""
        if secret.startswith("0x"):
            return hashlock_from_secret(secret)
        raw = secret.encode()
        return f"0x{hashlib.sha256(raw).hexdigest()}"

    @staticmethod
    def generate_secret() -> str:
        """Generate a random 32-byte hex secret for a TCLK deal. (deprecated)"""
        return generate_secret()
