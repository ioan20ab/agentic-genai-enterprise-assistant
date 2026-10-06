"""Measure retrieval hit rate and answer accuracy, e.g. to compare chunk sizes or prompts.

    python -m eval.evaluate                      # current settings
    python -m eval.evaluate --chunk-sizes 300 800 1500
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

QUESTIONS = Path(__file__).with_name("questions.jsonl")


def evaluate() -> dict:
    # Imported late so env overrides (CHUNK_SIZE, ...) take effect.
    from assistant.agent import run_agent
    from assistant.ingest import build_index

    build_index()
    rows = [json.loads(l) for l in QUESTIONS.read_text(encoding="utf-8").splitlines() if l.strip()]
    hits = correct = 0
    for r in rows:
        res = run_agent(r["question"])
        hit = r["expected_source"] in res.sources[:2]
        ok = all(t.lower() in res.answer.lower() for t in r["expected_terms"])
        hits += hit
        correct += ok
        if not ok:
            print(f"  [miss] {r['id']}: {r['question']} -> {res.answer[:100]!r}")
    n = len(rows)
    return {"questions": n, "retrieval_hit@2": hits / n, "answer_accuracy": correct / n}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chunk-sizes", type=int, nargs="*")
    args = ap.parse_args()
    for size in args.chunk_sizes or [None]:
        if size:
            os.environ["CHUNK_SIZE"] = str(size)
            os.environ["CHUNK_OVERLAP"] = str(size // 6)
        scores = evaluate()
        label = f"chunk_size={size}" if size else "current settings"
        print(f"{label}: retrieval hit@2={scores['retrieval_hit@2']:.0%}, "
              f"answer accuracy={scores['answer_accuracy']:.0%} ({scores['questions']} questions)")


if __name__ == "__main__":
    main()
