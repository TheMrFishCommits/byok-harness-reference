"""Fake `az account get-access-token`: mints test JWTs, logs each call, and can misbehave on demand.

Behaviour comes from fakeaz/mode.json, re-read on every call, e.g.
  {"mode": "ok", "ttl": 120}   mode: ok | slow | noisy | fail | wrong_aud
"""
import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import common  # noqa: E402


def main(argv):
    mode = {"mode": "ok", "ttl": 120, "slow_s": 0}
    try:
        mode.update(json.loads((HERE / "mode.json").read_text()))
    except Exception:
        pass
    common.LOGS.mkdir(exist_ok=True)
    with (common.LOGS / "az_calls.jsonl").open("a") as f:
        f.write(json.dumps({"ts": time.time(), "pid": os.getpid(), "argv": argv, "mode": mode["mode"]}) + "\n")

    if argv[:2] != ["account", "get-access-token"]:
        sys.stderr.write("fake az: only 'account get-access-token' is implemented\n")
        return 2
    if mode["mode"] == "fail":
        sys.stderr.write("ERROR: Please run 'az login' to setup account.\n")
        return 1
    if mode["mode"] == "slow":
        time.sleep(float(mode.get("slow_s", 6)))
    aud = common.AUDIENCE
    if mode["mode"] == "wrong_aud":
        aud = "https://cognitiveservices.azure.com"
    token = common.mint(ttl=mode["ttl"], aud=aud)
    if mode["mode"] == "noisy":
        sys.stdout.write("WARNING: some banner on stdout\n")
    sys.stdout.write(token + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
