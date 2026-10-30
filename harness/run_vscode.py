"""Launch an isolated VS Code with the LM probe extension and a given chatLanguageModels.json.

usage: run_vscode.py <scenario> <chatLanguageModels.json file> [--vendor V] [--wait-ms N] [--timeout S]
Prints the probe's output lines and the gateway requests it caused.
"""
import argparse
import json
import pathlib
import shutil
import subprocess
import time

import harness as h

ap = argparse.ArgumentParser()
ap.add_argument("scenario")
ap.add_argument("models_json")
ap.add_argument("--vendor", default="customendpoint")
ap.add_argument("--wait-ms", default="8000")
ap.add_argument("--timeout", type=int, default=120)
ap.add_argument("--settings", default="{}")
a = ap.parse_args()

base = h.WORK / "vscode" / a.scenario
shutil.rmtree(base, ignore_errors=True)
user = base / "user-data" / "User"
user.mkdir(parents=True)
(base / "ext").mkdir()
ws = base / "ws"
ws.mkdir()
shutil.copy(a.models_json, user / "chatLanguageModels.json")
settings = {"security.workspace.trust.enabled": False, "telemetry.telemetryLevel": "off", "update.mode": "none",
            "workbench.startupEditor": "none", "chat.agentHost.byokModels.enabled": True}
settings.update(json.loads(a.settings))
(user / "settings.json").write_text(json.dumps(settings))
out = base / "probe.jsonl"
env = h.clean_env({"LMTEST_OUT": str(out), "LMTEST_VENDOR": a.vendor, "LMTEST_WAIT_MS": a.wait_ms})
code = str(h.ROOT / "vscode-test" / ".vscode-test" / "vscode-win32-x64-archive-1.142.0" / "Code.exe")
m = h.marks()
proc = subprocess.Popen([code, "--user-data-dir", str(base / "user-data"), "--extensions-dir", str(base / "ext"),
                         "--extensionDevelopmentPath", str(h.ROOT / "vscode-probe"), "--new-window", "--disable-workspace-trust",
                         "--disable-updates", "--verbose", str(ws)], env=env,
                        stdout=open(base / "vs_out.txt", "w"), stderr=open(base / "vs_err.txt", "w"))
t0 = time.time()
while time.time() - t0 < a.timeout:
    if out.exists() and '"step":"done"' in out.read_text().replace(" ", ""):
        break
    time.sleep(1)
time.sleep(2)
lines = [json.loads(x) for x in out.read_text().splitlines()] if out.exists() else []
reqs, azs = h.since(m)
print(json.dumps({"scenario": a.scenario, "secs": round(time.time() - t0, 1), "probe": lines, **h.summarize(reqs, azs)}, indent=1))
# close only processes whose command line points at this scenario's folder
subprocess.run(["powershell", "-NoProfile", "-Command",
                f"Get-CimInstance Win32_Process -Filter \"Name='Code.exe'\" | Where-Object {{ $_.CommandLine -like '*{a.scenario}*' }} | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"], capture_output=True)
