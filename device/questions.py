# Question bank on flash: /q/<category>/<difficulty>.txt, one question per line:
#   question|correct|wrong|wrong|wrong
# <difficulty>.idx holds each line's byte offset, so any question loads in O(1)
# with almost no RAM.
import os
import random
import struct

CATEGORIES = [
    ("mixed", "Mixed Bag"),
    ("general", "General Knowledge"),
    ("history", "History"),
    ("geography", "Geography"),
    ("science", "Science"),
    ("nature", "Nature"),
    ("art_history", "Art History"),
    ("music", "Music"),
    ("movies_tv", "Movies & TV"),
    ("literature", "Literature"),
    ("english", "English"),
    ("french", "French"),
    ("math", "Math"),
    ("technology", "Technology"),
    ("politics", "Politics"),
    ("sports", "Sports"),
    ("video_games", "Video Games"),
]
LABELS = dict(CATEGORIES)
DIFFICULTIES = ("easy", "medium", "hard")

# Game modes: which difficulty each of the 15 questions is drawn from.
MODES = [
    ("classic", "Classic", "Starts easy, ends hard", ["easy"] * 5 + ["medium"] * 5 + ["hard"] * 5),
    ("easy", "Easy", "Friendly questions", ["easy"] * 15),
    ("medium", "Medium", "Trivia-night level", ["medium"] * 15),
    ("hard", "Hard", "For experts", ["hard"] * 15),
]

_counts = {}


def _path(cat, diff, ext=".txt"):
    return "/q/" + cat + "/" + diff + ext


def available(cat):
    """Categories that actually have question files (mixed is always available)."""
    if cat == "mixed":
        return True
    try:
        os.stat(_path(cat, "easy"))
        return True
    except OSError:
        return False


def _count(cat, diff):
    key = cat + "/" + diff
    if key not in _counts:
        try:
            _counts[key] = os.stat(_path(cat, diff, ".idx"))[6] // 4
        except OSError:
            _counts[key] = 0
    return _counts[key]


def _line(cat, diff, index):
    # The .idx file holds each line's byte offset (uint32, little-endian).
    with open(_path(cat, diff, ".idx"), "rb") as f:
        f.seek(index * 4)
        offset = struct.unpack("<I", f.read(4))[0]
    with open(_path(cat, diff), "rb") as f:
        f.seek(offset)
        return f.readline().decode().rstrip("\r\n")


class Question:
    def __init__(self, text, answers, correct, cat, diff):
        self.text, self.answers, self.correct = text, answers, correct
        self.cat, self.diff = cat, diff


def pick(cat, diff, used):
    """A random unused question; answers shuffled. ``used`` is a set of keys."""
    cats = [c for c, _ in CATEGORIES[1:] if available(c)] if cat == "mixed" else [cat]
    for _ in range(40):
        c = random.choice(cats)
        n = _count(c, diff)
        if not n:
            continue
        i = random.getrandbits(16) % n
        key = (c, diff, i)
        if key in used:
            continue
        fields = _line(c, diff, i).split("|")
        if len(fields) != 5:
            continue
        used.add(key)
        answers = fields[1:]
        order = list(range(4))
        for j in range(3, 0, -1):  # Fisher-Yates
            k = random.getrandbits(8) % (j + 1)
            order[j], order[k] = order[k], order[j]
        shuffled = [answers[o] for o in order]
        return Question(fields[0], shuffled, order.index(0), c, diff)
    raise RuntimeError("no questions for " + cat + "/" + diff)
