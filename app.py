"""Flask web app for the author-vs-LLM passage quiz."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, List

from flask import Flask, jsonify, render_template, request


DATA_DIR = Path(__file__).resolve().parent / "data"
ORIGINAL_PATH = DATA_DIR / "original_openings.jsonl"
GENERATED_PATH = DATA_DIR / "generated_openings.jsonl"


def load_jsonl(path: Path) -> List[Dict]:
    rows: List[Dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def load_datasets() -> Dict:
    originals = {str(row["book_id"]): row for row in load_jsonl(ORIGINAL_PATH)}
    generated = {str(row["book_id"]): row for row in load_jsonl(GENERATED_PATH)}
    common_ids = sorted(set(originals) & set(generated))
    return {
        "originals": originals,
        "generated": generated,
        "common_ids": common_ids,
    }


def build_pair(book_id: str, originals: Dict[str, Dict], generated: Dict[str, Dict], rng: random.Random) -> Dict:
    original = originals[book_id]
    gpt = generated[book_id]
    options = [
        {"label": "Original", "text": original["original_opening"]},
        {"label": "GPT", "text": gpt["gpt_opening"]},
    ]
    rng.shuffle(options)
    labeled = []
    for idx, option in enumerate(options):
        labeled.append({"slot": "A" if idx == 0 else "B", **option})
    correct_label = next(opt["slot"] for opt in labeled if opt["label"] == "Original")
    return {
        "book_id": int(book_id),
        "title": original["title"],
        "author": original["author"],
        "options": labeled,
        "correct_label": correct_label,
    }


def sample_pairs(data: Dict, count: int, seed: int | None = None) -> List[Dict]:
    rng = random.Random(seed)
    ids = data["common_ids"]
    if not ids:
        raise ValueError("No overlapping originals and generations. Run the generation script first.")
    chosen = rng.sample(ids, min(count, len(ids)))
    return [build_pair(book_id, data["originals"], data["generated"], rng) for book_id in chosen]


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["DATA_CACHE"] = load_datasets()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/quiz")
    def api_quiz():
        try:
            pairs = int(request.args.get("pairs", 10))
            seed_param = request.args.get("seed")
            seed = int(seed_param) if seed_param is not None else None
            if pairs <= 0:
                raise ValueError
        except ValueError:
            return jsonify({"error": "pairs must be a positive integer"}), 400
        data = app.config["DATA_CACHE"]
        try:
            payload = sample_pairs(data, pairs, seed=seed)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"pairs": payload})

    @app.route("/healthz")
    def healthz():
        return jsonify({"status": "ok", "pairs_available": len(app.config['DATA_CACHE']['common_ids'])})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
