"""Reproducible offline evaluation and conservative publication gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

PROTECTED = {"pricing", "breaking"}


def load_cases(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate(cases: Iterable[dict], classifier: Callable[[dict], dict]) -> dict:
    rows = list(cases)
    predictions = [classifier(case) for case in rows]
    positives = [case for case in rows if case["label"] in PROTECTED]
    tp = sum(pred.get("verdict") == case["label"] for case in positives for pred in [predictions[rows.index(case)]])
    protected_recall = tp / len(positives) if positives else 0.0
    negatives = [i for i, case in enumerate(rows) if case["label"] not in PROTECTED]
    false_positive = sum(predictions[i].get("verdict") in PROTECTED for i in negatives)
    fp_rate = false_positive / len(negatives) if negatives else 0.0
    return {
        "cases": len(rows),
        "protected_cases": len(positives),
        "protected_recall": protected_recall,
        "false_positive_rate": fp_rate,
        "gate_passed": protected_recall >= 0.90 and fp_rate < 0.10,
        "predictions": predictions,
    }


def gate_allows_publication(metrics: dict) -> bool:
    return bool(metrics.get("gate_passed", False))


def conservative_verdict(verdict: dict, metrics: dict) -> dict:
    """Force every result into review mode until the evaluation gate passes."""
    if gate_allows_publication(metrics):
        return verdict
    return {**verdict, "verdict": "needs_review", "review_status": "evaluation_gate_failed"}

