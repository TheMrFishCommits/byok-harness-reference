"""Minimal MCP stdio client: start a server, initialize, list tools, optionally call tools; print a JSON summary.

usage: mcp_client.py --label L [--env K=V ...] [--call NAME JSON ...] [--hold SECS] -- <server command...>
"""
import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--call", nargs=2, action="append", default=[], metavar=("NAME", "JSON"))
    ap.add_argument("--hold", type=float, default=0, help="seconds to keep the server running after the calls")
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = [c for c in a.cmd if c != "--"]
    env = dict(os.environ)
    for kv in a.env:
        k, _, v = kv.partition("=")
        env[k] = v
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True, encoding="utf-8", errors="replace", bufsize=1)
    out_q, err_lines = queue.Queue(), []
    threading.Thread(target=lambda: [out_q.put(l) for l in p.stdout], daemon=True).start()
    threading.Thread(target=lambda: [err_lines.append(l.rstrip()) for l in p.stderr], daemon=True).start()
    nid = [0]
    summary = {"label": a.label, "cmd": " ".join(cmd)}

    def rpc(method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            nid[0] += 1
            msg["id"] = nid[0]
        p.stdin.write(json.dumps(msg) + "\n")
        p.stdin.flush()
        if notify:
            return None
        deadline = time.time() + a.timeout
        while time.time() < deadline:
            try:
                line = out_q.get(timeout=0.5)
            except queue.Empty:
                if p.poll() is not None:
                    return {"error": f"server exited rc={p.returncode}"}
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("id") == msg["id"]:
                return r
            if "method" in r and "id" in r:  # server-initiated request (sampling, elicitation, roots)
                summary.setdefault("server_requests", []).append(r["method"])
                p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": r["id"], "error": {"code": -32601, "message": "not supported by test client"}}) + "\n")
                p.stdin.flush()
        return {"error": "timeout"}

    t0 = time.time()
    r = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "probe", "version": "0"}})
    summary["initialize_secs"] = round(time.time() - t0, 2)
    res = r.get("result", {})
    summary["server"] = res.get("serverInfo")
    summary["server_capabilities"] = sorted((res.get("capabilities") or {}).keys())
    summary["protocol"] = res.get("protocolVersion")
    rpc("notifications/initialized", notify=True)
    r = rpc("tools/list", {})
    tools = (r.get("result") or {}).get("tools", [])
    summary["tool_count"] = len(tools)
    summary["tool_names"] = [t["name"] for t in tools]
    summary["tool_schemas"] = {t["name"]: t.get("inputSchema") for t in tools if t["name"] in ("get_azure_bestpractices", "documentation", "bicepschema")}
    ann = {"readOnly": 0, "destructive": 0, "openWorld": 0, "none": 0}
    for t in tools:
        an = t.get("annotations") or {}
        if an.get("readOnlyHint"):
            ann["readOnly"] += 1
        if an.get("destructiveHint"):
            ann["destructive"] += 1
        if an.get("openWorldHint"):
            ann["openWorld"] += 1
        if not an:
            ann["none"] += 1
    summary["annotations"] = ann
    summary["calls"] = []
    for name, js in a.call:
        t1 = time.time()
        r = rpc("tools/call", {"name": name, "arguments": json.loads(js)})
        body = json.dumps(r)[:900]
        summary["calls"].append({"name": name, "secs": round(time.time() - t1, 2), "is_error": (r.get("result") or {}).get("isError"), "response_head": body})
    if a.hold:
        time.sleep(a.hold)
    try:
        p.stdin.close()
    except Exception:
        pass
    time.sleep(0.5)
    p.terminate()
    summary["stderr_head"] = [l[:200] for l in err_lines[:12]]
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, f"mcp_{a.label}.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    print(f"[{a.label}] tools={summary.get('tool_count')} calls={[(c['name'], c['is_error']) for c in summary['calls']]} -> results\\mcp_{a.label}.json")


if __name__ == "__main__":
    sys.exit(main())
