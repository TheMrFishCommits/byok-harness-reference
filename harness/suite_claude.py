"""Claude Code scenario suite. Writes results/claude_suite.json and prints a compact table."""
import json
import subprocess
import sys

import harness as h

PY = sys.executable


def scenario(name, args, before=None, after=None):
    if before:
        before()
    p = subprocess.run([PY, "run_claude.py", name, *args], capture_output=True, text=True, encoding="utf-8")
    txt = p.stdout
    j = json.loads(txt[: txt.index("\n--- stdout:")])
    out_txt = txt[txt.index("--- stdout:"):]
    j["stdout_head"] = out_txt[:700]
    if after:
        after()
    return j


def reset():
    h.ctl(force_status=None, force_count=0, sse_delay_ms=0)
    h.az_mode("ok", 120)


results = []
S = results.append

# c02 custom header + no static creds
reset()
S(scenario("c02-custom-header", ["--settings", json.dumps({"env": {"ANTHROPIC_CUSTOM_HEADERS": "Ocp-Apim-Subscription-Key: sub-123\nX-Tenant: acme"}})]))

# c03 model pinning to a deployment name
reset()
S(scenario("c03-model-map", ["--settings", json.dumps({"env": {
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "dep-sonnet", "ANTHROPIC_DEFAULT_HAIKU_MODEL": "dep-haiku", "ANTHROPIC_DEFAULT_OPUS_MODEL": "dep-opus"}}),
    "--model", "sonnet"]))

# c04 model setting with custom name directly
reset()
S(scenario("c04-model-direct", ["--settings", json.dumps({"model": "my-deployment"})]))

# c05 noisy helper stdout
S(scenario("c05-noisy-helper", [], before=lambda: (reset(), h.az_mode("noisy", 120)), after=reset))

# c06 failing helper (az not logged in)
S(scenario("c06-helper-fails", ["--timeout", "90"], before=lambda: (reset(), h.az_mode("fail", 120)), after=reset))

# c07 wrong audience
S(scenario("c07-wrong-aud", ["--timeout", "90"], before=lambda: (reset(), h.az_mode("wrong_aud", 120)), after=reset))

# c08 slow helper 6s (under claude's 10s warning)
S(scenario("c08-slow-6s", [], before=lambda: (reset(), h.az_mode("slow", 120, 6)), after=reset))

# c09 server forces 401 once -> does claude re-run helper?
S(scenario("c09-401-once", [], before=lambda: (reset(), h.ctl(force_status=401, force_count=1)), after=reset))

# c10 ANTHROPIC_AUTH_TOKEN set statically alongside helper (precedence)
reset()
S(scenario("c10-auth-token-precedence", ["--settings", json.dumps({"env": {"ANTHROPIC_AUTH_TOKEN": "static-not-a-jwt"}})]))

# c11 short-lived token (20s) with TTL cache 5s: second prompt after expiry should refresh
reset()
S(scenario("c11-ttl-5s-token-20s", ["--settings", json.dumps({"env": {"CLAUDE_CODE_API_KEY_HELPER_TTL_MS": "5000"}})],
           before=lambda: h.az_mode("ok", 20), after=reset))

import pathlib
pathlib.Path("results").mkdir(exist_ok=True)
pathlib.Path("results/claude_suite.json").write_text(json.dumps(results, indent=1))

for r in results:
    print(f"\n== {r['scenario']} rc={r['rc']} secs={r['secs']} az_calls={r['az_calls']}")
    for q in r["requests"]:
        print(f"   #{q['seq']} {q['status']} {q['path']} auth={q['auth']} scheme={q['scheme']} xkey={q['x_api_key']} jti={q['jti']} ttl={q['ttl']} model={q['model']} tools={q['tools']} hdr={ {k:v for k,v in q['hdr'].items() if k.startswith(('ocp','x-tenant'))} }")
    print("   ", r["stdout_head"].replace("\n", " ")[:260])
