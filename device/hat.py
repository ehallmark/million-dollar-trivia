# Waveshare LCD HAT on the Waveshare RP2040-PiZero: the 1.44" (ST7735S, 128x128), which
# the game and enclosure are built around, or the 1.3" (ST7789, 240x240). Both use the
# same pins and buttons. board.py (written by tools/deploy.sh) says which one is fitted.
# HAT pins are Pi BCM numbers; the PiZero routes them to these RP2040 GPIOs.
import framebuf
import time

import machine
from machine import SPI, Pin

try:
    from board import DISPLAY
except ImportError:
    DISPLAY = "1.44"

W = H = 128 if DISPLAY == "1.44" else 240
PIN_SCK, PIN_MOSI, PIN_CS, PIN_DC, PIN_RST, PIN_BL = 10, 11, 8, 25, 27, 24

# Active low. KEY1/KEY2/DOWN share GPIOs with the microSD slot (leave it empty).
BUTTONS = {
    "UP": 6, "DOWN": 19, "LEFT": 15, "RIGHT": 26, "PRESS": 13,
    "KEY1": 21, "KEY2": 20, "KEY3": 16,
}


def rgb(r, g, b):
    """RGB888 -> RGB565, byte-swapped (framebuf is little-endian, the ST7789 big-endian)."""
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((c & 0xFF) << 8) | (c >> 8)


def _fast_spi():
    """Clock the SPI peripheral from the 125 MHz system clock instead of 48 MHz.

    MicroPython computes SPI dividers assuming clk_peri = 48 MHz, so asking for
    24 MHz then actually runs at 125/2 = 62.5 MHz (the ST7789's limit): a full
    screen refresh drops from ~46 ms to ~19 ms. clk_peri only feeds SPI and UART
    here (the REPL is on USB), so nothing else is affected.
    """
    CLK_PERI_CTRL = 0x40008048
    machine.mem32[CLK_PERI_CTRL] = 0             # disable while switching source
    time.sleep_us(10)
    machine.mem32[CLK_PERI_CTRL] = 1 << 11       # AUXSRC 0 = clk_sys, ENABLE


