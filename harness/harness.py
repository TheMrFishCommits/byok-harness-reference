"""Test-harness utilities: clean child environments, gateway log slicing, fake-az mode control."""
import json
import os
import pathlib
import subprocess
import time
import urllib.request

import common

ROOT = pathlib.Path(__file__).parent
GW = "http://127.0.0.1:18080"
REQLOG = common.LOGS / "requests.jsonl"
AZLOG = common.LOGS / "az_calls.jsonl"
HELPER = pathlib.Path(os.environ.get("HARNESS_HELPER", ROOT / "get-apim-token.ps1"))
FAKEAZ = pathlib.Path(os.environ.get("HARNESS_AZ_DIR", ROOT / "fakeaz"))  # dir holding az.cmd; point at a real az wrapper to use it
WORK = ROOT / "work"


def ctl(**kw):
    req = urllib.request.Request(GW + "/_ctl", data=json.dumps(kw).encode(), method="POST")
    return json.load(urllib.request.urlopen(req))


def az_mode(mode="ok", ttl=120, slow_s=0):
    (FAKEAZ / "mode.json").write_text(json.dumps({"mode": mode, "ttl": ttl, "slow_s": slow_s}))


def _lines(p):
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def marks():
    return {"req": len(_lines(REQLOG)), "az": len(_lines(AZLOG))}


def since(m):
    return _lines(REQLOG)[m["req"]:], _lines(AZLOG)[m["az"]:]


def clean_env(extra=None, drop_prefixes=("CLAUDE_CODE_", "ANTHROPIC_", "CLAUDECODE", "OPENAI_", "CODEX_")):
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop_prefixes) and k != "CLAUDE_CONFIG_DIR"}
    env["PATH"] = str(FAKEAZ) + os.pathsep + env.get("PATH", "")
    env.update(extra or {})
    return env


def run(cmd, env, cwd=None, timeout=180, stdin=None):
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            input=stdin if stdin is not None else "", encoding="utf-8", errors="replace",
        )
        return {"rc": p.returncode, "out": p.stdout, "err": p.stderr, "secs": round(time.time() - t0, 1)}
    except subprocess.TimeoutExpired as e:
        return {"rc": "TIMEOUT", "out": (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
                "err": (e.stderr or b"").decode() if isinstance(e.stderr, bytes) else (e.stderr or ""),
                "secs": round(time.time() - t0, 1)}


def summarize(reqs, azs):
    rows = []
    for r in reqs:
        a = r.get("auth", {})
        rows.append({
            "seq": r["seq"], "status": r["status"], "path": r["path"], "query": r["query"],
            "auth": a.get("result"), "scheme": a.get("authorization_scheme"),
            "x_api_key": a.get("x_api_key_present"), "same": a.get("x_api_key_equals_bearer"),
            "jti": (a.get("claims") or {}).get("jti", "")[:8],
            "ttl": (a.get("claims") or {}).get("ttl_remaining"),
            "model": (r.get("body") or {}).get("model"), "stream": (r.get("body") or {}).get("stream"),
            "tools": (r.get("body") or {}).get("n_tools"),
            "hdr": {k: v for k, v in r["headers"].items() if k.startswith(("ocp-", "x-", "anthropic-version", "user-agent", "openai", "originator", "session"))},
        })
    return {"requests": rows, "az_calls": len(azs)}
