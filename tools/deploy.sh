#!/usr/bin/env bash
# Build and install the trivia game on the RP2040 board (running MicroPython 1.29).
#   PORT=/dev/cu.usbmodem101 tools/deploy.sh          code + fonts + questions
#   PORT=/dev/cu.usbmodem101 tools/deploy.sh --code   code only (fast)
# HAT is the display: 1.44 (Waveshare 1.44" LCD HAT, ST7735S 128x128; the default) or
# 1.3 (Waveshare 1.3" LCD HAT, ST7789 240x240). /scores.json on the board is never touched.
# Find PORT with: mpremote devs
# PORT is required, and the script only installs onto a board that already has this game
# or a blank MicroPython board (FORCE=1 overrides): boards with other apps look identical
# over USB, and these RP2040-PiZero boards' flash has no unique ID to tell them apart.
#
# Modules are precompiled with mpy-cross: compiling .py on the board needs more
# RAM than it has left beside the frame buffer.
set -euo pipefail
cd "$(dirname "$0")/.."
MPREMOTE_BIN="${MPREMOTE:-mpremote}"
: "${PORT:?set PORT to the serial port of the board, e.g. PORT=/dev/cu.usbmodem101}"
mp() { "$MPREMOTE_BIN" connect "$PORT" "$@"; }
HAT="${HAT:-1.44}"
case "$HAT" in
    1.3|1.44) ;;
    *) echo "HAT must be 1.44 or 1.3 (the LCD HAT on this board)" >&2; exit 1 ;;
esac
IDENT="$(mp exec "import os; l=os.listdir('/'); print('TRIVIA' if 'app.mpy' in l or 'scores.json' in l else 'BLANK' if not [n for n in l if n not in ('boot.py', 'main.py')] else 'OTHER')" 2>&1 | tr -d '\r' | tail -1)" || IDENT=ERROR
case "$IDENT" in
    TRIVIA|BLANK) ;;
    *)  if [ "${FORCE:-}" != 1 ]; then
            echo "The board on $PORT has another app on it ($IDENT). Not touching it (FORCE=1 overrides)." >&2
            exit 1
        fi ;;
esac
UV="${UV:-uv}"

echo "==> Compiling"
rm -rf build/mpy && mkdir -p build/mpy build
printf 'DISPLAY = "%s"\n' "$HAT" > build/board.py
for f in device/*.py build/board.py; do
    name="$(basename "$f" .py)"
    [ "$name" = main ] && continue  # main.py stays source: it's what runs at power-on
    "$UV" tool run --from mpy-cross mpy-cross -O2 -o "build/mpy/$name.mpy" "$f"
done

echo "==> Copying code"
mp exec "import os
for f in os.listdir('/'):
    if f.endswith('.py') or f.endswith('.mpy'):
        os.remove(f)" > /dev/null
mp cp build/mpy/*.mpy : + cp device/main.py : > /dev/null

if [ "${1:-}" != "--code" ]; then
    echo "==> Copying fonts and questions"
    python3 tools/build_questions.py
    mp exec "import os
def rm(p):
    try:
        if os.stat(p)[0] & 0x4000:
            for n in os.listdir(p): rm(p + '/' + n)
            os.rmdir(p)
        else:
            os.remove(p)
    except OSError:
        pass
rm('/q'); rm('/fonts')" > /dev/null
    mp fs mkdir :/fonts > /dev/null
    mp cp device/fonts/*.bin :/fonts/ > /dev/null
    (cd build && mp cp -r q : > /dev/null)
fi

mp exec "import os, gc; s=os.statvfs('/'); print('flash free:', s[0]*s[3]//1024, 'KB')"
echo "==> Restarting"
mp reset
