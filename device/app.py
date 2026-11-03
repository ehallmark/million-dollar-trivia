# Million Dollar Trivia: title screen and menus. Runs at power-on.
import gc
import os
import random

# Seed from the RP2040's hardware noise source. The boot-time tick count is nearly the
# same on every power-up (and this board's flash has no unique ID), which can replay
# the same "random" questions and answer order.
random.seed(int.from_bytes(os.urandom(4), "little"))

import hat
lcd = hat.LCD()
inp = hat.Input()

import questions
import scores
import ui
from game import Game
from hat import W
from ui import BODY, SMALL, TITLE

HOW_TO_PLAY = [
    ("How to play", "Answer 15 questions to climb the money ladder to $1,000,000. "
     "Reach $1,000 and $32,000 and that money is safe even if you miss later."),
    ("Controls", "The joystick moves. KEY1 (top) is OK: press it to pick an answer, "
     "and again to lock in your final answer. KEY2 always goes back."
     + (" On the answers, LEFT shows the question again." if ui.COMPACT else "")),
    ("Lifelines", "Press KEY3 for lifelines. 50:50 removes two wrong answers, the "
     "Audience votes, and a Friend gives a hint. One use each per game."),
    ("Walking away", "KEY3 also lets you walk away with what you've won so far. "
     "In Classic mode the questions get harder as you climb."),
    ("Credits", "Many questions come from the Open Trivia Database (opentdb.com), "
     "licensed CC BY-SA 4.0. The rest were written for this game."),
]


MENU = ["Play", "High scores", "How to play"]


def title_screen(sel):
    ui.background(lcd)
    if ui.COMPACT:
        for i, (word, y) in enumerate((("MILLION", 1), ("DOLLAR", 22), ("TRIVIA", 43))):
            TITLE.draw_center(lcd, word, W // 2, y, ui.GOLD if i != 1 else ui.WHITE)
        for i, item in enumerate(MENU):
            y = 71 + i * 19
            chosen = i == sel
            ui.panel(lcd, 14, y, W - 28, 18, ui.SELECT if chosen else ui.PANEL,
                     ui.GOLD if chosen else ui.PANEL_EDGE)
            SMALL.draw_center(lcd, item, W // 2, y + 2, ui.BLACK if chosen else ui.WHITE)
        lcd.show()
        return
    for i, (word, y) in enumerate((("MILLION", 22), ("DOLLAR", 48), ("TRIVIA", 74))):
        TITLE.draw_center(lcd, word, W // 2, y, ui.GOLD if i != 1 else ui.WHITE)
    lcd.hline(50, 104, W - 100, ui.DIM_GOLD)
    for i, item in enumerate(MENU):
        y = 112 + i * 28
        chosen = i == sel
        ui.panel(lcd, 40, y, W - 80, 25, ui.SELECT if chosen else ui.PANEL,
                 ui.GOLD if chosen else ui.PANEL_EDGE)
        BODY.draw_center(lcd, item, W // 2, y + 3, ui.BLACK if chosen else ui.WHITE)
    ui.hint(lcd, "^v choose   K1 = OK")
    lcd.show()


def show_high_scores():
    if ui.COMPACT:
        return show_high_scores_compact()
    ui.background(lcd)
    TITLE.draw_center(lcd, "High scores", W // 2, 6, ui.GOLD)
    top = scores.top()
    if not top:
        BODY.draw_center(lcd, "No scores yet.", W // 2, 100, ui.LIGHT)
        BODY.draw_center(lcd, "Be the first!", W // 2, 124, ui.LIGHT)
    for i, (initials, amount, mode, cat) in enumerate(top):
        y = 38 + i * 19
        color = ui.GOLD if i == 0 else ui.WHITE
        SMALL.draw(lcd, str(i + 1) + ".", 8, y + 2, ui.DIM)
        BODY.draw(lcd, initials, 28, y, color)
        BODY.draw_right(lcd, ui.money(amount), 140, y, color)
        SMALL.draw(lcd, SMALL.fit(questions.LABELS.get(cat, cat), 92), 146, y + 2, ui.LIGHT)
    ui.hint(lcd, "K1 or K2 to go back")
    lcd.show()
    inp.wait(ui.OK + ("KEY2",))
    inp.release()


def show_high_scores_compact():
    """Five per page on the small screen; v for the next page."""
    top = scores.top()
    pages = max(1, (len(top) + 4) // 5)
    for page in range(pages):
        ui.background(lcd)
        BODY.draw_center(lcd, "High scores", W // 2, 1, ui.GOLD)
        if not top:
            SMALL.draw_center(lcd, "No scores yet.", W // 2, 50, ui.LIGHT)
            SMALL.draw_center(lcd, "Be the first!", W // 2, 64, ui.LIGHT)
        for row, (initials, amount, mode, cat) in enumerate(top[page * 5:page * 5 + 5]):
            i = page * 5 + row
            y = 21 + row * 19
            color = ui.GOLD if i == 0 else ui.WHITE
            SMALL.draw_right(lcd, str(i + 1), 12, y + 3, ui.DIM)
            BODY.draw(lcd, initials, 16, y, color)
            BODY.draw_right(lcd, ui.money(amount), W - 2, y, color)
        ui.hint(lcd, "K1 = next" if page < pages - 1 else "K1 = back")
        lcd.show()
        if inp.wait(ui.OK + ("KEY2", "DOWN")) == "KEY2":
            inp.release()
            return
        inp.release()


def how_to_play():
    for title, body in HOW_TO_PLAY:
        ui.message(lcd, inp, title, body, footer="K1 = next")


def new_game():
    names = [m[1] if ui.COMPACT else m[1] + "  -  " + m[2] for m in questions.MODES]
    m = ui.menu(lcd, inp, "Choose a mode", names, rows=4, row_h=34, top=50)
    if m is None:
        return
    mode = questions.MODES[m]
    cats = [c for c in questions.CATEGORIES if questions.available(c[0])]
    fmt = ui.money_short if ui.COMPACT else ui.money
    best = lambda i: fmt(scores.best(mode[0], cats[i][0])) if scores.best(mode[0], cats[i][0]) else ""
    c = ui.menu(lcd, inp, "Pick a category", [label for _, label in cats],
                subtitle=mode[1] + (" mode" if ui.COMPACT else " mode  -  your best on the right"), right=best)
    if c is None:
        return
    gc.collect()
    Game(lcd, inp, mode, cats[c][0]).play()


def main():
    sel = 0
    while True:
        title_screen(sel)
        e = inp.wait(("UP", "DOWN") + ui.OK)
        if e == "UP":
            sel = (sel - 1) % len(MENU)
        elif e == "DOWN":
            sel = (sel + 1) % len(MENU)
        else:
            inp.release()
            (new_game, show_high_scores, how_to_play)[sel]()
            gc.collect()


main()
