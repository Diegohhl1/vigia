#!/usr/bin/env python3
"""Run the labelled classifier evaluation without network or Ollama."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vigia.eval import evaluate, load_cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", nargs="?", default="eval/classifier_cases.v1.jsonl")
    args = parser.parse_args()
    cases = load_cases(args.dataset)
    # The dataset stores deterministic expected outputs for parser/gate checks.
    metrics = evaluate(cases, lambda case: case["prediction"])
    print(json.dumps({k: v for k, v in metrics.items() if k != "predictions"}, sort_keys=True))
    return 0 if metrics["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
