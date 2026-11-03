# Drawing helpers and the colour theme (dark blue and gold, game-show style).
from font import Font
from hat import H, W, rgb

# Small screens (the 1.44" HAT, 128x128) get compact layouts throughout.
COMPACT = W < 200

SMALL = Font("/fonts/small.bin")
BODY = Font("/fonts/body.bin")
TITLE = Font("/fonts/title.bin")

WHITE = rgb(255, 255, 255)
BLACK = rgb(0, 0, 0)
GOLD = rgb(255, 196, 48)
DIM_GOLD = rgb(150, 110, 30)
LIGHT = rgb(170, 195, 255)
DIM = rgb(85, 95, 140)
PANEL = rgb(16, 26, 78)
PANEL_EDGE = rgb(80, 120, 225)
SELECT = rgb(240, 168, 28)
LOCKED = rgb(255, 112, 0)
GREEN = rgb(28, 168, 72)
RED = rgb(196, 32, 44)
REMOVED = rgb(22, 26, 52)

_TOP, _BOTTOM = (8, 8, 40), (34, 20, 98)
_ROWS = [rgb(_TOP[0] + (_BOTTOM[0] - _TOP[0]) * y // H,
             _TOP[1] + (_BOTTOM[1] - _TOP[1]) * y // H,
             _TOP[2] + (_BOTTOM[2] - _TOP[2]) * y // H) for y in range(H)]


def background(lcd, y0=0, y1=H):
    rows = _ROWS
    for y in range(y0, y1):
        lcd.hline(0, y, W, rows[y])


def panel(lcd, x, y, w, h, fill=PANEL, edge=PANEL_EDGE):
    """A rounded box with a 1 px border."""
    lcd.fill_rect(x + 1, y + 1, w - 2, h - 2, fill)
    lcd.hline(x + 2, y, w - 4, edge)
    lcd.hline(x + 2, y + h - 1, w - 4, edge)
    lcd.vline(x, y + 2, h - 4, edge)
    lcd.vline(x + w - 1, y + 2, h - 4, edge)
    lcd.pixel(x + 1, y + 1, edge)
    lcd.pixel(x + w - 2, y + 1, edge)
    lcd.pixel(x + 1, y + h - 2, edge)
    lcd.pixel(x + w - 2, y + h - 2, edge)


def money(amount):
    s = str(amount)
    out = ""
    while len(s) > 3:
        out = "," + s[-3:] + out
        s = s[:-3]
    return "$" + s + out


def money_short(amount):
    """$1M, $250K, $32K, $500: for tight columns on the small screen."""
    if amount >= 1000000 and amount % 1000000 == 0:
        return "$%dM" % (amount // 1000000)
    if amount >= 1000 and amount % 1000 == 0:
        return "$%dK" % (amount // 1000)
    return money(amount)


def hint(lcd, text, y=None):
    """A small centred hint line at the bottom of the screen."""
    if COMPACT:  # "^v choose   K1 = OK" -> "^v K1=OK"
        text = SMALL.fit(text.replace(" = ", "=").replace("choose", "").replace("   ", " ")
                         .replace("  ", " ").strip(), W - 4)
    SMALL.draw_center(lcd, text, W // 2, (H - 14 if COMPACT else H - 16) if y is None else y, DIM)


def text_block(lcd, font, lines, x, y, color, line_gap=0, center=False, width=W):
    for i, line in enumerate(lines):
        yy = y + i * (font.height + line_gap)
        if center:
            font.draw_center(lcd, line, x + width // 2, yy, color)
        else:
            font.draw(lcd, line, x, yy, color)


# KEY1 (the top button) is OK; pressing the joystick in works too. KEY2 is back.
OK = ("KEY1", "PRESS")


def menu(lcd, inp, title, items, start=0, subtitle=None, right=None, rows=8, row_h=24, top=40,
         footer="^v choose   K1 = OK   K2 = back"):
    """A scrollable list. Returns the chosen index, or None on KEY2 (back).

    right(i) can return short text shown right-aligned on each row (e.g. a best score).
    """
    if COMPACT:  # the callers' sizes are for 240x240: recompute for the small screen
        top = 33 if subtitle else 21
        room = H - 16 - top
        row_h = max(17, min(28, room // len(items)))   # short menus get big rows
        rows = room // row_h
    sel, first = start, max(0, start - rows + 1)
    while True:
        scroll = None
        first = min(max(first, sel - rows + 1), sel)
        background(lcd)
        if COMPACT:
            BODY.draw_center(lcd, BODY.fit(title, W - 4), W // 2, 1, GOLD)
            if subtitle:
                SMALL.draw_center(lcd, SMALL.fit(subtitle, W - 4), W // 2, 19, LIGHT)
        else:
            TITLE.draw_center(lcd, title, W // 2, 4, GOLD)
            if subtitle:
                SMALL.draw_center(lcd, subtitle, W // 2, 28, LIGHT)
        for row in range(min(rows, len(items))):
            i = first + row
            if i >= len(items):
                break
            y = top + row * row_h
            chosen = i == sel
            color = BLACK if chosen else WHITE
            if COMPACT:
                panel(lcd, 3, y, W - 8, row_h - 2, SELECT if chosen else PANEL,
                      GOLD if chosen else PANEL_EDGE)
                r = right(i) if right else ""
                room = W - 16 - (SMALL.width(r) + 4 if r else 0)
                font = BODY if row_h >= 22 and BODY.width(items[i]) <= room else SMALL
                ty = y + (row_h - 2 - font.height) // 2
                if chosen and font.width(items[i]) > room:   # scrolls while highlighted
                    scroll = (i, font, room, ty, y)
                font.draw(lcd, font.fit(items[i], room), 7, ty, color)
                if r:
                    SMALL.draw_right(lcd, r, W - 9, y + (row_h - 2 - SMALL.height) // 2,
                                     BLACK if chosen else GOLD)
                continue
            panel(lcd, 8, y, W - 16, row_h - 3, SELECT if chosen else PANEL,
                  GOLD if chosen else PANEL_EDGE)
            BODY.draw(lcd, BODY.fit(items[i], 150 if right else 200), 16, y + 1, color)
            if right:
                r = right(i)
                if r:
                    SMALL.draw_right(lcd, r, W - 16, y + 4, BLACK if chosen else GOLD)
        if len(items) > rows:  # scroll bar
            bar_h = rows * row_h * rows // len(items)
            bar_y = top + (rows * row_h - bar_h) * first // max(1, len(items) - rows)
            lcd.fill_rect(W - 3 if COMPACT else W - 4, bar_y, 2, bar_h, DIM)
        hint(lcd, footer)
        lcd.show()
        keys_ = ("UP", "DOWN", "KEY2", "RIGHT") + OK
        e = marquee(lcd, inp, keys_, items[scroll[0]], *scroll[1:]) if scroll else inp.wait(keys_)
        if e == "UP":
            sel = (sel - 1) % len(items)
        elif e == "DOWN":
            sel = (sel + 1) % len(items)
        elif e in OK or e == "RIGHT":
            inp.release()
            return sel
        elif e == "KEY2":
            inp.release()
            return None


def message(lcd, inp, title, body, footer="K1 to continue", wait=True):
    """A full-screen message with a wrapped body."""
    if COMPACT:
        return _message_compact(lcd, inp, title, body, footer, wait)
    background(lcd)
    TITLE.draw_center(lcd, title, W // 2, 14, GOLD)
    lines = BODY.wrap(body, W - 28)
    text_block(lcd, BODY, lines, 14, 52, WHITE, line_gap=2)
    hint(lcd, footer)
    lcd.show()
    if wait:
        inp.wait(OK + ("KEY2",))
        inp.release()


def _message_compact(lcd, inp, title, body, footer, wait):
    """Small-screen message: small text, split into pages when it doesn't fit."""
    room = H - 16 - 21
    font = BODY                       # the biggest font that fits on one page
    lines = [l for para in body.split("\n") for l in (BODY.wrap(para, W - 8) or [""])]
    if len(lines) * (BODY.height + 1) > room:
        font = SMALL
        lines = [l for para in body.split("\n") for l in (SMALL.wrap(para, W - 8) or [""])]
    step = font.height + (1 if font is BODY else -1)
    per = room // step
    pages = [lines[i:i + per] for i in range(0, len(lines), per)] or [[]]
    for n, page in enumerate(pages):
        background(lcd)
        BODY.draw_center(lcd, BODY.fit(title, W - 4), W // 2, 1, GOLD)
        for i, line in enumerate(page):
            font.draw(lcd, line, 4, 21 + i * step, WHITE)
        hint(lcd, footer if n == len(pages) - 1 else "K1 = more")
        lcd.show()
        if wait or n < len(pages) - 1:
            inp.wait(OK + ("KEY2",))
            inp.release()


_strip_fb = None


def marquee(lcd, inp, accept, text, font, room, ty, row_y, x=7, fill=None, color=None):
    """Wait for a key while scrolling `text` (too wide for `room` px) in place.
    Pauses at each end. Draws through an off-screen strip so it can't spill over."""
    global _strip_fb
    import framebuf
    fill = SELECT if fill is None else fill
    color = BLACK if color is None else color
    if _strip_fb is None or _strip_fb[1] != (room, font.height):
        buf = bytearray(room * font.height * 2)
        _strip_fb = (framebuf.FrameBuffer(buf, room, font.height, framebuf.RGB565), (room, font.height))
    strip = _strip_fb[0]
    overflow = font.width(text) - room
    offset, t, pause = 0, 0, 900
    while True:
        e = inp.wait(accept, timeout_ms=45)
        if e is not None:
            return e
        t += 45
        if t < pause:
            continue
        if offset < overflow:
            offset = min(overflow, offset + 3)
        elif t > pause + (overflow // 3) * 45 + pause:
            offset, t = 0, 0
        else:
            continue
        strip.fill(fill)
        font.draw(strip, text, -offset, 0, color)
        lcd.blit(strip, x, ty)
        lcd.show_rect(x, ty, room, font.height)
