"""Run cycle: fetch sources, classify diffs, insert changes."""

from __future__ import annotations

import fcntl
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Callable

import httpx

from vigia.fetch import fetch_source
from vigia.difftext import extract_diff
from vigia.classify import classify, PROMPT_VERSION, DEFAULT_MODEL, PROTECTED


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _apply_gate(verdict_dict: dict, gate: bool | None) -> dict:
    """Apply publication gate to verdict.

    gate=None: pricing/breaking → needs_review with review_status="evaluation_gate_not_passed"
    gate=True: pass through
    gate=False: pricing/breaking → needs_review with review_status="evaluation_gate_failed"
    """
    if gate is True:
        return verdict_dict

    verdict = verdict_dict.get("verdict")
    if verdict in PROTECTED:
        status = "evaluation_gate_failed" if gate is False else "evaluation_gate_not_passed"
        return {
            **verdict_dict,
            "verdict": "needs_review",
            "review_status": status
        }

    return verdict_dict


def run_all(
    conn: sqlite3.Connection,
    client: httpx.Client | None,
    classifier: Callable | None = None,
    limit: int | None = None,
    gate: bool | None = None,
) -> dict:
    """Fetch all enabled sources, classify diffs, insert changes.

    Args:
        conn: Database connection
        client: HTTP client (or None to create one)
        classifier: Callable(diff_text, source_meta, **kwargs) -> dict, or None for needs_review
        limit: Max sources to process (None = all)
        gate: Publication gate. None=fail-closed (protected→needs_review with review_status),
              True=publish, False=fail with review_status="evaluation_gate_failed"

    Returns:
        dict with keys: sources_processed, changes_created, errors (list)
    """
    # Lock to prevent concurrent executions
    lockfile_path = Path("/tmp/vigia-run.lock")
    lockfile = lockfile_path.open("w")
    try:
        fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lockfile.close()
        raise RuntimeError("Another run is already in progress (lock held)")

    try:
        if client is None:
            client = httpx.Client(timeout=30.0)
            own_client = True
        else:
            own_client = False

        try:
            sources = conn.execute(
                "SELECT * FROM sources WHERE enabled = 1 ORDER BY id LIMIT ?",
                (limit,) if limit else (-1,)
            ).fetchall()

            sources_processed = 0
            changes_created = 0
            errors = []

            for source in sources:
                source_id = source["id"]
                try:
                    result = fetch_source(conn, source, client, commit=False)

                    if result.get("error"):
                        # Error ya fue commiteado por _failure
                        errors.append({"source_id": source_id, "error": result["error"]})
                        continue

                    if not result.get("changed"):
                        # 304 o sin cambios, ya commiteado
                        sources_processed += 1
                        continue

                    # Process edits (RSS)
                    for edit in result.get("edits", []):
                        old_content = edit["old_content"]
                        new_content = edit["new_content"]
                        url = edit["url"]

                        diff_dict = extract_diff(old_content, new_content)
                        diff_text = f"REMOVED:\n{diff_dict['before']}\n\nADDED:\n{diff_dict['after']}"

                        if classifier is None:
                            verdict_dict = {
                                "verdict": "needs_review",
                                "score": 0,
                                "summary": "no_classifier",
                                "evidence": ""
                            }
                        else:
                            source_meta = {
                                "source_id": source_id,
                                "url": source["url"],
                                "provider_id": source["provider_id"]
                            }
                            verdict_dict = classifier(diff_text, source_meta)
                            verdict_dict = _apply_gate(verdict_dict, gate)

                        conn.execute(
                            """INSERT OR IGNORE INTO changes (
                                source_id, detected_at, verdict, score, summary, evidence,
                                diff_text, old_excerpt, new_excerpt, source_url, model, prompt_version, review_status
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                source_id,
                                _now(),
                                verdict_dict["verdict"],
                                verdict_dict.get("score", 0),
                                verdict_dict.get("summary", ""),
                                verdict_dict.get("evidence", ""),
                                diff_text,
                                diff_dict["before"],
                                diff_dict["after"],
                                url,
                                DEFAULT_MODEL if classifier else None,
                                PROMPT_VERSION if classifier else None,
                                verdict_dict.get("review_status"),
                            )
                        )
                        changes_created += 1

                    # Process new entries (RSS post-baseline)
                    for new_entry in result.get("new", []):
                        content = new_entry["content"]
                        url = new_entry["url"]
                        diff_text = f"ADDED:\n{content}"

                        if classifier is None:
                            verdict_dict = {
                                "verdict": "needs_review",
                                "score": 0,
                                "summary": "no_classifier",
                                "evidence": ""
                            }
                        else:
                            source_meta = {
                                "source_id": source_id,
                                "url": source["url"],
                                "provider_id": source["provider_id"]
                            }
                            verdict_dict = classifier(diff_text, source_meta)
                            verdict_dict = _apply_gate(verdict_dict, gate)

                        conn.execute(
                            """INSERT OR IGNORE INTO changes (
                                source_id, detected_at, verdict, score, summary, evidence,
                                diff_text, old_excerpt, new_excerpt, source_url, model, prompt_version, review_status
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                source_id,
                                _now(),
                                verdict_dict["verdict"],
                                verdict_dict.get("score", 0),
                                verdict_dict.get("summary", ""),
                                verdict_dict.get("evidence", ""),
                                diff_text,
                                "",  # new entries don't have old_excerpt
                                content,
                                url,
                                DEFAULT_MODEL if classifier else None,
                                PROMPT_VERSION if classifier else None,
                                verdict_dict.get("review_status"),
                            )
                        )
                        changes_created += 1

                    # Commit atómico: fetch + changes de esta fuente
                    conn.commit()
                    sources_processed += 1

                except Exception as exc:
                    conn.rollback()
                    errors.append({"source_id": source_id, "error": str(exc)})

            return {
                "sources_processed": sources_processed,
                "changes_created": changes_created,
                "errors": errors
            }
        finally:
            if own_client and client is not None:
                client.close()
    finally:
        fcntl.flock(lockfile.fileno(), fcntl.LOCK_UN)
        lockfile.close()
