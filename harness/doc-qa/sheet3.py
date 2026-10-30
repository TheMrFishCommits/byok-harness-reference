import pymupdf, sys
D = r"C:\Users\USER\Local\apim-harness-test\handoff\byok-reference\pdf"
for n in ("00-summary-reference", "01-testing-scope-and-harness"):
    d = pymupdf.open(rf"{D}\{n}.pdf")
    k = min(6, d.page_count)
    pm = [d[i].get_pixmap(dpi=70) for i in range(k)]
    w, h = pm[0].width, pm[0].height
    cols, rows = 3, (k + 2) // 3
    s = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w * cols, h * rows), False); s.set_rect(s.irect, (255, 255, 255))
    for i, p in enumerate(pm):
        p.set_origin((i % cols) * w, (i // cols) * h); s.copy(p, p.irect)
    s.save(rf"{D}\{n}-sheet.png"); print(n, d.page_count)
