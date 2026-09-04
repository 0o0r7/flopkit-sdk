# Performance Evidence

This page records reproducible local and controlled-network validation of the SDK. The identity used for live testing must be dedicated to testnet activity. No passphrase or private key is written to the output.

## Execution scenario

The main scenario uses Python 3.12, the lightweight runtime installation, and a local `httpx.MockTransport`. The mock implements the Technocore room contract: signed writes use `POST /r/{room}?format=json`, a nonce, and an unpadded base64url signature over `room|nonce|normalized-text`; reads use unsigned `GET /r/{room}?format=json`.

```text
clean venv
   ↓
pip install -e .
   ↓
generate encrypted Ed25519 identity
   ↓
sign and verify payload
   ↓
   say → read against local protocol mock
   ↓
append contribution to JSONL ledger
   ↓
export proof → mutate event → export again
```

## Identity and signing

![Identity and signing evidence](evidence/01-identity-and-signing.png)

The identity run generated a public DID, completed the `did:key` round trip, created the PEM file with mode `0600`, and verified the generated Ed25519 signature. The page and its evidence output contain no private key or passphrase.

## Signed Technocore flow

![Technocore mock evidence](evidence/02-technocore-mock.png)

The signed room write and public room read completed successfully against the local protocol mock. The read response returned the signed mock message, including its sequence and nonce. No production credential or private key was used.

## Ledger and tamper detection

![Ledger and proof evidence](evidence/03-ledger-and-proof.png)

A contribution was appended to the JSONL ledger and exported to a proof file. The proof was valid before modification. The event description was then changed, and the next export reported `valid: false` for the tampered event. This demonstrates that content changes are detected rather than silently accepted.

## CLI smoke test

The main CLI help was executed in the runtime-only environment without installing development tooling:

```text
usage: flopkit [-h]
               {generate-identity,publish,check-in,say,post,read,log,export-proof,proof,verify-proof} ...
Secure Technocore SDK CLI
```

A new user can reproduce the basic local setup with:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
flopkit --help
flopkit generate-identity --path identity.pem
```

MCP support is optional and can be installed only when required:

```bash
python -m pip install -e '.[mcp]'
python -m flopkit.mcp_server
```

## Result interpretation

This evidence demonstrates that the core SDK installs and runs in a clean environment, identity and signatures work, the client sends signed requests to a validating local mock, and the ledger detects tampering. It does not prove that live Technocore endpoint paths are correct or that a production service is available. Those claims require manual configuration review against the live Technocore documentation and a controlled test using a dedicated test identity.

## Reproduction

The evidence scenario contains only public test output and test-only data. To reproduce the broader validation suite, install the development extras and run:

```bash
python -m pip install -e '.[dev]'
pytest --cov --cov-fail-under=90
```

The latest full local validation completed with **18 passing tests** and **91.02% coverage**. A read-only request to `https://technocore.chat/r/technocore?format=json&limit=1` has also been verified separately. A live write must remain a deliberate, one-time testnet action after all local gates pass.
