"""Tests for eval.py with synthetic cases and real jsonl."""

from __future__ import annotations

from vigia.eval import (
    load_cases,
    evaluate,
    gate_allows_publication,
    conservative_verdict,
    PROTECTED,
)


def test_evaluate_recall_with_synthetic_pricing_and_breaking():
    """Recall calculation should correctly count TP for pricing and breaking."""
    cases = [
        {"label": "pricing", "diff": "price $10"},
        {"label": "breaking", "diff": "removed API"},
        {"label": "noise", "diff": "typo fix"},
    ]

    def fake_classifier(case: dict) -> dict:
        # Perfect classifier
        return {"verdict": case["label"]}

    result = evaluate(cases, fake_classifier)

    assert result["protected_cases"] == 2
    assert result["protected_recall"] == 1.0  # 2/2 correct


def test_evaluate_false_positive_rate():
    """FP rate should count non-protected labeled as protected."""
    cases = [
        {"label": "noise", "diff": "nav"},
        {"label": "minor", "diff": "small"},
        {"label": "pricing", "diff": "price"},
    ]

    def fake_classifier(case: dict) -> dict:
        # Always says pricing (2 FP for noise/minor, 1 TP for pricing)
        return {"verdict": "pricing"}

    result = evaluate(cases, fake_classifier)

    assert result["false_positive_rate"] == 1.0  # 2/2 non-protected mislabeled


def test_evaluate_gate_passed_at_threshold():
    """Gate should pass exactly at recall ≥ 0.90 per class and FP < 0.10."""
    # 10 pricing, 10 breaking, 10 noise
    cases = [{"label": "pricing", "diff": f"p{i}"} for i in range(10)]
    cases += [{"label": "breaking", "diff": f"b{i}"} for i in range(10)]
    cases += [{"label": "noise", "diff": f"n{i}"} for i in range(10)]

    def classifier_90_recall_0_fp(case: dict) -> dict:
        # 9/10 pricing correct, 0 FP
        if case["label"] == "pricing" and case["diff"] != "p9":
            return {"verdict": "pricing"}
        if case["label"] == "pricing" and case["diff"] == "p9":
            return {"verdict": "noise"}  # 1 FN
        return {"verdict": case["label"]}

    result = evaluate(cases, classifier_90_recall_0_fp)
    assert result["recall_pricing"] == 0.9
    assert result["recall_breaking"] == 1.0
    assert result["false_positive_rate"] == 0.0
    assert result["gate_passed"] is True


def test_evaluate_gate_fails_below_threshold():
    """Gate should fail if recall < 0.90 or FP ≥ 0.10."""
    cases = [{"label": "pricing", "diff": f"p{i}"} for i in range(10)]
    cases += [{"label": "noise", "diff": f"n{i}"} for i in range(10)]

    def classifier_89_recall(case: dict) -> dict:
        # Only 8.9/10 = 89% recall
        if case["label"] == "pricing" and case["diff"] not in ["p9", "p8"]:
            return {"verdict": "pricing"}
        if case["label"] == "pricing" and case["diff"] == "p8":
            return {"verdict": "pricing"}  # 9/10 = 0.9 but we want to test < 0.9
        return {"verdict": "noise"}

    # Actually let's make it fail clearly
    def classifier_80_recall(case: dict) -> dict:
        # 8/10 pricing correct
        if case["label"] == "pricing" and int(case["diff"][1:]) < 8:
            return {"verdict": "pricing"}
        return {"verdict": "noise"}

    result = evaluate(cases, classifier_80_recall)
    assert result["protected_recall"] == 0.8
    assert result["gate_passed"] is False


def test_conservative_verdict_forces_needs_review_when_gate_fails():
    """conservative_verdict should force needs_review if gate_passed is False."""
    verdict = {"verdict": "pricing", "score": 8, "summary": "test"}
    metrics = {"gate_passed": False}

    result = conservative_verdict(verdict, metrics)

    assert result["verdict"] == "needs_review"
    assert result["review_status"] == "evaluation_gate_failed"


def test_conservative_verdict_allows_when_gate_passes():
    """conservative_verdict should pass through verdict if gate_passed is True."""
    verdict = {"verdict": "pricing", "score": 8, "summary": "test"}
    metrics = {"gate_passed": True}

    result = conservative_verdict(verdict, metrics)

    assert result == verdict


def test_load_cases_reads_real_jsonl():
    """load_cases should read the real classifier_cases.v1.jsonl with valid structure."""
    cases = load_cases("eval/classifier_cases.v1.jsonl")

    assert len(cases) >= 50
    for case in cases:
        assert "id" in case
        assert "label" in case
        assert case["label"] in ("pricing", "breaking", "noise", "minor", "needs_review")
        assert "diff" in case
        assert "prediction" in case


