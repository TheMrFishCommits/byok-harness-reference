# Testing procedures: coding harnesses with Entra-style JWT authentication

Detailed method and exact procedures. A colleague with a Windows 11 machine should be able to repeat every test from this document. Results and conclusions are in the Findings document; this document gives only the pass criteria and what to capture.

## 1. Scope and conventions

**What was tested.** How coding harnesses authenticate to an Azure API Management (APIM) style gateway that validates a short-lived JWT on every request, and which external hosts the harnesses contact. The harnesses: Claude Code (CLI and VS Code extension), Codex (CLI and VS Code extension), GitHub Copilot CLI, VS Code Copilot Chat with bring-your-own-key (BYOK), and JetBrains AI Assistant in PyCharm (OpenAI-compatible provider, configured through the settings UI). It also covers the Azure MCP Server (a local MCP server) registered in three of the harnesses. The gateway was a local mock, not a real APIM.

**Conventions used in this document.**

- `$root` means the test folder, `C:\Users\<you>\Local\apim-harness-test`. All commands run in PowerShell 7 unless noted. The helper script is run under Windows PowerShell 5.1 (`powershell`) because that is what the tools invoke.
- Test JWTs are throwaway, signed with a key generated on first use under `$root\keys`, except in section 14, which uses real tokens from the owner's own sign-in. No token value, tenant ID or account name appears in this document. Placeholders such as `<you>` and `<apim-app-id>` stand for your own values.
- "Gateway log" means `$root\logs\requests.jsonl`. "Pass criterion" is what must be observed for a procedure to count as passed. "Capture" means record the observation; no pass or fail is applied.
- Scenario names (c01, x07, P4, d13, h3 and so on) are the names used in the scripts, config files and result files.
- Where a step was run inline in a console and is not in a script, the exact command is given here.

## 2. Environment and prerequisites

**2.1 Tools and versions used**

| Item | Version | How obtained |
|---|---|---|
| Windows | 11 Pro, build 10.0.26200 | n/a |
| PowerShell | 7 (`pwsh`) for commands; Windows PowerShell 5.1 (`powershell`) for the helper script | Preinstalled / PowerShell 7 installed |
| Python | 3.12 | `uv venv .venv --python 3.12` (uv manages the interpreter) |
| Node.js | 24 | Preinstalled |
| Claude Code CLI | 2.1.311 | Preinstalled (`C:\Users\<you>\.local\bin\claude.exe`) |
| Claude Code VS Code extension | `anthropic.claude-code` 2.1.312 | `code.cmd --install-extension` into the test copy (section 2.3) |
| Codex CLI | 0.153.2 | Preinstalled |
| Codex VS Code extension | `openai.chatgpt` 26.1021.22027 (bundled Codex 0.164.0) | `code.cmd --install-extension` into the test copy |
| GitHub Copilot CLI | 1.0.105 | `npm install @github/copilot` into `$root\copilot-cli` |
| VS Code (test copy) | 1.142.0, archive build | `@vscode/test-electron` into `$root\vscode-test\.vscode-test` |
| Playwright | `playwright-core` 1.64.1 | `npm install playwright-core` in `$root\vscode-test` |
| Azure CLI | 2.91.0 portable ZIP | `https://aka.ms/installazurecliwindowszipx64` extracted to `$root\azcli` |
| PyCharm | 2026.2.3 (build PY-262.10968.92) | JetBrains installer, silent per-user install |
| JetBrains AI Assistant plugin | `com.intellij.ml.llm` | Launcher `installPlugins` command |
| Azure MCP Server | `@azure/mcp` 4.0.0-beta.3 (`azmcp.exe`, about 116 MiB) | `npm install @azure/mcp@latest` in `$root\azure-mcp` (section 15.1) |
| Python packages | aiohttp, PyJWT (2.15.1) with `cryptography`, psutil, PyMuPDF, defusedxml (0.7.1), lxml (6.1.3) | `uv pip install`; versions not pinned except where recorded here |
| Word | Installed desktop Word (COM automation) | Used only for document QA |

**2.2 One-time setup commands**

```powershell
$root = 'C:\Users\<you>\Local\apim-harness-test'
New-Item -ItemType Directory -Force $root | Out-Null
Set-Location $root

# Python environment for the mock gateway, token proxy, watchers and document QA
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe aiohttp "pyjwt[crypto]" cryptography
uv pip install --python .venv\Scripts\python.exe psutil pymupdf defusedxml lxml
```

Copy the scripts listed in section 2.4 into `$root` (they are the scripts this document describes).

**VS Code test copy and Playwright**

```powershell
New-Item -ItemType Directory -Force "$root\vscode-test" | Out-Null
Set-Location "$root\vscode-test"
npm init -y
npm install --no-audit --no-fund @vscode/test-electron playwright-core
@'
const { downloadAndUnzipVSCode } = require('@vscode/test-electron');
(async () => {
  const p = await downloadAndUnzipVSCode({ version: '1.142.0', cachePath: require('path').join(__dirname, '.vscode-test') });
  console.log('EXE=' + p);
})().catch(e => { console.error('ERR ' + e); process.exit(1); });
'@ | Set-Content -Encoding utf8 download.js
node download.js
```

The download is about 335 MB. The executable is `$root\vscode-test\.vscode-test\vscode-win32-x64-archive-1.142.0\Code.exe`. Do not use the installed VS Code for these tests: a running update on the installed copy holds an installer lock that stops a second instance (section 8.9).

**Extension folders, one extension per profile**

```powershell
$vs  = "$root\vscode-test\.vscode-test\vscode-win32-x64-archive-1.142.0"
$cli = "$vs\bin\code.cmd"
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
$ud  = "$root\work\vscode-install\user-data"
foreach ($x in @(@('vscode-ext-claude','anthropic.claude-code'), @('vscode-ext-codex','openai.chatgpt'))) {
  $dir = "$root\$($x[0])"; New-Item -ItemType Directory -Force $dir | Out-Null
  & $cli --user-data-dir $ud --extensions-dir $dir --install-extension $x[1] --force
}
New-Item -ItemType Directory -Force "$root\vscode-ext-none" | Out-Null   # built-in extensions only
```

Installing `openai.chatgpt` also installs `openai.codex-audio`. An earlier shared folder `$root\vscode-ext` held both extensions; the per-extension folders were created for the egress audit (section 10).

**Copilot CLI**

```powershell
New-Item -ItemType Directory -Force "$root\copilot-cli" | Out-Null
Set-Location "$root\copilot-cli"
npm init -y
npm install --no-audit --no-fund @github/copilot
& "$root\copilot-cli\node_modules\.bin\copilot.cmd" --version     # GitHub Copilot CLI 1.0.105
```

**2.3 Folder layout under `$root`**

| Path | Contents |
|---|---|
| `.venv\` | Python environment |
| `keys\` | Throwaway RSA key (`private.pem`), created on first use |
| `fakeaz\` | Fake Azure CLI (`az.cmd`, `az_main.py`, `mode.json`) |
| `logs\` | `requests.jsonl`, `az_calls.jsonl`, `egress_deny.jsonl`, `egress_label.txt`, `codex_exec_command_schema.json`, `egress\<label>.json` |
| `results\` | Suite outputs (`claude_suite.json`, `claude_refresh.json`, `codex_suite.json`, `codex_refresh.json`, `helper_hardened.json`) |
| `work\` | Per-scenario isolated config and profile folders (`work\claude\<scenario>`, `work\codex\<scenario>`, `work\vscode\<scenario>`, `work\copilot-home`, `work\azconfig`, and others) |
| `vscode-test\` | Playwright driver `drive.js`, scenario files `cfg_*.json`, the VS Code test copy |
| `vscode-probe\` | Test-only extension that lists and calls language models |
| `vscode-cfg\` | Model configuration JSON used by VS Code scenarios |
| `vscode-ext-claude\`, `vscode-ext-codex\`, `vscode-ext-none\`, `vscode-ext\` | Extension folders (section 2.2) |
| `copilot-cli\` | Copilot CLI install and `providers.json` |
| `azcli\`, `realaz\` | Real Azure CLI and its wrapper (section 12) |
| `jetbrains\` | PyCharm installer, install, isolated config, UI helper (section 13) |
| `azure-mcp\` | Azure MCP Server install (section 15) |
| `handoff\` | Documents and their PDF renders |

**2.4 Scripts**

| Script | Role |
|---|---|
| `common.py` | Key creation, JWKS, JWT minting |
| `gateway.py` | Mock gateway |
| `fakeaz\az_main.py`, `fakeaz\az.cmd` | Fake `az account get-access-token` |
| `get-apim-token.ps1` | Helper script under test |
| `get-apim-token-real.ps1` | Copy of the helper with the Azure Resource Manager scope and audience, used for the real-token runs (section 14.4) |
| `harness.py` | Gateway control, log slicing, scrubbed environment, subprocess runner; the environment variables `HARNESS_HELPER` and `HARNESS_AZ_DIR` override the helper script and the folder holding `az.cmd` (section 14.6) |
| `run_claude.py`, `run_codex.py` | Single-scenario runners for the two CLIs |
| `suite_claude.py`, `suite_claude_refresh.py`, `suite_codex.py`, `suite_codex_refresh.py`, `suite_helper_hardened.py`, `suite_proxy.py` | Scenario suites |
| `proxy.py` | Local token-injecting proxy |
| `run_vscode.py` | First VS Code runner (used for v01 and v02 only) |
| `vscode-probe\extension.js`, `vscode-test\drive.js` | VS Code probe extension and Playwright driver |
| `egress_watch.py`, `egress_deny_proxy.py`, `parse_netlog.py` | Egress audit tools |
| `real_az_check.ps1` | Real token check, run after `az login` |
| `mcp_client.py` | Minimal MCP stdio client: initialize, list tools, optional tool calls; writes `results\mcp_<label>.json` (section 15.3) |
| `scan_exe_hosts.py` | Static scan of the Azure MCP Server binary for hostnames (section 15.2) |
| `jetbrains\jb_ui.ps1` | Guarded UI helper for the test PyCharm |
| `render_pdf.py`, `sheet.py`, `sheet2.py` | PDF page rendering for document QA |

**2.5 Ports**

| Port | Service |
|---|---|
| 18080 | Mock gateway |
| 18081 | Local token proxy |
| 18090 | Deny-all logging proxy |

All services bind to `127.0.0.1`.

**2.6 Isolation rules**

Every harness runs against its own throwaway configuration so that no real account, setting or credential is read or changed.

| Harness | Isolation |
|---|---|
| Claude Code CLI | `CLAUDE_CONFIG_DIR=$root\work\claude\<scenario>`; `settings.json` and `.claude.json` written fresh each run |
| Codex CLI | `CODEX_HOME=$root\work\codex\<scenario>`; `config.toml` written fresh each run |
| Copilot CLI | `USERPROFILE`, `HOME`, `APPDATA` and `LOCALAPPDATA` set to `$root\work\copilot-home` and its subfolders |
| Azure CLI (real) | `AZURE_CONFIG_DIR=$root\work\azconfig` set inside `realaz\az.cmd` |
| VS Code | `--user-data-dir $root\work\vscode\<scenario>\user-data` and `--extensions-dir <one of the extension folders>` |
| Claude extension inside VS Code | `CLAUDE_CONFIG_DIR` passed in the scenario `env` |
| Codex extension inside VS Code | `CODEX_HOME` passed in the scenario `env`; always set it whenever the Codex extension is installed in the extensions folder |
| PyCharm | `PYCHARM_PROPERTIES=$root\jetbrains\cfg\idea.properties` (section 13). PyCharm also created `%USERPROFILE%\PycharmProjects\WelcomeScreen` (containing `.idea`) at first launch; that folder is outside this isolation |

**2.7 Environment scrubbing**

`harness.clean_env()` copies the current environment, then removes every variable whose name starts with `CLAUDE_CODE_`, `ANTHROPIC_`, `CLAUDECODE`, `OPENAI_` or `CODEX_`, and removes `CLAUDE_CONFIG_DIR`. It then prepends `$root\fakeaz` to `PATH` so that `az` resolves to the fake. `drive.js` applies the same removal (plus `ELECTRON_RUN_AS_NODE`) before launching VS Code and sets `LMTEST_QUIT=0` so the probe extension does not quit VS Code. This matters because the console that runs the tests may itself be inside an Electron application or a Claude Code session whose variables would otherwise leak into the child process.

## 3. Mock gateway and fake `az`

**Purpose.** Stand in for APIM and for the Azure CLI so that every authentication behaviour can be repeated and every request inspected.

**3.1 What the gateway does**

- `common.py` generates a 2048-bit RSA key on first use (`keys\private.pem`) and mints RS256 JWTs with header `kid` `test-key-1`, issuer `https://login.microsoftonline.com/00000000-0000-0000-0000-00000000test/v2.0`, audience `api://apim-test`, and claims `iat`, `nbf`, `exp`, `jti`, `upn`, `oid`, `scp`.
- `gateway.py` validates the bearer token on every route: signature, `aud`, `iss`, and `exp` are required. It never logs the raw token. In lenient mode (3.3 and section 14) it checks only that the token is a well-formed, unexpired JWT.
- Routes: `POST /anthropic/v1/messages` (Anthropic Messages, streaming and non-streaming), `POST /openai/v1/responses` (OpenAI Responses, streaming and non-streaming), `POST /openai/v1/chat/completions` (OpenAI Chat Completions, streaming and non-streaming), `POST <any>/count_tokens`, `GET <any>/models`, `GET /jwks.json`, `GET|POST /_ctl`. Anything else returns 404 and is logged. Only the three model routes and the paths above exist: a client that calls `/openai/models` (no `/v1`) receives the model list but cannot chat there.
- Chat Completions route (added for the JetBrains test): a non-streaming call returns a `chat.completion` object; a streaming call returns `chat.completion.chunk` events (a role chunk, content chunks, a `stop` chunk) ending with `data: [DONE]`. `sse_delay_ms` applies between chunks.
- `GET <any>/models`: for paths containing `/openai/` it returns the OpenAI list shape `{"object":"list","data":[{"id":"gpt-test",...},{"id":"gpt-test-2",...}]}`; for other paths it returns an Anthropic-shaped list (`claude-test`). Runs made before this change received the Anthropic-shaped list on every `/models` path.
- Replies are canned: `MOCK-OK model=<model> seq=<n>`.
- Scripted tool turns: when the control value `tool_turns` is greater than 0, requests that include tools receive a tool call instead of text until that many tool results are present. For Anthropic requests it emits a `Bash` tool call (`echo step<N>`); for OpenAI requests it emits an `exec_command` call with the argument key `cmd`. The first Codex request with an `exec_command` tool writes its schema to `logs\codex_exec_command_schema.json`.
- `turn_delay_s` delays the reply of any request that carries tools by that many seconds.

**3.2 Start and check**

```powershell
Set-Location $root
$py = "$root\.venv\Scripts\python.exe"
$env:PATH = "$root\fakeaz;" + $env:PATH
Start-Process $py -ArgumentList gateway.py -WorkingDirectory $root -WindowStyle Hidden
Start-Sleep 2
curl.exe -s http://127.0.0.1:18080/_ctl
# {"force_status": null, "force_count": 0, "sse_delay_ms": 0, "seq": 0}   (plus tool_turns and turn_delay_s once set)
```

