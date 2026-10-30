"""Codex scenario suite (single-turn faults and config options)."""
import json
import pathlib
import subprocess
import sys

import harness as h


def reset():
    h.ctl(force_status=None, force_count=0, sse_delay_ms=0, tool_turns=0, turn_delay_s=0)
    h.az_mode("ok", 120)


def sc(name, args, before=None):
    reset()
    if before:
        before()
    p = subprocess.run([sys.executable, "run_codex.py", name, *args], capture_output=True, text=True, encoding="utf-8")
    txt = p.stdout
    j = json.loads(txt[: txt.index("\n--- config:")])
    tail = txt[txt.index("--- stdout:"):]
    j["stdout_head"] = tail[:600]
    reset()
    return j


R = []
R.append(sc("x02-query-and-headers", ["--provider-lines",
    'query_params = { api-version = "2025-04-01-preview" }',
    'http_headers = { "Ocp-Apim-Subscription-Key" = "sub-123", "X-Tenant" = "acme" }']))
R.append(sc("x03-noisy-helper", [], before=lambda: h.az_mode("noisy", 120)))
R.append(sc("x04-helper-fails", ["--timeout", "90"], before=lambda: h.az_mode("fail", 120)))
R.append(sc("x05-wrong-aud", ["--timeout", "90"], before=lambda: h.az_mode("wrong_aud", 120)))
R.append(sc("x06-slow6s-default-timeout", ["--auth", json.dumps({"timeout_ms": 5000})], before=lambda: h.az_mode("slow", 120, 6)))
R.append(sc("x07-slow6s-timeout15s", [], before=lambda: h.az_mode("slow", 120, 6)))
R.append(sc("x08-401-once", [], before=lambda: h.ctl(force_status=401, force_count=1)))
R.append(sc("x09-no-auth-block", ["--no-auth", "--timeout", "40"]))
R.append(sc("x10-auth-plus-env-key", ["--provider-lines", 'env_key = "FOO_KEY"', "--timeout", "40"]))

pathlib.Path("results").mkdir(exist_ok=True)
pathlib.Path("results/codex_suite.json").write_text(json.dumps(R, indent=1))
for r in R:
    print(f"\n== {r['scenario']} rc={r['rc']} secs={r['secs']} az_calls={r['az_calls']}")
    for q in r["requests"]:
        extra = {k: v for k, v in q["hdr"].items() if k.startswith(("ocp", "x-tenant"))}
        print(f"   #{q['seq']} {q['status']} {q['path']} q={q['query']} auth={q['auth']} jti={q['jti']} model={q['model']} {extra}")
    print("   ", r["stdout_head"].replace("\n", " ")[:420])
