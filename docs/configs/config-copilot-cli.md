# GitHub Copilot CLI: BYOK with an Entra-issued token and no vendor network access

## Summary

This configuration runs GitHub Copilot CLI against your own gateway using bring-your-own-key (BYOK) models. No GitHub sign-in is needed, and with offline mode on the CLI makes no network requests other than to the gateway. Entra-issued tokens are supplied through the local token proxy (Appendix B), which gets tokens from the helper command (Appendix A), because the CLI has no native token-command setting. GitHub-hosted models and Copilot Fusion are not available in this configuration.

## Applies to

| Item | Value |
|---|---|
| Product | GitHub Copilot CLI |
| Version | 1.0.105 (npm package `@github/copilot`) |
| Operating system | Windows 11. Other operating systems: not documented here |
| Provider file | `providers.json`. Default folder `~/.copilot` (on Windows `%USERPROFILE%\.copilot`). Override the path with `COPILOT_PROVIDERS_CONFIG` |
| Environment variables | `COPILOT_PROVIDERS_CONFIG`, `COPILOT_OFFLINE` |
| Scope | User. The file takes precedence over provider environment variables |

## Prerequisites

1. Copilot CLI installed and on the `PATH` (`copilot --version` prints the version).
2. A gateway endpoint that implements the OpenAI Responses API (set `wireApi` to `responses`) or the OpenAI Chat Completions API (the default). `azure` and `anthropic` provider types also exist.
3. A model behind that endpoint that supports tool calling and streaming. The CLI requires both.
4. The local token proxy running on the workstation (Appendix B at the end of this guide), which obtains Entra tokens through the token helper command (Appendix A).
5. No GitHub token set in the environment (see the table below).

## Authentication: how the token reaches the gateway

Method: local token proxy with a placeholder key in `providers.json`.

- Copilot CLI sends the configured key as `Authorization: Bearer <key>`.
- `providers.json` holds a static `apiKey` (or `bearerToken`, which is used instead of `apiKey`). A command that fetches a fresh token is not documented, so the CLI cannot refresh an expiring Entra token by itself.
- Point `baseUrl` at the local token proxy and set `apiKey` to any non-empty placeholder. The proxy discards that value and sends a fresh Entra JWT to the gateway on every request, retrying once if the gateway returns 401.
- Values in `providers.json` are plain text. A value such as `$MY_API_KEY` is treated as literal text and is not read from the environment.
- Custom request headers: not documented.
- If the gateway needs no token (for example, a private network), omit `apiKey`.

## Provider and model configuration

File: `~/.copilot/providers.json` (or the path in `COPILOT_PROVIDERS_CONFIG`).

```json
{
  "providers": [
    {
      "name": "apim",
      "type": "openai",
      "baseUrl": "http://127.0.0.1:<proxy-port>/<apim-api-path>/v1",
      "apiKey": "<any-non-empty-placeholder>",
      "wireApi": "responses"
    }
  ],
  "models": [
    {
      "id": "<deployment-name>",
      "provider": "apim",
      "maxPromptTokens": 100000,
      "maxOutputTokens": 8000
    }
  ]
}
```

Provider fields: `name` (required, unique), `type` (`openai` by default, `azure` or `anthropic`), `baseUrl`, `apiKey`, `bearerToken`, `wireApi` (`responses` for the OpenAI or Azure Responses API, default `completions`), and for Azure an `azure.apiVersion`.

