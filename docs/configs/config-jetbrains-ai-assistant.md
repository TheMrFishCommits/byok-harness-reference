# JetBrains AI Assistant: BYOK with an Entra-issued token and no vendor network access

## Summary

This configuration points the JetBrains AI Assistant OpenAI-compatible provider at the local token proxy (Appendix B, which gets tokens from the helper command in Appendix A), which forwards requests to your gateway with a fresh Entra token. No JetBrains account or JetBrains AI subscription is needed for this provider. The gateway must serve the OpenAI Chat Completions API and a model list, and a model must be assigned to the AI Assistant features before chat works. Expect about a dozen model calls per chat prompt.

## Applies to

| Item | Value |
|---|---|
| Product | JetBrains AI Assistant (plugin `com.intellij.ml.llm`), documentation version 2026.2 |
| IDE | PyCharm 2026.2.3 (build PY-262.10968.92). The documentation lists CLion, DataGrip, DataSpell, GoLand, IntelliJ IDEA, PhpStorm, PyCharm, Rider, RubyMine, RustRover and WebStorm |
| Operating system | Windows 11. Other operating systems: not documented here |
| Where it is configured | IDE settings: Settings > Tools > AI Assistant > Providers & API keys, section Third-party AI providers (Beta) |
| Where the values are stored | Not documented |
| Scope | Not documented |

## Prerequisites

1. The AI Assistant plugin installed and enabled in the IDE.
2. A gateway endpoint that implements the OpenAI Chat Completions API with streaming, and a model list endpoint that returns the OpenAI list shape. The Responses API is not used for chat.
3. A model behind that endpoint that supports tool calling (the Tool calling checkbox is on by default).
4. The local token proxy running on the workstation (Appendix B at the end of this guide), which obtains Entra tokens through the token helper command (Appendix A). If the proxy speaks plain HTTP/1.1, select HTTP/1.1 in the provider settings.
5. An organization that has not disabled custom models. Organizations managed by JetBrains IDE Services or JetBrains Central can have an administrator set the provider or disable custom models.

## Authentication: how the token reaches the gateway

Method: local token proxy with a placeholder API key.

- The OpenAI-compatible provider sends `Authorization: Bearer <API key>`. It sends no `x-api-key` header.
- The form has no custom header setting and no command that fetches a token. The key is static.
- Because Entra tokens expire, set the provider URL to the local token proxy and enter any non-empty value as the API key. The proxy discards that value and sends a fresh Entra JWT to the gateway on each request, retrying once if the gateway returns 401.
- The client identifies itself as `ktor-client`.
- With this provider, prompts and context go directly from the IDE to the provider URL. JetBrains is not in that path. The IDE shows a Data Sharing with Third-Party AI Service Providers confirmation when you choose a third-party provider: data may be sent to the hosts in the provider settings, and JetBrains disclaims responsibility for it. The confirmation can appear more than once.

## Provider and model configuration

In the IDE:

1. Open Settings > Tools > AI Assistant > Providers & API keys.
2. In Third-party AI providers (Beta), open the provider dropdown. Options: None, Gemini API key, Google Vertex AI, Anthropic, OpenAI-compatible, OpenAI, LM Studio, Ollama. Choose OpenAI-compatible and accept the Data Sharing confirmation.
3. Enter the URL (see the URL rule below).
4. Enter the API Key (the field is masked): any non-empty placeholder.
5. Leave the HTTP version on HTTP/2 (the default) or select HTTP/1.1. A plain-HTTP local proxy that speaks HTTP/1.1 needs HTTP/1.1. Plain-text HTTP/2 was not tried.
6. Leave Tool calling ticked (the default) if the model supports it and you want MCP tool calls.
7. Choose Test Connection. It reports Connected and requests the model list twice.
8. Assign a model under Model Assignment. This step is required (see below). In small dialogs, scroll down to reach Test Connection and Model Assignment.

URL rule. The plugin appends only the endpoint name to the URL you enter. It does not add `/v1`. If the URL is `http://127.0.0.1:<proxy-port>/<apim-api-path>`, the plugin requests `<apim-api-path>/models`. If the URL ends in `/v1`, it requests `/v1/models` and `/v1/chat/completions` under that path. Include `/v1` (or whatever prefix your gateway uses) in the URL.

API used. Chat uses the OpenAI Chat Completions API with `stream: true` and the header `Accept: application/json,text/event-stream`. The model list is `GET <url>/models`, and the response must have the OpenAI shape `{"object":"list","data":[{"id":"<model-id>"}]}`.

Model assignment is required. After Test Connection reports Connected, chat still answers No compatible model is available for Chat mode until a model is assigned. Under Model Assignment, set the Core features and Instant helpers dropdowns. They list the models returned by `GET <url>/models`, shown as `OpenAIAPI/<model-id>`.

Alternative entry point: the AI Chat starting screen lists OpenAI-compatible, LM Studio and Ollama and asks for Base URL, Key and Model, then Continue.

Code completion is separate. It uses JetBrains models unless you configure the AI Completion section (OpenAI Compatible), which has API key, Base URL, Model, Model context, Max output tokens and Prompt schema.

## Disabling login, telemetry and background network calls

