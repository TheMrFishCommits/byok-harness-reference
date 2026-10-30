"""Does Codex refresh the JWT when one session outlives the token? (20 s tokens, 4 tool turns x 8 s delay)"""
import json
import pathlib
import subprocess
import sys

import harness as h


def go(name, refresh_ms, token_ttl=20, turns=4, delay=8):
    h.az_mode("ok", token_ttl)
    h.ctl(tool_turns=turns, turn_delay_s=delay, force_status=None, force_count=0)
    p = subprocess.run(
        [sys.executable, "run_codex.py", name, "--timeout", "200", "--auth", json.dumps({"refresh_interval_ms": refresh_ms})],
        capture_output=True, text=True, encoding="utf-8")
    txt = p.stdout
    j = json.loads(txt[: txt.index("\n--- config:")])
    j["stdout_head"] = txt[txt.index("--- stdout:"):][:200]
    h.ctl(tool_turns=0, turn_delay_s=0)
    h.az_mode("ok", 120)
    return j


res = [go("x12-refresh5s-token20s", 5000), go("x13-refresh30min-token20s", 1800000), go("x14-refresh0-token20s", 0)]
pathlib.Path("results").mkdir(exist_ok=True)
pathlib.Path("results/codex_refresh.json").write_text(json.dumps(res, indent=1))
for r in res:
    print(f"\n== {r['scenario']} rc={r['rc']} secs={r['secs']} az_calls={r['az_calls']}")
    for q in r["requests"]:
        if "responses" in q["path"]:
            print(f"   #{q['seq']} {q['status']} auth={q['auth']} jti={q['jti']} ttl_left={q['ttl']}")
    print("   ", r["stdout_head"].replace("\n", " ")[:200])
