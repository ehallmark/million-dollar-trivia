"""Assemble the question bank the game uses: build/q/<category>/<difficulty>.txt.

Sources, in order of preference:
  1. questions/<category>/<difficulty>.txt  written for this game
  2. Open Trivia Database (tools/opentdb/raw.json, CC BY-SA 4.0), mapped to our categories
  3. OpenTriviaQA (CC BY-SA 4.0), rated by TypeSafe's Jev model (tools/classify_jev.py):
     only questions Jev judges correct, current and clear, binned by its difficulty score

Every question is checked against the screen limits and the font, duplicates are
dropped, and each file is capped at TARGET questions. Prints a coverage table.
"""

import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "q"
TARGET = 500
JEV = ROOT / "tools" / "opentriviaqa" / "jev.jsonl"
# Jev's difficulty score runs 0 (easy) .. 2 (hard).
EASY_BELOW, HARD_FROM = 0.6, 1.25
MAX_Q, MAX_A = 110, 26
DIFFS = ("easy", "medium", "hard")

# Our categories -> Open Trivia DB category ids.
OPENTDB = {
    "general": [9],
    "history": [23],
    "geography": [22],
    "science": [17],
    "nature": [27],
    "art_history": [25],
    "music": [12],
    "movies_tv": [11, 14],
    "literature": [10],
    "english": [],
    "french": [],
    "math": [19],
    "technology": [18, 30],
    "politics": [24],
    "sports": [21],
    "video_games": [15],
}

# Characters the device font has: printable ASCII, Latin-1 letters, a few symbols.
FONT = set(chr(c) for c in range(32, 127)) | set(chr(c) for c in range(0xC0, 0x100)) | set(
    "’…°·Œœ€£×÷«»")
REPLACE = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-",
           "—": "-", " ": " ", "…": "..."}


def unmojibake(text):
    """Undo UTF-8 that was decoded as Latin-1 ("JÃ¼rgen" -> "Jürgen"). Genuine Latin-1
    text ("café") doesn't survive the round trip, so it is left alone."""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def clean(text):
    text = unmojibake(text)
    text = re.sub(r"(\d)([½¼])", r"\1 \2", text)         # 8½ -> 8 ½ -> 8 1/2
    text = text.replace("½", "1/2").replace("¼", "1/4")    # the font has neither
    for a, b in REPLACE.items():
        text = text.replace(a, b)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\.\?$", "?", text)  # "...for mankind.?" in some sources


def ok(fields):
    q, answers = fields[0], fields[1:]
    if len(fields) != 5 or not all(fields) or any("|" in f for f in fields):
        return False
    if len(q) > MAX_Q or any(len(a) > MAX_A for a in answers):
        return False
    if len(set(a.lower() for a in answers)) != 4:
        return False
    return all(ch in FONT for f in fields for ch in f)


def key(question):
    return re.sub(r"[^a-z0-9]", "", question.lower())


# Contractions with only one sensible reading.
CONTRACTIONS = {w.replace("'", "").lower(): w for w in (
    "don't doesn't didn't isn't wasn't aren't weren't can't couldn't wouldn't shouldn't "
    "won't hasn't haven't hadn't I'm I've you're they're that's what's who's she's "
    "there's here's where's how's you've we've they've you'll they'll").split()}


def fix_contractions(text):
    def sub(m):
        w = m.group(0)
        rep = CONTRACTIONS.get(w.lower())
        if not rep:
            return w
        return rep[0].upper() + rep[1:] if w[0].isupper() else rep
    return re.sub(r"[A-Za-z]+", sub, text)


