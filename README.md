# LLM vs. Author First-Passage Demo

This repo builds a simple experiment comparing the first passage of public-domain novels with GPT-written counterparts. The pipeline is split into three scripts:

1) **Fetch openings**: grab the first ~500 words of ~100 lesser-known works by famous authors from Project Gutenberg (via Gutendex).
2) **Generate model passages**: ask `gpt-5.1` (key from `$OAI_RLHF`) to write similarly-styled first passages.
3) **Run the demo**: play through 10 random A/B pairs, guess which is human vs GPT, then review the answers.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OAI_RLHF=your_openai_api_key  # needed for generation
```

## 1) Fetch the author passages

```
python scripts/fetch_openings.py --limit 100 --seed 123 --max-words 500
```

Outputs:
- `data/book_metadata.json`: metadata (book id, author, title, source URLs, 10-word subject blurb).
- `data/original_openings.jsonl`: same metadata plus the opening passage.

The script filters out the best-known titles per author and removes Gutenberg indexes; it shuffles the pool to keep a mix of authors. Adjust `--limit`, `--seed`, or `--max-words` as needed.

## 2) Generate GPT-written passages

```
python scripts/generate_llm_pages.py --max-records 100 --workers 30
```

Notes:
- Uses `model="gpt-5.1"` with `reasoning_effort="low"` and `verbosity="low"`.
- Progress is shown via `tqdm`; reruns skip already-generated entries unless `--overwrite` is set. Calls run in parallel (default 30 workers).
- Output lives in `data/generated_openings.jsonl` with prompts and the generated text.

## 3) Run the A/B guessing demo

```
python scripts/run_demo.py --pairs 10 --seed 7
```

The script randomly chooses pairs where both the original and GPT passages exist, shuffles A/B order, tallies your picks, and then shows the accuracy plus a labeled review of each pair.

## Data snapshot

The repo currently includes a collected sample of 100 passages from famous authors’ less-taught works (see `data/original_openings.jsonl`). Regenerate anytime with the fetch script if you want a different mix.

## Safety and housekeeping

- Keep secrets out of version control; the OpenAI key should stay in `$OAI_RLHF`.
- Large data (>10 MB) should be kept out of the repo or added to `.gitignore` (see included patterns).
