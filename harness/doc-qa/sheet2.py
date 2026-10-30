import pymupdf
d = pymupdf.open(r"C:\Users\USER\Local\apim-harness-test\handoff\pdf\no-vendor-egress-harness-setup.pdf")
pm = [d[i].get_pixmap(dpi=75) for i in range(min(4, d.page_count))]
w, h = pm[0].width, pm[0].height
s = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w * 2, h * 2), False); s.set_rect(s.irect, (255, 255, 255))
for i, p in enumerate(pm):
    p.set_origin((i % 2) * w, (i // 2) * h); s.copy(p, p.irect)
s.save(r"C:\Users\USER\Local\apim-harness-test\handoff\pdf\no-vendor-egress-sheet.png"); print(d.page_count)