Model fields: `id`, `provider` (must equal a provider `name`), optional `wireModel` (the deployment name or the provider's own model name when `id` is a custom label), optional `modelId` (a model name the CLI recognizes, used for capabilities and limits), `maxPromptTokens` and `maxOutputTokens` (whole numbers greater than zero). For an unknown model the CLI can default to a 128,000 token prompt limit.

URL rule: with `wireApi` set to `responses`, requests go to `<baseUrl>/responses`. The gateway must expose that path under the API prefix you put in `baseUrl`.

Select the model when starting a session: `copilot --model <provider-name>/<model-id>`, for example `copilot --model apim/<deployment-name>`.

## Disabling login, telemetry and background network calls

| Setting | Where | Value | Default | Effect |
|---|---|---|---|---|
| `COPILOT_OFFLINE` | Environment variable | `true` | Unset | No GitHub authentication is attempted. The CLI only makes network requests to the configured BYOK provider. Telemetry is fully disabled. |
| `COPILOT_GITHUB_TOKEN`, `GH_TOKEN`, `GITHUB_TOKEN` | Environment variables | Leave unset | Unset | These are the GitHub authentication variables, in that precedence order. They are not needed for BYOK. |
| `COPILOT_PROVIDERS_CONFIG` | Environment variable | Path to `providers.json` | `~/.copilot` folder | Selects the provider file. The file takes precedence over provider environment variables. |
| `--experimental`, `/experimental on` | CLI flag or command | Do not enable | Off | Enables experimental features, including Copilot Fusion models, which need GitHub. |

PowerShell session setup:

```powershell
Remove-Item Env:GH_TOKEN, Env:GITHUB_TOKEN, Env:COPILOT_GITHUB_TOKEN -ErrorAction SilentlyContinue
$env:COPILOT_PROVIDERS_CONFIG = "$env:USERPROFILE\.copilot\providers.json"
$env:COPILOT_OFFLINE = "true"
copilot --model apim/<deployment-name>
```

## Network behaviour with this configuration

| Situation | Hosts the CLI contacts |
|---|---|
| Offline mode on | Only the host in `baseUrl` (the local token proxy, which then contacts the gateway and the Entra token endpoint) |
| Offline mode off, BYOK model selected, signed out | `api.github.com`, `api.individual.githubcopilot.com`, `telemetry.individual.githubcopilot.com`, plus the `baseUrl` host. The BYOK request still succeeds, and telemetry is sent normally. |
| GitHub device sign-in (not used here) | `github.com/login/device` |

Allow: the `baseUrl` host only. Block: the three GitHub hosts above (nothing in this configuration needs them).

Offline mode is only fully air-gapped if the BYOK provider is local or inside the same isolated environment. If `baseUrl` points to a remote endpoint, prompts and code context are still sent to it.

## Effects and limits of this configuration

- GitHub-hosted models are not available. Selecting Copilot Fusion while signed out is sent to GitHub and rejected with `400 The requested model is not supported`. Fusion routing decisions run in GitHub's cloud.
- Without GitHub authentication, `/delegate`, the GitHub MCP server and GitHub Code Search are unavailable.
- A BYOK model is not automatically eligible for Copilot Fusion.
- Models must support tool calling and streaming.
- `providers.json` stores keys in plain text. Restrict access to the file.
- The CLI cannot refresh an expiring token itself. A static `bearerToken` expires with the token, so use the token proxy.
- Telemetry is disabled only in offline mode. With offline mode off, BYOK still sends telemetry normally.

## Confirming it works

1. Set the environment variables above in a new terminal.
2. Run `copilot --model apim/<deployment-name> -p "Reply with the single word: ok"`.
3. The reply text should print and the CLI should exit.
4. In the gateway log, expect one `POST <api-path>/responses` request carrying `Authorization: Bearer <JWT>` with the audience, issuer and expiry your gateway policy requires.
5. With offline mode on, no other outbound connection from the CLI should appear.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `Execution failed: 400 The requested model is not supported` | A GitHub-hosted or Fusion model was selected. Use `--model <provider-name>/<model-id>`. |
| The CLI asks to sign in | `COPILOT_OFFLINE` is not set, or a GitHub-hosted model was chosen. Set offline mode and select the BYOK model. |
| Model name not recognized | The `provider` value in `models[]` does not match a provider `name`, or the file is not the one in use. Check `COPILOT_PROVIDERS_CONFIG`. |
| 401 from the gateway | The token proxy is not running or its helper failed. Check that the proxy is running and that the helper command in Appendix A prints a token when run by hand. |
| 404 from the gateway | The path after `baseUrl` does not match a gateway operation. Check the API prefix and `wireApi`. |
| Key not picked up from an environment variable | Values in `providers.json` are literal text. Put the value in the file or use the token proxy. |
| Requests to GitHub hosts still appear | Offline mode is not set in the shell that started the CLI. |

## References

- Adding LLM models to GitHub Copilot CLI: https://docs.github.com/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models
- Authenticating Copilot CLI and offline mode: https://docs.github.com/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli
- Discover local models in Copilot CLI: https://github.blog/changelog/2026-10-07-discover-local-models-in-github-copilot-cli
- Copilot Fusion: https://docs.github.com/copilot/concepts/models/copilot-fusion

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

## Appendix B: Local token proxy

This appendix is part of this guide. It is a small program that lets a tool that can only send a static key use an expiring Entra token. Use it wherever this guide calls for the proxy.

**What it does.** It listens on 127.0.0.1, replaces whatever credential the client sends with a fresh Entra ID JWT obtained from a helper command (Appendix A), forwards the request to the gateway, and streams the response back. The client is given any non-empty key; the proxy supplies the real token. It makes no network calls other than to the gateway and to the helper command, and has no telemetry or login of its own.

**Requirements.** Python 3.9 or later and the `aiohttp` package (`pip install aiohttp`); the helper command from Appendix A and one `az login`; the gateway URL.

**Run.**

```powershell
python proxy.py --upstream https://<apim-host> --port 18081 --margin-s 300 -- powershell -NoProfile -File C:\Users\<you>\bin\get-apim-token.ps1
```

| Argument | Meaning | Default |
|---|---|---|
| `--upstream` | Base URL of the gateway. The request path and query from the client are appended to it | required |
| `--port` | Local port, bound to 127.0.0.1 | 18081 |
| `--margin-s` | A cached token is reused until fewer than this many seconds remain before expiry | 300 |
| `--local-key` | Optional shared key clients must send | none |
| `--` command | Helper command that prints the JWT on standard output | required |

Point the client at `http://127.0.0.1:<port>/<same path as the gateway URL>` and give it any non-empty key.

**Behaviour.**

- For each request it removes the client's `Authorization`, `x-api-key` and `api-key` headers and the hop-by-hop headers, then sends `Authorization: Bearer <jwt>` to the gateway.
- The token comes from the helper command (30 second limit). The proxy reads the `exp` claim (it does not verify the signature) and reuses the token until it is within `--margin-s` seconds of expiry.
- If the gateway answers 401, the proxy fetches a new token and retries once.
- If the helper fails, the client receives HTTP 502 with `{"error": "token helper failed", "detail": "<helper message>"}`; the next request runs the helper again, so it recovers without a restart.
- Responses are streamed, so server-sent events pass through. Redirects are not followed.
- `GET /_proxy/health` returns `{"ok": true, "token_fetches": <n>}`.
- It writes no logs and does not record tokens.

**Security.** It binds to the loopback address only, but any process running as the same user can use it, which is the same exposure as running `az account get-access-token`. `--local-key` makes it require a shared key.

**Source (proxy.py).**

```python
"""Local token-injecting reverse proxy for tools that can only send a static key (VS Code Copilot BYOK, JetBrains, ...).

Clients send any dummy key to http://127.0.0.1:<port>; the proxy replaces Authorization with a fresh JWT obtained from a
helper command, streams the response back, and retries once on an upstream 401 with a forced token refresh.

usage: proxy.py --upstream https://<apim>.azure-api.net [--port 18081] [--margin-s 300] [--local-key K] -- <helper cmd...>
"""
import argparse
import asyncio
import base64
import json
import sys
import time

from aiohttp import ClientSession, ClientTimeout, web

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
       "transfer-encoding", "upgrade", "host", "content-length"}
DROP_IN = {"authorization", "x-api-key", "api-key"}


class TokenSource:
    def __init__(self, cmd, margin):
        self.cmd, self.margin, self.tok, self.exp, self.lock, self.fetches = cmd, margin, None, 0, asyncio.Lock(), 0

    async def get(self, force=False):
        async with self.lock:
            if not force and self.tok and self.exp - time.time() > self.margin:
                return self.tok
            p = await asyncio.create_subprocess_exec(*self.cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await asyncio.wait_for(p.communicate(), 30)
            if p.returncode != 0:
                raise RuntimeError(err.decode(errors="replace").strip() or f"helper exited {p.returncode}")
            tok = out.decode().strip()
            seg = tok.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))
            self.tok, self.exp, self.fetches = tok, claims["exp"], self.fetches + 1
            return tok


def make_app(upstream, tokens, local_key):
    async def handler(request):
        if request.path == "/_proxy/health":
            return web.json_response({"ok": True, "token_fetches": tokens.fetches})
        if local_key:
            sent = request.headers.get("x-api-key") or request.headers.get("api-key") or \
                   request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if sent != local_key:
                return web.json_response({"error": "bad local key"}, status=401)
        body = await request.read()
        fwd = {k: v for k, v in request.headers.items() if k.lower() not in HOP | DROP_IN}
        url = upstream.rstrip("/") + request.path_qs
        sess = request.app["sess"]
        for attempt in (0, 1):
            try:
                tok = await tokens.get(force=attempt == 1)
            except Exception as e:  # noqa: BLE001
                return web.json_response({"error": "token helper failed", "detail": str(e)}, status=502)
            async with sess.request(request.method, url, data=body or None,
                                    headers={**fwd, "Authorization": f"Bearer {tok}"}, allow_redirects=False) as up:
                if up.status == 401 and attempt == 0:
                    continue
                resp = web.StreamResponse(status=up.status,
                                          headers={k: v for k, v in up.headers.items() if k.lower() not in HOP})
                await resp.prepare(request)
                async for chunk in up.content.iter_any():
                    await resp.write(chunk)
                await resp.write_eof()
                return resp

    async def on_start(app):
        app["sess"] = ClientSession(auto_decompress=False, timeout=ClientTimeout(total=None, sock_connect=15))

    async def on_stop(app):
        await app["sess"].close()

    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.on_startup.append(on_start)
    app.on_cleanup.append(on_stop)
    app.router.add_route("*", "/{tail:.*}", handler)
    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", required=True)
    ap.add_argument("--port", type=int, default=18081)
    ap.add_argument("--margin-s", type=int, default=300)
    ap.add_argument("--local-key")
    ap.add_argument("helper", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = [x for x in a.helper if x != "--"]
    web.run_app(make_app(a.upstream, TokenSource(cmd, a.margin_s), a.local_key), host="127.0.0.1", port=a.port, print=lambda *_: None)


if __name__ == "__main__":
    sys.exit(main())

```
