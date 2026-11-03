"""Pre-render bitmap fonts for the Pico (MicroPython can't rasterize TrueType).

Uses Pillow's built-in font for ASCII (an ASCII-only subset of Aileron) and the full
Aileron (tools/fonts/Aileron-Regular.otf) for accented letters and symbols, which the
subset lacks: they used to render as a placeholder box. Same design and line metrics, so
ASCII text keeps its exact widths. Writes one .bin per size:

    b"BF" | height u8 | ascent u8 | count u16
    count x (codepoint u16, width u8, advance u8, offset u32)
    glyph bitmaps: height rows x ceil(width/8) bytes, MONO_HLSB (MSB = leftmost pixel)

Covers printable ASCII plus Latin-1 letters (French accents) and a few symbols.
Run: uv run --with pillow tools/make_fonts.py
"""

import struct
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "device" / "fonts"
FULL = Path(__file__).resolve().parent / "fonts" / "Aileron-Regular.otf"
SIZES = {"small": 11, "body": 15, "title": 21}
THRESHOLD = 90  # grey level (0..255) that becomes a lit pixel
CHARS = [chr(c) for c in range(32, 127)] + [chr(c) for c in range(0xC0, 0x100)] + list(
    "’…°·éŒœ€£×÷«»"
)


# Small accent marks drawn by hand: at 11-15 px the font's own grave and acute come out
# as a single pixel or the same shape, so "è" looked like "é". Rows top to bottom.
MARKS = {
    "\u0301": [".#", "#."],               # acute
    "\u0300": ["#.", ".#"],               # grave
    "\u0302": [".#.", "#.#"],             # circumflex
    "\u0308": ["#.#"],                    # diaeresis
    "\u0303": [".#.#", "#.#."],           # tilde
    "\u030a": [".#.", "#.#", ".#."],      # ring
    "\u0327": [".#.", "..#", ".#."],      # cedilla (below)
}
MARK_SCALE_FROM = 20   # px: from this size up, each mark pixel is drawn 2x2


def rasterize(font, ch, height, space_pad=0):
    """(rows of 0/1, width, advance) for one character."""
    left, _, right, _ = font.getbbox(ch)
    advance = max(1, round(font.getlength(ch))) + space_pad
    width = max(1, max(right, advance) - min(left, 0))
    # Render antialiased, then threshold low: drawing straight into 1-bit mode drops
    # thin strokes (most of "t" vanished, leaving a stem that looked shifted left).
    gray = Image.new("L", (width, height), 0)
    ImageDraw.Draw(gray).text((-min(left, 0), 0), ch, font=font, fill=255)
    px = gray.load()
    rows = [[1 if px[x, y] >= THRESHOLD else 0 for x in range(width)] for y in range(height)]
    return rows, width, advance


def compose(ascii_font, full, ch, height, scale=1):
    """Base letter + hand-drawn mark, or None if ch isn't a letter with one simple accent."""
    parts = unicodedata.normalize("NFD", ch)
    if len(parts) != 2 or parts[1] not in MARKS or not parts[0].isascii():
        return None
    base = "\u0131" if parts[0] == "i" else parts[0]      # dotless i under the accent
    rows, width, advance = rasterize(full if base == "\u0131" else ascii_font, base, height)
    ink = [y for y in range(height) if any(rows[y])]
    cols = [x for x in range(width) if any(rows[y][x] for y in range(height))]
    mark = [("".join(c * scale for c in line)) for line in MARKS[parts[1]] for _ in range(scale)]
    mw = len(mark[0])
    x0 = max(0, (cols[0] + cols[-1]) // 2 - (mw - 1) // 2)
    if x0 + mw > width:          # mark wider than a narrow letter: widen the bitmap only
        rows = [r + [0] * (x0 + mw - width) for r in rows]
        width = x0 + mw
    if parts[1] == "\u0327":                               # below the letter
        y0 = min(ink[-1] + 1, height - len(mark))
    else:                                                  # above, one blank row between
        y0 = max(0, ink[0] - scale - len(mark))
    for dy, line in enumerate(mark):
        for dx, c in enumerate(line):
            if c == "#":
                rows[y0 + dy][x0 + dx] = 1
    return rows, width, advance


def render(size: int) -> bytes:
    ascii_font = ImageFont.load_default(size=size)
    full = ImageFont.truetype(str(FULL), size)
    if full.getmetrics() != ascii_font.getmetrics():
        raise SystemExit("font metrics differ at size %d" % size)
    ascent, descent = ascii_font.getmetrics()
    height = ascent + descent
    index, data = [], bytearray()
    for ch in dict.fromkeys(CHARS):  # dedupe, keep order
        glyph = compose(ascii_font, full, ch, height, 2 if size >= MARK_SCALE_FROM else 1)
        if glyph is None:
            font = ascii_font if ord(ch) < 127 else full
            # Aileron's spaces are tight at these small sizes: one extra pixel.
            glyph = rasterize(font, ch, height, space_pad=1 if ch == " " else 0)
        rows, width, advance = glyph
        row_bytes = (width + 7) // 8
        offset = len(data)
        for y in range(height):
            for bx in range(row_bytes):
                b = 0
                for bit in range(8):
                    x = bx * 8 + bit
                    if x < width and rows[y][x]:
                        b |= 0x80 >> bit
                data.append(b)
        index.append(struct.pack("<HBBI", ord(ch), width, advance, offset))
    header = b"BF" + struct.pack("<BBH", height, ascent, len(index))
    return header + b"".join(index) + bytes(data)


def main() -> None:
    """make_fonts.py [OUT_DIR name=size ...]: other sizes for other projects, e.g.
    make_fonts.py /tmp/bigfonts small=20 body=28"""
    import sys
    global OUT
    sizes = SIZES
    if len(sys.argv) > 1:
        OUT = Path(sys.argv[1])
        sizes = {k: int(v) for k, v in (a.split("=") for a in sys.argv[2:])}
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in sizes.items():
        blob = render(size)
        (OUT / f"{name}.bin").write_bytes(blob)
        print(f"{name}.bin: size {size}px, height {blob[2]}px, {len(blob)} bytes")


if __name__ == "__main__":
    main()
