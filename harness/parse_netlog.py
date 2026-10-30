import re, sys, json, collections
for scen in ("h0-vscode-bare", "h1-claude-ext-base", "h2-claude-ext-quiet"):
    p = rf"C:\Users\USER\Local\apim-harness-test\work\vscode\{scen}\netlog.json"
    try:
        t = open(p, encoding="utf-8", errors="replace").read()
    except Exception as e:
        print(scen, "no netlog", e); continue
    urls = re.findall(r'"url":"(https?://[^"]+)"', t)
    hosts = collections.Counter(re.sub(r'^https?://([^/:?#]+).*', r'\1', u) for u in urls)
    print(f"== {scen}: netlog {len(t)//1024} KB, {len(urls)} url events")
    for h, n in hosts.most_common(25):
        if h not in ("127.0.0.1", "localhost"):
            ex = next((u for u in urls if u.startswith(("https://"+h, "http://"+h))), "")
            print(f"   {n:3}  {h}   e.g. {ex[:110]}")
