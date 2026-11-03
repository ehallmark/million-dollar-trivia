# High scores, saved as JSON on the board's flash.
import json

PATH = "/scores.json"
TOP = 10


def _load():
    try:
        with open(PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.setdefault("top", [])    # [[initials, amount, mode, category], ...]
    data.setdefault("best", {})   # {"mode/category": amount}
    return data


_data = _load()


def _save():
    with open(PATH + ".tmp", "w") as f:
        json.dump(_data, f)
    import os
    os.rename(PATH + ".tmp", PATH)  # atomic, so a power cut can't corrupt it


def top():
    return _data["top"]


def best(mode, cat):
    return _data["best"].get(mode + "/" + cat, 0)


def qualifies(amount):
    """Would this score make the top-10 table?"""
    return amount > 0 and (len(_data["top"]) < TOP or amount > _data["top"][-1][1])


def record(amount, mode, cat, initials=None):
    """Save a finished game. Returns True if it set a new best for mode/category."""
    key = mode + "/" + cat
    new_best = amount > _data["best"].get(key, 0)
    if new_best:
        _data["best"][key] = amount
    if initials and qualifies(amount):
        _data["top"].append([initials, amount, mode, cat])
        _data["top"].sort(key=lambda e: -e[1])
        del _data["top"][TOP:]
    _save()
    return new_best