Pass criterion: `/_ctl` returns the state JSON.

**3.3 Fault injection (`POST /_ctl`, merged into the state)**

| Key | Effect |
|---|---|
| `force_status` and `force_count` | The next `force_count` requests to the two model routes return `force_status` (for example 401) and are logged with `forced: true` |
| `sse_delay_ms` | Delay between streamed events |
| `tool_turns` | Number of scripted tool turns (section 3.1) |
| `turn_delay_s` | Delay before replying to requests that carry tools |
| `lenient` | When true, accept any well-formed, unexpired JWT without verifying signature, audience or issuer, and log `aud`, `ver`, `real_token` and `token_chars` (used for real Entra tokens, section 14.5) |
| `mcp_call` | A tool name; the next streaming model request that carries a matching tool receives one scripted call to it with empty arguments (section 15.6) |

From Python: `import harness as h; h.ctl(force_status=401, force_count=1)`. Reset with `h.ctl(force_status=None, force_count=0, sse_delay_ms=0, tool_turns=0, turn_delay_s=0)`.

**3.4 Fake `az`**

`fakeaz\az.cmd` runs `.venv\Scripts\python.exe fakeaz\az_main.py %*`. It implements only `account get-access-token` (any other command writes a message to stderr and exits 2). It reads `fakeaz\mode.json` on every call, writes one line to `logs\az_calls.jsonl` (`ts`, `pid`, `argv`, `mode`), then behaves as follows.

| Mode | Behaviour |
|---|---|
| `ok` | Prints a fresh JWT with lifetime `ttl` seconds (default 120) |
| `slow` | Sleeps `slow_s` seconds, then behaves like `ok` |
| `noisy` | Prints `WARNING: some banner on stdout` on stdout, then the JWT |
| `fail` | Writes `ERROR: Please run 'az login' to setup account.` to stderr, exits 1 |
| `wrong_aud` | Prints a JWT whose audience is `https://cognitiveservices.azure.com` |

Set the mode from Python: `import harness as h; h.az_mode('slow', 120, 6)` (mode, ttl, slow_s). The file content is for example `{"mode": "ok", "ttl": 120, "slow_s": 0}`.

**3.5 Reading the logs**

`logs\requests.jsonl` has one JSON object per request:

| Field | Meaning |
|---|---|
| `seq`, `ts`, `method`, `path`, `query` | Sequence number, epoch time, request line |
| `headers` | All request headers except `authorization` and `x-api-key`, names lower-cased |
| `body` | `model`, `stream`, `n_messages`, `n_tools`, `tool_names`, `max_tokens`, `last_text` (first 100 characters) |
| `auth.authorization_scheme`, `auth.x_api_key_present`, `auth.x_api_key_equals_bearer` | How the token arrived |
| `auth.result` | `ok`, `missing_bearer`, `expired`, or `invalid:<exception name>` such as `invalid:InvalidAudienceError` |
| `auth.claims` | `jti`, `iat`, `exp`, `ttl_remaining`, `upn` for valid or expired tokens |
| `route`, `status`, `forced` | Route handled, HTTP status, whether the status was injected |

`harness.marks()` and `harness.since(mark)` slice the log (and `az_calls.jsonl`) to the requests made by one run; `harness.summarize()` condenses them. To read the log by hand:

```powershell
Get-Content "$root\logs\requests.jsonl" | Select-Object -Last 5 | ForEach-Object { $_ | ConvertFrom-Json } |
  ForEach-Object { "{0} {1} status={2} auth={3} jti={4}" -f $_.method,$_.path,$_.status,$_.auth.result,$_.auth.claims.jti }
```

**Cleanup.** Stop only processes started from the test folder:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'apim-harness-test' -and $_.Name -match '^(python|Code|pycharm64|node|copilot|codex|claude|powershell)\.exe$' -and $_.CommandLine -notmatch 'Get-CimInstance' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
```

**Pitfall.** Never stop processes by image name alone (for example all `node.exe`); they may belong to other work on the machine.

## 4. Helper script and its direct tests

**Purpose.** The helper prints one JWT on stdout. Both CLIs and both extensions run it. It was tested on its own before being used by the tools.

**4.1 The two versions**

The original helper, used for scenarios c01 to c11, the Claude refresh tests and x01 to x14:

```powershell
$ErrorActionPreference = 'Stop'
$token = az account get-access-token --scope "api://apim-test/.default" --query accessToken -o tsv
if (-not $token) { exit 1 }
Write-Output $token.Trim()
```

The hardened helper (`get-apim-token.ps1`, used from `suite_helper_hardened.py` onward, including c12, c13 and every extension, egress and proxy test): it runs the same `az` command with `2>$null`, exits 1 with `get-apim-token: az failed (exit N). Run: az login` when `az` fails, keeps only the stdout line that matches `^eyJ[\w-]+\.[\w-]+\.[\w-]+$`, decodes the payload, exits 1 with a one-line message if `aud` is not one of the values in `$ExpectedAud` (a list, `@('api://apim-test')` in the tests, checked with `-notcontains`; the helper copy used for the real-token runs, section 14.4, still compares against a single string) or if less than `$MinLifeSecs` (60) seconds remain, and otherwise writes the JWT with `[Console]::Out.Write`. The exact text is the script in the test folder.

**4.2 Direct tests**

```powershell
$env:PATH = "$root\fakeaz;" + $env:PATH
foreach ($m in 'ok','noisy','wrong_aud','fail') {
  & $py -c "import harness as h; h.az_mode('$m',120)"
  $t = powershell -NoProfile -File "$root\get-apim-token.ps1"
  "{0}: len={1} rc={2}" -f $m, $t.Length, $LASTEXITCODE
}
```

Pass criteria: `ok` and `noisy` return one token (length 801 in the recorded run) and exit 0; `wrong_aud` prints `get-apim-token: token aud is '...', expected 'api://apim-test'` on stderr and exits 1; `fail` prints `get-apim-token: az failed (exit 1). Run: az login` and exits 1. Run the same loop with the original helper to capture the unhardened behaviour (capture only).

**4.3 Combined helper test with both CLIs**

`python suite_helper_hardened.py` runs `run_claude.py` and `run_codex.py` once for each of `ok`, `noisy`, `wrong_aud`, `fail` (timeout 60 s each) and writes `results\helper_hardened.json`. Capture: return code, seconds, helper (az) call count, and the status and `auth.result` of each model request.

## 5. Claude Code CLI procedures

**5.1 Runner.** `run_claude.py <scenario> [--prompt P] [--settings JSON] [--model M] [--timeout S] [--no-helper] [--allow-bash] [--allowed VALUE] [--claude-json JSON]` (the last two are described in section 15.6) creates `work\claude\<scenario>` (deleting any previous one) and writes:

```json
{ "apiKeyHelper": "powershell -NoProfile -File <root>\\get-apim-token.ps1",
  "env": { "ANTHROPIC_BASE_URL": "http://127.0.0.1:18080/anthropic", "CLAUDE_CODE_API_KEY_HELPER_TTL_MS": "300000" } }
```

to `settings.json` (the `--settings` JSON is merged in; its `env` keys are merged into `env`), and `{"hasCompletedOnboarding": true, "numStartups": 5}` to `.claude.json`. It then runs, with the scrubbed environment plus `CLAUDE_CONFIG_DIR` and `DISABLE_AUTOUPDATER=1`, in `work\claude\<scenario>\cwd`:

```
claude -p "<prompt>" --output-format json --permission-mode default [--model M] [--allowedTools Bash]
```

The default prompt is `Reply with the single word: ok`. It prints the summarized gateway requests, the return code, seconds, the number of helper calls, then the first 1500 characters of stdout and stderr.

**5.2 Baseline and scenarios** (`python suite_claude.py` runs c02 to c11 and writes `results\claude_suite.json`; c01, c12 and c13 were run singly)

| Scenario | Setup | Capture or pass criterion |
|---|---|---|
| c01 baseline | `python run_claude.py c01-baseline` | Pass: rc 0; at least one `POST /anthropic/v1/messages` with `auth.result` `ok`; token arrives as both `Authorization: Bearer` and `x-api-key` (`x_api_key_equals_bearer` true) |
| c02 custom headers | `--settings '{"env":{"ANTHROPIC_CUSTOM_HEADERS":"Ocp-Apim-Subscription-Key: sub-123\nX-Tenant: acme"}}'` | Pass: both headers present in the gateway log |
| c03 model mapping | env `ANTHROPIC_DEFAULT_SONNET_MODEL=dep-sonnet`, `..._HAIKU_MODEL=dep-haiku`, `..._OPUS_MODEL=dep-opus`, `--model sonnet` | Capture: `body.model` of each request |
| c04 model setting | `--settings '{"model":"my-deployment"}'` | Capture: `body.model` |
| c05 noisy helper | `h.az_mode('noisy',120)` | Capture: rc, `auth.result`, request count |
| c06 failing helper | `h.az_mode('fail',120)`, `--timeout 90` | Capture: rc, seconds, helper calls, stdout and stderr text |
| c07 wrong audience | `h.az_mode('wrong_aud',120)`, `--timeout 90` | Capture: rc or timeout, request count, helper calls (original helper) |
| c08 slow helper | `h.az_mode('slow',120,6)` | Pass: rc 0 |
| c09 one 401 | `h.ctl(force_status=401, force_count=1)` | Capture: whether a second request is made and whether the helper runs again |
| c10 static token | `--settings '{"env":{"ANTHROPIC_AUTH_TOKEN":"static-not-a-jwt"}}'` | Capture: which credential the gateway sees, rc or timeout (120 s) |
| c11 short token, one prompt | helper TTL 5000, token lifetime 20 s | Capture only. A single prompt finishes in about 1.4 s, so this does not test expiry; the refresh tests below replace it |
| c12 model override | `--settings '{"modelOverrides":{"claude-opus-5-5":"dep-override"}}'` | Capture: `body.model` |
| c13 helper message | `h.az_mode('wrong_aud',120)`, `--timeout 60`, hardened helper | Capture: the `result` text and stderr line that Claude Code prints |

Reset between scenarios: `h.ctl(force_status=None, force_count=0, sse_delay_ms=0)` and `h.az_mode('ok',120)` (the suite does this).

**5.3 Mid-session token expiry (`python suite_claude_refresh.py`, about 90 s; writes `results\claude_refresh.json`)**

Purpose: a single session must outlive the token. Two runs:

| Run | Token lifetime | Helper cache (`CLAUDE_CODE_API_KEY_HELPER_TTL_MS`) |
|---|---|---|
| r1-helperttl5s-token20s | 20 s | 5000 |
| r2-helperttl300s-token20s | 20 s | 300000 |

Each run sets `h.az_mode('ok', 20)` and `h.ctl(tool_turns=4, turn_delay_s=8)`, then runs `run_claude.py <name> --allow-bash --timeout 200 --prompt "Run: echo hello" --settings '{"env":{"CLAUDE_CODE_API_KEY_HELPER_TTL_MS":"<value>"}}'`. The mock returns a `Bash` tool call four times, 8 s apart, so the session lasts about 40 s. Reset with `h.ctl(tool_turns=0, turn_delay_s=0)` and `h.az_mode('ok',120)`. Pass criterion: rc 0. Capture: the `jti` and `ttl_remaining` of each `POST /anthropic/v1/messages`, any 401 with `auth.result` `expired`, and the helper call count.

**Pitfalls.** Use `--allow-bash`, otherwise the tool call is denied and the session ends early. Do not set `ANTHROPIC_AUTH_TOKEN` in the user shell; `clean_env` removes `ANTHROPIC_*` for this reason.

## 6. Codex CLI procedures

**6.1 Runner.** `run_codex.py <scenario> [--prompt P] [--provider-lines L ...] [--top-lines L ...] [--auth JSON] [--no-auth] [--base-url U] [--timeout S] [--model M]` creates `work\codex\<scenario>\config.toml`:

```toml
model = "gpt-test"
model_provider = "apim"
# --top-lines go here, before any [table]

[model_providers.apim]
name = "Azure APIM"
base_url = "http://127.0.0.1:18080/openai/v1"
wire_api = "responses"
# --provider-lines go here

[model_providers.apim.auth]
command = 'powershell'
args = ['-NoProfile', '-File', '<root>\get-apim-token.ps1']
timeout_ms = 15000
refresh_interval_ms = 1800000
```

`--auth` JSON overrides keys in the `auth` table; `--no-auth` omits the table. It runs `codex exec --skip-git-repo-check "<prompt>"` with `CODEX_HOME` set to the scenario folder.

**6.2 Scenarios** (`python suite_codex.py` runs x02 to x10 and writes `results\codex_suite.json`; x01 and x11 were run singly)

| Scenario | Setup | Capture or pass criterion |
|---|---|---|
| x01 baseline | `python run_codex.py x01-baseline` | Pass: rc 0; `POST /openai/v1/responses` with `auth.result` `ok`; `Authorization: Bearer` and no `x-api-key`. Also capture the `GET /models` calls |
| x02 query and headers | `--provider-lines 'query_params = { api-version = "2025-04-01-preview" }' 'http_headers = { "Ocp-Apim-Subscription-Key" = "sub-123", "X-Tenant" = "acme" }'` | Pass: query parameter and headers present on `/models` and `/responses` |
| x03 noisy helper | `h.az_mode('noisy',120)` | Capture: rc, seconds, `auth.result`, helper calls |
| x04 failing helper | `h.az_mode('fail',120)`, `--timeout 90` | Capture: rc, seconds, helper calls, stderr text |
| x05 wrong audience | `h.az_mode('wrong_aud',120)`, `--timeout 90` | Capture: rc, seconds, request count |
| x06 slow helper, default timeout | `h.az_mode('slow',120,6)`, `--auth '{"timeout_ms":5000}'` | Capture: rc or timeout, helper calls |
| x07 slow helper, 15 s timeout | `h.az_mode('slow',120,6)` | Pass: rc 0 |
| x08 one 401 | `h.ctl(force_status=401, force_count=1)` | Capture: whether the helper runs again and the retry succeeds |
| x09 no auth table | `--no-auth --timeout 40` | Capture: request status |
| x10 auth plus env_key | `--provider-lines 'env_key = "FOO_KEY"' --timeout 40` | Capture: whether the config loads (`Error loading config.toml` text) |
| x11 scripted tool turns | `h.ctl(tool_turns=2)` then `python run_codex.py x11-toolturns --timeout 90` | Pass: three `POST /openai/v1/responses` requests in one run |

x01 to x08 and x11 used the original helper (the refresh runs x12 to x14 also ran before the helper was hardened). In x03 to x05 and x11 the runner prints the gateway summary; read the stderr text from the `--- stderr:` section.

**6.3 Mid-session token expiry (`python suite_codex_refresh.py`, about 2.5 min; writes `results\codex_refresh.json`)**

| Run | `refresh_interval_ms` |
|---|---|
| x12-refresh5s-token20s | 5000 |
| x13-refresh30min-token20s | 1800000 |
| x14-refresh0-token20s | 0 |

Each run: `h.az_mode('ok', 20)`, `h.ctl(tool_turns=4, turn_delay_s=8)`, `run_codex.py <name> --timeout 200 --auth '{"refresh_interval_ms": <value>}'`, then reset. Pass criterion: rc 0. Capture: `jti` and `ttl_remaining` per `POST /openai/v1/responses`, any `expired` 401, helper call count.

## 7. Local token proxy procedures

**Purpose.** Some tools only send a static key. `proxy.py` replaces the client key with a fresh JWT from the helper, streams the reply, and retries once on an upstream 401.

**7.1 Start**

```powershell
$env:PATH = "$root\fakeaz;" + $env:PATH
Start-Process $py -ArgumentList @('proxy.py','--upstream','http://127.0.0.1:18080','--port','18081','--margin-s','5','--','powershell','-NoProfile','-File',"$root\get-apim-token.ps1") -WorkingDirectory $root -WindowStyle Hidden
curl.exe -s http://127.0.0.1:18081/_proxy/health      # {"ok": true, "token_fetches": 0}
```

`--margin-s 5` makes the proxy fetch a new token when fewer than 5 s remain (the production setting suggested elsewhere is 300). `--local-key K` (not tested) would require a shared key from the client.

**7.2 Tests** (`python suite_proxy.py` runs P1 to P4; P5 to P7 were run singly)

| Test | Procedure | Pass criterion |
|---|---|---|
| P1 | `POST /anthropic/v1/messages` to port 18081 with `Authorization: Bearer dummy-local-key` and `x-api-key: dummy-local-key` | Gateway log: `auth.result` ok, `x_api_key_present` false |
| P2 | Same with `stream: true` and `h.ctl(sse_delay_ms=150)` | Response contains `message_stop`; elapsed time reflects the delay |
| P3 | `POST /openai/v1/responses` with `{"model":"gpt-test","stream":false,"input":"hi"}` | HTTP 200 |
| P4 | `h.ctl(force_status=401, force_count=1)`, then one request | Gateway log shows a 401 followed by a 200 with a different `jti` |
| P5 | Stop the proxy, `h.az_mode('fail',120)`, start a new proxy, send one request, then `h.az_mode('ok',120)` and send another on the same proxy | First: HTTP 502 JSON with the helper message; second: HTTP 200 |
| P6 | `python run_claude.py p1 --no-helper --settings '{"env":{"ANTHROPIC_BASE_URL":"http://127.0.0.1:18081/anthropic","ANTHROPIC_AUTH_TOKEN":"local-dummy"}}'` | rc 0; gateway sees a valid JWT with no helper call by Claude Code |
| P7 | `python run_codex.py p2 --no-auth --base-url http://127.0.0.1:18081/openai/v1 --provider-lines 'experimental_bearer_token = "local-dummy"'` | rc 0; gateway sees a valid JWT |

