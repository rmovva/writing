"""Collect opening pages for a set of public-domain novels via Gutendex.

The script builds a metadata file and a matching openings file:
- data/book_metadata.json: metadata for the selected books
- data/original_openings.jsonl: first ~500 words of each book
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests
from tqdm import tqdm


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
METADATA_PATH = DATA_DIR / "book_metadata.json"
OPENINGS_PATH = DATA_DIR / "original_openings.jsonl"
DEFAULT_LIMIT = 100
DEFAULT_WORDS = 500


# Famous authors with instructions to skip the obvious works.
AUTHOR_CONFIG = [
    {"name": "Herman Melville", "exclude": ["Moby Dick", "Moby-Dick", "Typee", "Omoo", "Billy Budd"], "target": 4},
    {"name": "Nathaniel Hawthorne", "exclude": ["The Scarlet Letter", "The House of the Seven Gables", "Twice-Told Tales"], "target": 4},
    {"name": "Henry James", "exclude": ["The Portrait of a Lady", "The Turn of the Screw", "Daisy Miller", "The American", "Washington Square"], "target": 5},
    {"name": "Thomas Hardy", "exclude": ["Tess of the d'Urbervilles", "Far from the Madding Crowd", "Jude the Obscure", "The Mayor of Casterbridge"], "target": 5},
    {"name": "Charles Dickens", "exclude": ["Great Expectations", "A Tale of Two Cities", "Oliver Twist", "A Christmas Carol", "David Copperfield", "Bleak House", "Hard Times"], "target": 4},
    {"name": "Mark Twain", "exclude": ["Adventures of Huckleberry Finn", "The Adventures of Tom Sawyer", "The Prince and the Pauper", "A Connecticut Yankee in King Arthur's Court", "Life on the Mississippi"], "target": 4},
    {"name": "George Eliot", "exclude": ["Middlemarch", "Silas Marner", "Daniel Deronda", "Adam Bede"], "target": 4},
    {"name": "Joseph Conrad", "exclude": ["Heart of Darkness", "Lord Jim", "Nostromo", "The Secret Agent"], "target": 5},
    {"name": "Edith Wharton", "exclude": ["The Age of Innocence", "Ethan Frome", "The House of Mirth"], "target": 4},
    {"name": "Willa Cather", "exclude": ["My Antonia", "O Pioneers!", "The Song of the Lark"], "target": 3},
    {"name": "E. M. Forster", "exclude": ["A Room with a View", "Howards End", "A Passage to India", "Where Angels Fear to Tread"], "target": 3},
    {"name": "Rudyard Kipling", "exclude": ["The Jungle Book", "Kim", "Just So Stories", "The Man Who Would Be King"], "target": 4},
    {"name": "H. G. Wells", "exclude": ["The War of the Worlds", "The Time Machine", "The Invisible Man", "The Island of Doctor Moreau"], "target": 4},
    {"name": "Arthur Conan Doyle", "exclude": ["The Hound of the Baskervilles", "A Study in Scarlet", "The Sign of the Four", "The Adventures of Sherlock Holmes", "Adventures of Sherlock Holmes", "Sherlock Holmes"], "target": 4},
    {"name": "Robert Louis Stevenson", "exclude": ["Treasure Island", "Strange Case of Dr Jekyll and Mr Hyde", "Kidnapped"], "target": 4},
    {"name": "Louisa May Alcott", "exclude": ["Little Women", "Little Men"], "target": 3},
    {"name": "Jack London", "exclude": ["The Call of the Wild", "White Fang", "The Sea-Wolf"], "target": 4},
    {"name": "Anthony Trollope", "exclude": ["Barchester Towers", "The Warden", "Doctor Thorne"], "target": 4},
    {"name": "Wilkie Collins", "exclude": ["The Moonstone", "The Woman in White", "Armadale"], "target": 4},
    {"name": "Elizabeth Gaskell", "exclude": ["Cranford", "North and South", "Mary Barton"], "target": 3},
    {"name": "Stephen Crane", "exclude": ["The Red Badge of Courage", "Maggie: A Girl of the Streets"], "target": 3},
    {"name": "Kate Chopin", "exclude": ["The Awakening", "Bayou Folk"], "target": 3},
    {"name": "Charlotte Bronte", "exclude": ["Jane Eyre", "Shirley", "Villette"], "target": 3},
    {"name": "Fyodor Dostoevsky", "exclude": ["Crime and Punishment", "The Brothers Karamazov", "The Idiot"], "target": 3},
    {"name": "Leo Tolstoy", "exclude": ["War and Peace", "Anna Karenina", "Resurrection"], "target": 3},
    {"name": "Alexandre Dumas", "exclude": ["The Three Musketeers", "The Count of Monte Cristo", "The Black Tulip"], "target": 3},
    {"name": "H. Rider Haggard", "exclude": ["King Solomon's Mines", "She", "Allan Quatermain"], "target": 3},
    {"name": "Jules Verne", "exclude": ["Twenty Thousand Leagues under the Sea", "Around the World in Eighty Days", "Journey to the Center of the Earth", "From the Earth to the Moon"], "target": 3},
    {"name": "Oscar Wilde", "exclude": ["The Picture of Dorian Gray", "The Canterville Ghost"], "target": 3},
    {"name": "Bram Stoker", "exclude": ["Dracula", "The Lair of the White Worm"], "target": 3},
    {"name": "P. G. Wodehouse", "exclude": ["The Inimitable Jeeves", "My Man Jeeves"], "target": 3},
    {"name": "James Fenimore Cooper", "exclude": ["The Last of the Mohicans", "The Pathfinder"], "target": 3},
    {"name": "Edith Nesbit", "exclude": ["The Railway Children", "Five Children and It"], "target": 3},
]


@dataclass
class BookRecord:
    book_id: int
    title: str
    author: str
    download_url: str
    gutendex_url: str
    description: str
    subjects: List[str]


def normalized_title(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return " ".join(cleaned.split())


def _looks_like_text(url: str) -> bool:
    text_suffixes = (
        ".txt",
        ".txt?download=1",
        ".txt.utf-8",
        ".txt.utf-8?download=1",
    )
    return any(url.endswith(suffix) for suffix in text_suffixes)


def best_text_url(formats: Dict[str, str]) -> Optional[str]:
    preferred = [
        "text/plain; charset=utf-8",
        "text/plain; charset=us-ascii",
        "text/plain; charset=iso-8859-1",
        "text/plain",
    ]
    for key in preferred:
        url = formats.get(key)
        if url and _looks_like_text(url):
            return url
    for key, url in formats.items():
        if key.startswith("text/plain") and _looks_like_text(url):
            return url
    return None


def strip_gutenberg_headers(text: str) -> str:
    start_markers = [
        "*** START OF THIS PROJECT GUTENBERG EBOOK",
        "***START OF THE PROJECT GUTENBERG EBOOK",
        "*** START OF THE PROJECT GUTENBERG EBOOK",
    ]
    end_markers = [
        "*** END OF THIS PROJECT GUTENBERG EBOOK",
        "***END OF THE PROJECT GUTENBERG EBOOK",
        "*** END OF THE PROJECT GUTENBERG EBOOK",
    ]
    lower_text = text.lower()
    start_index = 0
    for marker in start_markers:
        loc = lower_text.find(marker.lower())
        if loc != -1:
            start_index = loc + len(marker)
            break
    end_index = len(text)
    for marker in end_markers:
        loc = lower_text.find(marker.lower())
        if loc != -1:
            end_index = loc
            break
    return text[start_index:end_index].strip()


def extract_opening(text: str, max_words: int = DEFAULT_WORDS) -> str:
    clean_text = text.replace("\r\n", "\n").strip()
    paragraphs = [p.strip() for p in clean_text.split("\n\n") if p.strip()]
    selected: List[str] = []
    word_total = 0
    for para in paragraphs:
        words = para.split()
        word_total += len(words)
        selected.append(para)
        if word_total >= max_words:
            break
    return "\n\n".join(selected)


def padded_description(subjects: Iterable[str]) -> str:
    tokens: List[str] = []
    for subject in subjects:
        tokens.extend(re.findall(r"[A-Za-z']+", subject))
    tokens = [token.lower() for token in tokens if token]
    default_words = ["literary", "fiction", "classic", "character", "driven", "story", "public", "domain", "novel", "themes"]
    while len(tokens) < 10:
        tokens.append(default_words[len(tokens) % len(default_words)])
    return " ".join(tokens[:10])


def author_matches(target: str, candidate: str) -> bool:
    def tokens(name: str) -> set[str]:
        return set(re.findall(r"[A-Za-z]+", name.lower()))

    target_tokens = tokens(target)
    candidate_tokens = tokens(candidate)
    return target_tokens.issubset(candidate_tokens)


def fetch_books(limit: int, seed: int) -> List[BookRecord]:
    collected: List[BookRecord] = []
    seen_ids = set()
    seen_titles = set()
    for config in AUTHOR_CONFIG:
        target = config.get("target", 3)
        excluded = {normalized_title(title) for title in config.get("exclude", [])}
        author_name = config["name"]
        page_url = f"https://gutendex.com/books?search={requests.utils.quote(author_name)}"
        author_books: List[BookRecord] = []
        while page_url and len(author_books) < target:
            resp = requests.get(page_url, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
            for book in payload.get("results", []):
                if not book.get("languages") or "en" not in book["languages"]:
                    continue
                if not any(author_matches(author_name, a["name"]) for a in book.get("authors", [])):
                    continue
                title = book.get("title", "")
                title_norm = normalized_title(title)
                if (
                    title_norm in excluded
                    or any(title_norm.startswith(f"{ex} ") or f" {ex} " in title_norm or title_norm.endswith(f" {ex}") for ex in excluded)
                    or "index of the project gutenberg works" in title_norm
                    or title_norm.startswith("project gutenberg collection of")
                ):
                    continue
                if book["id"] in seen_ids:
                    continue
                if title_norm in seen_titles:
                    continue
                text_url = best_text_url(book.get("formats", {}))
                if not text_url:
                    continue
                description = padded_description(book.get("subjects", []))
                record = BookRecord(
                    book_id=book["id"],
                    title=book.get("title", "").strip(),
                    author=author_name,
                    download_url=text_url,
                    gutendex_url=f"https://www.gutenberg.org/ebooks/{book['id']}",
                    description=description,
                    subjects=book.get("subjects", []),
                )
                seen_ids.add(record.book_id)
                seen_titles.add(title_norm)
                author_books.append(record)
                if len(author_books) >= target:
                    break
            page_url = payload.get("next")
        collected.extend(author_books)
    if len(collected) > limit:
        rng = random.Random(seed)
        rng.shuffle(collected)
        return collected[:limit]
    return collected


def fetch_opening_text(record: BookRecord, max_words: int) -> str:
    resp = requests.get(record.download_url, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.encoding or "utf-8"
    cleaned = strip_gutenberg_headers(resp.text)
    if not cleaned:
        cleaned = resp.text
    return extract_opening(cleaned, max_words=max_words)


def save_metadata(records: List[BookRecord]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with METADATA_PATH.open("w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in records], f, indent=2)


def save_openings(records: List[BookRecord], openings: Dict[int, str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OPENINGS_PATH.open("w", encoding="utf-8") as f:
        for record in records:
            payload = asdict(record)
            payload["original_opening"] = openings.get(record.book_id, "")
            f.write(json.dumps(payload) + "\n")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch first pages for public-domain novels.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Total number of books to collect.")
    parser.add_argument("--max-words", type=int, default=DEFAULT_WORDS, help="Approximate word count for openings.")
    parser.add_argument("--seed", type=int, default=42, help="Shuffle seed when trimming the list.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    records = fetch_books(args.limit, args.seed)
    if not records:
        print("No books collected. Check network or config.", file=sys.stderr)
        sys.exit(1)
    save_metadata(records)

    openings: Dict[int, str] = {}
    print(f"Fetching openings for {len(records)} books...")
    for record in tqdm(records, desc="Downloading texts"):
        try:
            openings[record.book_id] = fetch_opening_text(record, args.max_words)
        except Exception as exc:
            print(f"Failed to fetch {record.title} ({record.book_id}): {exc}", file=sys.stderr)
            openings[record.book_id] = ""

    save_openings(records, openings)
    print(f"Wrote metadata to {METADATA_PATH} and openings to {OPENINGS_PATH}")


if __name__ == "__main__":
    main()
