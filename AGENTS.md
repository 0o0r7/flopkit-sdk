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

32 of 35 tests pass. 3 wizard interactive-menu tests fail due to a **pre-existing bug**: the tests call `run_wizard(prompt_fn, output_fn)` with two positional args, but `wizard.run()` accepts none. This is in the upstream repo, not caused by the Base44 setup.

## Secrets

No external credentials are required. The SDK works locally with mock transports; live Technocore interaction needs a real endpoint configured by the user but is not required for the preview or tests.