def jev_pool():
    """{(category, difficulty): [fields, ...]}, most likely correct first."""
    pool = {}
    if not JEV.exists():
        return pool
    fixes = {}  # apostrophes restored by tools/fix_apostrophes_jev.py
    if (JEV.parent / "apostrophes.jsonl").exists():
        for line in (JEV.parent / "apostrophes.jsonl").read_text().splitlines():
            row = json.loads(line)
            fixes[row["key"]] = row["fix"]
    for line in JEV.read_text().splitlines():
        item = json.loads(line)
        j = item["jev"]
        if j["correct"] < 0.75 or j["dated"] >= 0.35 or j["clear"] < 0.8 or j["category"] == "other":
            continue
        d = j["difficulty"]
        diff = "easy" if d < EASY_BELOW else "hard" if d >= HARD_FROM else "medium"
        fields = [clean(f) for f in item["fields"]]   # rated with older cleaning rules
        fields = [f[:1].upper() + f[1:] for f in fields]
        if fixes:
            fix = fixes.get(key(fields[0]), {})
            fields = [fix_contractions(re.sub(r"[A-Za-z]+", lambda m: fix.get(m.group(0), m.group(0)), f))
                      for f in fields]
        pool.setdefault((j["category"], diff), []).append((j["correct"], fields))
    return {k: [f for _, f in sorted(v, key=lambda t: -t[0])] for k, v in pool.items()}


def main():
    raw = {}
    raw_path = ROOT / "tools" / "opentdb" / "raw.json"
    if raw_path.exists():
        raw = json.loads(raw_path.read_text())
    seen = set()
    table, opentdb_used, jev_used = [], 0, 0
    jev = jev_pool()
    for cat, ids in OPENTDB.items():
        row = [cat]
        for diff in DIFFS:
            chosen, ours, theirs = [], 0, 0
            own = ROOT / "questions" / cat / f"{diff}.txt"
            if own.exists():
                for line in own.read_text().splitlines():
                    fields = [clean(f) for f in line.split("|")]
                    if ok(fields) and key(fields[0]) not in seen:
                        seen.add(key(fields[0]))
                        chosen.append(fields)
                        ours += 1
            for cid in ids:
                for item in raw.get(str(cid), {}).get(diff, []):
                    if len(chosen) >= TARGET:
                        break
                    fields = [clean(item["question"]), clean(item["correct"])] + [
                        clean(w) for w in item["wrong"]]
                    if ok(fields) and key(fields[0]) not in seen:
                        seen.add(key(fields[0]))
                        chosen.append(fields)
                        theirs += 1
            rated = 0
            for fields in jev.get((cat, diff), []):
                if len(chosen) >= TARGET:
                    break
                if ok(fields) and key(fields[0]) not in seen:
                    seen.add(key(fields[0]))
                    chosen.append(fields)
                    rated += 1
            chosen = chosen[:TARGET]
            opentdb_used += theirs
            jev_used += rated
            if chosen:
                path = OUT / cat / f"{diff}.txt"
                path.parent.mkdir(parents=True, exist_ok=True)
                data = b"".join(("|".join(f) + "\n").encode() for f in chosen)
                path.write_bytes(data)
                # <diff>.idx: little-endian uint32 byte offset of each line, for O(1) lookup.
                offsets, pos = [], 0
                for line in data.splitlines(keepends=True):
                    offsets.append(pos)
                    pos += len(line)
                path.with_suffix(".idx").write_bytes(struct.pack(f"<{len(offsets)}I", *offsets))
            row.append((len(chosen), ours, theirs, rated))
        table.append(row)

    print(f"{'category':12} " + "  ".join(f"{d:>22}" for d in DIFFS)
          + "   (total = ours + opentdb + opentriviaqa)")
    total = 0
    for cat, *cells in table:
        total += sum(c[0] for c in cells)
        print(f"{cat:12} " + "  ".join(f"{c[0]:4} = {c[1]:3} + {c[2]:3} + {c[3]:3}" for c in cells))
    print(f"total questions: {total}  (Open Trivia DB: {opentdb_used}, OpenTriviaQA: {jev_used})")
    if "--gaps" in sys.argv:
        gaps = {cat: {d: TARGET - c[0] for d, c in zip(DIFFS, cells) if c[0] < TARGET}
                for cat, *cells in table}
        (ROOT / "build" / "gaps.json").write_text(json.dumps(gaps, indent=1))


if __name__ == "__main__":
    main()
