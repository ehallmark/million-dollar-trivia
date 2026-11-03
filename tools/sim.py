"""Desktop preview: run the real device code on CPython and save screenshots.

Provides stand-ins for MicroPython's framebuf/machine/micropython modules and a scripted
button source, so layouts can be checked for either display without flashing a board.

  uv run --no-project --with pillow tools/sim.py 1.44 out_dir
"""

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- framebuf


class FrameBuffer:
    def __init__(self, buf, w, h, fmt):
        self.buf, self.w, self.h, self.fmt = buf, w, h, fmt

    def _set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            if self.fmt == RGB565:
                i = (y * self.w + x) * 2
                self.buf[i] = c & 0xFF
                self.buf[i + 1] = (c >> 8) & 0xFF
            else:
                raise NotImplementedError

    def _get(self, x, y):
        if self.fmt == RGB565:
            i = (y * self.w + x) * 2
            return self.buf[i] | (self.buf[i + 1] << 8)
        row = (self.w + 7) // 8
        return (self.buf[y * row + x // 8] >> (7 - x % 8)) & 1

    def pixel(self, x, y, c=None):
        if c is None:
            return self._get(x, y)
        self._set(x, y, c)

    def fill(self, c):
        self.fill_rect(0, 0, self.w, self.h, c)

    def fill_rect(self, x, y, w, h, c):
        for yy in range(max(0, y), min(self.h, y + h)):
            for xx in range(max(0, x), min(self.w, x + w)):
                self._set(xx, yy, c)

    def hline(self, x, y, w, c):
        self.fill_rect(x, y, w, 1, c)

    def vline(self, x, y, h, c):
        self.fill_rect(x, y, 1, h, c)

    def rect(self, x, y, w, h, c, fill=False):
        if fill:
            return self.fill_rect(x, y, w, h, c)
        self.hline(x, y, w, c)
        self.hline(x, y + h - 1, w, c)
        self.vline(x, y, h, c)
        self.vline(x + w - 1, y, h, c)

    def text(self, s, x, y, c=1):
        pass

    def blit(self, src, x, y, key=-1, palette=None):
        for yy in range(src.h):
            for xx in range(src.w):
                v = src._get(xx, yy)
                if palette is not None:
                    v = palette._get(v, 0)
                if v != key:
                    self._set(x + xx, y + yy, v)


RGB565, MONO_HLSB = 1, 3
framebuf = types.ModuleType("framebuf")
framebuf.FrameBuffer, framebuf.RGB565, framebuf.MONO_HLSB = FrameBuffer, RGB565, MONO_HLSB

# ---------------------------------------------------------------- machine / time


class _Pin:
    IN, OUT, PULL_UP = 0, 1, 2

    def __init__(self, *a, **k):
        self.v = 1

    def __call__(self, v=None):
        return self.value(v)

    def value(self, v=None):
        if v is None:
            return 1
        self.v = v


class _SPI:
    def __init__(self, *a, **k):
        pass

    def write(self, b):
        pass


machine = types.ModuleType("machine")
machine.Pin, machine.SPI = _Pin, _SPI
machine.mem32 = {}
machine.reset = lambda: print("(reset)")
machine.unique_id = lambda: b"\x00" * 8
micropython = types.ModuleType("micropython")
micropython.kbd_intr = lambda n: None
micropython.viper = lambda f: f
micropython.native = lambda f: f

import time as _t  # noqa: E402
for name, fn in (("sleep_ms", lambda ms: None), ("sleep_us", lambda us: None),
                 ("ticks_ms", lambda: int(_t.time() * 1000)), ("ticks_us", lambda: int(_t.time() * 1e6)),
                 ("ticks_diff", lambda a, b: a - b)):
    setattr(_t, name, fn)

sys.modules.update({"framebuf": framebuf, "machine": machine, "micropython": micropython})


def save_png(fb, path, scale=2):
    from PIL import Image
    px = []
    for i in range(0, fb.w * fb.h * 2, 2):
        v = fb.buf[i] | (fb.buf[i + 1] << 8)       # framebuf stores little-endian
        v = ((v & 0xFF) << 8) | (v >> 8)            # undo the byte swap in rgb()
        px.append((((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31))
    im = Image.new("RGB", (fb.w, fb.h))
    im.putdata(px)
    im.resize((fb.w * scale, fb.h * scale), Image.NEAREST).save(path)


def mount(display, root):
    """Make the board's absolute paths (/fonts, /q, /scores.json) point into `root`."""
    import builtins
    import os as _os
    os.makedirs(root, exist_ok=True)
    board = types.ModuleType("board")
    board.DISPLAY = display
    sys.modules["board"] = board

    def m(p):
        if isinstance(p, str) and p.startswith("/"):
            for prefix, local in (("/fonts/", os.path.join(ROOT, "device", "fonts") + "/"),
                                  ("/q/", os.path.join(ROOT, "build", "q") + "/")):
                if p.startswith(prefix):
                    return local + p[len(prefix):]
            if p.count("/") == 1:            # a file at the board's root, e.g. /scores.json
                return os.path.join(root, p.lstrip("/"))
        return p

    real_open, real_stat, real_rename, real_remove = builtins.open, _os.stat, _os.rename, _os.remove
    builtins.open = lambda p, *a, **k: real_open(m(p), *a, **k)
    _os.stat = lambda p, *a, **k: real_stat(m(p), *a, **k)
    _os.rename = lambda a, b: real_rename(m(a), m(b))
    _os.remove = lambda p: real_remove(m(p))


class Script:
    """Stands in for hat.Input / keys.Keys: returns scripted presses, screenshotting first."""

    def __init__(self, lcd, keys, out_dir, prefix="s"):
        self.lcd, self.keys, self.out, self.prefix, self.n = lcd, list(keys), out_dir, prefix, 0
        os.makedirs(out_dir, exist_ok=True)

    def snap(self, label=""):
        save_png(self.lcd, os.path.join(self.out, "%s%03d%s.png" % (self.prefix, self.n, label)))
        self.n += 1

    def wait(self, accept=None, timeout_ms=None):
        self.snap()
        if not self.keys:
            raise SystemExit("script done")
        k = self.keys.pop(0)
        return k if k != "-" else None

    read = wait

    def release(self):
        pass

    def held(self):
        return set()

    def poll(self):
        return []


if __name__ == "__main__":
    display, out = sys.argv[1], sys.argv[2]
    sys.path.insert(0, os.path.join(ROOT, "device"))
    mount(display, os.path.join(out, "_fs"))
    import random
    random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 5)
    import hat
    keys = sys.argv[4].split(",") if len(sys.argv) > 4 else (
        ["KEY1", "KEY1", "KEY1", "-", "KEY1", "DOWN", "KEY1", "KEY1", "-",
         "KEY1", "KEY3", "KEY2", "KEY1", "LEFT", "KEY1", "KEY1", "KEY1"])
    real_lcd = hat.LCD
    holder = {}

    def make_lcd(*a, **k):
        holder["lcd"] = real_lcd(*a, **k)
        return holder["lcd"]

    hat.LCD = make_lcd
    hat.Input = lambda *a, **k: Script(holder["lcd"], keys, out)
    try:
        import app  # noqa: F401  (runs the game)
    except SystemExit as e:
        print(e)
