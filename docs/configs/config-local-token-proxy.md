# Local token proxy: a loopback reverse proxy that adds a fresh Entra JWT to every request

## Summary

A small Python program that listens on 127.0.0.1, replaces whatever credential the client sends with a fresh Entra ID JWT obtained from a helper command, forwards the request to the gateway, and streams the response back. It is for tools that can only send a static API key or bearer value and have no command-backed token setting (for example VS Code Copilot Chat custom endpoints and JetBrains AI Assistant). The client is given any non-empty key; the proxy supplies the real token. It makes no network calls other than to the gateway and to the helper command.

## Applies to

| Item | Value |
|---|---|
| Component | `proxy.py` (source in the appendix) |
| Requires | Python 3.9 or later (`str.removeprefix`) and the `aiohttp` package. A helper command that prints a JWT (Appendix A) |
| OS | Windows (the helper is PowerShell); the proxy itself is portable |
| Config locations | Command-line arguments only. No configuration file |
| Scope | Per user, run in the user's session |

## Prerequisites

1. `pip install aiohttp`.
2. The helper command in Appendix A (or any command that prints a fresh JWT), and one `az login`.
3. The gateway URL, including the path segment of the API. The client's request path is appended to the upstream URL unchanged.

## Authentication: how the token reaches the gateway

Run:

```powershell
python proxy.py --upstream https://<apim-host> --port 18081 --margin-s 300 -- powershell -NoProfile -File C:\Users\<you>\bin\get-apim-token.ps1
```

| Argument | Meaning | Default |
|---|---|---|
| `--upstream` | Base URL of the gateway. The request path and query from the client are appended to it | required |
| `--port` | Local port, bound to 127.0.0.1 | 18081 |
| `--margin-s` | A cached token is reused until fewer than this many seconds remain before expiry | 300 |
| `--local-key` | Optional shared key that clients must send. Implemented, with no run-time confirmation yet | none |
| `--` command | Helper command that prints the JWT on stdout | required |

Behaviour:

- For each request the proxy removes the client's `Authorization`, `x-api-key` and `api-key` headers and the hop-by-hop headers (`Connection`, `Keep-Alive`, `Proxy-Authenticate`, `Proxy-Authorization`, `TE`, `Trailers`, `Transfer-Encoding`, `Upgrade`, `Host`, `Content-Length`), then sends `Authorization: Bearer <jwt>` to the gateway.
- The token comes from the helper command, run with a 30 second limit. The proxy reads the `exp` claim from the token (it does not verify the signature) and reuses the token until it is within `--margin-s` seconds of expiry. Token fetches are serialized.
- If the gateway answers 401, the proxy fetches a new token (forced refresh) and retries the request once.
- If the helper fails, the client receives HTTP 502 with a JSON body `{"error": "token helper failed", "detail": "<helper stderr line>"}`. The next request runs the helper again, so the proxy recovers without a restart once the helper works.
- Responses are streamed chunk by chunk, so server-sent events pass through. Upstream status and headers (minus hop-by-hop headers) are returned. Content encoding is passed through unchanged. Redirects are not followed.
- `GET /_proxy/health` returns `{"ok": true, "token_fetches": <n>}` and is not forwarded.
- With `--local-key`, a request must carry that value in `x-api-key`, `api-key` or as a bearer value, otherwise the proxy answers 401 `{"error": "bad local key"}`. The health path is not checked.
- The proxy prints nothing and does not log tokens or requests.

## Provider and model configuration

Point the client at `http://127.0.0.1:<port>/<same path as the gateway URL>` and give it any non-empty key. The model, API format and path are the client's usual ones. Examples:

| Client | Setting |
|---|---|
| Claude Code | `ANTHROPIC_BASE_URL=http://127.0.0.1:18081/<anthropic-api-path>` and `ANTHROPIC_AUTH_TOKEN=<any non-empty value>`; no `apiKeyHelper` |
| Codex | `base_url = "http://127.0.0.1:18081/<openai-responses-api-path>"` and `experimental_bearer_token = "<any non-empty value>"` in the provider; no `auth` table |
| GitHub Copilot CLI | `baseUrl` of the `providers.json` provider set to `http://127.0.0.1:18081/<path>` and `apiKey` set to any non-empty value |
| VS Code Copilot Chat custom endpoint | Model `url` set to `http://127.0.0.1:18081/<path>/<endpoint>` and any non-empty key stored through the Add Models flow |
| JetBrains AI Assistant | OpenAI-compatible provider URL set to `http://127.0.0.1:18081/<path>` and any non-empty API key. Not confirmed |

## Disabling login, telemetry and background network calls

| Setting | Where | Value | Default | Effect |
|---|---|---|---|---|
| Telemetry or update checks | proxy | none exist | n/a | The proxy has no telemetry, update check or login of its own |
| Request and token logging | proxy | none exists | n/a | Nothing is written to a log |
| Client-side login | client | not applicable | n/a | The client uses its static-key path and never needs a vendor sign-in for the model request |

## Network behaviour with this configuration

- The proxy accepts connections only on 127.0.0.1 (the bind address is fixed in the source).
- It connects only to the `--upstream` host and runs the helper command, which contacts Entra endpoints through the Azure CLI when a token is needed.
- The gateway sees the user's token and the proxy host's address.
- HTTPS to the upstream uses aiohttp's default certificate checking. A TLS-inspecting proxy needs its CA trusted by the Python installation.

## Effects and limits of this configuration

- Any process that can reach 127.0.0.1 on the port can send requests that carry the user's token. This is the same exposure as `az account get-access-token`, but on a shared or multi-user host the loopback interface is shared. Use `--local-key`, a firewall rule, or a per-user host.
- The gateway cannot tell clients apart; every request carries the user's identity.
- One token is used for all clients; there is no per-client or per-request audit in the proxy.
- The client must accept a dummy key (some tools check the key format).
- The proxy adds one local hop. Large request bodies are held in memory (limit 64 MB per request).
- HTTP to the proxy is plain text on the loopback interface only.
- The `/_proxy/health` path is reserved.
- HTTPS to a real gateway through the proxy has no run-time confirmation yet.

## Confirming it works

1. Start the proxy and run `curl http://127.0.0.1:18081/_proxy/health`. Expect `{"ok": true, "token_fetches": 0}`.
2. Send a request through it with a dummy key. In the gateway log the request carries `Authorization: Bearer <jwt>` and no `x-api-key`; the health call now shows `token_fetches` of 1 or more.
3. Sign out of the Azure CLI after the cached token has expired and send a request. Expect HTTP 502 with the helper's message. Sign in again and the next request succeeds without restarting the proxy.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| 502 `token helper failed` | The helper exited with an error. The `detail` field has its stderr line. Run `az login` or fix the helper |
| 401 from the gateway on every request | Wrong audience or policy mismatch. Check the token claims |
| 401 `bad local key` | `--local-key` is set and the client sent a different key |
| Client says the key is invalid | The client rejects the dummy value. Use a different non-empty value |
| Connection refused | The proxy is not running, or the client uses a different port |
| Gateway path wrong (404) | The client URL must contain the same path segment as the gateway API, because the path is appended to `--upstream` |

## References

- https://docs.aiohttp.org/
- https://learn.microsoft.com/en-us/azure/api-management/validate-jwt-policy
- https://code.visualstudio.com/docs/agent-customization/language-models
- https://docs.github.com/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models

## Appendix B: source of proxy.py

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

