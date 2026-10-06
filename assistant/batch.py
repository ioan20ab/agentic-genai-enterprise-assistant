"""Offline batch inference over a JSONL file of questions.

    python -m assistant.batch questions.jsonl answers.jsonl

Each input line: {"id": "...", "question": "..."}  ->  output adds answer, sources, actions.
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .agent import run_agent
from .config import get_settings


def run_batch(in_path: Path, out_path: Path) -> int:
    rows = [json.loads(line) for line in in_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    with ThreadPoolExecutor(max_workers=get_settings().batch_workers) as pool:
        results = list(pool.map(lambda r: {**r, **run_agent(r["question"]).to_dict()}, rows))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(results)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    n = run_batch(args.input, args.output)
    print(f"Answered {n} questions -> {args.output}")


if __name__ == "__main__":
    main()
