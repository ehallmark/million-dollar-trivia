# Bitmap fonts pre-rendered by tools/make_fonts.py (proportional, with French accents).
# Kept lean on RAM: glyph metrics are read from the font file's bytes on demand.
import framebuf
import os
import struct

_KEY = 0x2108  # an RGB565 value never used as a text colour: marks transparent pixels
_ASCII = 95    # the first 95 glyphs are printable ASCII (32..126), in order


class Font:
    def __init__(self, path):
        # framebuf needs a writable buffer, so read into a bytearray.
        blob = bytearray(os.stat(path)[6])
        with open(path, "rb") as f:
            f.readinto(blob)
        if blob[:2] != b"BF":
            raise ValueError("not a font file: " + path)
        self.height, self.ascent, self._count = struct.unpack_from("<BBH", blob, 2)
        self._blob = blob
        self._data_start = 6 + self._count * 8
        # Non-ASCII glyphs (accents, symbols): codepoint -> glyph index.
        self._extra = {}
        for i in range(_ASCII, self._count):
            self._extra[struct.unpack_from("<H", blob, 6 + i * 8)[0]] = i
        self._fbs = {}
        self._pal = framebuf.FrameBuffer(bytearray(4), 2, 1, framebuf.RGB565)
        self._pal.pixel(0, 0, _KEY)

    def _index(self, ch):
        c = ord(ch)
        if 32 <= c < 127:
            return c - 32
        return self._extra.get(c, ord("?") - 32)

    def _metrics(self, i):
        _, width, advance, offset = struct.unpack_from("<HBBI", self._blob, 6 + i * 8)
        return width, advance, offset

    def advance(self, ch):
        return self._blob[6 + self._index(ch) * 8 + 3]

    def width(self, text):
        blob = self._blob
        return sum(blob[6 + self._index(c) * 8 + 3] for c in text)

    def draw(self, fb, text, x, y, color):
        """Draw text with its top-left at (x, y). Returns the x after the last glyph."""
        self._pal.pixel(1, 0, color)
        pal, fbs = self._pal, self._fbs
        for ch in text:
            i = self._index(ch)
            glyph = fbs.get(i)
            if glyph is None:  # first use: build and cache the glyph's frame buffer
                width, advance, offset = self._metrics(i)
                start = self._data_start + offset
                size = ((width + 7) // 8) * self.height
                glyph = (framebuf.FrameBuffer(memoryview(self._blob)[start:start + size], width,
                                              self.height, framebuf.MONO_HLSB), advance)
                fbs[i] = glyph
            fb.blit(glyph[0], x, y, _KEY, pal)
            x += glyph[1]
        return x

    def draw_center(self, fb, text, cx, y, color):
        self.draw(fb, text, cx - self.width(text) // 2, y, color)

    def draw_right(self, fb, text, rx, y, color):
        self.draw(fb, text, rx - self.width(text), y, color)

    def wrap(self, text, max_width):
        """Word-wrap text into lines no wider than max_width pixels."""
        lines, line = [], ""
        for word in text.split():
            trial = word if not line else line + " " + word
            if self.width(trial) <= max_width:
                line = trial
                continue
            if line:
                lines.append(line)
            while self.width(word) > max_width:  # a word wider than a line: hard-break it
                cut = len(word)
                while cut > 1 and self.width(word[:cut]) > max_width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        if line:
            lines.append(line)
        return lines

    def fit(self, text, max_width):
        """Truncate text with an ellipsis so it fits on one line."""
        if self.width(text) <= max_width:
            return text
        while text and self.width(text + "...") > max_width:
            text = text[:-1]
        return text + "..."
