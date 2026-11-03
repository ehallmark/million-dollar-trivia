"""Restore the apostrophes OpenTriviaQA lost ("Uncle Toms Cabin", "dont").

Code proposes spellings for every word that might need an apostrophe; Jev picks the
right spelling for each word in context (or keeps it as written). Only questions
that pass the build filter are checked. Writes tools/opentriviaqa/apostrophes.jsonl:
{"key": question key, "fix": {word: spelling}} (re-runnable).

  uv run --no-project --with typesafe-sdk tools/fix_apostrophes_jev.py
"""

import asyncio
import json
import re
import sys
from pathlib import Path

from typesafe_sdk import AsyncTypeSafeClient, Choice

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_questions import CONTRACTIONS, JEV, jev_pool, key  # noqa: E402

OUT = JEV.parent / "apostrophes.jsonl"
CONCURRENCY = 24

# Contractions that are also ordinary words: Jev decides.
AMBIGUOUS = {"its": ["its", "it's"], "lets": ["lets", "let's"], "hes": ["hes", "he's"]}
# Words ending in "s" that are never possessives.
NOT_POSSESSIVE = set("""is was has his hers its this thus us yes as gas bus plus less unless
across perhaps always sometimes towards afterwards whereas various famous serious previous
numerous nervous jealous religious obvious its ours yours theirs times years series species
news means physics mathematics politics athletics economics olympics games""".split())


def candidates(word):
    low = word.lower()
    if low in CONTRACTIONS:
        return None  # fixed in code
    if low in AMBIGUOUS:
        opts = AMBIGUOUS[low]
        return opts and [word] + [o[0].upper() + o[1:] if word[0].isupper() else o for o in opts[1:]]
    if len(word) < 4 or not low.endswith("s") or low in NOT_POSSESSIVE or low.endswith("ss"):
        return None
    if low.endswith("us") or low.endswith("is"):
        return None
    return [word, word[:-1] + "'s", word + "'"]


async def check(client, sem, fields, out):
    text = " | ".join(fields)
    words = sorted({w for w in re.findall(r"[A-Za-z]+", text) if candidates(w)})
    fix = {}
    if words:
        questions = {
            f"w{i}": Choice(
                instructions=f"This trivia question lost its apostrophes. How should the word "
                             f"`{w}` be spelled where it appears in `question` and `answers`? "
                             f"Keep it as written if it is a plain plural or ordinary word.",
                criteria={c: None for c in candidates(w)})
            for i, w in enumerate(words)}
        async with sem:
            try:
                r = await client.system_one(
                    state={"question": fields[0], "answers": fields[1:]}, questions=questions)
            except Exception as exc:
                print("  error:", type(exc).__name__, exc, flush=True)
                return
        for i, w in enumerate(words):
            pick = r.choices[f"w{i}"]
            if pick.choice != w and pick.confidence >= 0.4:
                fix[w] = pick.choice
    out.write(json.dumps({"key": key(fields[0]), "fix": fix}) + "\n")
    out.flush()


async def main():
    done = set()
    if OUT.exists():
        done = {json.loads(l)["key"] for l in OUT.read_text().splitlines() if l}
    items = [f for fields in jev_pool().values() for f in fields if key(f[0]) not in done]
    if "--limit" in sys.argv:
        items = items[:int(sys.argv[sys.argv.index("--limit") + 1])]
    print(f"{len(done)} done, {len(items)} to check", flush=True)
    sem = asyncio.Semaphore(CONCURRENCY)
    async with AsyncTypeSafeClient() as client:
        with OUT.open("a") as out:
            tasks = [check(client, sem, f, out) for f in items]
            for i in range(0, len(tasks), 1000):
                await asyncio.gather(*tasks[i:i + 1000])
                print(f"  {min(i + 1000, len(tasks))}/{len(tasks)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
