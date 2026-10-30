"""Re-run the failure modes with the hardened helper: should fail fast and clearly, and noisy stdout should be tolerated."""
import json
import pathlib
import subprocess
import sys

import harness as h


def cc(name, mode, **kw):
    h.az_mode(mode, kw.get("ttl", 120), kw.get("slow_s", 0))
    p = subprocess.run([sys.executable, "run_claude.py", name, "--timeout", "60"], capture_output=True, text=True, encoding="utf-8")
    t = p.stdout
    j = json.loads(t[: t.index("\n--- stdout:")])
    return {"tool": "claude", "mode": mode, "rc": j["rc"], "secs": j["secs"], "az_calls": j["az_calls"],
            "reqs": [(q["status"], q["auth"]) for q in j["requests"] if "messages" in q["path"]],
            "head": t[t.index("--- stdout:"):][:420].replace("\n", " ")}


def cx(name, mode, **kw):
    h.az_mode(mode, kw.get("ttl", 120), kw.get("slow_s", 0))
    p = subprocess.run([sys.executable, "run_codex.py", name, "--timeout", "60"], capture_output=True, text=True, encoding="utf-8")
    t = p.stdout
    j = json.loads(t[: t.index("\n--- config:")])
    return {"tool": "codex", "mode": mode, "rc": j["rc"], "secs": j["secs"], "az_calls": j["az_calls"],
            "reqs": [(q["status"], q["auth"]) for q in j["requests"] if "responses" in q["path"]],
            "head": t[t.index("--- stdout:"):][:520].replace("\n", " ")}


h.ctl(force_status=None, force_count=0, tool_turns=0, turn_delay_s=0)
R = []
for mode in ("ok", "noisy", "wrong_aud", "fail"):
    R.append(cc(f"h-claude-{mode}", mode))
    R.append(cx(f"h-codex-{mode}", mode))
h.az_mode("ok", 120)
pathlib.Path("results").mkdir(exist_ok=True)
pathlib.Path("results/helper_hardened.json").write_text(json.dumps(R, indent=1))
for r in R:
    print(f"\n== {r['tool']:6} mode={r['mode']:9} rc={r['rc']} secs={r['secs']} az_calls={r['az_calls']} model_reqs={r['reqs'][:4]}")
    print("   ", r["head"][:380])
