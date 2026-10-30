# Entra token helper: a command that prints a fresh JWT for an APIM gateway

## Summary

A short PowerShell script that asks the Azure CLI for an Entra ID access token for the gateway's API, checks the token, and prints only the raw JWT on stdout. It is the shared credential source for tools that can run a command to obtain a token (Claude Code `apiKeyHelper`, Codex `[model_providers.<id>.auth]`) and for a local proxy program that substitutes a fresh token for a static key. The user signs in once with `az login`; the Azure CLI renews tokens silently. The script never prompts and never writes the token to disk.

## Applies to

| Item | Value |
|---|---|
| Component | `get-apim-token.ps1`, run with Windows PowerShell 5.1 (`powershell`) or PowerShell 7 |
| Requires | Azure CLI (`az account get-access-token --scope ...` is supported, for example in 2.91.0) |
| OS | Windows |
| Config locations | Save as `C:\Users\<you>\bin\get-apim-token.ps1`. The Azure CLI keeps its own sign-in state in its own folder (`AZURE_CONFIG_DIR` relocates it) |
| Scope | User |

## Prerequisites

1. An Entra app registration that represents the APIM API, with an Application ID URI such as `api://<apim-app-id>`. The APIM `validate-jwt` policy checks the `aud` and `iss` claims of tokens for that app.
2. The Azure CLI may request a token for that API: either pre-authorize the Azure CLI client ID `04b07795-8ddb-461a-bbee-02f9e1bf7b46` under "Expose an API" on the app registration, or have an administrator grant consent. Without this, `az` fails with `AADSTS65001` or `AADSTS70011`.
3. The Azure CLI installed, and one `az login` per user. Renewal is silent, subject to the tenant's Conditional Access sign-in frequency; the user runs `az login` again when that expires.
4. Know the audience value of the tokens your gateway expects. Tokens issued under the v1 and v2 endpoints can carry different `aud` values (an `api://` URI or an app ID). List every value your tokens can carry in `$ExpectedAud` (the helper accepts a list). For reference, a token for the Azure Resource Manager scope is about 2,400 characters, lives about 80 minutes, is a version 1.0 token, and has `aud` `https://management.azure.com` with no trailing slash; fetching it with the Azure CLI takes about 1 to 1.3 seconds.

## Authentication: how the token reaches the gateway

The script is the credential source, not the transport. Each harness runs it and sends the printed value to the gateway as a bearer token.

Script (replace `<apim-app-id>` in the first two variables):

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

Guards and why they exist:

- The stdout filter keeps only the line that looks like a JWT. A banner or warning on stdout otherwise makes both Claude Code and Codex send no usable credential.
- The audience check fails fast with a clear message. A token for the wrong audience otherwise produces 401 responses that Claude Code retries for minutes and Codex retries for tens of seconds.
- The lifetime check (`$MinLifeSecs`, 60 seconds) refuses a token that is about to expire.
- All messages go to stderr; stdout carries only the token. Claude Code and Codex show the stderr line when the helper fails.

Exit codes and messages:

| Exit | Output | Meaning |
|---|---|---|
| 0 | the JWT on stdout, no trailing newline | success |
| 1 | `get-apim-token: az failed (exit N). Run: az login` on stderr | `az` returned an error, for example not signed in |
| 1 | `get-apim-token: az output contained no JWT` on stderr | `az` printed no token-shaped line |
| 1 | `get-apim-token: token aud is '<aud>', expected '<expected>'` on stderr | wrong audience |
| 1 | `get-apim-token: token expires in <N>s` on stderr | token has less than 60 seconds left |

## Provider and model configuration

Not applicable: this component holds no model configuration. How each harness calls it:

