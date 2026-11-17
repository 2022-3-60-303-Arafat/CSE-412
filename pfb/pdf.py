"""A very small PDF writer for text reports. Standard library only.

It knows headings, paragraphs and rules on A4 pages, with the two built-in
Helvetica fonts. That is all the legal report (PB-18) needs.
"""

import textwrap

PAGE_WIDTH, PAGE_HEIGHT, MARGIN = 595, 842, 56
# style: (font, size, space above the line, line height)
STYLES = {
    "title": ("F2", 20, 0, 26),
    "heading": ("F2", 13, 12, 18),
    "text": ("F1", 11, 0, 15),
    "bold": ("F2", 11, 0, 15),
    "small": ("F1", 9, 0, 12),
}
# Helvetica letters are about half as wide as they are tall; bold is a little wider.
CHAR_WIDTH = {"F1": 0.5, "F2": 0.56}


def _encode(text):
    """Text as a PDF string. Letters outside Latin-1 (for example Bangla) become '?'."""
    raw = str(text).encode("latin-1", "replace").decode("latin-1")
    return "(" + raw.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def build_pdf(blocks):
    """Build a PDF from (style, text) pairs. Style is a key of STYLES, "gap" or "rule"."""
    pages = [[]]
    y = PAGE_HEIGHT - MARGIN

    def room(height):
        nonlocal y
        if y - height < MARGIN:
            pages.append([])
            y = PAGE_HEIGHT - MARGIN

    for style, text in blocks:
        if style == "gap":
            y -= 10
            continue
        if style == "rule":
            room(12)
            y -= 6
            pages[-1].append(f"0.7 G 0.8 w {MARGIN} {y} m {PAGE_WIDTH - MARGIN} {y} l S")
            y -= 6
            continue
        font, size, above, line_height = STYLES[style]
        width = int((PAGE_WIDTH - 2 * MARGIN) / (size * CHAR_WIDTH[font]))
        lines = textwrap.wrap(str(text), width) or [""]
        room(above + line_height * min(len(lines), 2))
        y -= above
        for line in lines:
            room(line_height)
            y -= line_height
            pages[-1].append(f"BT /{font} {size} Tf {MARGIN} {y} Td {_encode(line)} Tj ET")

    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        None,  # the page list, filled in below
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    kids = []
    for operations in pages:
        stream = "\n".join(operations)
        page_number = len(objects) + 1
        kids.append(f"{page_number} 0 R")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] /Contents {page_number + 1} 0 R "
            "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>"
        )
        objects.append(f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"

    output = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode("latin-1")
    output += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("latin-1")
    return output
