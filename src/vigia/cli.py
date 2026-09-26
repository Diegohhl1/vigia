"""CLI entry point for vigia."""

from __future__ import annotations

import argparse
import sys

import httpx

from vigia.db import get_conn
from vigia.run import run_all
from vigia.classify import classify
from vigia.eval import load_cases, evaluate


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(prog="vigia", description="Vigía - SaaS pricing/breaking change monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # vigia run
    run_parser = subparsers.add_parser("run", help="Run fetch cycle")
    run_parser.add_argument("--limit", type=int, help="Max sources to process")
    run_parser.add_argument("--db", default="vigia.sqlite3", help="Database path")

    # vigia eval
    eval_parser = subparsers.add_parser("eval", help="Evaluate classifier")

    args = parser.parse_args()

    if args.command == "run":
        conn = get_conn(args.db)
        client = httpx.Client(timeout=30.0)
        try:
            report = run_all(conn, client, classifier=classify, limit=args.limit)
            print(f"Sources processed: {report['sources_processed']}")
            print(f"Changes created: {report['changes_created']}")
            if report['errors']:
                print(f"Errors: {len(report['errors'])}")
                for error in report['errors']:
                    print(f"  - Source {error['source_id']}: {error['error']}")
                sys.exit(1)
        finally:
            client.close()
            conn.close()

    elif args.command == "eval":
        cases = load_cases("eval/classifier_cases.v1.jsonl")

        def use_prediction(case):
            return case["prediction"]

        metrics = evaluate(cases, use_prediction)

        print(f"Cases: {metrics['cases']}")
        print(f"Protected cases: {metrics['protected_cases']}")
        print(f"Protected recall: {metrics['protected_recall']:.2%}")
        print(f"False positive rate: {metrics['false_positive_rate']:.2%}")
        print(f"Gate passed: {metrics['gate_passed']}")

        if not metrics['gate_passed']:
            sys.exit(1)


if __name__ == "__main__":
    main()
