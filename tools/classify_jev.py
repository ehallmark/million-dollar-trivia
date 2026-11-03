"""Rate OpenTriviaQA questions with TypeSafe's Jev model.

OpenTriviaQA (github.com/uberspot/OpenTriviaQA, CC BY-SA 4.0) has ~50k questions but
no difficulty labels and some stale or wrong answers. For every question that fits
the screen, Jev judges: difficulty, whether the marked answer is right (and the
others wrong), whether it may be out of date, whether it reads clearly on its own,
and which of our categories it belongs to.

Results are appended to tools/opentriviaqa/jev.jsonl (re-runnable: rated questions
are skipped). Needs TYPESAFE_API_KEY in the environment.

  uv run --no-project --with typesafe-sdk tools/classify_jev.py [--limit N]
"""

import asyncio
import json
import sys
from pathlib import Path

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_questions import OPENTDB, clean, key, ok  # noqa: E402

SRC = Path.home() / "tools" / "opentriviaqa" / "repo" / "categories"
OUT = Path(__file__).resolve().parent / "opentriviaqa" / "jev.jsonl"
CONCURRENCY = 24

CATEGORY_HINTS = {
    "general": "general knowledge that fits no narrower category (food, everyday life, holidays, brands)",
    "history": "historical events, people, wars, empires, eras",
    "geography": "countries, capitals, cities, rivers, mountains, landmarks, flags",
    "science": "physics, chemistry, biology, astronomy, medicine, the human body",
    "nature": "animals, plants, ecosystems, the natural world",
    "art_history": "painting, sculpture, architecture, artists, art movements",
    "music": "songs, bands, musicians, composers, instruments, albums",
    "movies_tv": "films, television shows, actors, directors, celebrities of the screen",
    "literature": "books, novels, poems, plays, authors, fictional characters from books",
    "english": "English words, grammar, spelling, vocabulary, idioms, etymology",
    "french": "the French language, French culture, France-specific facts",
    "math": "arithmetic, geometry, algebra, numbers, mathematicians",
    "technology": "computers, the internet, inventions, gadgets, engineering, vehicles",
    "politics": "governments, politicians, elections, law, political systems, mythology and religion are NOT politics",
    "sports": "sports, athletes, teams, games like chess, the Olympics",
    "video_games": "video games, consoles, game characters",
    "other": "none of the above fits well (for example mythology, religion, comics, celebrity gossip, hobbies)",
}
assert set(CATEGORY_HINTS) - {"other"} == set(OPENTDB)

QUESTIONS = {
    "difficulty": Score(
        instructions="How hard is this multiple-choice trivia question for a typical adult "
                     "English-speaking player who sees the question and all four options?",
        criteria=[
            "Easy: most adults would know it or could easily pick it from the options",
            "Medium: a regular at pub trivia nights would probably get it; many casual players would not",
            "Hard: only enthusiasts or specialists in the subject would know it",
        ],
    ),
    "correct": Noul(
        instructions="Is `correct` truly the right answer to `question`, and are all of the "
                     "`wrong` options actually wrong, so the question has exactly one right answer?"),
    "dated": Noul(
        instructions="Could the right answer to `question` have changed since it was written "
                     "(around 2010)? For example: current office holders, records, latest or "
                     "most recent things, someone's age, counts that keep growing, or 'currently'."),
    "clear": Noul(
        instructions="Does `question` make sense on its own as a quiz question, without a picture, "
                     "earlier question, or missing context, and is it free of offensive content?"),
    "category": Choice(
        instructions="Which trivia category does `question` belong to?",
        criteria=CATEGORY_HINTS,
    ),
}


def read_text(path):
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def parse():
    """Yield (source_file, fields) for every 4-option question that fits the screen."""
    for path in sorted(SRC.iterdir()):
        block = []
        for line in read_text(path).splitlines() + [""]:
            if line.startswith("#Q "):
                block = [line[3:]]
            elif block and line.strip() and not line.startswith("#"):
                block.append(line)
            elif not line.strip() and block:
                yield path.name, block
                block = []
            elif block and line.startswith("#"):  # wrapped question text
                block[0] += " " + line.lstrip("#").strip()


def to_fields(block):
    q, rest = block[0], block[1:]
    correct = [r[2:] for r in rest if r.startswith("^ ")]
    options = [r[2:] for r in rest if len(r) > 2 and r[0] in "ABCD" and r[1] == " "]
    if len(correct) != 1 or len(options) != 4:
        return None
    c = clean(correct[0])
    opts = [clean(o) for o in options]
    if c not in opts:
        return None
    fields = [clean(q), c] + [o for o in opts if o != c]
    return fields if ok(fields) else None


async def rate(client, sem, item, out):
    q, c, *wrong = item["fields"]
    async with sem:
        try:
            r = await client.system_one(
                state={"question": q, "correct": c, "wrong": wrong}, questions=QUESTIONS)
        except Exception as exc:  # keep going; the item is retried on the next run
            print("  error:", type(exc).__name__, exc, flush=True)
            return
    item["jev"] = {
        "model": r.model,
        "difficulty": round(r.scores["difficulty"].score, 3),
        "difficulty_conf": round(r.scores["difficulty"].confidence, 3),
        "correct": round(r.nouls["correct"].noul, 3),
        "dated": round(r.nouls["dated"].noul, 3),
        "clear": round(r.nouls["clear"].noul, 3),
        "category": r.choices["category"].choice,
        "category_conf": round(r.choices["category"].confidence, 3),
    }
    out.write(json.dumps(item, ensure_ascii=False) + "\n")
    out.flush()


async def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    done = set()
    if OUT.exists():
        done = {key(json.loads(l)["fields"][0]) for l in OUT.read_text().splitlines() if l}
    items, seen = [], set(done)
    for source, block in parse():
        fields = to_fields(block)
        if fields and key(fields[0]) not in seen:
            seen.add(key(fields[0]))
            items.append({"source": source, "fields": fields})
    items = items[:limit] if limit else items
    print(f"{len(done)} already rated, {len(items)} to rate", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(CONCURRENCY)
    async with AsyncTypeSafeClient() as client:
        with OUT.open("a") as out:
            tasks = [rate(client, sem, item, out) for item in items]
            for i in range(0, len(tasks), 500):
                await asyncio.gather(*tasks[i:i + 500])
                print(f"  {min(i + 500, len(tasks))}/{len(tasks)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
