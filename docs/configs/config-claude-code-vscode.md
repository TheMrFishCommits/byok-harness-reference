# Claude Code VS Code extension: BYOK with an Entra-issued token and no vendor network access

## Summary

The Claude Code extension for VS Code runs its own bundled Claude Code binary and reads the same `settings.json` as the Claude Code CLI. With `apiKeyHelper` configured there, the extension sends model requests to an Anthropic-Messages-compatible gateway (for example an Azure API Management endpoint) with a fresh Entra ID JWT obtained from a helper command, and shows no login prompt. No claude.ai or Anthropic sign-in is needed. A small set of environment variables switches off the background traffic the bundled binary otherwise sends to Anthropic hosts. VS Code itself has separate network behaviour that is configured in VS Code settings.

## Applies to

| Item | Value |
|---|---|
| Product | Claude Code extension for VS Code (`anthropic.claude-code`) |
| Versions | 2.1.312 (win32-x64) with VS Code 1.142.0. The bundled binary reports the same version as the extension. Custom headers need 2.1.227 or later. From 2.1.227 a helper that prints anything besides the credential fails |
| OS | Windows (the helper is PowerShell). The settings keys are the same on other systems with a different helper |
| Config locations | Claude settings: `%USERPROFILE%\.claude\settings.json` (user), `.claude\settings.json` (project, committed), `.claude\settings.local.json` (project local), `managed-settings.json` (managed). `CLAUDE_CONFIG_DIR` in VS Code's environment relocates the user folder. VS Code user settings: `claudeCode.*` keys |
| Scope used here | User. Do not put credentials in the committed project file |

## Prerequisites

1. A gateway that exposes the Anthropic Messages API: `POST <base>/v1/messages` (the binary adds `?beta=true`), with server-sent events streamed through unbuffered. `POST <base>/v1/messages/count_tokens` is optional. The gateway forwards the `anthropic-version` and `anthropic-beta` headers unchanged and returns upstream error bodies and `Retry-After` (integer seconds) unmodified.
2. A gateway policy that reads the JWT from the `Authorization` header (for example APIM `validate-jwt`).
3. The helper command: a script that prints a fresh Entra ID access token for the gateway's API (Appendix A, at the end of this guide, gives the script and its requirements: an Entra app registration for the gateway API, the Azure CLI, and one `az login` per user).
4. The model (deployment) names the gateway serves.
5. `az` reachable from VS Code's environment. If VS Code is started from the Start menu or desktop, the extension host may not have `az` on its PATH. Put the full path to `az.cmd` in the helper (`(Get-Command az).Source` shows it).
6. The extension installed in VS Code.

## Authentication: how the token reaches the gateway

Method: `apiKeyHelper`, a shell command that prints the current credential on stdout. The extension starts its bundled binary, which reads `settings.json` and runs the `apiKeyHelper` command. The value is sent in both the `Authorization: Bearer <value>` header and the `x-api-key` header, so a gateway can read either.

Steps:

1. Save the script from Appendix A as `C:\Users\<you>\bin\get-apim-token.ps1` and fill in the two audience values at its top.
2. Run `az login` once.
3. Set `apiKeyHelper` to the command that runs the script, `powershell -NoProfile -File C:\Users\<you>\bin\get-apim-token.ps1` (backslashes doubled in JSON), and set `CLAUDE_CODE_API_KEY_HELPER_TTL_MS` below the token lifetime (1800000 is 30 minutes; the default is 5 minutes).

User `settings.json`:

```json
{
  "apiKeyHelper": "powershell -NoProfile -File C:\\Users\\<you>\\bin\\get-apim-token.ps1",
  "env": {
    "ANTHROPIC_BASE_URL": "https://<apim-host>/<anthropic-api-path>",
    "CLAUDE_CODE_API_KEY_HELPER_TTL_MS": "1800000"
  }
}
```

Behaviour:

