import fitz, sys
for name in ("claude-code-apim-entra-setup", "codex-apim-entra-setup"):
    d = fitz.open(rf"C:\Users\USER\Local\apim-harness-test\handoff\pdf\{name}.pdf")
    for i in (0, 1):
        d[i].get_pixmap(dpi=80).save(rf"C:\Users\USER\Local\apim-harness-test\handoff\pdf\{name}-p{i+1}.png")
    print(name, d.page_count)