## 8. VS Code UI procedures (Playwright)

**8.1 Why Playwright.** The test copy of VS Code is an Electron application. `playwright-core` launches it directly (`_electron.launch`) and drives it with mouse and keyboard events, reads the page text, takes screenshots, and lists frames. This works without the computer-use tooling and without giving focus to the console, because the events are sent to the test instance only.

**8.2 Driver and scenario files.** `node drive.js <cfg.json>` run from `$root\vscode-test`. A scenario file is JSON:

| Key | Meaning |
|---|---|
| `scenario` | Name; profile folder is `$root\work\vscode\<scenario>` (deleted at start unless `keepProfile` is true) |
| `modelsJson` | File copied to `User\chatLanguageModels.json` (skipped when `keepProfile` is true) |
| `settings` | Merged over the default `settings.json` |
| `probe` | Load the probe extension unless `false` |
| `extDir` | Extensions folder (default `$root\vscode-ext`) |
| `env` | Extra environment variables for VS Code (for example `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, proxy variables) |
| `pathPrepend` | Folder prepended to `PATH` (always `$root\fakeaz`) |
| `args` | Extra VS Code arguments; `{base}` expands to the profile folder |
| `wait_ms` | Wait after the workbench window appears (default 15000) |
| `steps` | List of step objects (below) |
| `keepProfile` | Reuse the existing profile folder |

Default settings written to every profile: `security.workspace.trust.enabled` false, `telemetry.telemetryLevel` `off`, `update.mode` `none`, `workbench.startupEditor` `none`, `chat.agentHost.byokModels.enabled` true. The driver launches `Code.exe` with `--user-data-dir`, `--extensions-dir`, `--new-window`, `--disable-workspace-trust`, `--disable-updates`, `--skip-welcome`, `--skip-release-notes`, then `--extensionDevelopmentPath $root\vscode-probe` (unless `probe` is false), then `args`, then the workspace folder `work\vscode\<scenario>\ws`.

Steps: `wait` (`ms`), `click_xy` (`x`, `y`), `type` (`text`, 15 ms per key), `press` (`key`, for example `Enter`, `Control+a`, `ArrowDown`), `palette` (F1, type text, Enter), `shot` (`name`, saves `<name>.png` in the profile folder), `text` (logs the first 1500 characters of the page text), `webview_text`, `frames`, `click_text`, `webview_type`. At the end it saves `final.png`, closes the app (kills the process after 8 s if the close hangs) and exits. Output lines are JSON: `{"step":"click_xy","ok":true}`, `{"text":"..."}`, `{"shot":"<path>"}`.

**Screen assumptions.** All coordinates were read from screenshots 1440 by 900 pixels. The driver does not set the window size, so on another display re-derive the coordinates from a `shot`.

**8.3 Probe extension** (`vscode-probe`). Activates on startup finished, waits `LMTEST_WAIT_MS` (default 8000), calls `vscode.lm.selectChatModels({})`, writes the list to `probe.jsonl`, sends one prompt to each model of vendor `LMTEST_VENDOR` (default `customendpoint`), and quits VS Code unless `LMTEST_QUIT=0` (the driver sets it to 0). Used in scenarios d01 to d14 only.

**8.4 Capturing the result.** For every UI scenario record the gateway log lines created during the run (take `(Get-Content logs\requests.jsonl).Count` before starting and read the lines after), the `text` step output, and the screenshots. Pass criterion for a chat test: a `POST` to the expected route with `auth.result` `ok`, and the reply text `MOCK-OK model=...` visible in the panel text or screenshot.

**8.5 Claude Code extension** (scenarios d12, d13, g1, h1, i1)

Preconditions: gateway running; `h.az_mode('ok',120)`; `CLAUDE_CONFIG_DIR` folder `$root\work\claude-vsext` containing `settings.json` with `apiKeyHelper` (hardened helper) and `env.ANTHROPIC_BASE_URL` `http://127.0.0.1:18080/anthropic`, and `.claude.json` as in section 5.1. Nothing is set in VS Code's own Claude settings.

Scenario file (key parts): `extDir` `$root\vscode-ext-claude`, `env` `{ "CLAUDE_CONFIG_DIR": "<folder>" }`, `probe` false, `wait_ms` 14000, steps:

| Step | Detail |
|---|---|
| 1 | `click_xy` (1355, 884): status-bar item "Claude Code" opens the panel |
| 2 | `wait` 15000 |
| 3 | `click_xy` (745, 794): the panel input |
| 4 | `press` `Control+a` (clears stray text) |
| 5 | `type` `Reply with the single word: ok` |
| 6 | `press` `Enter` |
| 7 | `wait` 25000, then `shot` |

Pass criterion: gateway shows two `HEAD /anthropic/api/hello` (404) and a `POST /anthropic/v1/messages` with `auth.result` `ok`, user agent containing `claude-vscode`; the panel shows `MOCK-OK model=claude-opus-5-5`.

**8.6 Codex extension** (scenarios d09 to d11, g3, h3, i3)

Preconditions: `$root\work\codex-vsext\config.toml` with the provider and auth block from section 6.1 (`base_url` `http://127.0.0.1:18080/openai/v1`). Scenario: `extDir` `$root\vscode-ext-codex`, `env` `{ "CODEX_HOME": "<folder>" }`, `probe` false, steps:

| Step | Detail |
|---|---|
| 1 | `click_xy` (1190, 851): the session-type dropdown, labelled "Local", at the bottom left of the chat box |
| 2 | `wait` 1500 |
| 3 | `click_xy` (1208, 767): the "Codex" entry; the Codex panel opens in the editor area |
| 4 | `wait` 36000 (the panel needs about 35 s to finish loading; before that it shows only a logo) |
| 5 | `click_xy` (745, 785): "Ask Codex anything" input |
| 6 | `type` the prompt, `press` `Enter`, `wait` 25000, `shot` |

Pass criterion: gateway shows `GET /openai/v1/models` and `POST /openai/v1/responses` with `auth.result` `ok` and header `originator: codex_vscode`; the panel shows `MOCK-OK model=gpt-test`.

**8.7 Copilot Chat with BYOK** (scenarios j1 to j8)

Purpose: test chat with a custom endpoint while signed out of GitHub.

A. Failing configuration (scenarios d01 to d08, v02). Copy `vscode-cfg\via_proxy_responses.json` to `User\chatLanguageModels.json` with a literal `"apiKey": "dummy-local-key"` and `url` `http://127.0.0.1:18081/openai/v1/responses`. Open the Language Models editor (`palette` `Chat: Manage Language Models`, wait 3000) and the chat picker (`click_xy` 1271, 818). Capture: whether the model appears in the editor, in the picker, and in `vscode.lm.selectChatModels` (probe output); what happens when a message is sent (text of the panel).

B. Adding the provider through the UI (scenarios j3, j4). Start with no `chatLanguageModels.json`. Steps in one driver run (`probe` false, `extDir` `$root\vscode-ext-none`, `wait_ms` 16000):

| Step | Detail |
|---|---|
| 1 | `palette` `Chat: Manage Language Models`, `wait` 3000 |
| 2 | `click_xy` (1091, 168): **Add Models** button; `wait` 1500 |
| 3 | `click_xy` (1134, 415): **Custom Endpoint** in the list; `wait` 2500 |
| 4 | `type` `APIM-UI` (group name), `press` `Enter`, `wait` 2500 |
| 5 | `type` `dummy-local-key` (API key; use a real key or the token-proxy dummy), `press` `Enter`, `wait` 3000 |
| 6 | The API type prompt lists Chat Completions, Responses, Messages. `press` `ArrowDown` then `Enter` selects Responses; `wait` 4000; `shot` |

VS Code then writes `User\chatLanguageModels.json` containing a group with `"apiKey": "${input:chat.lm.secret.<id>}"` and `"apiType": "responses"`, and opens that file with a template model.

C. Add the model. Close the run, then edit the generated file (keep the placeholder unchanged) so that the group has:

```json
"models": [ { "id": "gpt-test", "name": "GPT Test (UI-added)", "url": "http://127.0.0.1:18081/openai/v1/responses",
              "apiType": "responses", "toolCalling": true, "vision": false, "maxInputTokens": 100000, "maxOutputTokens": 8000 } ]
```

Delete `work\vscode\j4-byok-ui-added\user-data\Backups` and `...\User\workspaceStorage`. Otherwise VS Code restores the unsaved template buffer from the killed run (hot exit) and the picker shows an empty model row.

D. Select the model and chat (scenarios j6, j7). Relaunch with `keepProfile` true, `wait_ms` 22000, `extDir` `$root\vscode-ext-none`, `pathPrepend` `$root\fakeaz`; start the token proxy first (section 7.1). Steps: `click_xy` (1268, 818) opens the picker, which shows a tab named `APIM-UI`; `wait` 2000; `click_xy` (1070, 786) selects the model row; `wait` 2000; `click_xy` (1250, 782) focuses the chat input (a "Set BYOK utility models" card sits above it); `type` the prompt; `press` `Enter`; `wait` 25000; `shot`; `text`.

Pass criterion: gateway shows `POST /openai/v1/responses` with `auth.result` `ok`, user agent `GitHubCopilotChat/...`, and the panel text contains `MOCK-OK model=gpt-test`.

E. Flag variation (j1). Same configuration with `settings` `{"chat.agentHost.byokModels.enabled": false}`; capture the picker contents.

F. Session types (d07, d14). `click_xy` (1190, 851) opens the session-type dropdown (entries: Local, Copilot, Codex, Claude). Capture the entries and any "Sign in" or "No models available" text. d14 uses `vscode-cfg\via_proxy_messages.json` (`apiType` `messages`, `url` `http://127.0.0.1:18081/anthropic/v1/messages`).

**8.8 Scenario index (`$root\vscode-test\cfg_*.json`)**

| Scenarios | Purpose |
|---|---|
| d01 to d08 | Chat state, Language Models editor, picker, first message, session types, Codex harness selection |
| d09 to d11 | Codex extension (open, wait, send) |
| d12, d13 | Claude Code extension (open, send) |
| d14 | Messages-type BYOK model and session types |
| g1 to g4 | First egress runs (invalid for VS Code: see the pitfall in section 10.1) |
| h0 to h4 | Egress, default and quiet profiles, one extension per profile, with net-log |
| i0, i1, i3 | Egress through the deny-all proxy |
| j1 to j8 | Copilot BYOK procedure and its denied run (j8) |

**8.9 Pitfalls observed**

- Launching the installed VS Code with a separate `--user-data-dir` exited after about 31 s with "Code is currently being updated" when an update was in progress (installer lock `vscode-updating`); `code.cmd --wait` produced no logs. Use the downloaded test copy.
- `ELECTRON_RUN_AS_NODE` set in the console makes `Code.exe` behave as Node. The driver removes it; remove it also before running `code.cmd` by hand.
- The probe extension quits VS Code unless `LMTEST_QUIT=0`; the first Playwright attempt failed with "Target page, context or browser has been closed" for that reason.
- `Control+Alt+I` toggles the chat panel; pressing it when the panel is already open closes it.
- In the Local session the model picker shows only a "GitHub Copilot" tab until a provider group with a stored secret exists. A literal `apiKey` in the JSON is not treated as configured.
- The Codex panel shows only a logo for about 35 s, then a "Finish Windows setup" prompt and, after sending, a model promotion dialog; they do not block the test.
- `app.close()` can hang; the driver force-kills the process it launched. A first attempt to clean up with a broad `Stop-Process -Name node` was correctly blocked; use command-line matching (section 3.5).
- The Claude Code panel input can contain stray text; send `Control+a` before typing.

## 9. Copilot CLI procedures

**Purpose.** Test BYOK with no GitHub login, with and without offline mode, and a Fusion model selection while signed out.

**Preconditions.** Section 2.2 install; gateway and token proxy running; `h.az_mode('ok',120)`.

**Isolated environment (set in each console before running)**

```powershell
$h = "$root\work\copilot-home"
New-Item -ItemType Directory -Force $h | Out-Null
$env:USERPROFILE=$h; $env:HOME=$h; $env:APPDATA="$h\AppData\Roaming"; $env:LOCALAPPDATA="$h\AppData\Local"
foreach ($k in 'GH_TOKEN','GITHUB_TOKEN','COPILOT_GITHUB_TOKEN') { Remove-Item "Env:$k" -ErrorAction SilentlyContinue }
$env:COPILOT_PROVIDERS_CONFIG = "$root\copilot-cli\providers.json"
$cp = "$root\copilot-cli\node_modules\.bin\copilot.cmd"
```

**providers.json** (`$root\copilot-cli\providers.json`)

```json
{
  "providers": [ { "name": "apim", "type": "openai", "baseUrl": "http://127.0.0.1:18081/openai/v1", "apiKey": "dummy-local-key", "wireApi": "responses" } ],
  "models": [ { "id": "gpt-test", "provider": "apim", "maxPromptTokens": 100000, "maxOutputTokens": 8000 } ]
}
```

**Procedures**

| Test | Command | Capture or pass criterion |
|---|---|---|
| Offline BYOK | `$env:COPILOT_OFFLINE='true'; & $cp --model apim/gpt-test -p "Reply with the single word: ok"` | Pass: output contains `MOCK-OK model=gpt-test`; gateway shows `POST /openai/v1/responses` with `auth.result` `ok` and user agent `OpenAI/JS ...`; no GitHub sign-in prompt |
| Online BYOK | Same command after `Remove-Item Env:COPILOT_OFFLINE` | Same pass criterion; capture elapsed time and the egress audit (section 10) |
| Fusion, HydraFusion name | `& $cp --experimental --model hydrafusion -p "Reply with the single word: ok"` | Capture: error text, whether the gateway received a request, egress audit |
| Fusion, alternative name | `& $cp --experimental --model copilot-fusion -p "Reply with the single word: ok"` | Same |

The tests ran each command in a PowerShell background job with a 90 s limit (`Start-Job`, `Wait-Job -Timeout 90`). The CLI prints a `Resume copilot --resume=<id>` line; that is normal.

**Pitfall.** The `providers.json` `bearerToken` field and custom headers were not tested; the dummy `apiKey` is replaced by the token proxy.

## 10. Egress audit procedures

**Purpose.** Record every external host each harness tries to reach, and check that each harness still works when only localhost is reachable.

**10.1 Connection watcher (`egress_watch.py`)**

Every 0.4 s it lists the established or connecting TCP connections of a process tree with `psutil` (the root process plus all descendants), ignores loopback addresses, and records `ip`, `port`, whether the address is private, process names and connection states. Every 2 s it refreshes a map of address to name from `Get-DnsClientCache`; for addresses it cannot name it tries a reverse lookup. It writes `logs\egress\<label>.json` and prints a summary including the number of processes tracked and their names.

Modes:

```powershell
# run a command and watch its tree until it exits (CLIs)
& $py egress_watch.py --label claude-cli-default --secs 150 --run -- $py run_claude.py e1-default --prompt "Reply with the single word: ok"
# watch the tree of a process found by command-line text and image name (GUI applications)
& $py egress_watch.py --label vscode-i1-claude-ext-denied --secs 85 --match i1-claude-ext-denied --name Code.exe
# watch an existing process tree by PID
& $py egress_watch.py --label pycharm-idle --secs 40 --pid <pid>
```

For `--match`, the watcher waits up to 60 s for a process to appear whose command line contains the text and which has no `--type=` argument.

Pitfall (found and fixed): the first VS Code audit used `--match` without `--name`; the watcher matched its own command line, tracked only itself (2 processes), and reported no connections. Fix: exclude the watcher's own process and any command line containing `egress_watch`, and require the image name `Code.exe`. Always check the summary line "tracked up to N processes (names)": for a VS Code run it should list `Code.exe` and several others (12 to 20 processes in the recorded runs).

**10.2 Deny-all logging proxy (`egress_deny_proxy.py`)**

Simulates a network where only localhost is reachable. It listens on `127.0.0.1:18090`, refuses every `CONNECT` or absolute-URI request with HTTP 403, and appends `{ts, label, method, host, port}` to `logs\egress_deny.jsonl`. The label comes from `logs\egress_label.txt`, which the operator sets before each run (`Set-Content logs\egress_label.txt <label>`).

```powershell
Remove-Item "$root\logs\egress_deny.jsonl" -ErrorAction SilentlyContinue
Start-Process $py -ArgumentList egress_deny_proxy.py -WorkingDirectory $root -WindowStyle Hidden
```

Environment for CLIs:

```powershell
$env:HTTPS_PROXY='http://127.0.0.1:18090'; $env:HTTP_PROXY='http://127.0.0.1:18090'; $env:ALL_PROXY='http://127.0.0.1:18090'
$env:NO_PROXY='127.0.0.1,localhost,::1'; $env:NODE_USE_ENV_PROXY='1'    # the last one makes Node-based tools honour the variables
```

For VS Code (scenarios i0, i1, i3, j8): the same variables in the scenario `env`, plus `args` `--proxy-server=http://127.0.0.1:18090` and `--proxy-bypass-list=127.0.0.1;localhost;<-loopback>`, plus `settings` `http.proxy` `http://127.0.0.1:18090` and `http.proxySupport` `override`. Remove the variables from the console afterwards (`Remove-Item Env:HTTPS_PROXY` and so on) so later runs are not affected.

Pass criteria for a denied run: the tool completes a prompt (gateway shows a valid request and the reply is visible); the watcher shows no public endpoint (nothing bypassed the proxy). Capture: the distinct hosts and counts in `egress_deny.jsonl` for the label:

```powershell
Get-Content "$root\logs\egress_deny.jsonl" | ForEach-Object { $_ | ConvertFrom-Json } |
  Where-Object { $_.label -eq '<label>' } | Group-Object host | ForEach-Object { "{0}  x{1}" -f $_.Name,$_.Count }
```

**10.3 Chromium net-log (VS Code only)**

Add `args` `--log-net-log={base}\netlog.json` to the scenario. After the run:

```powershell
& $py parse_netlog.py        # prints the hostnames of "url" events per scenario (edit the scenario list inside the script)
```

The net-log covers Chromium traffic (renderer, webviews, network service). It does not cover Node-based extension-host requests or child processes such as `claude.exe` and `codex.exe`; those appear in the watcher and the deny-proxy log.

**10.4 The three run modes and per-harness commands**

| Mode | Definition |
|---|---|
| default | As shipped: only the settings needed to point at the gateway |
| quiet | Default plus the switches below |
| denied | Default or quiet, with all traffic forced through the deny-all proxy |

Run each harness in default mode first. Quiet-mode switches used:

| Harness | Quiet switches |
|---|---|
| Claude Code CLI and extension | In `settings.json` `env`: `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, `DISABLE_TELEMETRY=1`, `DISABLE_ERROR_REPORTING=1`, `DISABLE_AUTOUPDATER=1` (CLI runs: `--settings '{"env":{...}}'`) |
| Codex CLI and extension | At the top of `config.toml`, before any table: `features = { plugins = false, remote_plugin = false, plugin_sharing = false, apps = false, in_app_updates = false }` and `analytics = { enabled = false }` (CLI runs: `--top-lines ...`) |
| Copilot CLI | `COPILOT_OFFLINE=true` |
| VS Code | Settings `extensions.autoCheckUpdates` false, `extensions.autoUpdate` false, `workbench.enableExperiments` false, `update.showReleaseNotes` false (telemetry level `off` and `update.mode` `none` are already in the defaults) |

CLI commands (gateway and fake `az` running; for the Copilot CLI use the environment of section 9):

```powershell
& $py egress_watch.py --label claude-cli-default --secs 150 --run -- $py run_claude.py e1-default --prompt "Reply with the single word: ok"
& $py egress_watch.py --label claude-cli-quiet   --secs 150 --run -- $py run_claude.py e2-quiet --prompt "Reply with the single word: ok" --settings '{"env":{"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC":"1","DISABLE_TELEMETRY":"1","DISABLE_ERROR_REPORTING":"1","DISABLE_AUTOUPDATER":"1"}}'
& $py egress_watch.py --label codex-cli-default  --secs 150 --run -- $py run_codex.py e3-default --prompt "Reply with the single word: ok"
& $py egress_watch.py --label codex-cli-quiet    --secs 150 --run -- $py run_codex.py e4-quiet --prompt "Reply with the single word: ok" --top-lines 'features = { plugins = false, remote_plugin = false, plugin_sharing = false, apps = false, in_app_updates = false }' 'analytics = { enabled = false }'
& $py egress_watch.py --label copilot-cli-offline          --secs 60 --run -- $cp --model apim/gpt-test -p "Reply with the single word: ok"   # with COPILOT_OFFLINE=true
& $py egress_watch.py --label copilot-cli-online-byok      --secs 60 --run -- $cp --model apim/gpt-test -p "Reply with the single word: ok"   # without it
& $py egress_watch.py --label copilot-cli-fusion-signed-out --secs 60 --run -- $cp --experimental --model hydrafusion -p "Reply with the single word: ok"
```

Denied CLI runs: set the proxy variables of section 10.2 and `Set-Content logs\egress_label.txt <label>` before each of `run_claude.py p1`, `run_codex.py p2` and the Copilot CLI command; read `egress_deny.jsonl` afterwards.

VS Code runs use one extension per profile and the same step lists as sections 8.5 and 8.6:

| Scenario | extDir | env | Mode |
|---|---|---|---|
| h0-vscode-bare | `vscode-ext-none` | `CODEX_HOME` set to an empty folder | default, 45 s wait only, `probe` false |
| h1-claude-ext-base | `vscode-ext-claude` | `CLAUDE_CONFIG_DIR=work\claude-vsext` | default |
| h2-claude-ext-quiet | `vscode-ext-claude` | `CLAUDE_CONFIG_DIR=work\claude-vsext-quiet` (settings with the four switches) | quiet |
| h3-codex-ext-base | `vscode-ext-codex` | `CODEX_HOME=work\codex-vsext` | default |
| h4-codex-ext-quiet | `vscode-ext-codex` | `CODEX_HOME=work\codex-vsext-quiet` (config with the flags) | quiet |
| i0, i1, i3 | none, claude, codex | as h0, h1, h3 plus proxy variables | denied |
| j8-vscode-copilot-byok-denied | `vscode-ext-none`, `keepProfile` | proxy variables | denied, BYOK chat from section 8.7 |

Each scenario is run in the background and watched from a second command:

```powershell
$job = Start-Process -FilePath node -ArgumentList @('drive.js','cfg_h1-claude-ext-base.json') -PassThru -WindowStyle Hidden -RedirectStandardOutput "$root\work\h1-claude-ext-base.out.txt"
& $py "$root\egress_watch.py" --label vscode-h1-claude-ext-base --secs 85 --match h1-claude-ext-base --name Code.exe
$job | Wait-Process -Timeout 60 -ErrorAction SilentlyContinue
if (-not $job.HasExited) { Stop-Process -Id $job.Id -Force }
```

Watch durations used: 70 s for the bare run, 85 s for Claude extension runs, 105 s for Codex extension runs.

**10.5 Naming addresses.** The watcher records addresses; names come from (a) the deny-proxy log, (b) the net-log, (c) the DNS cache and reverse lookups, and (d) resolving candidate hostnames and matching addresses:

```powershell
$names = 'api.anthropic.com','console.anthropic.com','claude.ai','chatgpt.com','ab.chatgpt.com','api.openai.com','github.com','api.github.com','api.githubcopilot.com','telemetry.individual.githubcopilot.com','marketplace.visualstudio.com','update.code.visualstudio.com'
$map=@{}; foreach ($n in $names) { try { (Resolve-DnsName $n -Type A -ErrorAction Stop | Where-Object IPAddress).IPAddress | ForEach-Object { $map[$_] += @($n) } } catch {} }
```

Matches by method (d) are inferences from current DNS answers; treat them as such.

**10.6 JetBrains (PyCharm).** Two watcher runs on the PyCharm process tree, described in section 13.9: idle at the welcome screen (40 s) and while chatting with the provider configured (60 s). Pass criterion: no public endpoint in `logs\egress\<label>.json` (an empty list); note the process names in the summary line.

**10.7 Sampling limits.** A connection that opens and closes between two 0.4 s samples is missed by the watcher. Content of connections is not inspected. The deny proxy sees only tools that honour the proxy settings; the watcher is the check for tools that do not.

## 11. Token-at-rest scan

**Purpose.** Check that the isolated configuration folders do not contain the JWTs the tools handled.

**Procedure.** After all CLI runs, search every file under `work\claude` and `work\codex` for the mock-token prefix (the base64 of the JWT header, `eyJhbGciOiJSUzI1NiI`):

```powershell
$sig = 'eyJhbGciOiJSUzI1NiI'
foreach ($tool in 'claude','codex') {
  $dir = "$root\work\$tool"; $files = Get-ChildItem $dir -Recurse -File -ErrorAction SilentlyContinue; $hits = @()
  foreach ($f in $files) { try { if ((Get-Content -LiteralPath $f.FullName -Raw -ErrorAction Stop) -match [regex]::Escape($sig)) { $hits += $f.FullName } } catch {} }
  "{0}: scanned {1} files in {2} scenario folders; files containing a token: {3}" -f $tool,$files.Count,(Get-ChildItem $dir -Directory).Count,$hits.Count
}
Select-String -Path "$root\logs\requests.jsonl" -Pattern $sig -SimpleMatch -Quiet    # the gateway log must not hold raw tokens
```

Recorded counts: Claude 109 files in 20 scenario folders; Codex 21,909 files in 19 scenario folders (including SQLite state, logs and write-ahead files). Pass criterion: 0 files contain the prefix and the gateway log search returns False.

**Limits.** Mock tokens, short sessions, no debug logging. VS Code extension profiles and Copilot CLI home were not part of this scan.

## 12. Real Azure CLI checks and the device-code attempt

**12.1 Install (no administrator rights).**

```powershell
curl.exe -sSL -o "$root\azcli.zip" https://aka.ms/installazurecliwindowszipx64      # about 87 MB
Expand-Archive -Path "$root\azcli.zip" -DestinationPath "$root\azcli" -Force
New-Item -ItemType Directory -Force "$root\realaz" | Out-Null
Set-Content -Path "$root\realaz\az.cmd" -Encoding ascii -Value "@echo off`r`nset AZURE_CONFIG_DIR=$root\work\azconfig`r`ncall `"$root\azcli\bin\az.cmd`" %*"
$env:PATH = "$root\realaz;" + $env:PATH
az version
```

Pitfall: the `azure-cli` package installed with `uv pip install` failed at start-up with `AttributeError: module 'time' has no attribute 'clock'`; use the ZIP.

**12.2 No-login behaviour.**

```powershell
$t0 = Get-Date; az account get-access-token --scope "api://apim-test/.default" --query accessToken -o tsv; "exit=$LASTEXITCODE secs=$([math]::Round(((Get-Date)-$t0).TotalSeconds,1))"
powershell -NoProfile -File "$root\get-apim-token.ps1"; "helper exit=$LASTEXITCODE"
az account get-access-token --help | Select-String '--scope|--resource|--tenant'
```

Capture: exit code, time, stderr text, whether `--scope` is listed. The recorded run used the version in section 2.1.

**12.3 Real token check script.** After `az login` with the tester's own account, run `powershell -NoProfile -File $root\real_az_check.ps1 -Scope 'api://<apim-app-id>/.default' -Aud 'api://<apim-app-id>'`. It prints az latency, `aud` and whether it matches, `iss`, remaining lifetime, user, scopes and roles. Pass criterion: `aud` MATCH and a lifetime of more than 60 s. The script was tested against the fake `az` and against the real `az` while not logged in; it was not recorded as run against a real token (the real-token runs of section 14 used the commands in 14.3 and 14.4).

**12.4 Device-code login attempt.** Command used, in the isolated configuration folder, with output redirected to files:

```powershell
Start-Process -FilePath "$root\realaz\az.cmd" -ArgumentList @('login','--use-device-code','--allow-no-subscriptions') -PassThru -RedirectStandardOutput "$root\work\azlogin_out.txt" -RedirectStandardError "$root\work\azlogin_err.txt" -WindowStyle Hidden
```

The command prints a page address and a one-time code to stderr; the tester opens the page in a browser and enters the code. The tester, not the automation, enters credentials. Status of the first attempt: incomplete. The code was displayed but the sign-in was not finished before it expired; the process ended with `AADSTS70016` (authorization pending) and no account was added (`az account list` returned `[]`). A second attempt with a new code was completed by the owner; see section 14.2. The output files were reused by the second attempt.

## 13. JetBrains (PyCharm) procedure

**Purpose.** Configure the JetBrains AI Assistant OpenAI-compatible provider to use the local token proxy, assign a model, chat, and read from the gateway log which paths and authorization header the plugin uses.

**Status.** Completed on PyCharm 2026.2.3 with the AI Assistant plugin: the provider was configured through the settings UI, a model was assigned, the chat was answered by the mock gateway, the requests were read from the gateway log, and egress was watched. An earlier attempt had stopped before the Settings window could be opened because keyboard and mouse input could not be delivered safely (section 13.6); the owner cleared the cause and the procedure was completed. Click positions in 13.7 are read from the saved window captures (see the limitations in section 18).

**13.1 Download and verify**

```powershell
winget show JetBrains.PyCharm        # gives Installer Url: https://download.jetbrains.com/python/pycharm-2026.2.3.exe
curl.exe -sIL https://download.jetbrains.com/python/pycharm-2026.2.3.exe | Select-String 'HTTP|Content-Length'   # 962363888 bytes
curl.exe -sSL -o "$root\jetbrains\pycharm-2026.2.3.exe" https://download.jetbrains.com/python/pycharm-2026.2.3.exe
Get-AuthenticodeSignature "$root\jetbrains\pycharm-2026.2.3.exe" | Select-Object Status, @{n='Signer';e={$_.SignerCertificate.Subject}}   # Valid, JetBrains s.r.o.
```

Check the installer's requested execution level before running it (to avoid an elevation prompt): read the first 4 MB and look for `requestedExecutionLevel`; the recorded value was `asInvoker`.

**13.2 Silent per-user install**

```powershell
$p = Start-Process "$root\jetbrains\pycharm-2026.2.3.exe" -ArgumentList @('/S', "/D=$root\jetbrains\pycharm") -PassThru
$p | Wait-Process -Timeout 420        # about 209 s, exit code 0
```

**13.3 Isolated configuration and plugin.** Create `$root\jetbrains\cfg\idea.properties` with four lines (`idea.config.path`, `idea.system.path`, `idea.plugins.path`, `idea.log.path`) pointing at `$root\jetbrains\cfg\config`, `system`, `plugins` and `log`, using forward slashes. Then:

```powershell
$env:PYCHARM_PROPERTIES = "$root\jetbrains\cfg\idea.properties"
& "$root\jetbrains\pycharm\bin\pycharm64.exe" installPlugins com.intellij.ml.llm      # about 12 s; "installed plugin: JetBrains AI Assistant"
```

**13.4 Supporting services.** Start the mock gateway (section 3.2; it must include the Chat Completions route) and the token proxy (section 7.1), with `$env:PATH = "$root\fakeaz;" + $env:PATH` and `h.az_mode('ok',120)`. Check `curl.exe -s http://127.0.0.1:18081/_proxy/health`.

**13.5 Launch and first-launch dialogs**

```powershell
$env:PYCHARM_PROPERTIES = "$root\jetbrains\cfg\idea.properties"
$p = Start-Process "$root\jetbrains\pycharm\bin\pycharm64.exe" -PassThru
Start-Sleep 30        # then: . "$root\jetbrains\jb_ui.ps1"; Get-JbWindows
```

On the first start of a fresh configuration:

1. **JetBrains User Agreement** (window 600 by 460). Tick the confirmation checkbox at (50, 384), then Continue at (538, 423). Accept only with the explicit approval of the person who owns the machine; the test instance is a throwaway profile but the agreement is still a legal acceptance. The run was made only after that approval was given.
2. **Data Sharing** (window 600 by 460). Click Don't Send at (315, 423).
3. The welcome screen opens as a project named `WelcomeScreen`; PyCharm creates `%USERPROFILE%\PycharmProjects\WelcomeScreen` (containing `.idea`) at this point.
4. A "Meet the Islands Theme" popup may appear as a separate window (384 by 480). Click Skip at (190, 440) to dismiss it before continuing (whether it blocks other clicks was not established).

On later launches with the same configuration the dialogs do not appear (the configuration folder remembers them). The welcome screen window is 1400 by 1000 and titled `WelcomeScreen – Welcome to PyCharm`.

**13.6 UI helper and the focus guard (`jetbrains\jb_ui.ps1`)**

Dot-source the script, then use:

| Function | Action |
|---|---|
| `Get-JbWindows` | Lists visible windows of the test PyCharm (process path under `jetbrains\pycharm`), with handle, process id, title, position and size. Popups, dialogs and dropdown lists are separate windows and appear here |
| `Save-JbShot $w <name>` | Saves a window image with `PrintWindow` to `jetbrains\<name>.png`; works without focus and gives window-relative coordinates |
| `Click-Jb $w x y` | Real mouse click at window-relative coordinates (`SetCursorPos`, `mouse_event`) |
| `Type-Jb $w text`, `Key-Jb $w keys` | `SendKeys` input (for example `Key-Jb $w '^%s'` is Ctrl+Alt+S, `'{ENTER}'` is Enter) |
| `Assert-JbForeground $w` | Called first by every input function |

Design of the guard. `Assert-JbForeground` finds the current foreground window, attaches the script's input thread to the foreground thread (`AttachThreadInput`), restores and raises the target window (`ShowWindow`, `BringWindowToTop`, `SetForegroundWindow`), detaches, waits 500 ms, and checks the process id of the new foreground window. If it is not the test PyCharm it throws `foreground window is not the test PyCharm (pid N); refusing to send input`, and no input is sent. This prevents keystrokes or clicks from reaching any other application.

What the guard did in the run. The target window could not be brought to the foreground because another application's window was in front. On repeated checks (an input attempt, a retry after adding the `AttachThreadInput` step, and a status check after relaunching PyCharm) the foreground process was `PickerHost`, titled "Windows Security", a prompt that appeared to belong to the machine owner's own sign-in. The guard refused to send input each time, and the procedure waited until the owner cleared the prompt. At one later status check the foreground window belonged to the application hosting the console. After the prompt was cleared the target window could be brought forward and the procedure continued. The helper never overrides the check, and an operator should not close or answer such a prompt on the owner's behalf.

Input findings.

- Posted mouse messages (`PostMessage` with `WM_LBUTTONDOWN` and `WM_LBUTTONUP`) are ignored by PyCharm. Clicks need `mouse_event` with the window in the foreground.
- Posted character messages (`PostMessage` with `WM_CHAR` = 0x0102, one per character, about 25 ms apart) addressed to the Settings window handle are redirected by the IDE into the Settings search field whichever field has focus. They are usable only for the search box. The URL, API key and other form fields need real keystrokes (`SendKeys`) with the window in the foreground.
- Typing quickly into the Settings search box dropped characters (captures `k4`, `k5`, `k15` to `k19` show the field holding partial text). Type slowly, or wait and confirm the field content from a capture before continuing; clear the field (select all, delete) before retyping.

**13.7 Configure the provider (Settings window 900 by 700; positions window-relative)**

Positions below were read from the saved captures. The right-hand pane scrolls, so the same control sits at different heights in different captures; the captures named in the table show each layout.

| Step | Window and capture | Action |
|---|---|---|
| 1 | Main window (1400 by 1000), welcome screen | Press Ctrl+Alt+S (`Key-Jb $w '^%s'`). A window titled `Settings – WelcomeScreen` opens (capture `k3_0`) |
| 2 | Settings, `k6` | Click the search field at (150, 63) and type `AI Assistant` (slowly; see input findings) |
| 3 | Settings, `k7` | In the left tree click `Tools > AI Assistant > Providers & API keys` at (131, 474). The right pane shows JetBrains AI, Agent Authorization, Third-party AI providers (Beta) and AI Completion. Do not click Activate JetBrains AI |
| 4 | Settings, `k7` | Click the Provider dropdown (currently `None`) at (547, 486). A separate popup window (279 by 208) lists: None, Gemini API key, Google Vertex AI, Anthropic, OpenAI-compatible, OpenAI, LM Studio, Ollama |
| 5 | Popup, `k8_0` | Click OpenAI-compatible at about (100, 117) in the popup (entries are about 24 pixels apart, None at y 20) |
| 6 | Dialog (440 by 255), `k12_0` | A confirmation titled "Data Sharing with Third-Party AI Service Providers" (data may be sent to the hosts in the provider settings) opens. It blocks the Settings window until dismissed. Press Enter (the OK button is at about (286, 219); Cancel at (365, 219)). It can appear more than once, so after each action run `Get-JbWindows` and dismiss any new small window the same way. Dismissing it with OK was the run's choice |
| 7 | Settings, `k20`, `k23_0` | The provider form shows URL, API Key and HTTP version. In the layout of `k23_0`: click the URL field at (576, 473) and type the URL; click the API Key field at (590, 513) and type a dummy value (for example `dummy-local-key`); click the HTTP/1.1 radio button at (547, 548) (the default is HTTP/2; the local proxy speaks plain HTTP/1.1) |
| 8 | Settings, `k23_0` | Scroll the right pane (mouse wheel over the pane, or drag its scroll bar) until Test Connection is visible; the exact scroll gesture was not recorded. Click Test Connection at (519, 583) |
| 9 | Settings, `k23_0` | Read the result next to the button: "Connected". The Tool calling checkbox (at (461, 617), ticked by default) was left ticked |
| 10 | Settings, `k30` | Scroll to Model Assignment (Beta). In the layout of `k30`: click the Core features dropdown at (599, 520). A popup window (279 by 88) lists `OpenAIAPI/gpt-test`, `OpenAIAPI/gpt-test-2` and `Not selected` (`k29_0`); click `OpenAIAPI/gpt-test` at about (100, 20) in the popup |
| 11 | Settings, `k30` | Click the Instant helpers dropdown at (599, 581) and choose `OpenAIAPI/gpt-test` the same way |
| 12 | Settings, `k30` | Click OK at (673, 667). (Apply is at (841, 667) and Cancel at (757, 667)) |

URL values used. Run 1 with `http://127.0.0.1:18081/openai` (no `/v1`): Test Connection requested `GET /openai/models` twice. Run 2 with `http://127.0.0.1:18081/openai/v1`: Test Connection requested `GET /openai/v1/models`. The URL typed in the field is not rewritten by the plugin, so choose the form your gateway needs. Each run starts from the default state: if the URL field already holds text, select all and delete before typing.

**13.8 Chat and gateway log**

1. Optional check before step 10 (no model assigned yet): after Test Connection shows Connected, close Settings with OK, open the chat as in step 2 below, and send a prompt. The chat answers "No compatible model is available for Chat mode" and the gateway log gets no chat request. Then reopen Settings and continue from step 10. (The run recorded this outcome but not the exact order of the clicks used to reach it.)
2. After step 12, in the main window (1400 by 1000, capture `k25_0`) click the AI Assistant chat icon in the right-hand tool-window strip at about (1372, 101). The panel opens with a "Chat History" header, "New Chat", an input box at about (1125, 840), a mode and model selector at the bottom showing `Chat` and `gpt-test`, and a send icon at about (1303, 908). A promotional card ("Introducing Air in JetBrains IDEs") may sit above the input; it can be closed with its X at about (1323, 731).
3. Click the input box, type `Reply with the single word: ok` and send it (Enter or the send icon; which one the run used was not recorded).
4. Wait about 20 s and take a capture (`k31`). Record the gateway lines created during the run (count the log lines before starting, then read the new ones, as in section 8.4).

Pass criteria.

- Test Connection shows Connected, and the gateway shows `GET <url>/models` (twice) with `auth.result` `ok`, `authorization_scheme` `Bearer`, `x_api_key_present` false, user agent beginning `ktor-client`.
- With no model assigned: no chat requests and the message above.
- With the model assigned: the chat panel shows `MOCK-OK model=gpt-test seq=<n>`, and the gateway shows `POST /openai/v1/chat/completions` requests (`body.stream` true) with `auth.result` `ok` and a valid JWT, with no `x-api-key`. Record the count and `body.n_tools` of each.

Recorded in the run: 12 chat-completions requests for one prompt, one carrying 35 tool definitions and eleven carrying none. The whole gateway log, over all PyCharm runs (user agent `ktor-client`), contained `GET /openai/models` 18 times, `GET /openai/v1/models` 7 times, and `POST /openai/v1/chat/completions` 22 times (2 with 35 tools, 20 with none). The read-out command:

```powershell
Get-Content "$root\logs\requests.jsonl" | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.headers.'user-agent' -like 'ktor*' } |
  Group-Object { "{0} {1} status={2} tools={3}" -f $_.method,$_.path,$_.status,$_.body.n_tools } | ForEach-Object { "{0}  x{1}" -f $_.Name,$_.Count }
```

**13.9 Egress runs**

```powershell
& $py egress_watch.py --label pycharm-idle --secs 40 --pid <pycharm64 pid>     # welcome screen, provider not yet used
& $py egress_watch.py --label pycharm-chat --secs 60 --pid <pycharm64 pid>     # while chatting with the provider configured
```

The second command is given in the form of the first; its exact invocation was not recorded. Pass criterion for both: no public endpoint (`logs\egress\<label>.json` is an empty list). Capture the process names in the summary line; the chat run listed a local child process, `embeddings-server.exe`. Idle at the welcome screen the tree held `pycharm64.exe`, `fsnotifier.exe` and `conhost.exe`.

**13.10 Static inspection.** List classes and strings in the plugin jars under `jetbrains\cfg\plugins\ml-llm\lib` with `System.IO.Compression.ZipFile`, looking for classes under `com/intellij/ml/llm/core/providers/byok/` and strings such as `Authorization`, `Bearer `, `v1/chat/completions`, `v1/responses`, `v1/models`. This shows what the code contains, not what it sends at run time; the run time behaviour is the gateway log of 13.8.

**13.11 Pitfalls**

- The provider confirmation dialog blocks the Settings window and may reappear; check for new small windows after each action.
- Typed characters can be dropped in the Settings search box; verify from a capture.
- Window messages cannot be used for form fields (13.6).
- Models from an OpenAI-compatible endpoint are not assigned to features automatically; chat does not work until Model Assignment is set.
- The foreground guard refuses input while any other application holds the foreground; ask the owner to clear their prompt rather than forcing focus.
- The IDE writes `%USERPROFILE%\PycharmProjects\WelcomeScreen` outside the isolated configuration.

## 14. Real Entra token runs (real Azure CLI, lenient mock gateway)

**Purpose.** Show that the tools and the helper handle a real Entra access token (size, claims, latency) and that each tool still works when the helper obtains its token from the real Azure CLI.

**Status.** Completed for the sign-in, the token inspection, the helper tests and every tool listed in 14.7. This is not an APIM test: the mock did not verify the token (14.5 and 14.9).

**14.1 Rules and preconditions**

- The owner set a read-only rule: nothing in the tenant may be changed. Only `az login` and `az account get-access-token` were used. No app registration or other resource was created.
- The owner completed the sign-in in a browser. The automation never enters credentials.
- Tokens are never printed to a console log, a document or a result file. Claims are reported by name only, and no value of a tenant, user, object or account identifier is recorded anywhere in this document.
- Preconditions: the portable Azure CLI and its wrapper `realaz\az.cmd` (section 12.1), which sets `AZURE_CONFIG_DIR=$root\work\azconfig`, so the sign-in lives only in the isolated folder.

**14.2 Sign-in (device code)**

```powershell
Start-Process -FilePath "$root\realaz\az.cmd" -ArgumentList @('login','--use-device-code','--allow-no-subscriptions') -PassThru -RedirectStandardOutput "$root\work\azlogin_out.txt" -RedirectStandardError "$root\work\azlogin_err.txt" -WindowStyle Hidden
```

The command prints a page address and a one-time code to stderr. The owner opens the page, enters the code and signs in. The first attempt's code expired before the sign-in finished (`AADSTS70016`, authorization pending; section 12.4). A second attempt with a new code succeeded. `--allow-no-subscriptions` lets the login complete for an account without Azure subscriptions. Check that it worked without printing identifiers: `az account show` returns without an error (do not print its output into a record). The output files are reused by each attempt, so after the second attempt they no longer hold the first attempt's text.

**14.3 Token inspection (sanitized)**

The scope is Azure Resource Manager (`https://management.azure.com/.default`), chosen because it needs no app registration, and none was created for this work. Procedure (reconstructed; the exact inline command was not recorded):

```powershell
$env:PATH = "$root\realaz;" + $env:PATH
$sw = [Diagnostics.Stopwatch]::StartNew()
$t = az account get-access-token --scope https://management.azure.com/.default --query accessToken -o tsv
$secs = [math]::Round($sw.Elapsed.TotalSeconds, 2)
$p = $t.Split('.')[1].Replace('-','+').Replace('_','/'); while ($p.Length % 4) { $p += '=' }
$c = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($p)) | ConvertFrom-Json
"secs=$secs chars=$($t.Length) ver=$($c.ver) aud=$($c.aud) lifetime=$($c.exp - $c.iat)"
"claim names: " + (($c.PSObject.Properties.Name | Sort-Object) -join ', ')
Remove-Variable t, p, c
```

Run twice. Print only the line above and the claim names; never print `tid`, `upn`, `oid` or any other claim value.

Recorded observations:

| Item | Observation |
|---|---|
| Time to obtain a token | 1.23 s and 0.92 s |
| Token length | 2435 characters |
| Signature algorithm | RS256 |
| Version | v1 token (issuer begins `https://sts.windows.net/<tenant>/`) |
| `aud` | `https://management.azure.com` (no trailing slash) |
| Lifetime (`exp` minus `iat`) | about 4848 s |
| `azp` and `appid` | the Azure CLI's public client id |
| Claims present (names only) | `amr`, `groups`, `oid`, `scp`, `tid`, `upn` |

**14.4 The helper with the real Azure CLI**

`get-apim-token-real.ps1` is a copy of the hardened helper (section 4.1) with `$Scope = 'https://management.azure.com/.default'` and `$ExpectedAud = 'https://management.azure.com'`. It was made before the helper's audience check became a list (below), so it still compares against a single string.

```powershell
$env:PATH = "$root\realaz;" + $env:PATH
$sw = [Diagnostics.Stopwatch]::StartNew()
$t = powershell -NoProfile -File "$root\get-apim-token-real.ps1"      # Windows PowerShell 5.1
"rc=$LASTEXITCODE secs=$([math]::Round($sw.Elapsed.TotalSeconds,2)) chars=$($t.Length)"
```

Pass criteria: rc 0; one line of output that is the JWT only (2435 characters); about 1.1 to 1.3 s. Recorded: rc 0 and 1.1 to 1.3 s. Negative test: edit `$ExpectedAud` in a temporary copy to a value that is not the token's audience (the value used was not recorded) and run it; expected: rc 1 and the one-line message `get-apim-token: token aud is '<aud>', expected '<value>'`. Recorded: rc 1 with that message.

Audience list. The current `get-apim-token.ps1` accepts a list: `$ExpectedAud = @('api://<apim-app-id>', '<apim-app-client-id>')`, checked with `-notcontains`, because a v1 token and a v2 token for the same API can carry different `aud` values (the Application ID URI or the client id GUID). The real copy above predates this change.

**14.5 Lenient gateway and token proxy**

Real Entra tokens are signed with Microsoft keys, so the mock cannot verify them. The gateway has a `lenient` mode: `POST /_ctl {"lenient": true}` (from Python `h.ctl(lenient=True)`) makes it accept any well-formed, unexpired JWT without verifying the signature, audience or issuer. It logs, under `auth.claims`: `jti` (the token's `uti` claim, or the last 12 characters of the token if that claim is missing; in the recorded runs it was always the 22-character `uti`), `iat`, `exp`, `ttl_remaining`, `aud`, `ver`, `real_token` true and `token_chars`. A token that is expired or not a JWT is refused (`auth.result` `expired` or `invalid:lenient`). Turn it off again with `h.ctl(lenient=False)`.

Restart the services so that nothing from mock runs is left, with the real wrapper first on `PATH`:

```powershell
$env:PATH = "$root\realaz;" + $env:PATH
Start-Process $py -ArgumentList gateway.py -WorkingDirectory $root -WindowStyle Hidden
Start-Sleep 2
curl.exe -s -X POST http://127.0.0.1:18080/_ctl -d '{"lenient": true}'
Start-Process $py -ArgumentList @('proxy.py','--upstream','http://127.0.0.1:18080','--port','18081','--margin-s','300','--','powershell','-NoProfile','-File',"$root\get-apim-token-real.ps1") -WorkingDirectory $root -WindowStyle Hidden
curl.exe -s http://127.0.0.1:18081/_proxy/health
```

The proxy refreshes when fewer than 300 s remain (the mock runs used 5).

**14.6 Pointing the runners at the real helper**

`harness.py` reads two environment variables: `HARNESS_HELPER` (the helper script that `run_claude.py` and `run_codex.py` write into the tool configuration; default `get-apim-token.ps1`) and `HARNESS_AZ_DIR` (the folder holding the `az.cmd` that is put first on `PATH`; default `fakeaz`).

```powershell
$env:HARNESS_HELPER = "$root\get-apim-token-real.ps1"
$env:HARNESS_AZ_DIR = "$root\realaz"
```

Remove both variables afterwards (`Remove-Item Env:HARNESS_HELPER, Env:HARNESS_AZ_DIR`).

**14.7 Each tool with the real token as source**

| Tool | Procedure |
|---|---|
| Claude Code CLI | `python run_claude.py real1-claude` (section 5.1, helper from `HARNESS_HELPER`) |
| Codex CLI | `python run_codex.py real2-codex` (section 6.1, `timeout_ms` 15000); then `python run_codex.py real3-codex-default-timeout` with the default `timeout_ms` of 5000 (the exact arguments of this second run were not recorded; use `--auth '{"timeout_ms": 5000}'`). The 5000 ms limit was run because the real `az` takes about 1.2 s |
| Copilot CLI, offline BYOK | The commands of section 9 with `COPILOT_OFFLINE=true`, `COPILOT_PROVIDERS_CONFIG` pointing at the `providers.json` of section 9 (URL of the token proxy, dummy key), and the proxy of 14.5 |
| VS Code Copilot Chat, BYOK | Scenario `cfg_n1.json`: the profile `j4-byok-ui-added` kept (`keepProfile`; the key added through the UI as in section 8.7 B and C), `extDir` `vscode-ext-none`, `pathPrepend` `$root\realaz`; steps: `click_xy` (1250, 782), `type` the prompt, `press` Enter, `wait` 25000, `text`. The model URL points at the token proxy |
| Claude Code VS Code extension | Scenario `cfg_n2-claude-ext-real.json` (steps of section 8.5, plus a final `webview_text`): `CLAUDE_CONFIG_DIR` `$root\work\claude-vsext-real`, whose `settings.json` has `apiKeyHelper` = `powershell -NoProfile -File <root>\get-apim-token-real.ps1`, `env.ANTHROPIC_BASE_URL` `http://127.0.0.1:18080/anthropic` and `CLAUDE_CODE_API_KEY_HELPER_TTL_MS` 300000; `pathPrepend` `$root\realaz` |
| Codex VS Code extension | `CODEX_HOME` `$root\work\codex-vsext-real` with a `config.toml` as in section 6.1 whose auth command is the real helper (`timeout_ms` 15000, `base_url` `http://127.0.0.1:18080/openai/v1`); scenario `cfg_n3-codex-ext-real.json` (section 8.6, 36 s wait before typing). First attempt: the extension's own 30 s `renderer_ready_timeout` expired before the panel finished loading, although its backend had already received `GET /models` with status 200. Rerun with `cfg_n4.json`, identical except a 70 s wait before typing: the prompt was sent and answered |
| JetBrains AI Assistant | The provider and model assignment of section 13.7 (profile kept), the proxy of 14.5 with the real helper, and the chat of section 13.8 |

Before each run count the gateway log lines so the new lines can be read afterwards (section 8.4). Egress was not audited in these runs.

**14.8 Pass criteria**

For each tool: the gateway log shows requests from the tool's own user agent with `auth.claims.real_token` true, `auth.result` `ok` and status 200, and the reply (`MOCK-OK model=...`) is visible in the tool. Read-out:

```powershell
$rows = Get-Content "$root\logs\requests.jsonl" | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.auth.claims.real_token }
$rows | Group-Object { "{0} | {1} {2} status={3} chars={4} ver={5}" -f ($_.headers.'user-agent' -replace '\s\(.*',''),$_.method,$_.path,$_.status,$_.auth.claims.token_chars,$_.auth.claims.ver } |
  ForEach-Object { "{0}  x{1}" -f $_.Name,$_.Count }
($rows | ForEach-Object { $_.auth.claims.aud } | Select-Object -Unique) -join ', '
```

Recorded in the gateway log (32 requests between 19:28 and 19:37 local time, all status 200, token length 2435, version 1.0, one `aud` value `https://management.azure.com`):

| Tool (user agent) | Requests with the real token |
|---|---|
| Claude Code CLI (`claude-cli/2.1.311`) | `POST /anthropic/v1/messages` x2 |
| Claude Code extension (`claude-cli/2.1.312`) | `POST /anthropic/v1/messages` x2 |
| Codex CLI (`codex_exec/0.153.2`) | `GET /openai/v1/models` x4, `POST /openai/v1/responses` x2 (two runs) |
| Codex extension (`codex_vscode/0.164.0-alpha.11.1`) | `GET /openai/v1/models` x8, `POST /openai/v1/responses` x2 (both attempts together) |
| Copilot CLI (`OpenAI/JS 5.20.1`) | `POST /openai/v1/responses` x1 |
| VS Code Copilot Chat (`GitHubCopilotChat/0.70.0`) | `POST /openai/v1/responses` x1 |
| JetBrains AI Assistant (`ktor-client`) | `GET /openai/v1/models` x6, `POST /openai/v1/chat/completions` x4 (three without tools, one with 35 tools) |

The reply appeared in each tool.

**14.9 Limits of this procedure**

- Lenient mode checks only that the token is a well-formed, unexpired JWT. Signature, audience and issuer were not verified, so these runs show that the tools and the helper handle a real token (size, claims, latency, sign-in), not that an APIM `validate-jwt` policy would accept it.
- A token for a custom API audience (an Application ID URI or a client id GUID) was not obtained: that needs an app registration, which the read-only rule excluded.
- The token was a v1 token for a Microsoft resource issued to the Azure CLI's client; a token issued for your API may differ in version, `aud`, claims and size.
- The sign-in persists in `work\azconfig` (token cache and profile). Treat that folder and `logs\requests.jsonl` as sensitive: do not publish them. Sign out when finished with `realaz\az.cmd logout` and delete `work\azconfig` (this cleanup was not recorded as done).
- Refresh over the token lifetime (about 4848 s) was not observed; each run lasted seconds to about a minute.

## 15. Azure MCP Server tests

**Purpose.** Establish what the Azure MCP Server (a local MCP server that exposes Azure operations as tools) declares, which hosts it contacts, and whether each harness can register it and call one of its tools, using read-only operations only and no real Azure credential.

**Status.** Completed up to the point where a real Azure credential is needed. The owner's rule was read-only, no tenant changes, and the owner declined another sign-in, so no real-credential tool result was obtained: the only tool call made returns Azure's 401 for missing credentials. Per harness: Claude Code CLI, Codex CLI and Copilot CLI were exercised end to end; VS Code ran a tool through Copilot Chat; JetBrains ran a tool through AI Assistant chat.

**15.1 Install and inspect**

```powershell
New-Item -ItemType Directory -Force "$root\azure-mcp" | Out-Null
Set-Location "$root\azure-mcp"
npm init -y
npm install @azure/mcp@latest          # 4.0.0-beta.3 recorded; npm flags used were not recorded
$azmcp = "$root\azure-mcp\node_modules\@azure\mcp-win32-x64\dist\azmcp.exe"      # platform package holding the binary
& $azmcp --version                     # 4.0.0-beta.3+<commit>
& $azmcp server start --help
```

The executable measured about 116 MiB when this document was written. `server start` options (from its help text; descriptions shortened):

| Option | Meaning |
|---|---|
| `--transport <transport>` | Transport; default `stdio` |
| `--namespace <namespace>` | Expose only the named service namespaces (for example `storage`); repeatable |
| `--mode <mode>` | `single` (one tool `azure` that routes to all services), `namespace` (default; one tool per service namespace), `all` (every tool individually) |
| `--tool <tool>` | Expose only the named tools; switches to `all` mode; cannot be combined with `--namespace` |
| `--read-only` | No write operations allowed |
| `--debug` | Verbose logging to stderr |
| `--dangerously-disable-http-incoming-auth` | Disables HTTP incoming authentication |
| `--dangerously-disable-elicitation` | Disables user confirmation before high-risk commands |
| `--dangerously-disable-ssrf-protections-by-namespace <ns>` | Disables SSRF protections for the named namespaces (or `ALL`) |
| `--outgoing-auth-strategy <strategy>` | Outgoing authentication strategy: `NotSet` (default), `UseHostingEnvironmentIdentity` or `UseOnBehalfOf` |
| `--dangerously-write-support-logs-to-dir <dir>` | Detailed debug logs to a folder (may contain sensitive data) |
| `--dangerously-disable-retry-limits` | Removes bounds on retry delays, timeouts and retries |
| `--cloud <cloud>` | `AzureCloud` (default), `AzureChinaCloud` or `AzureUSGovernment` |
| `--disable-caching` | No caching of resource responses |
| `--structured-output-mode <mode>` | Structured output mode: `Compact` or `Duplicated` |
| `--disable-proxy-tools` | Disables tools proxied from external sources listed in the server's resource registry |
| `--learn` | Lists sub-commands and parameters without running an Azure operation |

Environment variables used in the tests (their effects are the observations in 15.5, not documented claims): `AZURE_TOKEN_CREDENTIALS=AzureCliCredential` (use the Azure CLI as the credential source), `AZURE_MCP_COLLECT_TELEMETRY=false`, `AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT=false`, and `AZURE_CONFIG_DIR` pointing at an isolated, logged-out Azure CLI folder (the folder was not recorded). The server honoured `HTTPS_PROXY`, `HTTP_PROXY` and `NO_PROXY` (its attempts appeared in the deny-proxy log).

**15.2 Static scan of the binary for hostnames**

```powershell
& $py scan_exe_hosts.py
```

The script finds the largest file under `azure-mcp\node_modules\@azure\mcp-win32-x64`, reads it in 8 MB blocks, extracts `http://` and `https://` host names in ASCII and UTF-16, drops schema, example, localhost and `aka.ms` hosts, counts them and prints the 70 most frequent. The run found 151 distinct hosts; notable ones: `login.microsoftonline.com` and its sovereign-cloud equivalents, `management.azure.com`, `learn.microsoft.com`, `api.loganalytics.io`, `dc.applicationinsights.azure.com`, `mcp.ai.azure.com` and `packages.microsoft.com`. The printed list was not saved to a file. This is a static scan: a host string in the binary does not mean the server contacts it.

**15.3 MCP client (`mcp_client.py`)**

A minimal MCP client over stdio: it starts the server command, sends `initialize` (protocol `2025-06-18`, empty client capabilities), `notifications/initialized` and `tools/list`, optionally `tools/call`, and writes `results\mcp_<label>.json`. Usage:

```
mcp_client.py --label L [--env K=V ...] [--call NAME JSON ...] [--hold SECS] [--timeout S] -- <server command...>
```

`--env` adds environment variables for the server (repeatable); `--call` calls a tool with a JSON argument object (repeatable); `--hold` keeps the server running for that many seconds after the calls (for egress observation); the default per-request timeout is 60 s. Any server-initiated request (sampling, elicitation, roots) is answered with "method not found" and its method name is recorded under `server_requests`. The result file holds: `label`, `cmd`, `initialize_secs`, `server` (name and version), `server_capabilities` (keys), `protocol`, `tool_count`, `tool_names`, `annotations` (counts of tools with `readOnlyHint`, `destructiveHint`, `openWorldHint`, and `none` for tools with no annotations), the schemas of three named tools when present, `calls` (name, seconds, `is_error`, first 900 characters of the response) and `stderr_head`. It prints one summary line.

**15.4 Startup and mode comparison**

For each row, run the client against the server command and read the result file (the argument lists below are reconstructed from the `cmd` recorded in each result file; the extra `--env` values were not recorded for the mode runs):

```powershell
& $py mcp_client.py --label all-mode -- $azmcp server start --mode all
```

| Label | Server arguments | Tools | Annotation counts (readOnly, destructive, openWorld, none) | Initialize |
|---|---|---|---|---|
| all-mode | `--mode all` | 426 | 235, 139, 28, 0 | 1.42 s |
| all-mode-readonly | `--mode all --read-only` | 235 | 235, 0, 12, 0 | 1.14 s |
| single-mode | `--mode single --read-only` | 1 (`azure`) | 0, 0, 0, 1 | 1.37 s |
| storage-only | `--namespace storage --read-only` | 4 (`storage`, `group_list`, `group_resource_list`, `subscription_list`) | 3, 0, 0, 0 | 1.25 s |
| no-proxy-tools | `--read-only --disable-proxy-tools` | 64 | 5, 0, 0, 0 | 1.38 s |
| denied-* (three runs) | `--read-only` (default namespace mode) | 68 | 5, 0, 0, 0 | 1.2 to 1.44 s |

In every run the server declared the capabilities `logging` and `tools` only, reported protocol `2025-06-18`, and made no server-initiated request. The difference between 68 and 64 tools is the proxied tools (`documentation`, `azd`, `foundry`, `arm`) removed by `--disable-proxy-tools`.

Unauthenticated call: the three denied runs also call `subscription_list` with `{}` using `--call subscription_list '{}'`. Pass criterion: `is_error` true and a JSON text result with `"status":401` and a message that Azure credentials were not found or unavailable. Recorded: it returned in 0.22 to 0.28 s, with the detail `Azure CLI not installed` when `az` was not on `PATH`.

**15.5 Egress with the deny-all proxy**

Start the deny-all proxy (section 10.2). For each run set the label, then run the client with the proxy variables in the server's environment (the command is reconstructed; the exact arguments were not recorded):

```powershell
Set-Content "$root\logs\egress_label.txt" azmcp-default-denied
& $py mcp_client.py --label denied-default --env AZURE_TOKEN_CREDENTIALS=AzureCliCredential --env HTTPS_PROXY=http://127.0.0.1:18090 --env HTTP_PROXY=http://127.0.0.1:18090 --env NO_PROXY=127.0.0.1,localhost --call subscription_list '{}' -- $azmcp server start --read-only
```

Read the hosts: `Get-Content logs\egress_deny.jsonl | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.label -eq '<label>' } | Group-Object host`. Recorded (all refused):

| Label | Setting | Hosts attempted |
|---|---|---|
| azmcp-default-denied | telemetry variables not set | `169.254.169.254` x3, `centralus-2.in.applicationinsights.azure.com` x1, `westus-0.in.applicationinsights.azure.com` x1 |
| azmcp-telemetry-off-denied | `AZURE_MCP_COLLECT_TELEMETRY=false` only | `westus-0.in.applicationinsights.azure.com` x1, `169.254.169.254` x1 |
| both off (label not recorded) | `AZURE_MCP_COLLECT_TELEMETRY=false` and `AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT=false` | none |
| azmcp-all-mode | `--mode all` | `login.microsoftonline.com` x6, `learn.microsoft.com` x1 |
| azmcp-all-mode-readonly | `--mode all --read-only` | `login.microsoftonline.com` x6, `learn.microsoft.com` x1 |

The last two runs contacted those hosts at start-up, before any call. Namespace mode and `--disable-proxy-tools` runs attempted nothing once telemetry was off. The connection watcher of section 10.1 was not recorded as used for these runs.

**15.6 Calling a tool from each harness (scripted tool call)**

**Gateway support.** `POST /_ctl {"mcp_call": "subscription_list"}` (Python: `h.ctl(mcp_call='subscription_list')`) makes the mock model emit one call, with empty arguments, to the tool whose name equals the value or ends with `__<value>` (Anthropic branch), or equals or ends with the value (OpenAI branch; tools nested inside namespaced tool groups are searched too). It does so once per conversation, only when the request is streaming and carries no tool result yet. For OpenAI-style requests the gateway keeps up to 10 tool names containing `azure` or `subscription` in the state value `mcp_seen_tools` (readable from `/_ctl`). Reset with `h.ctl(mcp_call=None)`.

**Runner support.** `run_claude.py --claude-json JSON` merges JSON into the isolated `.claude.json` (for example `mcpServers`); `--allowed VALUE` adds `--allowedTools VALUE` to the command.

**Server definition used in every harness:** command `azmcp.exe`, arguments `server start --read-only --disable-proxy-tools`, environment `AZURE_MCP_COLLECT_TELEMETRY=false`, `AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT=false`, `AZURE_TOKEN_CREDENTIALS=AzureCliCredential`. The fake `az` was first on `PATH`.

**Claude Code CLI** (`run_claude.py mcp1-claude`, `mcp2-claude`). The isolated `.claude.json` holds:

```json
{ "mcpServers": { "azure": { "type": "stdio", "command": "<azmcp.exe path>", "args": ["server","start","--read-only","--disable-proxy-tools"],
    "env": { "AZURE_MCP_COLLECT_TELEMETRY": "false", "AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT": "false", "AZURE_TOKEN_CREDENTIALS": "AzureCliCredential" } } } }
```

1. Registration check: `$env:CLAUDE_CONFIG_DIR = "$root\work\claude\mcp1-claude"; claude mcp list`. Pass criterion: `azure` is listed as Connected (recorded).
2. First run with that configuration: the model request carried 14 tools and no MCP tool, because Claude Code defers MCP tools behind its tool search, so the mock could not call it.
3. Second run (`mcp2-claude`): add `ENABLE_TOOL_SEARCH` set to `false` in the settings `env`, run with `h.ctl(mcp_call='subscription_list')`:

```powershell
python run_claude.py mcp2-claude --settings '{"env":{"ENABLE_TOOL_SEARCH":"false"}}' --claude-json '<mcpServers JSON above>' --allowed mcp__azure__subscription_list --prompt "<prompt not recorded>"
```

Recorded: the model request then carried 88 tools; after the scripted call the next request held 5 messages, so the tool ran, and the tool result was Azure's 401 JSON (the session file `work\claude\mcp2-claude\projects\<folder>\<session>.jsonl` contains the text "Azure credentials not found or unavailable").

**Codex CLI** (`run_codex.py mcp3-codex`). Add the server as a top-level inline table in `config.toml` (before any table; `--top-lines` does this):

```toml
mcp_servers = { azure = { command = '<azmcp.exe path>', args = ['server','start','--read-only','--disable-proxy-tools'], env = { AZURE_MCP_COLLECT_TELEMETRY = 'false', AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT = 'false', AZURE_TOKEN_CREDENTIALS = 'AzureCliCredential' } } }
```

Registration check: `$env:CODEX_HOME = "$root\work\codex\mcp3-codex"; codex mcp list`; recorded: `azure` enabled. In the first run (`mcp3-codex`) the model request carried 12 tools and none was an MCP tool, so the mock could not call it. Two causes were found later: the server path must be a Windows path (a Git Bash path such as `/c/Users/...` is accepted by `codex mcp list` but never starts), and Codex adds the MCP tools only to a later request of the run.

End-to-end run (`mcp9-codex`). The gateway was changed so that, with `h.ctl(mcp_late=True, mcp_fired=False, tool_turns=1, mcp_call='subscription_list')`, it first answers with one `echo` shell call (this forces a second model request, by which time the server has started) and then emits the MCP call. The call carries a `namespace` field equal to the name of the tool group that holds the tool (`mcp__azure`). Command:

```powershell
python run_codex.py mcp9-codex --top-lines "<mcp_servers inline table above, with startup_timeout_sec = 60 and a Windows path>" --prompt "Run the command: echo hi. Then list my Azure subscriptions using the azure tool."
```

Recorded: request 3 carried 12 tools; request 4 carried 13, including the group `mcp__azure`; the session file `work\codex\mcp9-codex\sessions\...\rollout-*.jsonl` holds a `function_call` named `subscription_list` in namespace `mcp__azure` and its output, which is Azure's 401 JSON ("Azure credentials not found or unavailable") with the same fake-`az` parse cause as the other harnesses. The shell call itself was refused by Codex's sandbox policy, which does not matter for this test. Status: exercised end to end up to the authentication step.

**Copilot CLI** (offline BYOK as in section 9, isolated home). Create `$root\work\copilot-home\.copilot\mcp-config.json`:

```json
{ "mcpServers": { "azure-mcp": { "type": "local", "command": "<azmcp.exe path>", "args": ["server","start","--read-only","--disable-proxy-tools"],
    "env": { "AZURE_MCP_COLLECT_TELEMETRY": "false", "AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT": "false", "AZURE_TOKEN_CREDENTIALS": "AzureCliCredential" }, "tools": ["*"] } } }
```

Run the section 9 command with `COPILOT_OFFLINE=true`, `h.ctl(mcp_call='subscription_list')` and `--allow-tool 'azure-mcp'` added (the exact prompt was not recorded). The MCP tools reach the model named `azure-mcp-<tool>`. Recorded: the request carried 83 tools; the next request held 3 messages; the tool ran and returned the same 401 (the session file `work\copilot-home\.copilot\session-state\<id>\events.jsonl` contains the text).

**VS Code** (`vscode-test\cfg_o4-mcp.json`, scenario `o4-vscode-mcp-start`; the pinned VS Code 1.142.0, signed out, no extensions, fake `az` first on `PATH`). The config puts the server under the `mcp` key of the user settings (`settings.mcp.servers.azure`, same command, arguments and environment as the other harnesses, with `/` separators in the path). Steps: command palette **MCP: List Servers**; arrow down to `azure`, Enter; Enter on **Start Server**; wait 12 s; **MCP: List Servers** again. Recorded: before starting, the list shows `azure` as Stopped, scope "Global in Code"; after starting it shows Running. The server log `user-data\logs\<stamp>\window1\mcpServer.mcp.config.usrlocal.azure.log` shows `Connection state: Starting`, `Running`, then `Discovered 64 tools` (68 minus the four proxy tools), and Stopped when the window closed. VS Code had also written the server into `user-data\User\mcp.json`. The server's sub-menu is Start Server, Status, Show Configuration, Show Output and further items; the first Enter on the server opens it. Tool call from Copilot Chat (`vscode-test\cfg_q6-mcp.json`, scenario `q1-copilot-mcp`: the profile with the custom-endpoint model added through the UI, copied from `j4-byok-ui-added`; the MCP server under the `mcp` user setting; the model selected in the picker; prompt "List my Azure resource groups using the azure tool."; gateway `h.ctl(mcp_call='group_list')`). Recorded: the request carried 88 tools, 37 of them named `mcp_azure_mcp_ser_<tool>` (`subscription_list` was not among them, so `group_list` was used); the server started automatically (log: Running, 64 tools); the chat shows "Ran List Resource Groups" and "Tool execution failed", and the Copilot Chat log names `mcp_azure_mcp_ser_group_list`. The cause of the failure was not captured (the call had empty arguments and no Azure sign-in). No confirmation prompt appeared. Setting `chat.tools.global.autoApprove` raises an "Enable global auto approve?" dialog and should not be used.

**JetBrains** (PyCharm 2026.2.3, throwaway install, isolated profile; driven with `jetbrains\jb_ui.ps1`, whose foreground guard refuses input when another window is in front). Launch with `PYCHARM_PROPERTIES` set to `jetbrains\cfg\idea.properties` (the variable `IDEA_PROPERTIES` is not read by PyCharm; without the correct variable PyCharm uses the default profile folders, and with the wrong one it failed to start). Steps: Ctrl+Alt+S; search `Model Context`; open Tools, AI Assistant, Model Context Protocol (MCP) (empty, "No MCP server configured"); Add server; in the JSON box select all and paste the `mcpServers` object (same command, arguments and environment as the other harnesses, Windows path with doubled backslashes); choose Server level Project; OK; Apply. Recorded: after OK the `azure` row shows Level Project and a disabled status icon; after Apply the status is a green check and an `azmcp.exe` process is running. The project file `.ai/mcp/mcp.json` existed but was 0 bytes when PyCharm was stopped about 10 s later, so its on-disk format was not captured. `Tools > MCP Server` is a different page (the IDE's own MCP server). Chat tool call (same session, after the file `.ai/mcp/mcp.json` held the server, 474 bytes): the gateway chat-completions branch was extended so that `h.ctl(mcp_call='group_list', mcp_fired=False)` makes the next request that carries tools answer with one `tool_calls` entry (empty arguments) for the tool whose name equals or ends with the value. The token proxy had to be started with the fake `az` directory first on `PATH`; without it the proxy returned 502 and the chat panel showed "Failed to connect to OpenAI-compatible provider", and after a retry the model dropdown listed no models until PyCharm was restarted with a working proxy. A new chat with the prompt "List my Azure resource groups using the azure tool." sent request 11 with 99 tools (35 IDE tools plus the server's, including `group_list`) and request 12 with 4 messages, whose last message was the tool result `{"status":400,"message":"Missing Required options: --subscription"}` (the server rejected the empty arguments; no Azure sign-in was involved). The first attempt of this test failed for a different reason: PyCharm was stopped about 10 s after Apply and the project file was empty (0 bytes), so the server was absent after restart. Pitfalls: a first launch with the wrong environment variable showed an "Import Settings" screen for the default profile (Skip Import was chosen; nothing imported); typing into the Settings search box can drop or add characters, so check the box text before relying on it.

**15.7 Pass criteria (summary)**

- Startup: `initialize` returns the server name and version, capabilities `logging` and `tools`, and no server-initiated requests; `tools/list` returns the count for the mode (15.4).
- Unauthenticated call: `is_error` true and a 401 JSON text result.
- Egress: the hosts recorded for each setting (15.5); with both telemetry variables false and namespace mode, no attempt.
- Harness registration: `claude mcp list` shows Connected, `codex mcp list` shows enabled; for Copilot CLI the MCP tool names appear in the model request.
- End to end: the model request carries the MCP tool, the next request has more messages (a tool call and its result), and the tool's own session record contains the 401 text.

**15.8 Pitfalls**

- The fake `az` on `PATH` prints a bare token, but the server's `AzureCliCredential` expects `az` to print JSON, so it fails. The 401 result then cites a parse failure (recorded cause: `'e' is an invalid start of a value`, the start of a token). With no `az` on `PATH` the detail is `Azure CLI not installed`. Neither is a result obtained with a real credential.
- Claude Code needs `ENABLE_TOOL_SEARCH=false` for the mock to see MCP tools; without it the tools are deferred and the request lists 14 tools.
- Codex lists MCP tools only from its second model request of a run, grouped under a namespace tool named `mcp__azure`; a scripted call must carry that namespace (section 15.6, run `mcp9-codex`).
- The Copilot CLI run used `--allow-tool 'azure-mcp'` to pre-approve the MCP tools; what happens without it was not recorded.
- `--mode all` contacts `login.microsoftonline.com` and `learn.microsoft.com` at start-up even with telemetry off.

**15.9 Limits**

- No real-credential tool result was obtained, so what the server sends to Azure when it has a credential (for example calls to `management.azure.com`) was not observed.
- Only `subscription_list` was called, and only through read-only server settings; write-capable tools were not called.
- The host list in 15.2 is a static scan; the observed attempts are those in 15.5.
- The result files and logs hold tool names and error text only; the 401 text names no tenant or account.

## 16. Document quality checks

**Purpose.** Verify that generated Word documents open, render and validate.

1. Generate the `.docx` from the `.md` with the session converter: `node md2docx.js '<path without extension>'` (run from its folder). It supports headings (`#`, `##`), bullets, numbered lists, tables, code fences, inline code and bold.
2. Open and export through Word:

```powershell
$word = New-Object -ComObject Word.Application; $word.Visible = $false
try { $d = $word.Documents.Open("$root\handoff\<name>.docx", $false, $true); $d.ExportAsFixedFormat("$root\handoff\pdf\<name>.pdf", 17); "pages=$($d.ComputeStatistics(2))"; $d.Close($false) } finally { $word.Quit() }
```

3. Render pages with PyMuPDF (`render_pdf.py`, `sheet.py`, `sheet2.py` in the test folder): `pymupdf.open(pdf)`, `page.get_pixmap(dpi=70..80)`, optionally tiled into a 2 by 2 contact sheet, then look at the images (tables, shaded code blocks, lists, links).
4. Validate with the docx skill's `validate.py` using `$root\.venv\Scripts\python.exe`. It needs `defusedxml` and `lxml`; without them it fails on every file with an import error, which was mistaken for a file defect in one run. Pass criterion: `All validations PASSED!`. Run it on a file that Word itself saved (open in Word and save as `.docx`) as a control.
5. Copy to the destination only when no file of the same name exists; compare with `Get-FileHash`.

## 17. Reproduction run book and evidence index

**17.1 Order of work (clean machine to full result set)**

1. Install tools and create the folder layout (section 2). Check: `uv`, `node`, `claude --version`, `codex --version`.
2. Create the venv and install packages; copy scripts (2.2).
3. Start the gateway; check `/_ctl` (3.2).
4. Direct helper tests with all four fake modes (4.2). Expected: `ok` and `noisy` return a token; `wrong_aud` and `fail` exit 1 with one stderr line.
5. Claude Code CLI: c01, `suite_claude.py`, c12, c13, `suite_claude_refresh.py` (section 5). Expected outputs: `results\claude_suite.json`, `results\claude_refresh.json`.
6. Codex CLI: x01, `suite_codex.py`, x11, `suite_codex_refresh.py` (section 6). Expected outputs: `results\codex_suite.json`, `results\codex_refresh.json`.
7. `suite_helper_hardened.py` (4.3). Expected output: `results\helper_hardened.json`.
8. Token proxy: start it, run `suite_proxy.py`, then P5, P6, P7 (section 7).
9. Download the VS Code test copy; install the extension folders (2.2).
10. VS Code UI: d-series (8.5 to 8.7), Copilot BYOK procedure (8.7 B to D).
11. Copilot CLI install and tests (section 9).
12. Egress audit: CLI default and quiet runs, VS Code h-series, deny-proxy runs for CLIs and VS Code i-series and j8 (section 10). Expected outputs: `logs\egress\<label>.json`, `logs\egress_deny.jsonl`, `work\vscode\<scenario>\netlog.json`.
13. Token-at-rest scan (section 11).
14. Real Azure CLI install and no-login checks (12.1, 12.2). With the owner present: device-code sign-in (12.4, 14.2), token inspection (14.3), helper test (14.4); restart the gateway in lenient mode and the token proxy with the real helper (14.5); run each tool (14.6, 14.7); read the gateway log (14.8). Expected: 32 requests with `real_token` true and status 200. Then sign out and delete `work\azconfig` (14.9).
15. JetBrains: download, verify, install, plugin, supporting services (13.1 to 13.4); first launch and dialogs (13.5); configure the provider, assign the model, chat, read the gateway log (13.7, 13.8); egress runs (13.9); static inspection (13.10). Expected outputs: `GET <url>/models` requests, then `POST /openai/v1/chat/completions` requests with a valid JWT; `logs\egress\pycharm-idle.json` and `pycharm-chat.json` empty; screenshots `jetbrains\k*.png`.
16. Azure MCP Server: install and inspect (15.1, 15.2); startup and mode comparison with `mcp_client.py` (15.3, 15.4); egress with the deny-all proxy (15.5); register and call a tool from Claude Code, Codex and Copilot CLI (15.6). Expected outputs: `results\mcp_*.json` (8 files) and `azmcp-*` entries in `logs\egress_deny.jsonl`.
17. Stop all test processes (3.5 cleanup). Confirm ports 18080, 18081 and 18090 are free.

**17.2 Evidence index**

| Location | Holds |
|---|---|
| `logs\requests.jsonl` | Every gateway request with auth result and claims (all tools) |
| `logs\az_calls.jsonl` | Every fake `az` call with the mode in force |
| `logs\egress\<label>.json` | Watcher output per run: endpoints, process names, states |
| `logs\egress_deny.jsonl` | Hosts refused by the deny proxy, with run label |
| `logs\codex_exec_command_schema.json` | Schema of the Codex `exec_command` tool |
| `results\*.json` | Suite outputs for Claude Code, Codex and the hardened helper |
| `work\claude\<scenario>`, `work\codex\<scenario>` | Isolated CLI configuration and state per scenario |
| `work\vscode\<scenario>\` | VS Code profile, `settings.json`, `chatLanguageModels.json`, screenshots (`*.png`), `probe.jsonl`, `netlog.json`, extension-host and agent-host logs under `user-data\logs\` |
| `work\<scenario>.out.txt`, `work\j8.out.txt` | Console output of Playwright runs (step results and page text) |
| `work\copilot-home`, `work\azconfig` | Copilot CLI home; Azure CLI configuration |
| `work\azlogin_out.txt`, `work\azlogin_err.txt` | Device-code login output (reused by each attempt; the second attempt's output) |
| `work\azconfig\` | Isolated Azure CLI configuration holding the signed-in token cache and profile. Sensitive: do not publish; sign out and delete it when finished |
| `azure-mcp\`, `mcp_client.py`, `scan_exe_hosts.py` | Azure MCP Server install and the two scripts used with it |
| `results\mcp_*.json` | Client summaries: `all-mode`, `all-mode-readonly`, `single-mode`, `storage-only`, `no-proxy-tools`, `denied-default`, `denied-telemetry-off`, `denied-both-off` |
| `logs\egress_deny.jsonl` entries labelled `azmcp-*` | Hosts the Azure MCP Server tried through the deny-all proxy |
| `work\claude\mcp1-claude`, `work\claude\mcp2-claude`, `work\codex\mcp3-codex`, `work\copilot-home\.copilot\mcp-config.json` | MCP configurations used by the three harnesses; the Claude session file under `mcp2-claude\projects` and the Copilot `session-state\<id>\events.jsonl` hold the tool exchange (the 401 text) |
| `get-apim-token-real.ps1` | Helper copy used for the real-token runs |
| `work\claude\real1-claude`, `work\codex\real2-codex`, `work\codex\real3-codex-default-timeout` | CLI runs with the real token (tool configuration and state; not scanned for tokens) |
| `work\claude-vsext-real`, `work\codex-vsext-real` | Config folders for the two VS Code extension real-token runs |
| `vscode-test\cfg_n1.json`, `cfg_n2-claude-ext-real.json`, `cfg_n3-codex-ext-real.json`, `cfg_n4.json` | Scenario files for the VS Code real-token runs (Copilot BYOK, Claude extension, Codex extension first attempt, Codex extension rerun) |
| `logs\requests.jsonl` entries with `auth.claims.real_token` true | The 32 real-token requests (claims by name and the listed fields only; treat the log as sensitive) |
| `jetbrains\*.png` | PyCharm window images. Settings-window captures are 900 by 700 and main-window captures 1400 by 1001. Key ones: `k3_0` Settings opened, `k6` search result, `k7` Providers & API keys, `k8_0` provider list, `k12_0` Data Sharing confirmation, `k20` URL and key entered, `k23_0` Connected, `k25_0` chat panel, `k29_0` model list, `k30` model assignment, `k31` chat reply; `k_index.png` is a labelled contact sheet of the `k*` captures |
| `logs\egress\pycharm-idle.json`, `pycharm-chat.json` | PyCharm watcher outputs (both empty lists) |
| `%USERPROFILE%\PycharmProjects\WelcomeScreen` | Folder PyCharm created outside the isolated profile |
| `LOG.md` | Chronological notes of the work; `RESULTS.md` summary tables |
| `handoff\` | Documents and `handoff\pdf\` renders |

## 18. Limitations and sources of error

- **Mock, not real.** The gateway validates signature, audience, issuer and expiry only. A real APIM adds policies, WAF rules, response buffering and its own error text; none of these were present. The fake `az` mints tokens locally for most runs. In the real-token runs (section 14) the gateway ran in lenient mode and did not verify signature, audience or issuer, so they show that the tools handle a real token, not that an APIM policy would accept it. Consent, Conditional Access, sign-in frequency and refresh-token lifetime beyond one sign-in were not exercised.
- **Real Azure CLI.** Tested without a login and, after the owner's sign-in, for token issuance, timing and the helper (section 14). Only a token for the Azure Resource Manager audience was obtained; no custom API audience (no app registration was created, by the owner's read-only rule).
- **Platform.** Windows 11 only. Paths, `powershell` 5.1 behaviour, `.cmd` wrappers and the DNS cache are Windows specific.
- **Versions.** Every version in section 2.1 was pinned by what was installed on the day; behaviour may differ in other versions. The VS Code test copy has the same build number as the installed copy but is a separate archive.
- **Short sessions.** Most runs lasted seconds to about a minute. Behaviour over hours (token renewal over an hour, update checks, caches) was not observed.
- **Sampling.** The connection watcher samples every 0.4 s and can miss very short connections. The deny proxy sees only proxy-aware traffic. Hostnames matched through DNS resolution are inferences.
- **Coordinates.** UI steps depend on screen size, window layout and extension versions; a changed layout needs new coordinates from screenshots. Fixed waits (for example 35 s for the Codex panel) are not conditions; on a slower machine they may need to be longer.
- **Throwaway data.** Keys and tokens are generated for the test and are valid only against the mock, except the real Entra tokens of section 14, which are real credentials: do not store or publish them, `work\azconfig` or the unredacted gateway log. Placeholder keys such as `dummy-local-key` are replaced by the token proxy.
- **Isolation lapses.** (a) In some early VS Code runs the Codex extension was active with no isolated Codex home, so it used the default location for its caches and logs. The `config.toml` there was not changed. From the per-extension profiles on, `CODEX_HOME` was always set. (b) PyCharm created `%USERPROFILE%\PycharmProjects\WelcomeScreen` at first launch, outside `idea.properties`.
- **JetBrains scope.** Only the OpenAI-compatible provider was configured and only chat was exercised. The separate AI Completion section, MCP tool calls, agents, other providers and JetBrains account activation were not tried. The click positions in section 13.7 were read from the saved window captures and are element centres; the exact coordinates and the send method (Enter or the send button) of the completed run were not saved in a script. The Settings layout depends on the scroll offset of the right pane, so positions must be re-read from a capture each time. The process was Windows only and ran in a dark theme at the default window sizes.
- **Azure MCP scope.** No real-credential tool result was obtained (the owner declined a further sign-in); only `subscription_list` was called, with read-only server settings. the host list from the binary is a static scan.
- **Not done.** A token for a custom API audience (needs an app registration); acceptance of a real token by a real APIM policy; the real APIM; token refresh over the full token lifetime; the `azure` provider's built-in Entra sign-in in VS Code; Fusion with a model identifier other than the two tried; which single Codex flag stops its startup calls; the `--local-key` option of the token proxy; HTTPS upstream through the token proxy; long-running sessions; the JetBrains items listed under JetBrains scope.
- **Version of the helper.** Scenarios c01 to c11, the Claude refresh tests and x01 to x14 used the original helper (section 4.1), so their behaviour on bad tokens differs from runs that used the hardened helper.
