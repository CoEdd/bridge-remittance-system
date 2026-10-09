"""
Builds the demo documents into demo-docs/.

Run inside the backend image, which has the font:  make demo-docs

The PDFs embed WenQuanYi Zen Hei, a Chinese font with TrueType outlines, so that
pdfplumber reads the Chinese text back exactly. (reportlab cannot embed CFF-based fonts
such as the Noto CJK .ttc files.) Output is byte-for-byte the same on every run.
"""

import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.seed.demo_docs import (
    CHANGED_DETAILS_LINES,
    HIDDEN_INSTRUCTION,
    MESSAGE_TEXTS,
    RENT_INVOICE_LINES,
    TUITION_INVOICE_LINES,
    demo_docs_dir,
)

FONT_FILE = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
FONT = "WenQuanYiZenHei"
SIZE = 10
LEADING = 18
MARGIN = 50
HIDDEN_SIZE = 1


def _wrap(line: str, width: float) -> list[str]:
    """Break a line at spaces so that each piece fits the page width."""
    pieces, current = [], ""
    for word in line.split(" "):
        candidate = f"{current} {word}" if current else word
        if current and pdfmetrics.stringWidth(candidate, FONT, SIZE) > width:
            pieces.append(current)
            current = word
        else:
            current = candidate
    return [*pieces, current]


def drawn_lines(lines: list[str]) -> list[str]:
    """The lines exactly as they appear on the page, after wrapping."""
    width = A4[0] - 2 * MARGIN
    return [piece for line in lines for piece in _wrap(line, width)]


def write_pdf(path: Path, title: str, lines: list[str], hidden: str | None = None) -> None:
    page = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    page.setTitle(title)
    page.setAuthor("Bridge demo (fictional document)")
    page.setFont(FONT, SIZE)
    page.setFillColorRGB(0, 0, 0)
    y = A4[1] - MARGIN - SIZE
    for line in drawn_lines(lines):
        page.drawString(MARGIN, y, line)
        y -= LEADING
    if hidden:
        # White, 1-point text near the bottom: invisible to a person, readable by software.
        page.setFont(FONT, HIDDEN_SIZE)
        page.setFillColorRGB(1, 1, 1)
        page.drawString(MARGIN, MARGIN, hidden)
    page.showPage()
    page.save()


def main(output: Path) -> None:
    if not Path(FONT_FILE).exists():
        raise SystemExit(f"Font not found: {FONT_FILE}. Run this inside the backend image (make demo-docs).")
    pdfmetrics.registerFont(TTFont(FONT, FONT_FILE, subfontIndex=0))
    output.mkdir(parents=True, exist_ok=True)

    write_pdf(output / "tuition_invoice.pdf", "Tuition Fee Invoice", TUITION_INVOICE_LINES)
    write_pdf(output / "changed_details_invoice.pdf", "Tuition Fee Invoice", CHANGED_DETAILS_LINES)
    write_pdf(output / "invoice_injection_en.pdf", "Rent Invoice", RENT_INVOICE_LINES, hidden=HIDDEN_INSTRUCTION)
    for filename, text in MESSAGE_TEXTS.items():
        (output / filename).write_text(text, encoding="utf-8")
    for path in sorted(output.iterdir()):
        if path.suffix in (".pdf", ".txt"):
            print(f"{path.name}  {path.stat().st_size} bytes")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else demo_docs_dir())
