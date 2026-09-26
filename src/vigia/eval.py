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

    # Per-class recall
    pricing_cases = [(i, case) for i, case in enumerate(rows) if case["label"] == "pricing"]
    breaking_cases = [(i, case) for i, case in enumerate(rows) if case["label"] == "breaking"]

    pricing_tp = sum(1 for i, _ in pricing_cases if predictions[i].get("verdict") == "pricing")
    breaking_tp = sum(1 for i, _ in breaking_cases if predictions[i].get("verdict") == "breaking")

    recall_pricing = pricing_tp / len(pricing_cases) if pricing_cases else 0.0
    recall_breaking = breaking_tp / len(breaking_cases) if breaking_cases else 0.0

    # Aggregate protected recall (for backwards compatibility)
    positives = [(i, case) for i, case in enumerate(rows) if case["label"] in PROTECTED]
    tp = sum(1 for i, case in positives if predictions[i].get("verdict") == case["label"])
    protected_recall = tp / len(positives) if positives else 0.0

    # False positive rate
    negatives = [i for i, case in enumerate(rows) if case["label"] not in PROTECTED]
    false_positive = sum(predictions[i].get("verdict") in PROTECTED for i in negatives)
    fp_rate = false_positive / len(negatives) if negatives else 0.0

    # Gate passes only if BOTH classes meet threshold
    gate_passed = (
        (recall_pricing >= 0.90 or not pricing_cases) and
        (recall_breaking >= 0.90 or not breaking_cases) and
        fp_rate < 0.10
    )

    return {
        "cases": len(rows),
        "protected_cases": len(positives),
        "protected_recall": protected_recall,
        "recall_pricing": recall_pricing,
        "recall_breaking": recall_breaking,
        "false_positive_rate": fp_rate,
        "gate_passed": gate_passed,
        "predictions": predictions,
    }


def gate_allows_publication(metrics: dict) -> bool:
    return bool(metrics.get("gate_passed", False))


def conservative_verdict(verdict: dict, metrics: dict) -> dict:
    """Force every result into review mode until the evaluation gate passes."""
    if gate_allows_publication(metrics):
        return verdict
    return {**verdict, "verdict": "needs_review", "review_status": "evaluation_gate_failed"}


def evaluate_real(
    cases: Iterable[dict],
    classify_fn: Callable,
    model: str | None = None,
    prompt_version: str | None = None,
    dataset: str | None = None,
) -> dict:
    """Evaluate classifier by calling it on fresh diffs from cases (no cached predictions)."""
    rows = list(cases)
    predictions = []
    for case in rows:
        diff_text = case.get("diff", "")
        source_meta = {"id": case.get("id", ""), "category": case.get("category", "")}
        verdict = classify_fn(diff_text, source_meta)
        predictions.append(verdict)

    # Per-class recall
    pricing_cases = [(i, case) for i, case in enumerate(rows) if case["label"] == "pricing"]
    breaking_cases = [(i, case) for i, case in enumerate(rows) if case["label"] == "breaking"]

    pricing_tp = sum(1 for i, _ in pricing_cases if predictions[i].get("verdict") == "pricing")
    breaking_tp = sum(1 for i, _ in breaking_cases if predictions[i].get("verdict") == "breaking")

    recall_pricing = pricing_tp / len(pricing_cases) if pricing_cases else 0.0
    recall_breaking = breaking_tp / len(breaking_cases) if breaking_cases else 0.0

    # Aggregate protected recall
    positives = [(i, case) for i, case in enumerate(rows) if case["label"] in PROTECTED]
    tp = sum(1 for i, case in positives if predictions[i].get("verdict") == case["label"])
    protected_recall = tp / len(positives) if positives else 0.0

    # False positive rate
    negatives = [i for i, case in enumerate(rows) if case["label"] not in PROTECTED]
    false_positive = sum(predictions[i].get("verdict") in PROTECTED for i in negatives)
    fp_rate = false_positive / len(negatives) if negatives else 0.0

    # Gate passes only if BOTH classes meet threshold
    gate_passed = (
        (recall_pricing >= 0.90 or not pricing_cases) and
        (recall_breaking >= 0.90 or not breaking_cases) and
        fp_rate < 0.10
    )

    result = {
        "cases": len(rows),
        "protected_cases": len(positives),
        "protected_recall": protected_recall,
        "recall_pricing": recall_pricing,
        "recall_breaking": recall_breaking,
        "false_positive_rate": fp_rate,
        "gate_passed": gate_passed,
        "predictions": predictions,
    }
    if model is not None:
        result["model"] = model
    if prompt_version is not None:
        result["prompt_version"] = prompt_version
    if dataset is not None:
        result["dataset"] = dataset
    return result