- With only this file in place and nothing in VS Code's own settings, the extension showed no login prompt and sent requests with the helper's token.
- The Claude Code documentation names `claudeCode.environmentVariables` as the place for a static gateway credential, because the extension's own login check reads it. It is not needed for `apiKeyHelper`. If a login prompt does appear, set the gateway variables there as well (see "Provider and model configuration").
- The helper output is cached for 5 minutes by default. `CLAUDE_CODE_API_KEY_HELPER_TTL_MS` (milliseconds) changes this. Keep it below the token lifetime.
- When a token expires inside the cache window, the gateway answers 401, the binary runs the helper again and retries with the new token. One 401 appears in the gateway log.
- Changes to `apiKeyHelper` apply without a restart.
- A helper that exits with an error, times out or prints nothing makes requests fail with "Your apiKeyHelper script is failing" after three attempts. A helper slower than 10 seconds triggers a slow-helper warning.
- Do not set `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY` anywhere (VS Code settings, Claude settings or the environment). They take precedence over `apiKeyHelper`, and a rejected static token is retried for minutes. Order of precedence: cloud provider credentials, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`, `apiKeyHelper`.
- Extra gateway headers: `ANTHROPIC_CUSTOM_HEADERS` takes `Name: Value` lines separated by newlines (2.1.227 or later). A non-empty custom header replaces a built-in header of the same name.

Example with a subscription-key header:

```json
{
  "env": {
    "ANTHROPIC_CUSTOM_HEADERS": "Ocp-Apim-Subscription-Key: <subscription-key>"
  }
}
```

## Provider and model configuration

Set the base URL without the `/v1/messages` suffix. The binary appends `/v1/messages?beta=true`.

Model names are set with environment variables or settings. Precedence: `/model` or `--model`, then `ANTHROPIC_MODEL`, then the `model` setting, then `ANTHROPIC_DEFAULT_MODEL` (2.1.236 or later).

```json
{
  "env": {
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "<deployment-name>",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "<deployment-name>",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "<deployment-name>"
  },
  "model": "<deployment-name>"
}
```

- `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL` and the `model` setting change the model name sent to the gateway. Set the Haiku variable as well: lightweight background requests use it.
- `modelOverrides` maps an Anthropic model ID to a provider deployment name and rewrites the name sent to the gateway: `{"modelOverrides": {"<anthropic-model-id>": "<deployment-name>"}}`.
- For a model ID the binary does not recognise, the context window is assumed to be 200K (1M with a `[1m]` suffix). The `ANTHROPIC_DEFAULT_*_SUPPORTED_CAPABILITIES` variables have no effect behind a gateway.
- Gateway model discovery is off. `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1` makes the binary call `GET <base>/v1/models?limit=1000` (3 second timeout, no redirects) and keep only IDs containing "claude" or "anthropic", so custom deployment names are filtered out.

Optional VS Code-level environment, applied to the process the extension starts (array of name and value):

```json
{
  "claudeCode.environmentVariables": [
    { "name": "ANTHROPIC_BASE_URL", "value": "https://<apim-host>/<anthropic-api-path>" },
    { "name": "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "value": "1" },
    { "name": "DISABLE_TELEMETRY", "value": "1" },
    { "name": "DISABLE_ERROR_REPORTING", "value": "1" },
    { "name": "DISABLE_AUTOUPDATER", "value": "1" }
  ]
}
```

Other `claudeCode.*` settings in the extension manifest that are relevant: `claudeCode.claudeProcessWrapper` (a wrapper that launches the Claude process), `claudeCode.useTerminal` (run in the terminal), `claudeCode.disableLoginPrompt`, `claudeCode.preferredLocation`, `claudeCode.initialPermissionMode`. Their behaviour is not described in the documentation pages reviewed.

Extension behaviour that differs from the CLI:

- When the panel opens, the bundled binary sends two `HEAD <base>/api/hello` probes (the CLI sends one at startup). A 404 from the gateway is harmless.
- Requests carry a user agent of the form `claude-cli/<version> (external, claude-vscode, ...)`.
- The extension runs a local MCP server bound to 127.0.0.1 for editor integration. It is not an external connection.
- Open the panel from the Claude Code status bar item, or with the commands `claude-vscode.editor.open`, `claude-vscode.sidebar.open` or `claude-vscode.window.open`. The panel needs about 15 seconds to become ready.

## Disabling login, telemetry and background network calls

Put the Claude variables in `env` in the Claude `settings.json`, or in `claudeCode.environmentVariables`. A settings-file value beats a shell export of the same name.

| Setting | Where | Value | Default | Effect |
|---|---|---|---|---|
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | env | `1` (any non-empty value; `0` or `false` still disables) | unset | Umbrella switch. Covers auto-updates, telemetry, error reporting, `/feedback` and drafted feedback, release notes, PR and MR status checks, availability checks (fast mode), feature-flag fetching and surveys. Also turns feedback off in the VS Code panel (2.1.284 or later). Does not cover the WebFetch domain check, official marketplace auto-install or gateway model discovery |
| `DISABLE_TELEMETRY` | env | `1` | on for the Claude API | Opts out of operational metrics (a Datadog log intake), feature-flag fetching and surveys. Does not disable `/feedback` |
| `DO_NOT_TRACK` | env | `1` | unset | Same effect as `DISABLE_TELEMETRY`. A value of `0` leaves telemetry on |
| `DISABLE_ERROR_REPORTING` | env | `1` | on for Pro and Max sign-ins on 2.1.198 or later, otherwise off | Opts out of error reports sent to a Datadog browser intake. Does not affect feature flags |
| `DISABLE_AUTOUPDATER` | env | `1` | updates on | Stops automatic background updates. Manual `claude update` still works |
| `DISABLE_UPDATES` | env | `1` | off | Blocks all updates, including manual `claude update` and `claude install` |
| `DISABLE_FEEDBACK_COMMAND` | env | `1` | unset | Disables `/feedback`, `/bug`, `/share`, Claude-drafted feedback and feedback in the panel |
| `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY` | env | `1` | unset | Disables the session survey only |
| `DISABLE_GROWTHBOOK` | env | `1` | unset | Stops feature-flag fetching. Telemetry events stay on unless `DISABLE_TELEMETRY` is also set |
| `ENABLE_CLAUDEAI_MCP_SERVERS` | env | `false` | on for signed-in users | Stops fetching claude.ai MCP servers (a mcp-proxy.anthropic.com host). The setting `disableClaudeAiConnectors: true` has the same intent |
| `skipWebFetchPreflight` | Claude settings | `true` | check on | Skips the WebFetch hostname check, which sends the hostname to api.anthropic.com. The documentation describes this two ways ("when Anthropic is unreachable" and "disables the check entirely") |
| `CLAUDE_CODE_DISABLE_WEB_FETCH` | env | `1` | off | Turns off the WebFetch tool (2.1.285 or later). WebSearch stays. No switch to disable WebSearch is documented |
| `CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL` | env | `1` | unset | Skips automatic registration of the official plugin marketplace. Read at the first interactive launch. Unsetting it later does not undo the skip |
| `disableRemoteControl` | Claude settings | `true` | false | Refuses Remote Control. Remote Control is already unavailable when feature-flag fetching is off or when the base URL host is not api.anthropic.com (2.1.196 or later) |
| `syncClaudeAiSkills`, `syncClaudeAiPlugins` | Claude settings (user, local, managed) | `false` | sync on for claude.ai sign-ins | Stops downloading claude.ai skills and plugins |
| `allowedProviders` | managed settings | `["customEndpoint"]` | unset | Refuses sessions pointed anywhere except the managed `ANTHROPIC_BASE_URL` (2.1.285 or later). Documented, effect not confirmed |
| `CLAUDE_CODE_ENABLE_TELEMETRY` | env | unset | off | OpenTelemetry export to your own collector is opt-in. `OTEL_METRICS_EXPORTER`, `OTEL_LOGS_EXPORTER` and `OTEL_TRACES_EXPORTER` accept `none` |
| `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` | env | `1` | unset | Skips automatic installation of IDE extensions |
| `CLAUDE_CODE_AUTO_CONNECT_IDE` | env | `false` | on in an IDE terminal | Stops auto-connecting to the IDE (the connection is local) |

Recommended minimum set, all in `env`:

```json
{
  "env": {
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "DISABLE_TELEMETRY": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "DISABLE_AUTOUPDATER": "1"
  }
}
```

With these four set, the bundled binary opened no connection to a host outside the gateway. Optional extras for sessions that use WebFetch or plugins: `skipWebFetchPreflight`, `CLAUDE_CODE_DISABLE_WEB_FETCH`, `CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL`.

Login: with `apiKeyHelper` as the credential source there is no claude.ai or Anthropic sign-in prompt. `DISABLE_LOGIN_COMMAND` hides `/login` (it is a command switch, not a network switch).

VS Code switches that reduce traffic made by VS Code around the extension (VS Code user settings):

| Setting | Where | Value | Default | Effect |
|---|---|---|---|---|
| `telemetry.telemetryLevel` | VS Code settings | `off` | `all` | No usage data, crash reports or error telemetry |
| `update.mode` | VS Code settings | `none` | `default` | No automatic update checks |
| `extensions.autoCheckUpdates` | VS Code settings | `false` | true | Stops background extension update checks. These contact the Marketplace |
| `extensions.autoUpdate` | VS Code settings | `false` | true | Stops automatic extension updates |
| `workbench.enableExperiments` | VS Code settings | `false` | true | Stops experiment (A/B) service requests |

Example VS Code user settings:

```json
{
  "telemetry.telemetryLevel": "off",
  "update.mode": "none",
  "extensions.autoCheckUpdates": false,
  "extensions.autoUpdate": false,
  "workbench.enableExperiments": false
}
```

With these VS Code settings and the four Claude variables, the extension and its binary opened no connection to Anthropic, and VS Code's own remaining calls were to Microsoft hosts (below).

## Network behaviour with this configuration

- Binary, default: it opens a connection to `api.anthropic.com` even when `ANTHROPIC_BASE_URL` points at a gateway.
- Documented hosts the binary may contact: api.anthropic.com (feature flags, telemetry events, WebFetch check, fast-mode check), claude.ai and platform.claude.com and sso.claude.com (sign-in), downloads.claude.ai (updates), storage.googleapis.com (plugin metadata), registry.npmjs.org (npm plugins), github.com (plugin and marketplace clones), raw.githubusercontent.com (release notes), code.claude.com (documentation lookups), http-intake.logs.us5.datadoghq.com and browser-intake-us5-datadoghq.com (telemetry and error reports), mcp-proxy.anthropic.com (claude.ai connectors).
- Binary, after the four variables: no external connection. The gateway model-discovery call, the WebFetch check and the marketplace auto-install have their own switches (table above).
- VS Code, default (telemetry off, updates off, signed out): `main.vscode-cdn.net` (remote chat feature configuration), `marketplace.visualstudio.com` (extension update query for `anthropic/claude-code`), `www.vscode-unpkg.net`.
- VS Code, after the settings above: `main.vscode-cdn.net` remained, plus one unnamed Microsoft address. The VS Code documentation names no setting for that fetch.
- The binary honours `HTTPS_PROXY`, `HTTP_PROXY` and `NO_PROXY` (SOCKS is not supported). It never proxies WebSocket connections to localhost, ::1 or 127.0.0.0/8. With every host except the gateway refused, the panel opens and model requests succeed; refused calls fail quietly.
- Allow: the gateway host and the Entra endpoints used by `az login` and the helper. Block or leave refused: every other host in the lists above.

## Effects and limits of this configuration

- With feature-flag fetching off, these features are unavailable: Remote Control, `claude import` and `/import`, `/skill-doctor`, claude.ai skill and plugin sync, the advisor tool, MCP tasks, artifact comments, the default PowerShell tool on Windows with Git Bash, Claude-drafted feedback and idle compaction.
- No `/feedback`, no automatic updates: update the extension and the bundled binary by hand. Feedback is off in the panel while the umbrella variable or `DISABLE_FEEDBACK_COMMAND` is set.
- Extension and Marketplace updates are manual.
- With a gateway token and no API key, the binary has no credential to fetch feature flags with.
- Model names, context windows and capabilities for custom deployment names are not discovered; set the names explicitly. Unrecognised IDs assume a 200K context window.
- WebFetch needs the hostname check or `skipWebFetchPreflight`. WebSearch behaviour behind a custom base URL is not documented.
- Remote Control is disabled when the base URL host differs from api.anthropic.com.
- The remaining VS Code CDN fetch (`main.vscode-cdn.net`) has no documented setting.

## Confirming it works

1. Run the helper by hand and check that it prints one long `eyJ...` line.
2. Open the Claude Code panel and send a short prompt. A reply appears and no sign-in screen is shown.
3. In the gateway log expect two unauthenticated `HEAD <path>/api/hello` requests and an authenticated `POST <path>/v1/messages?beta=true` with a user agent containing `claude-vscode`, `Authorization: Bearer <jwt>` and an identical `x-api-key`.
4. The JWT claims (audience, issuer, expiry) match the gateway policy.
5. If a login prompt appears, set the gateway variables in `claudeCode.environmentVariables` as shown above.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Login screen instead of a chat panel | The extension's own login check did not see the gateway settings. Add `ANTHROPIC_BASE_URL` to `claudeCode.environmentVariables`; see also `claudeCode.disableLoginPrompt` |
| "Your apiKeyHelper script is failing" | The helper exited with an error. Run it by hand. Often not signed in: run `az login`. If VS Code was started from the desktop, `az` may not be on its PATH: use the full path to `az.cmd` |
| Repeated 401 for minutes | `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY` is set somewhere and overrides the helper, or the token audience does not match the gateway policy |
| Settings changes are ignored | `CLAUDE_CONFIG_DIR` must be set in the environment of the VS Code process, not only in a terminal opened later |
| Requests succeed but the model is not found | Set `ANTHROPIC_DEFAULT_*_MODEL` or `model` to the gateway deployment name |
| Response stalls | The gateway is buffering server-sent events. Disable response buffering for `/v1/messages` |
| 403 with an HTML body | A web application firewall is blocking the request body. Exempt the messages route |
| Slow-helper warning | The helper takes longer than 10 seconds. Check `az` startup time |
| Panel slow to appear | The panel takes about 15 seconds on first open |

## References

- https://code.claude.com/docs/en/vs-code
- https://code.claude.com/docs/en/llm-gateway-connect
- https://code.claude.com/docs/en/llm-gateway-protocol
- https://code.claude.com/docs/en/authentication
- https://code.claude.com/docs/en/env-vars
- https://code.claude.com/docs/en/settings
- https://code.claude.com/docs/en/data-usage
- https://code.claude.com/docs/en/network-config
- https://code.claude.com/docs/en/model-config
- https://code.visualstudio.com/docs/setup/network

## Appendix A: Entra token helper script

This appendix is part of this guide. It is the command that obtains a fresh Entra ID access token for the gateway's API and prints only the token. Use it wherever this guide calls for the helper command.

**What it does.** It asks the Azure CLI for an access token for the API, checks the token, and prints the raw JWT on standard output. The user signs in once with `az login`; the Azure CLI renews tokens silently. The script never prompts, never writes the token to disk, and makes no network call itself (the Azure CLI contacts Microsoft Entra when it needs to renew).

**Prerequisites.**

1. An Entra app registration that represents the gateway's API, with an Application ID URI such as `api://<apim-app-id>`. The gateway's `validate-jwt` policy checks the `aud` and `iss` claims of tokens for that app.
2. The Azure CLI may request a token for that API: pre-authorize the Azure CLI client ID `04b07795-8ddb-461a-bbee-02f9e1bf7b46` under "Expose an API" on the app registration, or have an administrator grant consent. Without this, `az` fails with `AADSTS65001` or `AADSTS70011`.
3. The Azure CLI installed, and one `az login` per user. Renewal is silent, subject to the tenant's Conditional Access sign-in frequency; run `az login` again when that expires.
4. The audience value of the tokens your gateway expects. Tokens issued under the v1 and v2 endpoints can carry different `aud` values (an `api://` URI or an app ID). List every value your tokens can carry in `ExpectedAud` (the script accepts a list). For reference, a token for the Azure Resource Manager scope is about 2,400 characters, lives about 80 minutes, is a version 1.0 token, and has `aud` `https://management.azure.com` with no trailing slash; fetching it with the Azure CLI takes about 1 to 1.3 seconds.

**Script.** Save as `C:\Users\<you>\bin\get-apim-token.ps1` and replace `<apim-app-id>` and `<apim-app-client-id>` in the first two variables. It runs under Windows PowerShell 5.1 (`powershell`) or PowerShell 7.

```powershell
# Prints ONLY the raw JWT to stdout; on any problem prints a one-line reason to stderr and exits 1.
# Failing fast matters: both Claude Code and Codex retry hard on a bad token.
$Scope       = 'api://<apim-app-id>/.default'
$ExpectedAud = @('api://<apim-app-id>', '<apim-app-client-id>')   # accept both token forms
$MinLifeSecs = 60

$lines = & az account get-access-token --scope $Scope --query accessToken -o tsv 2>$null
if ($LASTEXITCODE -ne 0) { [Console]::Error.WriteLine("get-apim-token: az failed (exit $LASTEXITCODE). Run: az login"); exit 1 }

# Tolerate banners/warnings on stdout: keep only the line that looks like a JWT.
$jwt = $lines | ForEach-Object { "$_".Trim() } | Where-Object { $_ -match '^eyJ[\w-]+\.[\w-]+\.[\w-]+$' } | Select-Object -Last 1
if (-not $jwt) { [Console]::Error.WriteLine('get-apim-token: az output contained no JWT'); exit 1 }

# Sanity-check the claims so a wrong audience or nearly-expired token fails here, not as an endless 401 loop.
$p = $jwt.Split('.')[1].Replace('-', '+').Replace('_', '/')
while ($p.Length % 4) { $p += '=' }
$claims = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($p)) | ConvertFrom-Json
$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
if ($ExpectedAud -notcontains $claims.aud) { [Console]::Error.WriteLine("get-apim-token: token aud is '$($claims.aud)', expected '$($ExpectedAud -join "' or '")'"); exit 1 }
if ($claims.exp - $now -lt $MinLifeSecs) { [Console]::Error.WriteLine("get-apim-token: token expires in $($claims.exp - $now)s"); exit 1 }

[Console]::Out.Write($jwt)
```

**Guards and why they exist.**

- The standard-output filter keeps only the line that looks like a JWT. A banner or warning on standard output otherwise makes the calling tool send no usable credential.
- The audience check fails fast with a clear message. A token for the wrong audience otherwise produces 401 responses that the calling tool retries for a long time.
- The lifetime check (`MinLifeSecs`, 60 seconds) refuses a token that is about to expire.
- All messages go to standard error; standard output carries only the token.

**Exit codes.** 0: the JWT on standard output, no trailing newline. 1: one line on standard error, one of `az failed (exit N). Run: az login`, `az output contained no JWT`, `token aud is '<aud>', expected '<expected>'`, or `token expires in <N>s`.

**Notes.**

- A host launched from the Start menu or desktop may not have `az` on its PATH. Replace `az` in the script with the full path to `az.cmd` (find it with `(Get-Command az).Source`).
- Set the calling tool's helper timeout above the time `az` takes (about 1 to 1.3 seconds when signed in; a few seconds on first use), and any cache or refresh interval below the token lifetime.
- Check the claims locally, without pasting a token into an online decoder:

```powershell
$t = & powershell -NoProfile -File C:\Users\<you>\bin\get-apim-token.ps1
$p = $t.Split('.')[1].Replace('-','+').Replace('_','/'); while ($p.Length % 4) { $p += '=' }
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($p)) | ConvertFrom-Json | Select aud, iss, scp, upn, exp
```

- Troubleshooting: `AADSTS65001` or `AADSTS70011` means the Azure CLI is not pre-authorized for the API scope; "az failed. Run: az login" means not signed in or the session expired; "token aud is ..." means a different API than expected (compare `Scope` and `ExpectedAud` with a real token's claims); works in a terminal but fails in the tool means `az` is not on the tool's PATH.
