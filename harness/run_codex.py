"""Run Codex CLI (exec mode) against the mock gateway with a command-backed auth provider.

usage: run_codex.py <scenario> [--prompt P] [--provider-lines L ...] [--auth JSON] [--top-lines L ...] [--no-auth] [--timeout S]
"""
import argparse
import json
import shutil

import harness as h

ap = argparse.ArgumentParser()
ap.add_argument("scenario")
ap.add_argument("--prompt", default="Reply with the single word: ok")
ap.add_argument("--provider-lines", nargs="*", default=[])
ap.add_argument("--top-lines", nargs="*", default=[])
ap.add_argument("--auth", default="{}", help="JSON overrides for the [auth] table")
ap.add_argument("--no-auth", action="store_true")
ap.add_argument("--base-url", default=h.GW + "/openai/v1")
ap.add_argument("--timeout", type=int, default=120)
ap.add_argument("--model", default="gpt-test")
a = ap.parse_args()

home = h.WORK / "codex" / a.scenario
shutil.rmtree(home, ignore_errors=True)
home.mkdir(parents=True)
cwd = home / "cwd"
cwd.mkdir()

auth = {
    "command": "powershell",
    "args": ["-NoProfile", "-File", str(h.HELPER)],
    "timeout_ms": 15000,
    "refresh_interval_ms": 1800000,
}
auth.update(json.loads(a.auth))


def toml_val(v):
    if isinstance(v, str):
        return "'" + v + "'"
    if isinstance(v, list):
        return "[" + ", ".join(toml_val(x) for x in v) + "]"
    return str(v)


lines = [f'model = "{a.model}"', 'model_provider = "apim"', *a.top_lines, "",
         "[model_providers.apim]", 'name = "Azure APIM"', f'base_url = "{a.base_url}"', 'wire_api = "responses"',
         *a.provider_lines, ""]
if not a.no_auth:
    lines += ["[model_providers.apim.auth]", *[f"{k} = {toml_val(v)}" for k, v in auth.items()]]
(home / "config.toml").write_text("\n".join(lines) + "\n")

env = h.clean_env({"CODEX_HOME": str(home)})
cmd = ["codex", "exec", "--skip-git-repo-check", a.prompt]
m = h.marks()
res = h.run(cmd, env, cwd=str(cwd), timeout=a.timeout)
reqs, azs = h.since(m)
out = {"scenario": a.scenario, "rc": res["rc"], "secs": res["secs"], **h.summarize(reqs, azs)}
print(json.dumps(out, indent=1))
print("--- config:\n" + (home / "config.toml").read_text())
print("--- stdout:", res["out"][:1200])
print("--- stderr:", res["err"][:1500])
