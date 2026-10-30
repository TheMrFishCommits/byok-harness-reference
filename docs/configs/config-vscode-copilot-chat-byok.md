# VS Code Copilot Chat: BYOK with an Entra-issued token and no vendor network access

## Summary

This configuration uses the built-in GitHub Copilot Chat in VS Code with a Custom Endpoint model that points at your own gateway. No GitHub sign-in is needed for chat with that model. Entra-issued tokens are supplied through the local token proxy (Appendix B), which gets tokens from the helper command (Appendix A), because VS Code has no native token-command setting for these models. A quiet settings profile reduces VS Code's own background calls. Copilot Fusion and GitHub-hosted models are not available in this configuration.

## Applies to

| Item | Value |
|---|---|
| Product | Visual Studio Code with the built-in GitHub Copilot Chat extension |
| Versions | VS Code 1.142.0, Copilot Chat 0.70.0. Bring-your-own-key without GitHub sign-in is reported as added in VS Code 1.122; the primary documentation page does not state a minimum version |
| Operating system | Windows 11. Other operating systems: not documented here |
| Model file | `chatLanguageModels.json` in the user profile folder (on Windows `%APPDATA%\Code\User\chatLanguageModels.json`). The documentation does not state the location |
| Settings | `settings.json`, user or workspace scope |
| Enterprise policies | Windows registry key `Software\Policies\Microsoft\VSCode`. Use the command Developer: Policy Diagnostics to see applied policies |
| Scope | User profile (model file and key); user or workspace (settings); machine (policies) |

## Prerequisites

1. VS Code installed, with the built-in Copilot Chat extension enabled.
2. A gateway endpoint that implements the OpenAI Chat Completions API, the OpenAI Responses API, or the Anthropic Messages API, and a model that supports tool calling (needed for agent mode).
3. The local token proxy running on the workstation (Appendix B at the end of this guide), which obtains Entra tokens through the token helper command (Appendix A).
4. Organization policy for Copilot Business or Enterprise: the policy Bring Your Own Language Model Key in VS Code is enabled by default and an administrator can turn it off.

## Authentication: how the token reaches the gateway

Method: local token proxy with a placeholder key stored by VS Code.

- VS Code has no setting that runs a command to fetch a token for a Custom Endpoint model. The key you give VS Code is static.
- Default headers for a Custom Endpoint model: `Authorization: Bearer <apiKey>`, except `x-api-key` for the Messages API and `api-key` for Azure OpenAI URLs.
- Header override: a `requestHeaders` object on the model can set headers. If it contains `Authorization`, `api-key`, `x-api-key`, `x-goog-api-key` or `apikey`, VS Code does not also send the inferred header. The text `${apiKey}` inside a header value is replaced with the configured key. Example: `"Authorization": "Bearer ${apiKey}"`. Static headers such as `Ocp-Apim-Subscription-Key` can sit alongside it. This is the only dynamic token documented; `${input:...}` inside `requestHeaders` is not documented.
- Because Entra tokens expire, point the model `url` at the local token proxy and give VS Code any non-empty placeholder key. The proxy discards the placeholder and sends a fresh Entra JWT to the gateway on each request, retrying once if the gateway returns 401.
- Alternative, not verified: the built-in `azure` provider signs in with the user's Microsoft account (Entra) when its `apiKey` is not set, and the Copilot Chat extension requests the scope `https://cognitiveservices.azure.com/.default`. Your gateway would have to accept that audience. Treat this route as unconfirmed.

## Provider and model configuration

Add the provider through the VS Code interface so the key is held as a secret:

1. Run the command Chat: Manage Language Models, then choose Add Models, then Custom Endpoint.
2. Enter a group name, then the placeholder API key, then the API type (Chat Completions, Responses or Messages).
3. VS Code writes the provider into `chatLanguageModels.json` and stores the key in secret storage. The file then holds a placeholder such as `${input:chat.lm.secret.<id>}`, not the key.
4. Add the model under `models` in that file and save it:

