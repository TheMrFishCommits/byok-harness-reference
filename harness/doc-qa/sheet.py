import pymupdf, glob
H = r"C:\Users\USER\Local\apim-harness-test\handoff"
for n in ("codex-apim-entra-setup", "claude-code-apim-entra-setup", "vscode-extensions-apim-entra-setup"):
    d = pymupdf.open(rf"{H}\pdf\{n}.pdf")
    pm = [d[i].get_pixmap(dpi=70) for i in range(d.page_count)]
    w, h = pm[0].width, pm[0].height
    sheet = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w * 2, h * 2), False)
    sheet.set_rect(sheet.irect, (255, 255, 255))
    for i, p in enumerate(pm[:4]):
        p.set_origin((i % 2) * w, (i // 2) * h)
        sheet.copy(p, p.irect)
    sheet.save(rf"{H}\pdf\{n}-sheet.png")
    print(n, d.page_count, sheet.width, sheet.height)
