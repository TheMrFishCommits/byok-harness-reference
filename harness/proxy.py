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