```json
[
  {
    "name": "<group-name>",
    "vendor": "customendpoint",
    "apiKey": "${input:chat.lm.secret.<id>}",
    "apiType": "responses",
    "models": [
      {
        "id": "<deployment-name>",
        "name": "<display-name>",
        "url": "http://127.0.0.1:<proxy-port>/<apim-api-path>/responses",
        "apiType": "responses",
        "toolCalling": true,
        "vision": false,
        "maxInputTokens": 100000,
        "maxOutputTokens": 8000
      }
    ]
  }
]
```

Do not type a literal key into the `apiKey` field. A literal key leaves the model listed in the Language Models editor but missing from the chat model picker.

Model fields: `id` (sent to the API), `name` (shown in the picker), `url` (the full endpoint URL), `apiType` (`chat-completions`, `responses` or `messages`; inferred from the URL path when neither the model nor the provider sets it), `toolCalling` (required to appear in agent mode), `vision`, `maxInputTokens` and `maxOutputTokens` (their sum must not exceed the model's context window), and optionally `contextWindow`, `editTools`, `thinking`, `streaming` (default true), `zeroDataRetentionEnabled`, `statefulResponses`, `supportsReasoningEffort`, `reasoningEffortFormat`, `requestHeaders` and `modelOptions`.

URL rule: `url` is the complete endpoint path, for example `.../openai/v1/responses`. VS Code does not append a path to it.

Select the model: open the chat model picker. A tab with the group name appears, and the model is listed under it. Choose it in the Local session type and chat.

## Disabling login, telemetry and background network calls

All settings below are in `settings.json` unless the Setting cell says otherwise.

| Setting | Value | Default | Effect |
|---|---|---|---|
| GitHub sign-in (chat) | Not required | Not signed in | BYOK models work in the Local session without a GitHub account or Copilot plan. Documented. |
| `telemetry.telemetryLevel` (policy `TelemetryLevel`) | `off` | `all` | Stops usage, error and crash telemetry. Documented. One request to an Application Insights host was still attempted at this level. Some third-party extensions may not respect it. |
| `update.mode` (policy `UpdateMode`) | `none` | `default` | Stops update checks to the VS Code update server. Documented. |
| `extensions.autoCheckUpdates` | `false` | `true` | Stops periodic extension update checks to the Marketplace. Marketplace requests stopped when this was combined with the next setting and `workbench.enableExperiments`; the contribution of each was not isolated. |
| `extensions.autoUpdate` (policy `ExtensionsAutoUpdate`) | `false` | `true` | Stops automatic extension updates. Documented. |
| `workbench.enableExperiments` | `false` | `true` | Intended to stop the experiment service. Documented only indirectly (telemetry level `off` disables A/B experimentation); effect not confirmed. |
| `update.showReleaseNotes` | `false` | `true` | Avoids fetching release notes. Documented, effect not confirmed. |
| `chat.utilityModel` and `chat.utilitySmallModel` | A BYOK model | Unset | Removes the Set BYOK utility models prompt and lets utility tasks (chat titles, commit messages, rename suggestions) use your model. Documented. |
| `chat.agentHost.byokModels.enabled` | `true` | `false` | Experimental. Documented as required for Copilot harness sessions. It was enabled in the working configuration; whether the Local session needs it was not established. |
| `telemetry.feedback.enabled` (policy `EnableFeedback`) | `false` | `true` | Turns off the issue reporter and surveys. Documented, effect not confirmed. |
| Policies `ExtensionGalleryServiceUrl` and `AllowedExtensions` | Organization value | Not set | Repoint or restrict the extension gallery. Documented, effect not confirmed. |

Do not set the policy `ChatApprovedAccountOrganizations`. It blocks all AI features until a matching sign-in exists.

No setting or policy is documented for the remote chat configuration fetch from `main.vscode-cdn.net`, for the Azure metadata probe to `169.254.169.254`, or for a single offline mode. The telemetry page states that turning off online features does not put VS Code into offline mode.

Quiet profile (`settings.json`):

```json
{
  "telemetry.telemetryLevel": "off",
  "update.mode": "none",
  "extensions.autoCheckUpdates": false,
  "extensions.autoUpdate": false,
  "workbench.enableExperiments": false,
  "update.showReleaseNotes": false,
  "chat.agentHost.byokModels.enabled": true
}
```

## Network behaviour with this configuration

| Situation | Hosts VS Code contacts |
|---|---|
| Default settings, signed out | `main.vscode-cdn.net`, `marketplace.visualstudio.com`. `www.vscode-unpkg.net` also appears when extensions are installed. |
| Quiet profile above, chatting with the BYOK model | `main.vscode-cdn.net`, `169.254.169.254` (a link-local address that does not leave the machine), `westus-0.in.applicationinsights.azure.com`, plus the model `url` host. The Marketplace calls stop. |

No GitHub host was contacted in either situation. Refusing the Microsoft hosts above does not stop chat with the BYOK model.

Allow: the model `url` host (the local token proxy). Block, if your policy requires it: the Microsoft hosts above. Allow `marketplace.visualstudio.com` and related gallery hosts only while installing extensions.

To force all VS Code traffic through an approved proxy, VS Code supports the Chromium options `--proxy-server=<url>` and `--proxy-bypass-list=<list>`, and the settings `http.proxy`, `http.proxyStrictSSL` and `http.proxyAuthorization` apply in limited scenarios. The documentation states that extensions do not yet benefit from the same proxy support.

## Effects and limits of this configuration

- BYOK applies to chat and utility tasks. Inline code suggestions, semantic search and features that rely on embeddings still need a GitHub account or Copilot.
- Default utility models are not available without sign-in, so a notification asks you to set `chat.utilityModel` and `chat.utilitySmallModel`.
- Copilot Fusion (including HydraFusion) is not available: it needs a Copilot plan and its routing decisions run in GitHub's cloud. There is no documented setting that makes it work offline.
- The Copilot session type needs sign-in. The built-in Claude session type lists no models for a Custom Endpoint. The Codex session type opens the separate Codex extension. Use the Local session type.
- Usage is billed by your gateway or provider and does not count against Copilot quotas.
- Prompts and code context go to the endpoint in `url`.

## Confirming it works

1. Open the chat view and open the model picker. The group tab and model should be listed.
2. Select the model, type a short prompt, and press Enter. The reply should appear in the chat panel.
3. In the gateway log, expect one request to the path in `url` (for a Responses model, `POST <api-path>/responses`) carrying `Authorization: Bearer <JWT>` with the audience, issuer and expiry your policy requires. The user agent starts with `GitHubCopilotChat/`.
4. No request to a GitHub host should appear.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Model shows in Manage Language Models but not in the picker | The key in `chatLanguageModels.json` is a literal value. Re-add the provider through Add Models so the file holds `${input:chat.lm.secret.<id>}`. |
| Chat ends with Sign in to use GitHub Copilot | The default model Auto is a Copilot model. Select your BYOK model in the picker. |
| The model entry you saved does not take effect | VS Code restores unsaved edits to the file at start. Save or discard the open buffer, then reload the window. |
| Set BYOK utility models card remains | Set `chat.utilityModel` and `chat.utilitySmallModel`. |
| 401 from the gateway | The token proxy is not running or its helper failed. Check that the proxy is running and that the helper command in Appendix A prints a token when run by hand. |
| 404 from the gateway | `url` does not match a gateway operation. It must be the full endpoint path. |
| No models in the Claude session type | Expected for a Custom Endpoint. Use the Local session type. |
| Model missing in agent mode | `toolCalling` is not `true`. |

## References

- AI language models in VS Code: https://code.visualstudio.com/docs/agent-customization/language-models
- Use your own language model key in VS Code: https://code.visualstudio.com/blogs/2026/06/18/byok-vscode
- Bring your own language model key (GitHub changelog): https://github.blog/changelog/2026-04-22-bring-your-own-language-model-key-in-vs-code-now-available/
- Network connections in VS Code: https://code.visualstudio.com/docs/setup/network
- Enterprise policies: https://code.visualstudio.com/docs/enterprise/policies
- Telemetry: https://code.visualstudio.com/docs/configure/telemetry
- Updates: https://code.visualstudio.com/docs/enterprise/updates
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
