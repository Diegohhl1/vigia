"""CLI entry point for vigia."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from vigia.db import get_conn
from vigia.run import run_all
from vigia.classify import classify
from vigia.eval import load_cases, evaluate_real


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(prog="vigia", description="Vigía - SaaS pricing/breaking change monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # vigia run
    run_parser = subparsers.add_parser("run", help="Run fetch cycle")
    run_parser.add_argument("--limit", type=int, default=None, help="Max sources to process (0 = none)")
    run_parser.add_argument("--db", default="vigia.sqlite3", help="Database path")
    run_parser.add_argument("--gate", choices=["auto", "on", "off"], default="auto", help="Publication gate")

    # vigia eval
    eval_parser = subparsers.add_parser("eval", help="Evaluate classifier")
    eval_parser.add_argument("--dataset", default="eval/classifier_cases.v1.jsonl", help="Dataset path")
    eval_parser.add_argument("--model", help="Model name to use for evaluation")
    eval_parser.add_argument("--url", help="Ollama URL (default: http://127.0.0.1:11434)")

    # vigia smoke
    smoke_parser = subparsers.add_parser("smoke", help="Smoke test (run with limit)")
    smoke_parser.add_argument("--limit", type=int, default=2, help="Max sources to process")
    smoke_parser.add_argument("--db", default="vigia.sqlite3", help="Database path")

    args = parser.parse_args()

    if args.command == "run":
        # Resolve gate flag
        gate = None
        if args.gate == "on":
            gate = True
        elif args.gate == "off":
            gate = False
        elif args.gate == "auto":
            gate_file = Path("eval/gate_state.json")
            if gate_file.exists():
                gate_data = json.loads(gate_file.read_text())
                gate = gate_data.get("gate_passed", False)
            else:
                gate = None  # fail-closed

        conn = get_conn(args.db)
        client = httpx.Client(timeout=30.0)
        try:
            report = run_all(conn, client, classifier=classify, limit=args.limit, gate=gate)
            print(f"Sources processed: {report['sources_processed']}")
            print(f"Changes created: {report['changes_created']}")
            if report['errors']:
                print(f"Errors: {len(report['errors'])}")
                for error in report['errors']:
                    print(f"  - Source {error['source_id']}: {error['error']}")
                sys.exit(1)
        except RuntimeError as exc:
            if "lock" in str(exc).lower():
                print("another run in progress", file=sys.stderr)
                sys.exit(1)
            raise
        finally:
            client.close()
            conn.close()

    elif args.command == "eval":
        from datetime import datetime, timezone
        from vigia.eval import evaluate

        cases = load_cases(args.dataset)

        if args.model:
            # Real evaluation with fresh classifier calls
            def classifier_wrapper(diff_text, source_meta, **kwargs):
                kwargs_merged = {"ollama_url": args.url} if args.url else {}
                kwargs_merged["model"] = args.model
                return classify(diff_text, source_meta, **kwargs_merged)

            metrics = evaluate_real(cases, classifier_wrapper, model=args.model, dataset=args.dataset)
        else:
            # Use precalculated predictions
            metrics = evaluate(cases, lambda case: case["prediction"])

        # Save gate state (siempre; model=None si se usaron predicciones precalculadas)
        gate_file = Path("eval/gate_state.json")
        gate_file.parent.mkdir(exist_ok=True)
        gate_state = {
            "gate_passed": metrics["gate_passed"],
            "protected_recall": metrics["protected_recall"],
            "recall_pricing": metrics["recall_pricing"],
            "recall_breaking": metrics["recall_breaking"],
            "false_positive_rate": metrics["false_positive_rate"],
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "model": args.model,
            "dataset": args.dataset,
        }
        gate_file.write_text(json.dumps(gate_state, indent=2))

        print(f"Cases: {metrics['cases']}")
        print(f"Protected cases: {metrics['protected_cases']}")
        print(f"Protected recall: {metrics['protected_recall']:.2%}")
        print(f"Recall (pricing): {metrics['recall_pricing']:.2%}")
        print(f"Recall (breaking): {metrics['recall_breaking']:.2%}")
        print(f"False positive rate: {metrics['false_positive_rate']:.2%}")
        print(f"Gate passed: {metrics['gate_passed']}")

        if not metrics['gate_passed']:
            sys.exit(1)

    elif args.command == "smoke":
        import time
        conn = get_conn(args.db)
        client = httpx.Client(timeout=30.0)
        start = time.time()
        try:
            report = run_all(conn, client, classifier=classify, limit=args.limit)
            duration = time.time() - start
            print(f"Sources processed: {report['sources_processed']}")
            print(f"Changes created: {report['changes_created']}")
            print(f"Errors: {len(report['errors'])}")
            if report['errors']:
                for error in report['errors']:
                    print(f"  - Source {error['source_id']}: {error['error']}")
            print(f"Duration: {duration:.2f}s")
            if report['errors']:
                sys.exit(1)
        finally:
            client.close()
            conn.close()


if __name__ == "__main__":
    main()
