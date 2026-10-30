"""Does Claude Code refresh the JWT when a single session outlives the token?"""
import json
import pathlib
import subprocess
import sys

import harness as h


def go(name, token_ttl, helper_ttl_ms, turns=4, delay=8):
    h.az_mode("ok", token_ttl)
    h.ctl(tool_turns=turns, turn_delay_s=delay, force_status=None, force_count=0)
    p = subprocess.run(
        [sys.executable, "run_claude.py", name, "--allow-bash", "--timeout", "200", "--prompt", "Run: echo hello",
         "--settings", json.dumps({"env": {"CLAUDE_CODE_API_KEY_HELPER_TTL_MS": str(helper_ttl_ms)}})],
        capture_output=True, text=True, encoding="utf-8",
    )
    txt = p.stdout
    j = json.loads(txt[: txt.index("\n--- stdout:")])
    j["stdout_head"] = txt[txt.index("--- stdout:"):][:300]
    h.ctl(tool_turns=0, turn_delay_s=0)
    h.az_mode("ok", 120)
    return j


res = [
    go("r1-helperttl5s-token20s", 20, 5000),
    go("r2-helperttl300s-token20s", 20, 300000),
]
pathlib.Path("results").mkdir(exist_ok=True)
pathlib.Path("results/claude_refresh.json").write_text(json.dumps(res, indent=1))
for r in res:
    print(f"\n== {r['scenario']} rc={r['rc']} secs={r['secs']} az_calls={r['az_calls']}")
    for q in r["requests"]:
        if "messages" in q["path"]:
            print(f"   #{q['seq']} {q['status']} auth={q['auth']} jti={q['jti']} ttl_left={q['ttl']} tools={q['tools']}")
    print("   ", r["stdout_head"].replace("\n", " ")[:300])
