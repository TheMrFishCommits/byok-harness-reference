"""Egress audit: record every non-loopback TCP connection opened by a process tree, with hostnames from the DNS cache.

usage:
  egress_watch.py --label L --secs N --pid PID            watch an existing process tree
  egress_watch.py --label L --secs N --match SUBSTR       root = process whose command line contains SUBSTR (and has no --type=)
  egress_watch.py --label L --run -- <command...>         run a command (env inherited) and watch its tree until it exits
Writes logs/egress/<label>.json and prints a summary.
"""
import argparse
import ipaddress
import json
import pathlib
import socket
import subprocess
import sys
import threading
import time

import psutil

OUT = pathlib.Path(__file__).parent / "logs" / "egress"
OUT.mkdir(parents=True, exist_ok=True)


def dns_cache():
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-DnsClientCache | Where-Object { $_.Data } | ForEach-Object { \"$($_.Entry)|$($_.Data)\" }"],
            capture_output=True, text=True, timeout=15)
        m = {}
        for line in r.stdout.splitlines():
            if "|" in line:
                name, ip = line.split("|", 1)
                m.setdefault(ip.strip(), set()).add(name.strip())
        return m
    except Exception:
        return {}


def tree(root):
    try:
        p = psutil.Process(root)
        return [p] + p.children(recursive=True)
    except psutil.Error:
        return []


def find_root(match, name=None):
    me = psutil.Process().pid
    for p in psutil.process_iter(["pid", "cmdline", "name"]):
        if p.info["pid"] == me:
            continue
        c = " ".join(p.info["cmdline"] or [])
        if "egress_watch" in c:
            continue
        if name and (p.info["name"] or "").lower() != name.lower():
            continue
        if match.lower() in c.lower() and "--type=" not in c:
            return p.info["pid"]
    return None


STATS = {"max_procs": 0, "proc_names": set(), "denied": 0}


def watch(get_pids, stop, seen, names):
    last_dns = 0
    while not stop.is_set():
        pids = get_pids()
        STATS["max_procs"] = max(STATS["max_procs"], len(pids))
        for p in pids:
            try:
                STATS["proc_names"].add(p.name())
            except psutil.Error:
                pass
            try:
                for c in p.net_connections(kind="inet"):
                    if not c.raddr or c.status not in ("ESTABLISHED", "SYN_SENT", "CLOSE_WAIT", "TIME_WAIT"):
                        continue
                    ip = c.raddr.ip
                    try:
                        a = ipaddress.ip_address(ip)
                    except ValueError:
                        continue
                    if a.is_loopback:
                        continue
                    key = (ip, c.raddr.port)
                    e = seen.setdefault(key, {"procs": set(), "first": time.time(), "status": set()})
                    e["procs"].add(p.name())
                    e["status"].add(c.status)
            except (psutil.Error, OSError):
                pass
        if time.time() - last_dns > 2:
            for ip, ns in dns_cache().items():
                names.setdefault(ip, set()).update(ns)
            last_dns = time.time()
        time.sleep(0.4)


def summarize(label, seen, names):
    rows = []
    for (ip, port), e in sorted(seen.items()):
        a = ipaddress.ip_address(ip)
        host = sorted(names.get(ip, []))
        if not host:
            try:
                host = [socket.gethostbyaddr(ip)[0] + " (rdns)"]
            except Exception:
                host = []
        rows.append({"ip": ip, "port": port, "private": a.is_private, "hosts": host,
                     "procs": sorted(e["procs"]), "state": sorted(e["status"])})
    (OUT / f"{label}.json").write_text(json.dumps(rows, indent=1))
    pub = [r for r in rows if not r["private"]]
    print(f"[{label}] tracked up to {STATS['max_procs']} processes ({', '.join(sorted(STATS['proc_names']))[:160]})")
    print(f"[{label}] non-loopback endpoints: {len(rows)} (public: {len(pub)})")
    for r in rows:
        print(f"   {'PRIV' if r['private'] else 'PUB '} {r['ip']}:{r['port']}  {', '.join(r['hosts'][:3]) or '-'}  [{', '.join(r['procs'])}]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--secs", type=float, default=30)
    ap.add_argument("--pid", type=int)
    ap.add_argument("--match")
    ap.add_argument("--name", help="process image name for --match, e.g. Code.exe")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    seen, names, stop = {}, {}, threading.Event()
    if a.run:
        cmd = [x for x in a.cmd if x != "--"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        t = threading.Thread(target=watch, args=(lambda: tree(proc.pid), stop, seen, names), daemon=True)
        t.start()
        try:
            out, _ = proc.communicate(timeout=a.secs)
        except subprocess.TimeoutExpired:
            proc.kill()
            out = "(killed on timeout)"
        time.sleep(1.0)
        stop.set()
        t.join(3)
        print((out or "")[:400].replace("\n", " "))
    else:
        root = a.pid
        t_wait = time.time()
        while not root and time.time() - t_wait < 60:
            root = find_root(a.match, a.name)
            if not root:
                time.sleep(0.5)
        if not root:
            print("no root process found")
            return 1
        t = threading.Thread(target=watch, args=(lambda: tree(root), stop, seen, names), daemon=True)
        t.start()
        time.sleep(a.secs)
        stop.set()
        t.join(3)
    summarize(a.label, seen, names)


if __name__ == "__main__":
    sys.exit(main())
