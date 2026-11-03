# One game: 15 questions up the money ladder, three lifelines, walk away any time.
import framebuf
import random
import time

import questions
import scores
import ui
from hat import H, W
from ui import COMPACT, OK
from ui import BODY, SMALL, TITLE

LADDER = [100, 200, 300, 500, 1000, 2000, 4000, 8000, 16000, 32000,
          64000, 125000, 250000, 500000, 1000000]
SAFE = (4, 9)  # reaching $1,000 and $32,000 is guaranteed
LETTERS = "ABCD"

# How often lifelines point at the right answer, by question difficulty.
AUDIENCE_SHARE = {"easy": (55, 80), "medium": (40, 65), "hard": (28, 50)}
FRIEND_RIGHT = {"easy": 0.92, "medium": 0.75, "hard": 0.55}


def guaranteed(level):
    """Winnings kept when missing the question at ``level`` (0-based)."""
    kept = 0
    for s in SAFE:
        if level > s:
            kept = LADDER[s]
    return kept


class Game:
    def __init__(self, lcd, inp, mode, cat):
        self.lcd, self.inp = lcd, inp
        self.mode_key, self.mode_name, _, self.plan = mode
        self.cat = cat
        self.used = set()
        self.lifelines = {"50:50": True, "Audience": True, "Phone": True}

    # ---------- drawing ----------
    # ---------- small screen (1.44", 128x128): question and answers on separate screens ----------
    def _bar(self, level, banner=None):
        """Top line: question number, lifelines left, prize (or a banner instead)."""
        lcd = self.lcd
        if banner:
            SMALL.draw_center(lcd, banner, W // 2, 0, ui.GOLD)
            return
        SMALL.draw(lcd, "Q" + str(level + 1), 2, 0, ui.LIGHT)
        x = 26
        for name, short in (("50:50", "50"), ("Audience", "Au"), ("Phone", "Ph")):
            x = SMALL.draw(lcd, short, x, 0, ui.GOLD if self.lifelines[name] else ui.DIM) + 4
        SMALL.draw_right(lcd, ui.money(LADDER[level]), W - 2, 0, ui.GOLD)

    @staticmethod
    def _fit_lines(text, width, max_lines):
        """Biggest font whose wrapping fits in max_lines (BODY, else SMALL, else cut)."""
        for font in (BODY, SMALL):
            lines = font.wrap(text, width)
            if len(lines) <= max_lines(font):
                return font, lines
        lines = SMALL.wrap(text, width)[:max_lines(SMALL)]
        lines[-1] = SMALL.fit(lines[-1] + "...", width)
        return SMALL, lines

    def _question_screen(self, q, level):
        lcd = self.lcd
        ui.background(lcd)
        self._bar(level)
        top, bottom = 15, H - 15
        font, lines = self._fit_lines(q.text, W - 6, lambda f: (bottom - top) // (f.height + 1))
        y = top + (bottom - top - len(lines) * (font.height + 1)) // 2
        for line in lines:
            font.draw_center(lcd, line, W // 2, y, ui.WHITE)
            y += font.height + 1
        ui.hint(lcd, "K1 = answers  K3 = help")
        lcd.show()

    def _draw_compact(self, q, level, sel, removed, states=None, banner=None):
        lcd = self.lcd
        ui.background(lcd)
        self._bar(level, banner)
        for i in range(4):
            self._answer_compact(q, i, sel, removed, states[i] if states else None)
        lcd.show()

    _scroll = 0          # marquee offset (px) of the highlighted answer
    _strip_fb = None

    @staticmethod
    def _answer_layout(text):
        """(font, lines, line step, cut) for an answer row: one line of the big font, else
        two lines of the small one (13 px apart), else two cut lines (cut=True)."""
        width = W - 22
        if BODY.width(text) <= width:
            return BODY, [text], BODY.height, False
        lines = SMALL.wrap(text, width)
        if len(lines) <= 2:
            return SMALL, lines, 13, False
        lines = lines[:2]
        lines[1] = SMALL.fit(lines[1] + "...", width)
        return SMALL, lines, 13, True

    @staticmethod
    def _too_long(text):
        """True if the answer only fits its row by being cut short."""
        return Game._answer_layout(text)[3]

    def _strip(self, fill):
        if self._strip_fb is None:
            w, h = W - 22, BODY.height
            Game._strip_fb = framebuf.FrameBuffer(bytearray(w * h * 2), w, h, framebuf.RGB565)
        self._strip_fb.fill(fill)
        return self._strip_fb

    def _wait_scrolling(self, q, sel, removed, accept, state=None):
        """inp.wait, but while waiting scroll the highlighted answer if it is too long."""
        Game._scroll = 0
        if not COMPACT or not self._too_long(q.answers[sel]):
            return self.inp.wait(accept)
        overflow = BODY.width(q.answers[sel]) - (W - 22)
        t, pause = 0, 900                      # ms: hold at each end, then scroll
        while True:
            e = self.inp.wait(accept, timeout_ms=45)
            if e is not None:
                Game._scroll = 0
                return e
            t += 45
            if t < pause:
                continue
            if Game._scroll < overflow:
                Game._scroll = min(overflow, Game._scroll + 3)
                self._answer(q, sel, sel, removed, state, show=True)
            elif t > pause + overflow // 3 * 45 + pause:
                Game._scroll, t = 0, 0
                self._answer(q, sel, sel, removed, state, show=True)

    def _answer_compact(self, q, i, sel, removed, state=None, show=False):
        lcd = self.lcd
        row_h = (H - 14) // 4               # 28 px: room for two lines of the small font
        y = 14 + i * row_h
        if state:
            fill, edge, color = state
        elif i in removed:
            fill, edge, color = ui.REMOVED, ui.DIM, ui.DIM
        elif i == sel:
            fill, edge, color = ui.SELECT, ui.GOLD, ui.BLACK
        else:
            fill, edge, color = ui.PANEL, ui.PANEL_EDGE, ui.WHITE
        if show:
            ui.background(lcd, y, y + row_h)
        ui.panel(lcd, 1, y, W - 2, row_h - 1, fill, edge)
        letter_color = color if (state or i == sel or i in removed) else ui.GOLD
        BODY.draw(lcd, LETTERS[i], 4, y + (row_h - 1 - BODY.height) // 2, letter_color)
        if i not in removed:
            text = q.answers[i]
            if i == sel and self._too_long(text):
                # The highlighted answer doesn't fit: one line in the big font, scrolled
                # by self._scroll pixels, drawn through a strip so it can't spill over.
                strip = self._strip(fill)
                BODY.draw(strip, text, -self._scroll, 0, color)
                lcd.blit(strip, 18, y + (row_h - 1 - BODY.height) // 2)
            else:
                font, lines, step, _ = self._answer_layout(text)
                y0 = y + (row_h - 1 - (len(lines) - 1) * step - font.height) // 2
                for n, line in enumerate(lines):
                    font.draw(lcd, line, 18, y0 + n * step, color)
        if show:
            lcd.show_rect(0, y, W, row_h)

    def _ladder_compact(self, level, note=None):
        lcd = self.lcd
        ui.background(lcd)
        BODY.draw_center(lcd, "Question " + str(level + 1), W // 2, 6, ui.WHITE)
        SMALL.draw_center(lcd, "for", W // 2, 28, ui.LIGHT)
        TITLE.draw_center(lcd, ui.money(LADDER[level]), W // 2, 42, ui.GOLD)
        seg = (W - 4) // 15                  # 15 segments: done, current, safe havens
        for i in range(15):
            x = 2 + i * seg
            color = ui.SELECT if i == level else (ui.DIM_GOLD if i < level else
                                                  ui.LIGHT if i in SAFE else ui.PANEL_EDGE)
            lcd.fill_rect(x, 80 if i in SAFE else 82, seg - 1, 12 if i in SAFE else 8, color)
        if note:
            lines = SMALL.wrap(note, W - 4)[:2]
            for n, line in enumerate(lines):
                SMALL.draw_center(lcd, line, W // 2, 98 + n * 13, ui.LIGHT)
        lcd.show()

    # ---------- 240x240 ----------
    def _draw(self, q, level, sel, removed, states=None, banner=None):
        if COMPACT:
            return self._draw_compact(q, level, sel, removed, states, banner)
        lcd = self.lcd
        ui.background(lcd)
        # Top bar: question number, lifelines left, prize for this question.
        SMALL.draw(lcd, "Q" + str(level + 1) + "/15", 6, 3, ui.LIGHT)
        x = 62
        for name, short in (("50:50", "50:50"), ("Audience", "AUD"), ("Phone", "TEL")):
            color = ui.GOLD if self.lifelines[name] else ui.DIM
            x = SMALL.draw(lcd, short, x, 3, color) + 8
        SMALL.draw_right(lcd, ui.money(LADDER[level]), W - 6, 3, ui.GOLD)

        # Question.
        ui.panel(lcd, 4, 20, W - 8, 92)
        lines = BODY.wrap(q.text, W - 24)[:4]
        top = 20 + (92 - len(lines) * (BODY.height + 1)) // 2
        ui.text_block(lcd, BODY, lines, 12, top, ui.WHITE, line_gap=1, center=True, width=W - 24)

        for i in range(4):
            self._answer(q, i, sel, removed, states[i] if states else None)
        if banner:
            ui.panel(lcd, 30, 92, W - 60, 26, ui.BLACK, ui.GOLD)
            SMALL.draw_center(lcd, banner, W // 2, 98, ui.GOLD)
        lcd.show()

    def _answer(self, q, i, sel, removed, state=None, show=False):
        """Draw answer row i (optionally pushing just that row to the screen)."""
        if COMPACT:
            return self._answer_compact(q, i, sel, removed, state, show)
        lcd = self.lcd
        y = 116 + i * 30
        if state:
            fill, edge, color = state
        elif i in removed:
            fill, edge, color = ui.REMOVED, ui.DIM, ui.DIM
        elif i == sel:
            fill, edge, color = ui.SELECT, ui.GOLD, ui.BLACK
        else:
            fill, edge, color = ui.PANEL, ui.PANEL_EDGE, ui.WHITE
        if show:
            ui.background(lcd, y, y + 27)
        ui.panel(lcd, 4, y, W - 8, 27, fill, edge)
        letter_color = color if (state or i == sel or i in removed) else ui.GOLD
        BODY.draw(lcd, LETTERS[i] + ":", 12, y + 4, letter_color)
        if i not in removed:
            BODY.draw(lcd, BODY.fit(q.answers[i], W - 50), 34, y + 4, color)
        if show:
            lcd.show_rect(0, y, W, 27)

    def _ladder(self, level, note=None):
        """The money ladder, with the question about to be played highlighted."""
        if COMPACT:
            return self._ladder_compact(level, note)
        lcd = self.lcd
        ui.background(lcd)
        for i in range(15):
            y = 4 + (14 - i) * 15
            amount = ui.money(LADDER[i])
            if i == level:
                ui.panel(lcd, 40, y - 1, W - 80, 15, ui.SELECT, ui.GOLD)
                color = ui.BLACK
            else:
                color = ui.WHITE if i in SAFE else (ui.DIM_GOLD if i < level else ui.LIGHT)
            SMALL.draw(lcd, str(i + 1), 50, y, color)
            SMALL.draw_right(lcd, amount, W - 50, y, color)
        if note:
            SMALL.draw_center(lcd, note, W // 2, 228, ui.LIGHT)
        lcd.show()

    # ---------- lifelines ----------
    def _options(self, q, level, removed):
        """KEY3 menu: the unused lifelines plus walking away. Returns True to walk away."""
        names = [n for n, ok in self.lifelines.items() if ok]
        kept = ui.money(LADDER[level - 1] if level else 0)
        items = names + ["Walk away with " + kept]
        choice = ui.menu(self.lcd, self.inp, "Lifelines", items, rows=4, row_h=30, top=50,
                         footer="K1 = use   K2 = cancel")
        if choice is None:
            return False
        if choice == len(names):
            return ui.menu(self.lcd, self.inp, "Walk away?", ["Yes, keep " + kept, "No, keep playing"],
                           rows=2, row_h=32, top=70, footer="K1 = OK") == 0
        name = names[choice]
        self.lifelines[name] = False
        if name == "50:50":
            wrong = [i for i in range(4) if i != q.correct and i not in removed]
            for i in random.choice([wrong[:2], wrong[1:], [wrong[0], wrong[-1]]]):
                removed.add(i)
        elif name == "Audience":
            self._audience(q, removed)
        else:
            self._phone(q, removed)

    def _audience(self, q, removed):
        lo, hi = AUDIENCE_SHARE[q.diff]
        right = lo + random.getrandbits(8) % (hi - lo + 1)
        others = [i for i in range(4) if i != q.correct and i not in removed]
        weights = [1 + random.getrandbits(4) for _ in others]
        votes = [0] * 4
        votes[q.correct] = right
        left = 100 - right
        for i, w in zip(others, weights):
            votes[i] = left * w // sum(weights)
        votes[q.correct] += 100 - sum(votes)  # make it add up to 100
        lcd = self.lcd
        ui.background(lcd)
        if COMPACT:
            BODY.draw_center(lcd, "The Audience", W // 2, 1, ui.GOLD)
            pitch, bar_w, base, tall = W // 4, W // 4 - 8, H - 32, H - 70
        else:
            TITLE.draw_center(lcd, "Ask the Audience", W // 2, 8, ui.GOLD)
            pitch, bar_w, base, tall = 52, 36, 190, 140
        x0 = (W - 4 * pitch) // 2 + (pitch - bar_w) // 2
        for i in range(4):
            x = x0 + i * pitch
            h = votes[i] * tall // 100
            lcd.fill_rect(x, base - h, bar_w, h, ui.GOLD if i not in removed else ui.DIM)
            SMALL.draw_center(lcd, str(votes[i]) + "%", x + bar_w // 2, base - h - 15, ui.WHITE)
            BODY.draw_center(lcd, LETTERS[i], x + bar_w // 2, base + 1, ui.LIGHT)
        ui.hint(lcd, "K1 = back" if COMPACT else "K1 to go back to the question")
        lcd.show()
        self.inp.wait(OK + ("KEY2",))
        self.inp.release()

    def _phone(self, q, removed):
        if random.random() < FRIEND_RIGHT[q.diff]:
            pick = q.correct
        else:
            pick = random.choice([i for i in range(4) if i != q.correct and i not in removed])
        sure = {"easy": "Easy one, it's definitely", "medium": "I'm fairly sure it's",
                "hard": "Hmm, tough... maybe"}[q.diff]
        ui.message(self.lcd, self.inp, "Phone a Friend",
                   '"' + sure + " " + LETTERS[pick] + ": " + q.answers[pick] + '."',
                   footer="K1 = back" if COMPACT else "K1 to go back to the question")

    # ---------- play ----------
    def _ask(self, q, level):
        """Play one question. Returns (result, chosen answer, removed answers) where
        result is 'right', 'wrong' or 'walk'."""
        removed = set()
        sel = 0
        self.inp.release()
        redraw = True
        if COMPACT:  # read the question first; LEFT brings it back from the answers
            self._question_screen(q, level)
            while True:
                e = self.inp.wait(("KEY3",) + OK + ("RIGHT", "DOWN"))
                self.inp.release()
                if e != "KEY3":
                    break
                if self._options(q, level, removed):
                    return "walk", sel, removed
                self._question_screen(q, level)
        while True:
            while sel in removed:
                sel = (sel + 1) % 4
            if redraw:
                self._draw(q, level, sel, removed)
            redraw = False
            previous = sel
            e = self._wait_scrolling(q, sel, removed, ("UP", "DOWN", "KEY3", "LEFT", "RIGHT") + OK)
            if COMPACT and e == "LEFT":
                self.inp.release()
                self._question_screen(q, level)
                self.inp.wait(OK + ("RIGHT", "LEFT", "KEY2"))
                self.inp.release()
                redraw = True
                continue
            if e in ("UP", "DOWN", "LEFT", "RIGHT"):
                sel = self._move(sel, e, removed)
                self._answer(q, previous, sel, removed, show=True)
                self._answer(q, sel, sel, removed, show=True)
                continue
            redraw = True
            if e in ("UP", "LEFT"):
                sel = (sel - 1) % 4
                while sel in removed:
                    sel = (sel - 1) % 4
            elif e in ("DOWN", "RIGHT"):
                sel = (sel + 1) % 4
                while sel in removed:
                    sel = (sel + 1) % 4
            elif e == "KEY3":
                self.inp.release()
                if self._options(q, level, removed):
                    return "walk", sel, removed
            elif e in OK:
                self.inp.release()
                if self._confirm(q, level, sel, removed):
                    return ("right" if sel == q.correct else "wrong"), sel, removed

    @staticmethod
    def _move(sel, direction, removed):
        step = -1 if direction in ("UP", "LEFT") else 1
        sel = (sel + step) % 4
        while sel in removed:
            sel = (sel + step) % 4
        return sel

    def _confirm(self, q, level, sel, removed):
        """'Final answer?': OK again locks it in; any other button to rethink."""
        states = [None] * 4
        states[sel] = (ui.LOCKED, ui.GOLD, ui.BLACK)
        self._draw(q, level, sel, removed, states,
                   banner="Final answer? K1" if COMPACT else "Final answer? K1 again")
        e = self._wait_scrolling(q, sel, removed, None, states[sel])
        self.inp.release()
        return e in OK

    def _reveal(self, q, level, sel, removed, result):
        locked = [None] * 4
        locked[sel] = (ui.LOCKED, ui.GOLD, ui.BLACK)
        self._draw(q, level, sel, removed, locked)
        time.sleep_ms(900 + 150 * level)  # the pause grows as the stakes do
        right = [None] * 4
        right[q.correct] = (ui.GREEN, ui.WHITE, ui.WHITE)
        if result == "wrong":
            right[sel] = (ui.RED, ui.WHITE, ui.WHITE)
        for _ in range(3):  # flash the correct answer
            self._draw(q, level, sel, removed, right)
            time.sleep_ms(250)
            self._draw(q, level, sel, removed, right if result == "wrong" else locked)
            time.sleep_ms(150)
        self._draw(q, level, sel, removed, right)
        time.sleep_ms(700)

    def play(self):
        """Run the game. Returns the amount won."""
        for level in range(15):
            q = questions.pick(self.cat, self.plan[level], self.used)
            note = "safe haven" if level in SAFE else None
            if level == 0:
                note = "K1 = OK   K3 = lifelines / walk away"
            self._ladder(level, note)
            self.inp.wait(timeout_ms=1800 if level else 3500)
            self.inp.release()
            result, sel, removed = self._ask(q, level)
            if result == "walk":
                return self._finish(LADDER[level - 1] if level else 0, "You walked away with")
            self._reveal(q, level, sel, removed, result)
            if result == "wrong":
                right = LETTERS[q.correct] + ": " + q.answers[q.correct]
                ui.message(self.lcd, self.inp, "Wrong!", "The answer was " + right + ".")
                return self._finish(guaranteed(level), "You leave with")
        return self._finish(LADDER[-1], "MILLIONAIRE! You won")

    def _finish(self, amount, headline):
        lcd = self.lcd
        ui.background(lcd)
        big = "Game over" if amount < LADDER[-1] else "WINNER!"
        best = scores.best(self.mode_key, self.cat)
        if COMPACT:
            TITLE.draw_center(lcd, big, W // 2, 4, ui.GOLD)
            for n, line in enumerate(SMALL.wrap(headline, W - 4)[:2]):
                SMALL.draw_center(lcd, line, W // 2, 36 + n * 13, ui.WHITE)
            TITLE.draw_center(lcd, ui.money(amount), W // 2, 64, ui.GOLD)
            if amount > best:
                SMALL.draw_center(lcd, "New best here!", W // 2, 96, ui.LIGHT)
        else:
            TITLE.draw_center(lcd, big, W // 2, 40, ui.GOLD)
            BODY.draw_center(lcd, headline, W // 2, 90, ui.WHITE)
            TITLE.draw_center(lcd, ui.money(amount), W // 2, 118, ui.GOLD)
            if amount > best:
                BODY.draw_center(lcd, "New best for this category!", W // 2, 160, ui.LIGHT)
        ui.hint(lcd, "K1 to continue")
        lcd.show()
        self.inp.release()
        self.inp.wait(OK + ("KEY2",))
        self.inp.release()
        initials = enter_initials(lcd, self.inp) if scores.qualifies(amount) else None
        scores.record(amount, self.mode_key, self.cat, initials)
        return amount


def enter_initials(lcd, inp):
    """Three letters: up/down changes the letter, left/right moves, press saves."""
    chars = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    letters = [1, 1, 1]  # "AAA"
    pos = 0
    while True:
        ui.background(lcd)
        if COMPACT:
            TITLE.draw_center(lcd, "High score!", W // 2, 2, ui.GOLD)
            SMALL.draw_center(lcd, "Your initials", W // 2, 32, ui.WHITE)
            x0, y, box, gap = (W - 3 * 34 + 4) // 2, 52, 30, 34
        else:
            TITLE.draw_center(lcd, "High score!", W // 2, 30, ui.GOLD)
            BODY.draw_center(lcd, "Enter your initials", W // 2, 70, ui.WHITE)
            x0, y, box, gap = 60, 105, 36, 44
        for i in range(3):
            x = x0 + i * gap
            ui.panel(lcd, x, y, box, box + 4, ui.SELECT if i == pos else ui.PANEL,
                     ui.GOLD if i == pos else ui.PANEL_EDGE)
            TITLE.draw_center(lcd, chars[letters[i]], x + box // 2, y + 6,
                              ui.BLACK if i == pos else ui.WHITE)
        ui.hint(lcd, "^v <> K1 = save" if COMPACT else "^v letter   <> move   K1 = save")
        lcd.show()
        e = inp.wait(("UP", "DOWN", "LEFT", "RIGHT") + OK)
        if e == "UP":
            letters[pos] = (letters[pos] + 1) % len(chars)
        elif e == "DOWN":
            letters[pos] = (letters[pos] - 1) % len(chars)
        elif e == "LEFT":
            pos = (pos - 1) % 3
        elif e == "RIGHT":
            pos = (pos + 1) % 3
        elif e in OK:
            inp.release()
            return "".join(chars[i] for i in letters).strip() or "???"
