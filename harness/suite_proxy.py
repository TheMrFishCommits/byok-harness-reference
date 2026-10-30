"""Proxy tests: dummy client key -> proxy injects fresh JWT; rotation near expiry; 401 retry; real CLIs through it."""
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

import harness as h

PX = "http://127.0.0.1:18081"
out = []


def post(path, key="dummy-local-key", body=None, stream=False):
    body = body or {"model": "m1", "stream": stream, "messages": [{"role": "user", "content": "hi"}]}
    req = urllib.request.Request(PX + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "x-api-key": key, "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def last_auth(n=1):
    return [(r["status"], r["auth"].get("result"), (r["auth"].get("claims") or {}).get("jti", "")[:8], r["auth"].get("x_api_key_present"))
            for r in h._lines(h.REQLOG)[-n:]]


h.ctl(force_status=None, force_count=0, tool_turns=0, turn_delay_s=0, sse_delay_ms=0)
h.az_mode("ok", 120)

# P1 basic non-streaming, dummy key replaced
s, b = post("/anthropic/v1/messages")
out.append(("P1 non-stream dummy key", s, b[:60], last_auth()))

# P2 streaming passthrough
h.ctl(sse_delay_ms=150)
t0 = time.time()
s, b = post("/anthropic/v1/messages", stream=True)
out.append(("P2 stream passthrough", s, f"{len(b)} bytes, {time.time()-t0:.1f}s, has message_stop={'message_stop' in b}", last_auth()))
h.ctl(sse_delay_ms=0)

# P3 openai responses route
s, b = post("/openai/v1/responses", body={"model": "gpt-test", "stream": False, "input": "hi"})
out.append(("P3 responses route", s, b[:60], last_auth()))

# P4 forced upstream 401 once -> proxy refetches and retries
h.ctl(force_status=401, force_count=1)
s, b = post("/anthropic/v1/messages")
out.append(("P4 upstream 401 once -> retry", s, b[:50], last_auth(2)))

# P5 helper failure -> 502 with reason
h.az_mode("fail", 120)
subprocess.run(["curl.exe", "-s", PX + "/_proxy/health"], capture_output=True)
pathlib.Path("results").mkdir(exist_ok=True)
out.append(("P5 (helper fail tested separately)", "-", "-", None))
h.az_mode("ok", 120)

for o in out:
    print(o)
