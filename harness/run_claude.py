"""Run Claude Code (headless) against the mock gateway with an apiKeyHelper config.

usage: run_claude.py <scenario> [--prompt P] [--settings-json JSON-merge] [--env K=V ...] [--model M] [--timeout S]
"""
import argparse
import json
import shutil
import sys

import harness as h

ap = argparse.ArgumentParser()
ap.add_argument("scenario")
ap.add_argument("--prompt", default="Reply with the single word: ok")
ap.add_argument("--settings", default="{}", help="JSON merged into settings.json (deep for env)")
ap.add_argument("--model")
ap.add_argument("--timeout", type=int, default=120)
ap.add_argument("--keep", action="store_true")
ap.add_argument("--no-helper", action="store_true")
ap.add_argument("--allow-bash", action="store_true")
ap.add_argument("--allowed", help="extra value for --allowedTools, e.g. mcp__azure__subscription_list")
ap.add_argument("--claude-json", help="JSON merged into the isolated .claude.json (e.g. mcpServers)")
a = ap.parse_args()

cfg = h.WORK / "claude" / a.scenario
shutil.rmtree(cfg, ignore_errors=True)
cfg.mkdir(parents=True)
cwd = cfg / "cwd"
cwd.mkdir()

settings = {
    "apiKeyHelper": f"powershell -NoProfile -File {h.HELPER}",
    "env": {
        "ANTHROPIC_BASE_URL": h.GW + "/anthropic",
        "CLAUDE_CODE_API_KEY_HELPER_TTL_MS": "300000",
    },
}
if a.no_helper:
    settings.pop("apiKeyHelper")
over = json.loads(a.settings)
settings["env"].update(over.pop("env", {}))
settings.update(over)
(cfg / "settings.json").write_text(json.dumps(settings, indent=2))
cj = {"hasCompletedOnboarding": True, "numStartups": 5}
if a.claude_json:
    cj.update(json.loads(a.claude_json))
(cfg / ".claude.json").write_text(json.dumps(cj))

env = h.clean_env({"CLAUDE_CONFIG_DIR": str(cfg), "DISABLE_AUTOUPDATER": "1"})
cmd = ["claude", "-p", a.prompt, "--output-format", "json", "--permission-mode", "default"]
if a.model:
    cmd += ["--model", a.model]
if a.allow_bash:
    cmd += ["--allowedTools", "Bash"]
if a.allowed:
    cmd += ["--allowedTools", a.allowed]

m = h.marks()
res = h.run(cmd, env, cwd=str(cwd), timeout=a.timeout)
reqs, azs = h.since(m)
out = {"scenario": a.scenario, "rc": res["rc"], "secs": res["secs"], **h.summarize(reqs, azs)}
print(json.dumps(out, indent=1))
print("--- stdout:", res["out"][:1500])
print("--- stderr:", res["err"][:1500])