| Setting | Value | Default | Effect |
|---|---|---|---|
| JetBrains account or AI subscription | Not required | Not signed in | The OpenAI-compatible provider works without a JetBrains account or subscription. |
| Activate JetBrains AI | Skip | Not activated | Optional. Activating it alongside BYOK lets JetBrains AI cover features custom models do not support. |
| Start Free Trial button | Ignore | Shown | Optional. |
| Data Sharing (first-start dialog, or Settings > Appearance & Behavior > System Settings > Data Sharing) | Don't Send | Asked at first start | Declines anonymous usage statistics. The dialog states that the choice applies to all installed JetBrains products. |
| User Agreement (first-start dialog) | Accept | Asked at first start | Required to start the IDE. |
| Data Sharing with Third-Party AI Service Providers | Confirm | Asked when a third-party provider is chosen | Confirms that data may be sent to the hosts in the provider settings. May appear more than once. |
| Update, plugin and licence network calls | Not documented here | Not documented | Not documented, effect not confirmed. |

No JetBrains setting for AI Assistant telemetry, error reporting or a single offline mode is documented.

## Network behaviour with this configuration

- With the third-party provider configured, an idle IDE and an IDE during chat made no external connections. The IDE starts a local child process, `embeddings-server.exe`.
- Allow: the provider URL host (the local token proxy). The proxy then contacts the gateway and the Entra token endpoint.
- Default JetBrains cloud behaviour with no provider configured was not measured beyond an idle IDE at the welcome screen, which made no external connections. Hosts for IDE updates, the plugin repository and licensing are not documented here; block them only after checking what your organization needs.
- Local models (Ollama, LM Studio) run on the machine and need no key. Agents cannot use local models, and AI Assistant cannot call MCP tools with local models.

## Effects and limits of this configuration

- One chat prompt produces about twelve calls to `POST <url>/chat/completions`: one chat call that carries 35 tool definitions, and about eleven background calls without tools (helper tasks such as titles and summaries). Size gateway rate limits and cost for roughly a dozen model calls per prompt.
- A model must be assigned under Model Assignment before chat works. Models from OpenAI-compatible endpoints are not assigned automatically.
- The gateway must serve the Chat Completions API. A gateway that only serves the Responses API does not work for chat.
- No custom HTTP headers and no token command, so the token proxy is required for Entra tokens.
- Code completion uses JetBrains models unless the AI Completion section is configured separately.
- Features that rely on specific models are limited. Anthropic, Google and OpenAI models are assigned automatically from fixed lists, while OpenAI-compatible endpoints need manual assignment.
- BYOK usage is billed by the provider, not by JetBrains AI credits.
- An administrator using JetBrains IDE Services or JetBrains Central can set the provider or disable custom models.
- Free-tier JetBrains AI is not available in the Community editions of PyCharm and IntelliJ IDEA; the documentation states no product or version requirement for BYOK itself.

## Confirming it works

1. In Providers & API keys, choose Test Connection. It should report Connected, and the gateway log should show `GET <url>/models` requests that carry `Authorization: Bearer <JWT>`.
2. Under Model Assignment, set Core features and Instant helpers to a listed model.
3. Open AI Chat, send a short prompt, and check that the gateway reply appears in the chat panel.
4. In the gateway log, expect streaming `POST <url>/chat/completions` requests with `Authorization: Bearer <JWT>` carrying the audience, issuer and expiry your gateway policy requires, and the user agent `ktor-client`. About a dozen such requests per prompt is normal.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Test Connection fails with 404, or the log shows `/models` without a prefix | The URL has no `/v1` or gateway prefix. The plugin appends only the endpoint name. Add the prefix to the URL. |
| Test Connection reports Connected but chat says No compatible model is available for Chat mode | No model is assigned. Set Core features and Instant helpers under Model Assignment. |
| Test Connection fails against the local proxy | The HTTP version does not match. Select HTTP/1.1 for a plain-HTTP proxy that speaks HTTP/1.1. |
| 401 from the gateway | The token proxy is not running or its helper failed. Check that the proxy is running and that the helper command in Appendix A prints a token when run by hand. |
| Model Assignment lists no models | The gateway `/models` response is not in the OpenAI list shape, or the call failed. |
| Test Connection and Model Assignment are not visible | Scroll down in the settings page, especially in a small dialog. |
| Chat works but the gateway sees many requests | Normal: background helper calls add roughly eleven requests to each chat call. |
| MCP tool calls are unavailable | The Tool calling checkbox is off, or the model does not support tool calling. |
| The Data Sharing with Third-Party AI Service Providers prompt keeps appearing | Confirm it again; it can appear more than once. |
| Custom models are greyed out | An administrator disabled custom models through IDE Services or JetBrains Central. |

## References

- JetBrains AI Assistant help: https://www.jetbrains.com/help/ai-assistant/
- Activation scenarios: https://www.jetbrains.com/help/ai-assistant/activation-scenarios.html
- Bring your own key (BYOK): https://www.jetbrains.com/help/ai-assistant/bring-your-own-key-byok.html
- Use custom models: https://www.jetbrains.com/help/ai-assistant/use-custom-models.html
- Licensing and subscriptions: https://www.jetbrains.com/help/ai-assistant/licensing-and-subscriptions.html

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
