"""Deny-all logging proxy: simulates an environment where only localhost is reachable.

Every CONNECT / absolute-URI request is logged (host, port, label) and refused with 403. Point harnesses at it with
HTTPS_PROXY / HTTP_PROXY (+ NO_PROXY=127.0.0.1,localhost) and VS Code with --proxy-server. Label per run is read from
logs/egress_label.txt so one proxy serves many scenarios.
"""
import asyncio
import json
import pathlib
import time

LOG = pathlib.Path(__file__).parent / "logs" / "egress_deny.jsonl"
LABEL = pathlib.Path(__file__).parent / "logs" / "egress_label.txt"
PORT = 18090


def label():
    try:
        return LABEL.read_text().strip()
    except Exception:
        return ""


async def handle(reader, writer):
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
    except Exception:
        writer.close()
        return
    line = head.split(b"\r\n", 1)[0].decode("latin1", "replace")
    parts = line.split()
    method, target = (parts[0], parts[1]) if len(parts) >= 2 else ("?", "?")
    if method == "CONNECT":
        host, _, port = target.rpartition(":")
    else:
        t = target.split("://", 1)[-1].split("/", 1)[0]
        host, _, port = t.partition(":")
        port = port or "80"
    with LOG.open("a") as f:
        f.write(json.dumps({"ts": time.time(), "label": label(), "method": method, "host": host, "port": port}) + "\n")
    writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
    try:
        await writer.drain()
    finally:
        writer.close()


async def main():
    LOG.parent.mkdir(exist_ok=True)
    server = await asyncio.start_server(handle, "127.0.0.1", PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
