"""
Builds the demo documents into demo-docs/.

Run inside the backend image, which has the font:  make demo-docs

The PDFs embed WenQuanYi Zen Hei, a Chinese font with TrueType outlines, so that
pdfplumber reads the Chinese text back exactly. (reportlab cannot embed CFF-based fonts
such as the Noto CJK .ttc files.) Output is byte-for-byte the same on every run.
"""

import math
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.seed.demo_docs import (
    CHANGED_DETAILS_ROWS,
    HIDDEN_INSTRUCTION,
    MESSAGE_TEXTS,
    RENT_INVOICE_LINES,
    TUITION_INVOICE_ROWS,
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


NAVY = (15 / 255, 30 / 255, 46 / 255)
GREY_TEXT = (74 / 255, 85 / 255, 104 / 255)
FAINT_TEXT = (110 / 255, 117 / 255, 128 / 255)  # still far from white: pale text would be flagged as hidden
ALERT_TEXT = (138 / 255, 75 / 255, 0)
RULE = (0.80, 0.82, 0.85)
SHADE = (0.965, 0.97, 0.975)
HEAD = (0.91, 0.93, 0.955)
HIGHLIGHT = (1.0, 0.957, 0.898)
NOTICE = (0.933, 0.965, 0.957)
CREST = (0.93, 0.95, 0.97)
TEAL = (18 / 255, 128 / 255, 111 / 255)
SEAL = (0.75, 0.16, 0.13)
LEFT = MARGIN
RIGHT = A4[0] - MARGIN
VALUE_X = {"meta": LEFT + 112, "pay": LEFT + 150}

# role -> (font size, colour)
STYLE = {
    "crest": (11, NAVY),
    "name": (15, NAVY),
    "local": (11, GREY_TEXT),
    "address": (8.5, GREY_TEXT),
    "title": (19, NAVY),
    "meta": (9.5, NAVY),
    "items_head": (9.5, GREY_TEXT),
    "item": (10, NAVY),
    "total": (11.5, NAVY),
    "pay_head": (11, NAVY),
    "pay": (9.5, NAVY),
    "pay_alert": (9.5, ALERT_TEXT),
    "pay_note": (8.8, GREY_TEXT),
    "notice": (8.8, NAVY),
    "footer": (8.5, GREY_TEXT),
    "sample": (7, FAINT_TEXT),
}
# role -> (space before the first row of the section, space between its rows), in points
SPACING = {
    "crest": (0, 0), "name": (12, 0), "local": (18, 0), "address": (14, 0), "title": (50, 0),
    "meta": (34, 15), "items_head": (40, 0), "item": (22, 22), "total": (24, 0), "pay_head": (46, 0),
    "pay": (22, 17), "pay_alert": (17, 15), "pay_note": (20, 14), "notice": (24, 14),
}
FOOTER_BASELINE, SAMPLE_BASELINE = 96, 46


def _crest(page: canvas.Canvas, x: float, top: float) -> None:
    """A plain shield outline. The initials inside are drawn as text by the caller."""
    width, height = 44, 54
    path = page.beginPath()
    path.moveTo(x, top)
    path.lineTo(x + width, top)
    path.lineTo(x + width, top - height * 0.55)
    path.curveTo(x + width, top - height * 0.85, x + width * 0.62, top - height * 0.95, x + width / 2, top - height)
    path.curveTo(x + width * 0.38, top - height * 0.95, x, top - height * 0.85, x, top - height * 0.55)
    path.close()
    page.setFillColorRGB(*CREST)
    page.setStrokeColorRGB(*NAVY)
    page.setLineWidth(1.6)
    page.drawPath(path, stroke=1, fill=1)
    page.setLineWidth(0.8)
    page.line(x + 9, top - 30, x + width - 9, top - 30)
    page.setFillColorRGB(*NAVY)
    for column in (0, 1, 2):  # three columns of a small building under the initials
        page.rect(x + 13 + column * 7, top - 42, 3.2, 9, stroke=0, fill=1)
    page.rect(x + 11, top - 44, 22, 2, stroke=0, fill=1)


def _seal(page: canvas.Canvas, x: float, y: float) -> None:
    """A red finance-office seal: rings and a star, no text."""
    page.setStrokeColorRGB(*SEAL)
    page.setLineWidth(1.8)
    page.circle(x, y, 30, stroke=1, fill=0)
    page.setLineWidth(0.7)
    page.circle(x, y, 25.5, stroke=1, fill=0)
    page.setFillColorRGB(*SEAL)
    path = page.beginPath()
    for i in range(10):
        radius = 10 if i % 2 == 0 else 4
        angle = math.pi / 2 + i * math.pi / 5
        point = (x + radius * math.cos(angle), y + radius * math.sin(angle))
        if i == 0:
            path.moveTo(*point)
        else:
            path.lineTo(*point)
    path.close()
    page.drawPath(path, stroke=0, fill=1)


def write_invoice_pdf(path: Path, title: str, rows: list[tuple[str, tuple[str, ...]]]) -> None:
    """
    An invoice laid out like a real one: crest and letterhead, invoice details, line items
    with the total, a boxed "How to pay" section and a footer. Every part is drawn as dark
    text at a normal size, one row at a time from top to bottom, so the PDF reads back as
    row_lines(rows): one line per row, its columns joined by a space.
    """
    page = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    page.setTitle(title)
    page.setAuthor("Bridge demo (fictional document)")

    # First pass: the baseline of every row.
    y = A4[1] - 62
    placed: list[tuple[str, tuple[str, ...], float]] = []
    previous = None
    for role, parts in rows:
        if role == "footer":
            y = FOOTER_BASELINE
        elif role == "sample":
            y = SAMPLE_BASELINE
        else:
            lead, step = SPACING[role]
            y -= step if role == previous else lead
        placed.append((role, parts, y))
        previous = role
    baselines = {role: [b for r, _, b in placed if r == role] for role, _, _ in placed}

    def band(role: str, above: float, below: float) -> tuple[float, float]:
        return baselines[role][0] + above, baselines[role][-1] - below

    # Backgrounds and rules, drawn before the text.
    _crest(page, LEFT, A4[1] - 50)
    page.setFillColorRGB(*NAVY)
    page.rect(LEFT, baselines["address"][0] - 14, RIGHT - LEFT, 2.2, stroke=0, fill=1)
    page.setFillColorRGB(*TEAL)
    page.rect(LEFT, baselines["address"][0] - 18, RIGHT - LEFT, 0.8, stroke=0, fill=1)

    top, bottom = band("meta", 18, 9)
    page.setFillColorRGB(*SHADE)
    page.setStrokeColorRGB(*RULE)
    page.setLineWidth(0.6)
    page.rect(LEFT, bottom, RIGHT - LEFT, top - bottom, stroke=1, fill=1)

    for role, fill, height in (("items_head", HEAD, 22), ("item", (1, 1, 1), 22), ("total", HIGHLIGHT, 26)):
        for baseline in baselines[role]:
            page.setFillColorRGB(*fill)
            page.setStrokeColorRGB(*RULE)
            page.rect(LEFT, baseline - (9 if role == "total" else 7.5), RIGHT - LEFT, height, stroke=1, fill=1)

    top = baselines["pay_head"][0] + 20
    bottom = baselines["notice"][-1] - 14
    page.setFillColorRGB(1, 1, 1)
    page.setStrokeColorRGB(*NAVY)
    page.setLineWidth(1)
    page.rect(LEFT, bottom, RIGHT - LEFT, top - bottom, stroke=1, fill=1)
    note_top, note_bottom = baselines["notice"][0] + 13, baselines["notice"][-1] - 7
    page.setFillColorRGB(*NOTICE)
    page.setStrokeColorRGB(*TEAL)
    page.setLineWidth(0.6)
    page.rect(LEFT + 8, note_bottom, RIGHT - LEFT - 16, note_top - note_bottom, stroke=1, fill=1)
    if "pay_alert" in baselines:
        alert_top, alert_bottom = baselines["pay_alert"][0] + 12, baselines["pay_alert"][-1] - 6
        page.setFillColorRGB(*HIGHLIGHT)
        page.setStrokeColorRGB(0.85, 0.54, 0.12)
        page.rect(LEFT + 8, alert_bottom, RIGHT - LEFT - 16, alert_top - alert_bottom, stroke=1, fill=1)

    page.setStrokeColorRGB(*RULE)
    page.setLineWidth(0.6)
    page.line(LEFT, baselines["footer"][0] + 16, RIGHT, baselines["footer"][0] + 16)
    _seal(page, RIGHT - 46, baselines["footer"][0] + 2)

    # Second pass: the text.
    for role, parts, baseline in placed:
        size, colour = STYLE[role]
        page.setFillColorRGB(*colour)
        if role == "crest":
            page.setFont("Helvetica-Bold", size)
            page.drawCentredString(LEFT + 22, A4[1] - 50 - 14, parts[0])  # above the name line, so it reads first
            continue
        page.setFont(FONT, size)
        if role in ("name", "local", "address"):
            page.drawString(LEFT + 58, baseline, parts[0])
        elif role in VALUE_X:
            page.drawString(LEFT + 12, baseline, parts[0])
            page.drawString(VALUE_X[role], baseline, parts[1])
        elif role in ("items_head", "item", "total"):
            page.drawString(LEFT + 12, baseline, parts[0])
            page.drawRightString(RIGHT - 12, baseline, parts[1])
        elif role in ("pay_head", "pay_note"):
            page.drawString(LEFT + 12, baseline, parts[0])
        elif role in ("pay_alert", "notice"):
            page.drawString(LEFT + 16, baseline, parts[0])
        else:
            page.drawString(LEFT, baseline, parts[0])
        for part in parts:
            assert pdfmetrics.stringWidth(part, FONT, size) < RIGHT - LEFT - 24, f"too wide: {part}"
    page.showPage()
    page.save()


def main(output: Path) -> None:
    if not Path(FONT_FILE).exists():
        raise SystemExit(f"Font not found: {FONT_FILE}. Run this inside the backend image (make demo-docs).")
    pdfmetrics.registerFont(TTFont(FONT, FONT_FILE, subfontIndex=0))
    output.mkdir(parents=True, exist_ok=True)

    write_invoice_pdf(output / "tuition_invoice.pdf", "Tuition Fee Invoice", TUITION_INVOICE_ROWS)
    write_invoice_pdf(output / "changed_details_invoice.pdf", "Tuition Fee Invoice", CHANGED_DETAILS_ROWS)
    write_pdf(output / "invoice_injection_en.pdf", "Rent Invoice", RENT_INVOICE_LINES, hidden=HIDDEN_INSTRUCTION)
    for filename, text in MESSAGE_TEXTS.items():
        (output / filename).write_text(text, encoding="utf-8")
    for path in sorted(output.iterdir()):
        if path.suffix in (".pdf", ".txt"):
            print(f"{path.name}  {path.stat().st_size} bytes")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else demo_docs_dir())
