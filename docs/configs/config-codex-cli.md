# Codex CLI: BYOK with an Entra-issued token and no vendor network access

## Summary

Codex CLI sends model requests to an OpenAI-Responses-compatible gateway (for example an Azure API Management endpoint) and obtains a fresh Entra ID JWT from a command configured in `config.toml`. No ChatGPT sign-in is needed. A set of feature flags and the analytics key stops the calls Codex otherwise makes to chatgpt.com and github.com.

## Applies to

| Item | Value |
|---|---|
| Product | Codex CLI |
| Versions | 0.153.2. A provider that sets both `auth` and `env_key` is rejected at load |
| OS | Windows (the helper is PowerShell) |
| Config locations | `%USERPROFILE%\.codex\config.toml` (user). `CODEX_HOME` relocates the folder (default `~/.codex`). A project `.codex\config.toml` ignores `model_provider`, `model_providers`, `openai_base_url`, `chatgpt_base_url`, `notify`, `profile` and `otel` |
| Scope used here | User |

## Prerequisites

1. A gateway that exposes the OpenAI Responses API: `POST <base_url>/responses` with server-sent events. `wire_api = "responses"` is the only documented value.
2. A gateway policy that reads the JWT from the `Authorization: Bearer` header.
3. The helper script in Appendix A (saved as `C:\Users\<you>\bin\get-apim-token.ps1`), an Entra app registration for the gateway's API as described there, the Azure CLI, and one `az login` per user.
4. The model (deployment) name served by the gateway.
5. Codex CLI installed.

## Authentication: how the token reaches the gateway

Method: a command-backed token in `[model_providers.<id>.auth]`. Save the helper script from Appendix A as `C:\Users\<you>\bin\get-apim-token.ps1` (replace the placeholders in its first two variables), run `az login` once, and point `command` and `args` at the script. Codex runs the command when it needs a bearer token and sends the printed value as `Authorization: Bearer <token>`.

```toml
[model_providers.apim.auth]
command = "powershell"
args = ["-NoProfile", "-File", 'C:\Users\<you>\bin\get-apim-token.ps1']
timeout_ms = 15000
refresh_interval_ms = 1800000
```

| Key | Meaning | Default |
|---|---|---|
| `command` | Command run when a token is needed. It must print the token on stdout and receives no stdin | none |
| `args` | Arguments for the command | none |
| `timeout_ms` | Maximum command run time | 5000 |
| `refresh_interval_ms` | How often Codex refreshes the token proactively. `0` refreshes only after an authentication retry | 300000 |
| `cwd` | Working directory for the command | not stated |

Behaviour:

- Codex trims whitespace around the output; an empty token is an error.
- Set `timeout_ms` above the real helper time. With the default 5000 and a 6 second helper, Codex fails with "timed out after 5000 ms" and keeps retrying.
- A short `refresh_interval_ms` gives a fresh token for every request. With a long interval or `0`, an expired token gets one 401, the helper runs again and the request is retried with the new token. A 401 on a fresh token also triggers a helper re-run and a retry.
- A failing helper is run about 30 times in 25 seconds before Codex gives up, and the helper's stderr line is printed in Codex's error output.
- Do not combine the `auth` table with `env_key`, `experimental_bearer_token` or `requires_openai_auth`. Codex refuses to load the config ("provider auth cannot be combined with env_key").
- The provider id cannot be `openai`, `ollama` or `lmstudio`.
- Quote Windows paths in single quotes in TOML so backslashes need no escaping.

## Provider and model configuration

Complete `config.toml` (top-level keys come before any table):

```toml
model = "<deployment-name>"
model_provider = "apim"

[model_providers.apim]
name = "Azure APIM"
base_url = "https://<apim-host>/<openai-responses-api-path>"
wire_api = "responses"
# Only if the gateway needs them:
# query_params = { api-version = "<version>" }
# http_headers = { "Ocp-Apim-Subscription-Key" = "<subscription-key>" }

[model_providers.apim.auth]
command = "powershell"
args = ["-NoProfile", "-File", 'C:\Users\<you>\bin\get-apim-token.ps1']
timeout_ms = 15000
refresh_interval_ms = 1800000
```

- `query_params` and `http_headers` are added to every request to the provider, including the model list call. `env_http_headers` populates headers from environment variables.
- Codex requests `GET <base_url>/models?client_version=<version>` several times at startup and expects `{"models": [...]}`. A gateway that returns the usual `{"data": [...]}` list produces a non-fatal "failed to decode models response" error and a "Model metadata for `<model>` not found" warning, and Codex continues with generic metadata. `model_catalog_json` (a local catalog path) is documented; whether it suppresses the remote model call is not documented.
- Then Codex sends `POST <base_url>/responses` with streaming.
- Request retries and timeouts: `request_max_retries` (default 4), `stream_max_retries` (default 5), `stream_idle_timeout_ms` (default 300000).

## Disabling login, telemetry and background network calls

Add these keys near the top of `config.toml`, before any `[table]` header (inline tables are used so that no ordering problem arises):

```toml
features = { plugins = false, remote_plugin = false, plugin_sharing = false, apps = false, in_app_updates = false }
analytics = { enabled = false }
```