| Harness | How it is called |
|---|---|
| Claude Code CLI and extension | `"apiKeyHelper": "powershell -NoProfile -File C:\\Users\\<you>\\bin\\get-apim-token.ps1"` in `settings.json` |
| Codex CLI and extension | `command = "powershell"` and `args = ["-NoProfile", "-File", 'C:\Users\<you>\bin\get-apim-token.ps1']` in `[model_providers.<id>.auth]`, with `timeout_ms = 15000` |
| A local proxy program | Positional command after `--`: `powershell -NoProfile -File C:\Users\<you>\bin\get-apim-token.ps1` |

## Disabling login, telemetry and background network calls

| Setting | Where | Value | Default | Effect |
|---|---|---|---|---|
| Interactive prompts | script | none | n/a | The script never prompts. Sign-in happens only through `az login` |
| `AZURE_CONFIG_DIR` | environment | folder path | `%USERPROFILE%\.azure` | Keeps the Azure CLI's sign-in state in a separate folder |
| Azure CLI telemetry | Azure CLI | not covered here | not stated | The Azure CLI's own telemetry settings are outside this script; not documented in the sources reviewed |

The script makes no network call itself. `az account get-access-token` contacts Entra endpoints when it needs to renew a token.

## Network behaviour with this configuration

- The helper runs locally and prints to a pipe. The token is not written to a file by the script.
- Network use is the Azure CLI's: Microsoft Entra sign-in and token endpoints, only when a new token is needed.
- Allow the Entra endpoints your tenant uses for sign-in and token renewal. The exact host list for a real tenant was not established.

## Effects and limits of this configuration

- Latency: when not signed in, `az account get-access-token` exits with an error in about 0.6 seconds and the helper reports it in about 0.8 seconds. `az` start-up on its own takes a few seconds. The time to fetch a token on a real tenant is not established; set the calling tool's timeout above it (Codex `timeout_ms` default is 5000 and must be raised).
- GUI-launched hosts (VS Code started from the Start menu or desktop) may not have `az` on their PATH. Replace `az` with the full path to `az.cmd`: `(Get-Command az).Source`.
- A token is valid for the period set by the tenant (typically 60 to 90 minutes). Set cache or refresh intervals in the calling tool below the token lifetime.
- The Azure CLI stores its sign-in state in its own folder. How it encrypts that state is not covered here.
- The script does not cache tokens itself; each run asks the Azure CLI, which returns a cached token until it is near expiry.

## Confirming it works

1. Run `az login`, then `powershell -NoProfile -File C:\Users\<you>\bin\get-apim-token.ps1`. Expect one long line starting `eyJ` and nothing else.
2. Check the claims locally (do not paste tokens into online decoders):

```powershell
$t = & powershell -NoProfile -File C:\Users\<you>\bin\get-apim-token.ps1
$p = $t.Split('.')[1].Replace('-','+').Replace('_','/'); while ($p.Length % 4) { $p += '=' }
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($p)) | ConvertFrom-Json | Select aud, iss, scp, upn, exp
```

3. Sign out (`az logout`) and run the script again. Expect exit code 1 and one stderr line `get-apim-token: az failed (exit 1). Run: az login`.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `AADSTS65001` or `AADSTS70011` | The Azure CLI is not pre-authorized or consented for the API scope. See Prerequisites |
| "az failed. Run: az login" | Not signed in, or the session expired (Conditional Access). Run `az login` |
| "token aud is ..." | The token is for a different API. Check `$Scope` and `$ExpectedAud` against the claims of a real token |
| Works in a terminal, fails in the tool | `az` is not on the tool's PATH. Use the full path to `az.cmd` |
| The tool reports an empty or invalid credential | Something other than the JWT reached stdout. The filter removes banners; check for a different `az` wrapper |
| Tool timeout | `az` takes longer than the tool's helper timeout. Raise the timeout |

## References

- https://learn.microsoft.com/en-us/cli/azure/account#az-account-get-access-token
- https://learn.microsoft.com/en-us/azure/api-management/validate-jwt-policy
- https://code.claude.com/docs/en/llm-gateway-connect
- https://developers.openai.com/codex/config-advanced



