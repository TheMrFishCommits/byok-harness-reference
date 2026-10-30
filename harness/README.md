# apim-harness-test

Mock APIM gateway plus fake `az` for testing coding-agent harnesses that authenticate with short-lived Entra-style JWTs. Results are in `RESULTS.md`.

## Files

| File | Purpose |
|---|---|
| `common.py` | RSA key creation, JWKS, JWT minting |
| `gateway.py` | Mock APIM on `127.0.0.1:18080`. Validates RS256 JWTs (aud, iss, exp), logs requests to `logs/requests.jsonl`, serves canned Anthropic Messages (`/anthropic/v1/messages`) and OpenAI Responses (`/openai/v1/responses`) streams, scripted tool turns, fault injection via `POST /_ctl` |
| `fakeaz/az.cmd`, `fakeaz/az_main.py` | Fake `az account get-access-token`. Mode set in `fakeaz/mode.json` (ok, slow, noisy, fail, wrong_aud) |
| `get-apim-token.ps1` | The hardened helper script under test |
| `proxy.py` | Local token-injecting reverse proxy |
| `harness.py`, `run_claude.py`, `run_codex.py` | Runners that launch each CLI with an isolated config and scrubbed environment |
| `suite_*.py` | Scenario suites |

## Run

```powershell
cd C:\Users\USER\Local\apim-harness-test
# one-time: uv venv .venv --python 3.12; uv pip install --python .venv\Scripts\python.exe aiohttp "pyjwt[crypto]" cryptography
Start-Process .\.venv\Scripts\python.exe -ArgumentList gateway.py -WindowStyle Hidden
.\.venv\Scripts\python.exe suite_claude.py           # Claude Code basics and faults
.\.venv\Scripts\python.exe suite_claude_refresh.py   # mid-session expiry (about 90 s)
.\.venv\Scripts\python.exe suite_codex.py            # Codex basics and faults
.\.venv\Scripts\python.exe suite_codex_refresh.py    # mid-session expiry (about 2.5 min)
.\.venv\Scripts\python.exe suite_helper_hardened.py  # failure modes with the hardened helper
```

For the proxy tests, start `proxy.py` first (see the header of `proxy.py`) and then run `suite_proxy.py`.

The test keys under `keys/` are throwaway and only valid for this mock.

The suites rely on the mock's `/_ctl` fault injection and on `fakeaz`, so they are not set up to run against a real gateway as-is.
