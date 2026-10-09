"""Turns an uploaded file or a pasted message into plain text, keeping how each character looked."""

import io
from dataclasses import dataclass, field
from typing import Any

LINE_TOLERANCE = 2.0  # points: characters this close vertically are on the same line


class UnreadableDocument(ValueError):
    pass


@dataclass
class ReadResult:
    text: str
    # Runs of characters that share a size and colour: {"start", "end", "size", "color": [r, g, b]}.
    # Empty when the source carries no such information (images, pasted text).
    runs: list[dict[str, Any]] = field(default_factory=list)


def _rgb(color: Any) -> list[float]:
    """pdfplumber reports grey, RGB or CMYK. Normalise to RGB in the range 0 to 1."""
    if color is None:
        return [0.0, 0.0, 0.0]
    values = [float(value) for value in (color if isinstance(color, (list, tuple)) else [color])]
    if len(values) == 1:
        return [values[0]] * 3
    if len(values) == 4:
        c, m, y, k = values
        return [round(1 - min(1.0, part + k), 3) for part in (c, m, y)]
    return [round(value, 3) for value in values[:3]]


def read_pdf(data: bytes) -> ReadResult:
    """Text of a PDF, line by line, with the size and colour of every character."""
    import pdfplumber

    text_parts: list[str] = []
    runs: list[dict[str, Any]] = []
    offset = 0

    def add(piece: str, size: float | None, color: list[float] | None) -> None:
        nonlocal offset
        text_parts.append(piece)
        if size is not None and color is not None:
            last = runs[-1] if runs else None
            if last and last["end"] == offset and last["size"] == size and last["color"] == color:
                last["end"] = offset + len(piece)
            else:
                runs.append({"start": offset, "end": offset + len(piece), "size": size, "color": color})
        offset += len(piece)

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            first_line = True
            for page in pdf.pages:
                chars = sorted(page.chars, key=lambda char: (char["top"], char["x0"]))
                lines: list[list[dict[str, Any]]] = []
                for char in chars:
                    if lines and abs(char["top"] - lines[-1][0]["top"]) <= LINE_TOLERANCE:
                        lines[-1].append(char)
                    else:
                        lines.append([char])
                for line in lines:
                    if not first_line:
                        add("\n", None, None)
                    first_line = False
                    previous = None
                    for char in sorted(line, key=lambda item: item["x0"]):
                        size, color = round(float(char["size"]), 2), _rgb(char.get("non_stroking_color"))
                        # Some PDFs position words without space characters: put the space back.
                        gap = char["x0"] - previous["x1"] if previous else 0
                        if previous and gap > 0.25 * size and not (char["text"].isspace() or previous["text"].isspace()):
                            add(" ", size, color)
                        add(char["text"], size, color)
                        previous = char
    except Exception as error:  # pdfplumber raises several unrelated types on a damaged file
        raise UnreadableDocument("This PDF could not be read.") from error

    text = "".join(text_parts)
    if not text.strip():
        raise UnreadableDocument("This PDF has no text. Upload it as an image so it can be read by OCR.")
    return ReadResult(text=text, runs=runs)


def read_image(data: bytes) -> ReadResult:
    """Text of a photo or scan, read by OCR in Simplified Chinese and English."""
    import pytesseract
    from PIL import Image

    try:
        image = Image.open(io.BytesIO(data))
        text = pytesseract.image_to_string(image, lang="chi_sim+eng")
    except Exception as error:  # Pillow and tesseract raise several unrelated types
        raise UnreadableDocument("This image could not be read.") from error
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not text:
        raise UnreadableDocument("No text was found in this image.")
    return ReadResult(text=text)


def read_message(text: str) -> ReadResult:
    """A pasted message. Line endings are normalised; nothing else is changed or removed."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not cleaned.strip():
        raise UnreadableDocument("The message is empty.")
    return ReadResult(text=cleaned)
