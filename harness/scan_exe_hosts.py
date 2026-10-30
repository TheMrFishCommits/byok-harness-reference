import re, sys, collections, pathlib
root = pathlib.Path(r"C:\Users\USER\Local\apim-harness-test\azure-mcp\node_modules\@azure\mcp-win32-x64")
exe = max((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.stat().st_size)
print("scanning", exe.name, exe.stat().st_size // 1_000_000, "MB")
hosts = collections.Counter()
a = re.compile(rb"https?://([A-Za-z0-9._-]{4,80})(/[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]{0,60})?")
u = re.compile(rb"h\x00t\x00t\x00p\x00s?\x00:\x00/\x00/\x00((?:[A-Za-z0-9._-]\x00){4,80})")
ex = {}
with open(exe, "rb") as f:
    prev = b""
    while True:
        chunk = f.read(8_000_000)
        if not chunk: break
        buf = prev + chunk
        for m in a.finditer(buf):
            h = m.group(1).decode("latin1").lower(); hosts[h] += 1; ex.setdefault(h, (m.group(0)[:90]).decode("latin1"))
        for m in u.finditer(buf):
            h = m.group(1).decode("utf-16le").lower(); hosts[h] += 1; ex.setdefault(h, "utf16")
        prev = chunk[-200:]
skip = ("schemas.", "www.w3.org", "json-schema", "example.", "localhost", "127.0.0.1", "xml", "purl.org", "go.microsoft.com/fwlink", "aka.ms")
keep = [(h, n) for h, n in hosts.most_common() if "." in h and not any(s in h for s in skip)]
print("distinct hosts:", len(keep))
for h, n in keep[:70]:
    print(f"{n:4}  {h}")