| Setting | Where | Value | Default | Effect |
|---|---|---|---|---|
| `features.plugins`, `features.remote_plugin`, `features.plugin_sharing`, `features.apps`, `features.in_app_updates` | config.toml | `false` | stable, on | Stops the plugin catalog and curated plugin sync (chatgpt.com and github.com), app and connector integration and in-app updates. Which single flag matters most is not established |
| `analytics.enabled` | config.toml | `false` | unset (client default applies) | Disables anonymous usage and health data. Also disables custom OTLP metrics exporters |
| `feedback.enabled` | config.toml | `false` | true | Rejects `/feedback` submissions (user-initiated). Documented, effect not confirmed |
| `otel.metrics_exporter` | config.toml | `"none"` | `"statsig"` | Disables metrics export independently of logs and traces. Documented, effect not confirmed |
| `otel.exporter`, `otel.trace_exporter` | config.toml | `"none"` | none for `exporter` | OpenTelemetry log and trace export is off unless configured. Documented |
| `web_search` | config.toml | `"disabled"` | `"cached"` | Removes the web search tool. Full-access sandbox mode defaults to live. Documented, effect not confirmed |
| `mcp_servers.<id>.enabled` | config.toml | `false` | true | Disables one MCP server without removing its configuration. Documented |
| `check_for_update_on_startup` | config.toml | `false` | not stated | Stops the update check. The documentation advises setting it to false only when updates are centrally managed |
| `history.persistence` | config.toml | `"none"` | `"save-all"` | Local only: no history is written. No network effect |
| `forced_login_method` | config.toml | `"api"` | not stated | Restricts authentication to an API method. Whether it avoids chatgpt.com calls is not stated |

Optional extra keys, all documented but not confirmed against startup traffic:

```toml
web_search = "disabled"
feedback = { enabled = false }
otel = { exporter = "none", metrics_exporter = "none" }
```

- Any key can be overridden for one run with `-c key=value` (documented as a generic override; no example for these keys is given).
- No environment variable or command-line flag is documented to disable analytics, updates, feedback or the plugin sync, and there is no single offline switch.
- Login: with a custom provider and a command-backed token no ChatGPT sign-in screen or prompt appears.

## Network behaviour with this configuration

- Default: connections to `chatgpt.com` (including `ab.chatgpt.com`) and to `github.com` and `api.github.com` (curated plugin sync through `git`).
- After the keys above: no connection outside the gateway was opened during a prompt.
- TLS inspection: `CODEX_CA_CERTIFICATE` and `SSL_CERT_FILE` set CA bundles.
- With every host except the gateway refused, model requests still succeed.
- Allow: the gateway host and the Entra endpoints used by `az login`. Block the rest.
- Local sandboxed commands have network access off by default (`sandbox_workspace_write.network_access = false`); that setting does not govern Codex's own calls.

## Effects and limits of this configuration

- Plugins, app and connector integrations and in-app updates are unavailable.
- Anonymous usage data is not sent; `/feedback` is unavailable only if `feedback.enabled = false` is set.
- Model metadata for deployment names is not discovered when the `/models` shape differs, so Codex uses generic metadata.
- Only the Responses wire format is supported for a custom provider.
- Hosted tools (web search, MCP, apps) are not governed by the sandbox network settings.

## Confirming it works

1. Run the helper script from Appendix A by hand (`powershell -NoProfile -File C:\Users\<you>\bin\get-apim-token.ps1`) and check that it prints one long `eyJ...` line.
2. Run `codex` (or `codex exec "<prompt>"`), send a short prompt and confirm a reply.
3. In the gateway log expect `GET <path>/models` calls and a `POST <path>/responses`, each with `Authorization: Bearer <jwt>`. A `/models` decode error in Codex's output is expected unless the gateway mimics Codex's model list shape.
4. The JWT claims (audience, issuer, expiry) match the gateway policy.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| "timed out after N ms" | `timeout_ms` is shorter than the helper. Raise it (15000) |
| "provider auth cannot be combined with env_key" | Remove `env_key`, `experimental_bearer_token` and `requires_openai_auth` from the provider |
| Many helper runs, then failure | The helper fails (not signed in or wrong audience). Read the stderr line Codex prints and run `az login` |
| 401 from the gateway | Wrong audience or issuer, expired token, or a policy that needs an extra header (`http_headers`) |
| "failed to decode models response" | Gateway `/models` shape differs from Codex's. Non-fatal |
| Helper works in a terminal but not in Codex | `az` is not on Codex's PATH. Use the full path to `az.cmd` in the helper script (Appendix A) |
| `AADSTS65001` or `AADSTS70011` from the helper | The Azure CLI is not pre-authorized for the API scope. See the prerequisites in Appendix A |
| Provider config ignored | Provider settings in a project `.codex\config.toml` are ignored. Use the user file |

## References

- https://developers.openai.com/codex/config-advanced
- https://learn.chatgpt.com/docs/config-file/config-reference
- https://learn.chatgpt.com/docs/config-file/config-basic
- https://learn.chatgpt.com/docs/config-file/environment-variables

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
