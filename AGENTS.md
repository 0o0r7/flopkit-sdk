# Base44 Dev Environment — flopkit SDK

## What this project is

`flopkit` is a Python 3.12 SDK, CLI, and optional MCP server for Ed25519 DID identities and signed AI-agent contributions on the Flop Network. There is **no web frontend or backend API** — it is a library + command-line tool. All source lives under `sdk/`.

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

All 65 tests pass with 94% coverage. The full quality gate (ruff, mypy --strict, pytest --cov-fail-under=90, mkdocs --strict) passes cleanly.

## Upgrade summary

The SDK was upgraded to align with the latest FLOP ecosystem:

- **P0**: Fixed wizard.run() to accept injectable prompt_fn/output_fn; removed dead except blocks
- **P1**: Added GET signed-write lane (post_message_get), GET note-write lane (write_note_get), text/plain read path (read_room_text); fixed MCP server to use base64url instead of hex for signatures
- **P2**: Completed TCLK state machine (offer → accept → lock → reveal → refund); added CLI subcommands (events, mint-room, tclk-offer/accept/lock/reveal/refund); expanded __init__.py exports; full type annotations in tclk.py
- **P3**: Added ecosystem helpers (parse_rooms, parse_budget, setup_mailbox, long_poll); polished wizard TUI with ANSI colors (dim/bold/green/red/yellow); 5-option menu
- **CI**: Updated GitHub Actions to enforce ruff + mypy + pytest --cov-fail-under=90 + mkdocs --strict

## Secrets

No external credentials are required. The SDK works locally with mock transports; live Technocore interaction needs a real endpoint configured by the user but is not required for the preview or tests.