class LCD240(framebuf.FrameBuffer):
    """1.3" HAT: ST7789, 240x240."""

    def __init__(self, fast=True):
        self.spi = SPI(1, 24_000_000, polarity=0, phase=0, sck=Pin(PIN_SCK), mosi=Pin(PIN_MOSI))
        if fast:
            _fast_spi()
        self.cs = Pin(PIN_CS, Pin.OUT, value=1)
        self.dc = Pin(PIN_DC, Pin.OUT, value=1)
        self.rst = Pin(PIN_RST, Pin.OUT, value=1)
        self.bl = Pin(PIN_BL, Pin.OUT, value=0)
        self.buf = bytearray(W * H * 2)
        super().__init__(self.buf, W, H, framebuf.RGB565)
        self._init()
        self.bl.value(1)

    def _cmd(self, c, data=None):
        self.cs(0)
        self.dc(0)
        self.spi.write(bytes([c]))
        if data:
            self.dc(1)
            self.spi.write(bytes(data))
        self.cs(1)

    def _init(self):
        self.rst(1); time.sleep_ms(10)
        self.rst(0); time.sleep_ms(10)
        self.rst(1); time.sleep_ms(120)
        self._cmd(0x11)                  # sleep out
        time.sleep_ms(120)
        self._cmd(0x36, [0x70])          # MADCTL: landscape, matches the HAT's buttons
        self._cmd(0x3A, [0x05])          # 16-bit colour
        self._cmd(0x21)                  # inversion on (IPS panel)
        self._cmd(0x13)                  # normal display
        self._cmd(0x29)                  # display on

    def show(self):
        self.show_rect(0, 0, W, H)

    def show_rect(self, x, y, w, h):
        """Push one region of the frame buffer to the panel."""
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + w), min(H, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        self._cmd(0x2A, [0, x0, 0, x1 - 1])
        self._cmd(0x2B, [0, y0, 0, y1 - 1])
        mv = memoryview(self.buf)
        self.cs(0)
        self.dc(0)
        self.spi.write(b"\x2c")
        self.dc(1)
        if x0 == 0 and x1 == W:
            self.spi.write(mv[y0 * W * 2:y1 * W * 2])
        else:
            for row in range(y0, y1):
                i = (row * W + x0) * 2
                self.spi.write(mv[i:i + (x1 - x0) * 2])
        self.cs(1)


class LCD128(framebuf.FrameBuffer):
    """1.44" HAT: ST7735S, 128x128. Init sequence and offsets from Waveshare's LCD_1in44.py."""

    X_OFF, Y_OFF = 1, 2           # the 128x128 panel sits inside 132x162 of controller RAM

    def __init__(self):
        # Specified to ~15 MHz; 12 MHz is what the 48 MHz peripheral clock divides to.
        self.spi = SPI(1, 12_000_000, polarity=0, phase=0, sck=Pin(PIN_SCK), mosi=Pin(PIN_MOSI))
        self.cs = Pin(PIN_CS, Pin.OUT, value=1)
        self.dc = Pin(PIN_DC, Pin.OUT, value=1)
        self.rst = Pin(PIN_RST, Pin.OUT, value=1)
        self.bl = Pin(PIN_BL, Pin.OUT, value=0)
        self.buf = bytearray(W * H * 2)
        super().__init__(self.buf, W, H, framebuf.RGB565)
        self._init()
        self.fill(0)
        self.show()
        self.bl.value(1)

    def _cmd(self, c, data=None):
        self.cs(0)
        self.dc(0)
        self.spi.write(bytes([c]))
        if data:
            self.dc(1)
            self.spi.write(bytes(data))
        self.cs(1)

    def _init(self):
        self.rst(1); time.sleep_ms(10)
        self.rst(0); time.sleep_ms(10)
        self.rst(1); time.sleep_ms(10)
        self._cmd(0xB1, [0x01, 0x2C, 0x2D])                   # frame rate
        self._cmd(0xB2, [0x01, 0x2C, 0x2D])
        self._cmd(0xB3, [0x01, 0x2C, 0x2D, 0x01, 0x2C, 0x2D])
        self._cmd(0xB4, [0x07])                               # column inversion
        self._cmd(0xC0, [0xA2, 0x02, 0x84])                   # power sequence
        self._cmd(0xC1, [0xC5])
        self._cmd(0xC2, [0x0A, 0x00])
        self._cmd(0xC3, [0x8A, 0x2A])
        self._cmd(0xC4, [0x8A, 0xEE])
        self._cmd(0xC5, [0x0E])                               # VCOM
        self._cmd(0xE0, [0x0F, 0x1A, 0x0F, 0x18, 0x2F, 0x28, 0x20, 0x22,
                         0x1F, 0x1B, 0x23, 0x37, 0x00, 0x07, 0x02, 0x10])
        self._cmd(0xE1, [0x0F, 0x1B, 0x0F, 0x17, 0x33, 0x2C, 0x29, 0x2E,
                         0x30, 0x30, 0x39, 0x3F, 0x00, 0x07, 0x03, 0x10])
        self._cmd(0xF0, [0x01])
        self._cmd(0xF6, [0x00])
        self._cmd(0x3A, [0x05])                               # 16-bit colour
        self._cmd(0x36, [0x40 | 0x20 | 0x08])                 # MX | MV | BGR
        time.sleep_ms(200)
        self._cmd(0x11)                                       # sleep out
        time.sleep_ms(120)
        self._cmd(0x29)                                       # display on

    def show(self):
        self.show_rect(0, 0, W, H)

    def show_rect(self, x, y, w, h):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + w), min(H, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        self._cmd(0x2A, [0, x0 + self.X_OFF, 0, x1 - 1 + self.X_OFF])
        self._cmd(0x2B, [0, y0 + self.Y_OFF, 0, y1 - 1 + self.Y_OFF])
        mv = memoryview(self.buf)
        self.cs(0)
        self.dc(0)
        self.spi.write(b"\x2c")
        self.dc(1)
        if x0 == 0 and x1 == W:
            self.spi.write(mv[y0 * W * 2:y1 * W * 2])
        else:
            for row in range(y0, y1):
                i = (row * W + x0) * 2
                self.spi.write(mv[i:i + (x1 - x0) * 2])
        self.cs(1)


LCD = LCD128 if DISPLAY == "1.44" else LCD240


class Input:
    """Debounced button presses as events, with auto-repeat on the joystick."""

    REPEATS = ("UP", "DOWN", "LEFT", "RIGHT")

    def __init__(self, repeat_delay=380, repeat_every=110):
        self.pins = {n: Pin(g, Pin.IN, Pin.PULL_UP) for n, g in BUTTONS.items()}
        self.down = {}
        self.delay, self.every = repeat_delay, repeat_every

    def held(self):
        return {n for n, p in self.pins.items() if not p.value()}

    def poll(self):
        """Return the list of buttons that were just pressed (or are auto-repeating)."""
        now = time.ticks_ms()
        events = []
        held = self.held()
        for name in held:
            if name not in self.down:
                self.down[name] = now + self.delay
                events.append(name)
            elif name in self.REPEATS and time.ticks_diff(now, self.down[name]) >= 0:
                self.down[name] = now + self.every
                events.append(name)
        for name in list(self.down):
            if name not in held:
                del self.down[name]
        return events

    def wait(self, accept=None, timeout_ms=None):
        """Block until one of ``accept`` (default: any) is pressed; None on timeout."""
        start = time.ticks_ms()
        while True:
            for e in self.poll():
                if accept is None or e in accept:
                    return e
            if timeout_ms is not None and time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                return None
            time.sleep_ms(15)

    def release(self):
        """Wait until all buttons are up (so a press doesn't leak into the next screen)."""
        while self.held():
            time.sleep_ms(15)
        self.down = {}
