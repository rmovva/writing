"""CLI demo: guess whether A or B is human-written."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ORIGINAL_PATH = DATA_DIR / "original_openings.jsonl"
GENERATED_PATH = DATA_DIR / "generated_openings.jsonl"
NO_TEXT_MARKER = "[no text extracted]"


@dataclass
class Pair:
    book_id: int
    title: str
    author: str
    description: str
    options: List[Dict]
    correct_label: str


def load_jsonl(path: Path) -> List[Dict]:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    rows: List[Dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def build_pairs(count: int, seed: int | None) -> List[Pair]:
    originals = {str(row["book_id"]): row for row in load_jsonl(ORIGINAL_PATH)}
    generated = {str(row["book_id"]): row for row in load_jsonl(GENERATED_PATH)}
    common_ids = sorted(
        book_id
        for book_id in set(originals.keys()) & set(generated.keys())
        if originals[book_id].get("original_opening", "").strip() != NO_TEXT_MARKER
        and generated[book_id].get("gpt_opening", "").strip() != NO_TEXT_MARKER
    )
    if len(common_ids) < count:
        raise ValueError(f"Need {count} pairs but only {len(common_ids)} have generations.")
    rng = random.Random(seed)
    chosen_ids = rng.sample(common_ids, count)
    pairs: List[Pair] = []
    for book_id in chosen_ids:
        original_text = originals[book_id]["original_opening"]
        gpt_text = generated[book_id]["gpt_opening"]
        options = [
            {"label": "Original", "text": original_text},
            {"label": "GPT", "text": gpt_text},
        ]
        rng.shuffle(options)
        labeled_options = []
        for idx, option in enumerate(options):
            labeled_options.append({"slot": "A" if idx == 0 else "B", **option})
        correct_label = next(opt["slot"] for opt in labeled_options if opt["label"] == "Original")
        pairs.append(
            Pair(
                book_id=int(book_id),
                title=originals[book_id]["title"],
                author=originals[book_id]["author"],
                description=originals[book_id].get("description", ""),
                options=labeled_options,
                correct_label=correct_label,
            )
        )
    return pairs


def ask_user(pairs: List[Pair]) -> List[Dict]:
    responses: List[Dict] = []
    for idx, pair in enumerate(pairs, start=1):
        print(f"\nPair {idx}: {pair.title} by {pair.author}")
        for option in pair.options:
            print(f"\n--- {option['slot']} ---\n{option['text']}\n")
        choice = ""
        while choice not in ("a", "b"):
            choice = input("Pick A or B: ").strip().lower()
        correct = pair.correct_label.lower() == choice
        responses.append(
            {
                "pair": idx,
                "book_id": pair.book_id,
                "title": pair.title,
                "author": pair.author,
                "picked": choice.upper(),
                "correct_label": pair.correct_label,
                "is_correct": correct,
                "description": pair.description,
                "options": pair.options,
            }
        )
    return responses


def show_results(results: List[Dict]) -> None:
    correct = sum(1 for r in results if r["is_correct"])
    total = len(results)
    accuracy = (correct / total) * 100 if total else 0
    print(f"\nYou answered {correct} of {total} correctly ({accuracy:.1f}%).")
    print("\nReview the pairs with labels:\n")
    for result in results:
        print(f"Pair {result['pair']}: {result['title']} by {result['author']}")
        for option in result["options"]:
            marker = "Original" if option["label"] == "Original" else "GPT"
            label = f"{option['slot']} [{marker}]"
            print(f"\n--- {label} ---\n{option['text']}\n")
        verdict = "Correct" if result["is_correct"] else "Incorrect"
        print(f"Your pick: {result['picked']} | Correct answer: {result['correct_label']} | {verdict}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A/B demo guessing game.")
    parser.add_argument("--pairs", type=int, default=10, help="How many pairs to show.")
    parser.add_argument("--seed", type=int, help="Optional random seed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        pairs = build_pairs(args.pairs, args.seed)
    except FileNotFoundError as exc:
        print(f"{exc}. Run scripts/generate_llm_pages.py first.")
        return
    except ValueError as exc:
        print(f"{exc} Run scripts/generate_llm_pages.py to populate more pairs.")
        return
    results = ask_user(pairs)
    show_results(results)


if __name__ == "__main__":
    main()
