"""Download multiple-choice questions from the Open Trivia Database (opentdb.com).

Open Trivia DB questions are licensed CC BY-SA 4.0 (https://opentdb.com).
Writes tools/opentdb/raw.json: {opentdb_category_id: {difficulty: [question, ...]}}.
Respects the API rate limit (one request per 5 seconds). Re-runnable.
"""

import base64
import json
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "opentdb" / "raw.json"
CATEGORY_IDS = [9, 10, 11, 12, 14, 15, 17, 18, 19, 21, 22, 23, 24, 25, 27, 30]
API = "https://opentdb.com"


def get(url):
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.load(r)
        except Exception as exc:  # network hiccup
            print("  retry after error:", exc)
            time.sleep(10)
            continue
        if data.get("response_code") == 5:  # rate limited
            time.sleep(6)
            continue
        return data
    raise RuntimeError("giving up on " + url)


def b64(s):
    return base64.b64decode(s).decode("utf-8")


def main():
    raw = json.loads(OUT.read_text()) if OUT.exists() else {}
    for cat in CATEGORY_IDS:
        for diff in ("easy", "medium", "hard"):
            key = str(cat)
            if raw.get(key, {}).get(diff):
                continue  # already fetched
            token = get(f"{API}/api_token.php?command=request")["token"]
            time.sleep(5.2)
            got, amount = [], 50
            while True:
                data = get(f"{API}/api.php?amount={amount}&category={cat}&difficulty={diff}"
                           f"&type=multiple&encode=base64&token={token}")
                time.sleep(5.2)
                if data["response_code"] in (1, 4) and not data.get("results"):
                    # Fewer than `amount` left: ask for smaller batches, down to 1.
                    if amount > 1:
                        amount = max(1, amount // 3)
                        continue
                    break  # nothing left for this token
                for q in data["results"]:
                    got.append({
                        "question": b64(q["question"]),
                        "correct": b64(q["correct_answer"]),
                        "wrong": [b64(a) for a in q["incorrect_answers"]],
                    })
                if len(data["results"]) < amount:
                    break
            raw.setdefault(key, {})[diff] = got
            OUT.write_text(json.dumps(raw, indent=1, ensure_ascii=False))
            print(f"category {cat:2} {diff:6}: {len(got)} questions", flush=True)


if __name__ == "__main__":
    main()
