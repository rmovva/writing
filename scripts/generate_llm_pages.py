"""Generate first pages with GPT-5.1 to mirror the collected openings."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from openai import OpenAI
from tqdm import tqdm


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ORIGINAL_PATH = DATA_DIR / "original_openings.jsonl"
GENERATED_PATH = DATA_DIR / "generated_openings.jsonl"
MODEL_NAME = "gpt-5.1"


def subject_summary(subjects: Iterable[str] | None, fallback: str | None = None) -> str:
    if subjects:
        cleaned = [s.strip() for s in subjects if s and s.strip()]
        if cleaned:
            return ", ".join(cleaned[:10])
    if fallback:
        return fallback.strip()
    return "unspecified subjects"


def load_originals() -> List[Dict]:
    if not ORIGINAL_PATH.exists():
        raise FileNotFoundError(f"Missing originals at {ORIGINAL_PATH}")
    entries: List[Dict] = []
    with ORIGINAL_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            entries.append(json.loads(line))
    return entries


def load_existing() -> Dict[str, Dict]:
    existing: Dict[str, Dict] = {}
    if not GENERATED_PATH.exists():
        return existing
    with GENERATED_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            existing[str(record["book_id"])] = record
    return existing


def extract_text(response) -> str:
    # API response shape differs across client versions; cover the common variants.
    if hasattr(response, "output_text"):
        return response.output_text or ""
    output = getattr(response, "output", None) or []
    if isinstance(output, list):
        for item in output:
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text", "")
    return ""


def build_prompt(entry: Dict) -> str:
    subjects = subject_summary(entry.get("subjects"), fallback=entry.get("description"))
    return (
        f"Write the first page of a book in the style of {entry['author']}'s "
        f"{entry['title']}. Use approximately 500 words. As a reminder, the subject "
        f"material of this book includes: {subjects}. Even if the first page is in "
        f"your training data, make sure not to copy it exactly; write a "
        f"similarly-styled first page yourself."
    )


def make_client() -> OpenAI:
    api_key = os.getenv("OAI_RLHF")
    if not api_key:
        raise RuntimeError("OAI_RLHF environment variable is not set.")
    return OpenAI(api_key=api_key)


def write_records(records: List[Dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with GENERATED_PATH.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


def generate(max_records: Optional[int] = None, overwrite: bool = False) -> None:
    originals = load_originals()
    existing_map = load_existing()
    client = make_client()

    to_process = originals[: max_records or len(originals)]
    results: List[Dict] = []
    for entry in tqdm(to_process, desc="Generating pages"):
        key = str(entry["book_id"])
        if not overwrite and key in existing_map:
            results.append(existing_map[key])
            continue
        prompt = build_prompt(entry)
        response = client.responses.create(
            model=MODEL_NAME,
            input=[{"role": "user", "content": prompt}],
            reasoning={"effort": "low"},
            text={"verbosity": "low"},
        )
        generated_text = extract_text(response)
        record = {
            "book_id": entry["book_id"],
            "author": entry["author"],
            "title": entry["title"],
            "subjects_used": subjects,
            "prompt": prompt,
            "model": MODEL_NAME,
            "gpt_opening": generated_text,
        }
        results.append(record)
        write_records(results)

    # Ensure existing entries not touched are preserved if max_records is smaller.
    if not overwrite and len(to_process) < len(originals):
        for entry in originals[len(to_process) :]:
            key = str(entry["book_id"])
            if key in existing_map:
                results.append(existing_map[key])
    write_records(results)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate GPT-5.1 first pages.")
    parser.add_argument("--max-records", type=int, help="Limit how many books to process.")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate even if already present.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    generate(max_records=args.max_records, overwrite=args.overwrite)
    print(f"Wrote generations to {GENERATED_PATH}")


if __name__ == "__main__":
    main()
