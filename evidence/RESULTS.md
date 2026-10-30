# Synthetic test results: Claude Code and Codex with Entra-style JWTs through a mock APIM

Run on Windows 11, Claude Code 2.1.311, Codex CLI 0.153.2, Python 3.12, Windows PowerShell 5.1 for the helper (`powershell`). All results below are from real CLI runs against the local mock, with logs in `logs/` and per-run JSON in `results/`.

## What was tested

```
claude / codex  ->  [proxy.py]  ->  gateway.py (mock APIM)  <-  JWKS
 (isolated config)    optional      validates RS256 JWT, aud, iss, exp
                                    logs headers/path/query/model
fakeaz\az.cmd mints 20-120 s test JWTs and can be set to: ok | slow | noisy | fail | wrong_aud
get-apim-token.ps1 is the real helper script, run unmodified against the fake az
```

Each CLI ran with its own temporary config directory (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`) and a scrubbed environment, so no real account, config or billing was involved.

## Not tested (needs the real tenant)

- Real Entra and the real Azure CLI: consent, pre-authorization of the Azure CLI client, Conditional Access, refresh-token lifetime, real `az` latency.
- Real APIM policies, WAF, response buffering, and HTTPS. The proxy-to-HTTPS path was not exercised.
- The VS Code UIs: Copilot BYOK (`chatLanguageModels.json`), the Claude Code VS Code extension, and the Codex VS Code extension. The Codex docs say the extension shares `config.toml` with the CLI, but I did not run the extension.
- JetBrains and PyCharm.
- LiteLLM on a separate lab host as a backend: skipped. It would only add realistic model replies, not information about the auth path.

## Claude Code (`apiKeyHelper`)

| # | Scenario | Result |
|---|---|---|
| c01 | Baseline | Works. Helper ran once. Token sent as both `Authorization: Bearer` and `x-api-key` (identical). Path `/anthropic/v1/messages?beta=true`. Also probes `GET <base>/api/hello` (404 is harmless). |
| c02 | `ANTHROPIC_CUSTOM_HEADERS` | Works. `Ocp-Apim-Subscription-Key` and `X-Tenant` arrived. |
| c03 | `ANTHROPIC_DEFAULT_{SONNET,HAIKU,OPUS}_MODEL` | Works. `--model sonnet` sent `dep-sonnet`; the background call sent `dep-haiku`. |
| c04 | `"model": "my-deployment"` | Works. Name sent verbatim. |
| c12 | `modelOverrides` | Works. `claude-opus-5-5` was rewritten to `dep-override` in the request to the gateway. |
| c05 | Helper prints a banner on stdout | Fails. No usable credential reached the gateway (6 requests, all 401, rc=1). |
| c06 | Helper exits 1 (not logged in) | Fails fast: rc=1 in 4.4 s after 3 helper runs. Output says "Your apiKeyHelper script is failing" and stderr shows the helper's message. |
| c07 | Token with wrong audience | Bad: retried for over 90 s (16 requests, 10 helper runs) and hit the timeout. Looks like a hang. |
| c08 | Helper takes 6 s | Works (7.5 s total). |
| c09 | One forced 401 on a fresh token | Retried with the same cached token and succeeded. The helper did not re-run. |
| c10 | `ANTHROPIC_AUTH_TOKEN` also set | Confirmed: it overrides the helper. The static value was sent, the gateway returned 401, and it retried for the full 120 s timeout. |
| r1 | 20 s tokens, helper cache 5 s, session of 6 requests over 43 s | Works. JWT rotated 4 times, no 401s. |
| r2 | 20 s tokens, helper cache 300 s | Works with one 401. The expired token got a 401, the helper re-ran, and the retry succeeded with a new token. |
| h | Hardened helper (see below) | Noisy stdout tolerated. Wrong audience now fails in 4.7 s with a clear message. |

## Codex (`[model_providers.<id>.auth]`)

| # | Scenario | Result |
|---|---|---|
| x01 | Baseline | Works. `Authorization: Bearer` only (no `x-api-key`). Calls `GET <base>/models?client_version=...` twice, then `POST <base>/responses`. |
| x02 | `query_params` and `http_headers` | Works on both `/models` and `/responses`. |
| x03 | Noisy stdout | Fails: 401s, rc=1 after 12 s. |
| x04 | Helper exits 1 | Fails after 24 s. Helper ran 31 times (retry storm). Helper stderr is shown in Codex's error output. |
| x05 | Wrong audience | Fails after 12 s with 14 requests (all 401). |
| x06 | Helper takes 6 s, `timeout_ms = 5000` | Fails: "timed out after 5000 ms", 24 helper runs, ran into the 125 s test timeout. |
| x07 | Helper takes 6 s, `timeout_ms = 15000` | Works (14 s total). |
| x08 | One forced 401 | Works. The helper re-ran and the retry used a new token. |
| x09 | No `auth` block | 401s, as expected. |
| x10 | `auth` plus `env_key` | Rejected at load: "provider auth cannot be combined with env_key". |
| x12 | 20 s tokens, `refresh_interval_ms = 5000`, 4 tool turns x 8 s | Works. A fresh token for every request. |
| x13 | `refresh_interval_ms = 1800000` | Works with one 401: expired token got a 401, helper re-ran, retry succeeded. |
| x14 | `refresh_interval_ms = 0` | Same as x13. |
| h | Hardened helper | Noisy stdout tolerated. Wrong audience and not-logged-in fail with the helper's own message in Codex's stderr (still about 25 s of retries). |

Codex quirk: `GET /models` expects a response shaped like `{"models": [...]}`. A gateway that returns the usual `{"data": [...]}` list causes a non-fatal `ERROR ... failed to decode models response` in stderr and a warning that model metadata is missing, and Codex falls back to generic metadata. Requests still work.

## Local token proxy (for tools with only a static key field)

| # | Scenario | Result |
|---|---|---|
| P1 | Client sends a dummy `Authorization` and `x-api-key` | Both replaced; gateway saw a valid JWT and no `x-api-key`. |
| P2 | SSE streaming | Passed through intact (`message_stop` received). |
| P3 | `/openai/v1/responses` | Works. |
| P4 | Upstream 401 once | Proxy fetched a fresh token and the retry succeeded. |
| P5 | Helper failing | Proxy returns 502 with the helper's message. It recovered with no restart once the helper worked again. |
| P6 | Claude Code through the proxy, static dummy `ANTHROPIC_AUTH_TOKEN`, no helper | Works. |
| P7 | Codex through the proxy, `experimental_bearer_token = "dummy"` | Works. |

## IDE harnesses (VS Code 1.142.0, pinned copy driven with Playwright; isolated profile per run)

| Row | Harness | Result |
|---|---|---|
| 7 | **Codex VS Code extension** (`openai.chatgpt` 26.1021.22027, Codex 0.164.0) | **Passed.** With `CODEX_HOME` pointing at a `config.toml` with the command-backed auth provider, the extension needed no ChatGPT sign-in, ran the helper, and sent `GET /models` and `POST /responses` with valid JWTs (originator `codex_vscode`). A prompt typed in its panel returned `MOCK-OK model=gpt-test` in the panel. Panel took about 35 s to load. |
| 5 | **Claude Code VS Code extension** (`anthropic.claude-code` 2.1.312) | **Passed.** With `apiKeyHelper` and `ANTHROPIC_BASE_URL` in the config folder's `settings.json` and nothing in VS Code's settings, the extension showed no login prompt, its bundled `claude.exe` ran the helper, and `POST /v1/messages` arrived with a valid JWT in `Authorization: Bearer` and `x-api-key`. A prompt typed in its panel returned `MOCK-OK model=claude-opus-5-5`. |
| 1-4 | **VS Code Copilot BYOK** (`chatLanguageModels.json`) | **Passed, signed out of GitHub (corrected; the earlier "blocked" result was a configuration error).** A literal `"apiKey"` in the JSON showed the model in the Language Models editor but never in the chat picker, and chat ended at "Sign in to use GitHub Copilot". Adding the provider through **Chat: Manage Language Models > Add Models > Custom Endpoint** (key stored as a secret, `"apiKey": "${input:chat.lm.secret.<id>}"`) and adding the model entry made an **APIM-UI** group tab appear in the picker while signed out. A prompt returned `MOCK-OK model=gpt-test` in the chat panel; the gateway saw `POST /openai/v1/responses` from `GitHubCopilotChat/0.70.0` with a valid helper-issued JWT (via the token proxy). Under a deny-all proxy it still worked and tried only `main.vscode-cdn.net`, `169.254.169.254` and an Application Insights host, never GitHub. |
| 8 | **JetBrains / PyCharm** | **Attempted; stopped at a consent step.** PyCharm 2026.2.3 was installed per-user with no admin (installer signature valid) and the AI Assistant plugin was added through the launcher (`installPlugins com.intellij.ml.llm`, no account), in an isolated config under `jetbrains\`. It was not launched: first start requires accepting JetBrains' user agreement, which needs your explicit OK. No config-file or CLI route to set a provider was found in the plugin. A static read of the plugin code (not a runtime test) shows the key is sent as `Authorization: Bearer <key>` and the bundled OpenAI client appends `v1/chat/completions`, `v1/responses` and `v1/models` to the base URL; whether a custom URL keeps those paths is unconfirmed. JetBrains' AI Assistant 2026.2 docs (5 pages read) say BYOK works without a JetBrains AI subscription and do not say whether a JetBrains Account is needed. The OpenAI-compatible provider has only URL, API key, a tool-calling checkbox and model assignment; custom headers, a token command and the `Bearer` scheme are not documented. It is configured through the settings UI, so it could not be driven unattended here. The local token proxy is the supported path; a manual checklist is in `handoff\vscode-extensions-apim-entra-setup.md` section 8. (An earlier version of this row wrongly said an account sign-in was required.) |
| - | **Real Azure CLI 2.91.0** (official portable ZIP, isolated config) | **Partly tested.** Not logged in: `get-access-token --scope` exits 1 in 0.6 s with "ERROR: Please run 'az login' to setup account."; the helper reports it in 0.8 s. A real token needs your own `az login`; `real_az_check.ps1` is ready for that. |

Side findings: the built-in `azure` provider documents Entra sign-in when `apiKey` is unset and requests the scope `https://cognitiveservices.azure.com/.default` (not run); selecting "Codex" or "Claude" in the chat session-type dropdown opens the installed extension; the extension harnesses probe or call extra endpoints (`HEAD /api/hello`, repeated `GET /models`, and `chatgpt.com` plugin sync).

Token at rest: after all runs, 0 of 109 Claude Code files and 0 of 21,909 Codex files (including SQLite state and logs) contained the mock JWT.

## Real Entra token runs (read-only)

With the owner signed in to the isolated Azure CLI (device code), `az account get-access-token --scope https://management.azure.com/.default` returned a 2,435-character v1.0 token in about 1.2 s (aud `https://management.azure.com`, lifetime about 81 minutes). The real helper printed only the JWT (rc 0), failed fast on a wrong expected audience (rc 1), and now accepts a list of audiences. Using the real helper as the token source against the stand-in gateway (lenient mode: structure and expiry only), every harness completed a prompt with the reply visible: Claude Code CLI and extension, Codex CLI (also with the default 5 s helper timeout) and extension, Copilot CLI (offline BYOK via the proxy), VS Code Copilot Chat (via the proxy) and JetBrains AI Assistant (via the proxy). Not tested: a token for a custom API audience and your APIM policies. No tenant changes were made.
## Azure MCP server (read-only, no sign-in)

Standalone: capabilities `tools` and `logging` only (no model calls); 68 tools by default; `--read-only` removes destructive tools (426 to 235 in full mode); `--disable-proxy-tools` removes four forwarding tools. With both telemetry variables false it attempted no external connection; with one, an Application Insights attempt and a metadata probe remained; `--mode all` contacted Entra sign-in and Microsoft Learn at start-up. Through harnesses: Claude Code and Copilot CLI (offline BYOK, no GitHub login) ran a tool call up to Azure's "no credentials" answer; Codex registered it (tools load on demand, call not exercised); VS Code and JetBrains not exercised. Real-credential results not obtained.
## Egress audit: no contact with GitHub, Anthropic or OpenAI (requirement from the owner)

Method: a deny-all proxy (`egress_deny_proxy.py`) refused every non-local connection and logged hosts; `egress_watch.py` sampled every non-loopback TCP connection of each tool's process tree (0.4 s); Chromium net-logs named VS Code's hosts. Full write-up: `handoff\no-vendor-egress-harness-setup.md`.

| Harness | Works with only localhost reachable | Hosts attempted (refused) | Quiet switches |
|---|---|---|---|
| Claude Code CLI | Yes | `api.anthropic.com` | 4 env switches: 0 connections |
| Claude Code extension | Yes | `api.anthropic.com` + VS Code hosts | same, via config folder |
| Codex CLI | Yes | `chatgpt.com`, `ab.chatgpt.com`, `github.com`, `api.github.com` | feature flags + analytics off: 0 connections |
| Codex extension | Yes | `chatgpt.com`, `chat.openai.com`, `ab.chatgpt.com`, `github.com`, `api.github.com`, Sentry | flags silence its bundled Codex only; UI/host still call out |
| Copilot CLI BYOK | Yes | `api.github.com`, `api.individual.githubcopilot.com`, `telemetry.individual.githubcopilot.com` | `COPILOT_OFFLINE=true`: 0 connections |
| VS Code Copilot Chat BYOK | Yes (signed out) | `main.vscode-cdn.net`, `169.254.169.254`, Application Insights; no GitHub | n/a |
| Copilot Fusion (CLI, signed out) | **No** | GitHub (rejected `400 The requested model is not supported`) | not possible; docs say routing is in the cloud |
| PyCharm 2026.2.3 idle | n/a | none in 40 s | not configured or run end to end |

Watcher validation note: the first VS Code results were invalid because the watcher matched its own command line; it was fixed (match by process name, exclude itself) and all VS Code rows were rerun. Side effect: some earlier VS Code runs had the Codex extension active with the default Codex home, which may have written caches under `%USERPROFILE%\.codex` (its `config.toml` was not changed).

## Findings that changed the recommended setup

1. **The helper must print only the JWT.** Banners on stdout broke both tools. The hardened `get-apim-token.ps1` keeps only the line that looks like a JWT.
2. **The helper should check the audience and remaining lifetime itself.** A wrong-audience token made Claude Code retry for over 90 s and Codex for about 12-25 s. Failing in the helper gives a clear message in about 5 s (Claude Code) and shows up in both tools' stderr.
3. **Codex `timeout_ms` must exceed real `az` latency.** The default 5000 ms failed with a 6 s helper. Use 15000.
4. **Do not set `ANTHROPIC_AUTH_TOKEN` alongside `apiKeyHelper`.** It silently wins and Claude Code then retries a bad static token for minutes.
5. **Mid-session expiry is handled by both tools.** Either by a short refresh/cache interval (no 401s) or by 401, helper re-run and retry (one 401 in the APIM logs).
6. **`modelOverrides`, `ANTHROPIC_DEFAULT_*_MODEL` and `model` all work** with a gateway base URL.
7. **Codex's `/models` call** is noisy against a gateway that does not mimic its response shape. It does not stop requests.

## Reproduce

See `README.md` in this folder.


