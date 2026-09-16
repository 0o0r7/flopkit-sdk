# Base44 Dev Environment — flopkit SDK

## What this project is

`flopkit` is a Python 3.12 SDK, CLI, and optional MCP server for Ed25519 DID identities, signed AI-agent contributions, TCLK/1 deal-making, and DID delegation on the Flop Network. There is **no web frontend or backend API** — it is a library + command-line tool. All source lives under `sdk/`.

## How it runs in the preview

Since there is no web app, the preview serves the **MkDocs documentation site** (`sdk/mkdocs.yml`) on port 3000 via `mkdocs serve`. This is a live-reload dev server, so edits to `sdk/docs/*.md` and `mkdocs.yml` appear in the preview without a rebuild.

- Compose file: `docker-compose.base44.yml`
- Service: `docs` (python:3.12-slim, bind-mounted at `/app`, working dir `/app/sdk`)
- Start command installs `pip install -e '.[dev]'` then runs `mkdocs serve --dev-addr 0.0.0.0:3000`
- Health path: `/`

## Running the SDK / CLI

```bash
docker compose -f docker-compose.base44.yml exec -T docs sh -c "cd /app/sdk && flopkit --help"
```

## Tests

```bash
docker compose -f docker-compose.base44.yml exec -T docs sh -c "cd /app/sdk && python -m pytest -q"
```

All tests pass with 95% coverage. The full quality gate (ruff, mypy --strict, pytest --cov-fail-under=90, mkdocs --strict) passes cleanly.

## Upgrade summary (second pass)

The SDK was finalized to align with the latest FLOP ecosystem:

- **P0**: Fixed wizard.py dead code (duplicate `if action == "back": break` line)
- **P0**: Updated README.md — removed duplicated CLI command listings, added all new TCLK subcommands (tclk-cancel, tclk-heartbeat, tclk-receipt, tclk-status, tclk-fold, tclk-advertise) and delegation commands (delegate, verify-delegate, revoke-delegate), updated wizard section from 5-option menu to 6-category hierarchical menu, updated architecture diagram to include delegation.py, added Delegation section to CLI reference
- **P0**: Updated quickstart.md — updated help output to 30+ subcommands, updated wizard section to 6 hierarchical categories, fixed TCLK CLI examples with correct spec-conformant parameters, added delegation examples
- **P1**: Created tclk-guide.md — comprehensive TCLK/1 protocol reference (8 frame types, state machine, contract ID derivation, deal rooms, transcript folding, HTLC flow, PTLC interface, settlement rails, capability advertisement)
- **P1**: Added tclk-guide.md to mkdocs.yml navigation and linked from index.md and quickstart.md
- **P1**: Added test_coverage_gaps.py — 83 new tests covering TCLK state machine guards, wizard actions, and error paths; raised coverage from 85% to 95%
- **P2**: Rewrote AGENTS.md to reflect the second upgrade (TCLK/1 spec conformance, delegation, wizard TUI, CLI expansion, MCP server, documentation updates)

## TCLK/1 spec conformance

The TCLK module (`sdk/src/flopkit/tclk.py`) implements all 8 frame types per `flop-labs/tclk SPEC.md`:
- Offer, accept, lock, reveal, refund, cancel, heartbeat, receipt
- Content-addressed offer IDs (domain-separated SHA-256)
- Deterministic contract ID derivation over {offer, accept-core}
- Derived deal rooms (`mb-p-tclk-<hex>`)
- State machine with guards (claim deadline, refund window, replay dedupe)
- Transcript folding with signature verification
- Settlement rail protocol (PaperRail reference implementation)
- HTLC full path + PTLC wire-format interface (reference/unaudited)

## Delegation

The delegation module (`sdk/src/flopkit/delegation.py`) implements DID delegation:
- Create/verify/revoke delegation records in DID notes
- Nonce-based revocation (higher nonce wins)
- Expiry checking
- Scope validation

## Wizard TUI

The wizard (`sdk/src/flopkit/wizard.py`) provides a 6-category hierarchical menu:
1. Identity & DID (create, show, publish, resolve, delegate, verify, revoke)
2. Messaging (post, read JSON, read text, events)
3. TCLK Trading (offer, accept, lock, reveal, refund, cancel, heartbeat, receipt, status)
4. Discovery (rooms, mint, mailbox, long poll)
5. Contributions (log, export, verify)
6. Exit

## CLI expansion

The CLI (`sdk/src/flopkit/cli.py`) now has 30+ subcommands covering identity, messaging, notes, TCLK/1, delegation, and discovery.

## Secrets

No external credentials are required. The SDK works locally with mock transports; live Technocore interaction needs a real endpoint configured by the user but is not required for the preview or tests.