def test_evaluate_on_real_predictions_gives_coherent_metrics():
    """evaluate using PRECALCULATED predictions from jsonl (fixture check only)."""
    cases = load_cases("eval/classifier_cases.v1.jsonl")

    def use_stored_prediction(case: dict) -> dict:
        return case["prediction"]

    result = evaluate(cases, use_stored_prediction)

    assert result["cases"] == len(cases)
    assert 0.0 <= result["protected_recall"] <= 1.0
    assert 0.0 <= result["false_positive_rate"] <= 1.0
    # Predictions are deterministic and tuned, should be high quality
    assert result["protected_recall"] >= 0.90  # per-class threshold


def test_evaluate_real_classifier_calls_classify_function():
    """evaluate_real should call the classifier on fresh diffs, not cached predictions."""
    cases = [
        {"id": "t1", "label": "pricing", "diff": "price is $10"},
        {"id": "t2", "label": "noise", "diff": "typo fix"},
    ]

    calls_made = []

    def tracking_classifier(diff_text, source_meta, **kwargs):
        calls_made.append(diff_text)
        if "$10" in diff_text:
            return {"verdict": "pricing", "score": 8, "summary": "test", "evidence": "$10"}
        return {"verdict": "noise", "score": 1, "summary": "test", "evidence": "typo"}

    from vigia.eval import evaluate_real

    result = evaluate_real(cases, tracking_classifier)

    # The classifier should be called with diff_text from each case
    assert len(calls_made) == 2
    assert any("$10" in call for call in calls_made)
    assert result["recall_pricing"] == 1.0  # pricing case classified correctly


def test_evaluate_per_class_recall_not_compensated():
    """Recall must be ≥90% PER CLASS (pricing AND breaking), not aggregated."""
    # 10 pricing (100% recall), 10 breaking (50% recall) → gate FAILS
    cases = [{"label": "pricing", "diff": f"p{i}"} for i in range(10)]
    cases += [{"label": "breaking", "diff": f"b{i}"} for i in range(10)]

    def classifier_perfect_pricing_bad_breaking(case: dict) -> dict:
        if case["label"] == "pricing":
            return {"verdict": "pricing"}  # 10/10 pricing
        if case["label"] == "breaking" and int(case["diff"][1:]) < 5:
            return {"verdict": "breaking"}  # only 5/10 breaking
        return {"verdict": "noise"}

    result = evaluate(cases, classifier_perfect_pricing_bad_breaking)

    # Aggregate recall would be 15/20 = 75%, but per-class should fail
    assert result["recall_pricing"] == 1.0
    assert result["recall_breaking"] == 0.5
    assert result["gate_passed"] is False  # breaking recall < 0.90


def test_evaluate_real_includes_metadata():
    """evaluate_real should include model, prompt_version, dataset in metrics."""
    cases = [{"id": "t1", "label": "pricing", "diff": "price $10"}]

    def fake_classifier(diff_text, source_meta, **kwargs):
        return {"verdict": "pricing", "score": 8, "summary": "test", "evidence": "$10"}

    from vigia.eval import evaluate_real

    result = evaluate_real(
        cases,
        fake_classifier,
        model="qwen3.5:9b",
        prompt_version="classifier-v2",
        dataset="test-dataset.jsonl"
    )

    assert result["model"] == "qwen3.5:9b"
    assert result["prompt_version"] == "classifier-v2"
    assert result["dataset"] == "test-dataset.jsonl"


def test_evaluate_dataset_threshold_per_class():
    """Dataset evaluation should check ≥90% recall PER CLASS (pricing AND breaking)."""
    cases = load_cases("eval/classifier_cases.v1.jsonl")

    def use_stored_prediction(case: dict) -> dict:
        return case["prediction"]

    result = evaluate(cases, use_stored_prediction)

    # Per-class thresholds
    assert result["recall_pricing"] >= 0.90
    assert result["recall_breaking"] >= 0.90
    assert result["false_positive_rate"] < 0.10


def test_evaluate_gate_fails_when_protected_class_missing():
    """Una clase protegida sin casos en el dataset → gate FAILED (nunca aprobada por defecto)."""
    cases = [{"label": "pricing", "diff": f"p{i}"} for i in range(10)]
    cases += [{"label": "noise", "diff": f"n{i}"} for i in range(10)]

    result = evaluate(cases, lambda case: {"verdict": case["label"]})

    assert result["recall_pricing"] == 1.0
    assert result["gate_passed"] is False

    from vigia.eval import evaluate_real
    real = evaluate_real(cases, lambda diff, meta: {"verdict": "pricing" if diff.startswith("p") else "noise"})
    assert real["gate_passed"] is False


def test_cli_eval_always_writes_gate_state(tmp_path, monkeypatch):
    """`vigia eval` sin --model escribe eval/gate_state.json con model=None."""
    import json
    import sys
    import pytest
    from vigia.cli import main

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(json.dumps({"id": "c1", "label": "pricing", "diff": "p", "prediction": {"verdict": "pricing"}}) + "\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["vigia", "eval", "--dataset", str(dataset)])

    with pytest.raises(SystemExit):  # sin breaking → gate falla → exit 1
        main()

    state = json.loads((tmp_path / "eval" / "gate_state.json").read_text())
    assert state["model"] is None
    assert state["gate_passed"] is False
    assert state["dataset"] == str(dataset)
