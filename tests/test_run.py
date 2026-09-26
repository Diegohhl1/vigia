"""Tests for run.py with mocked fetch and classifiers."""

from __future__ import annotations

import sqlite3
import httpx

from vigia.db import get_conn
from vigia.run import run_all


def test_run_two_sources_one_changes():
    """Two sources, one changes → exactly 1 change row with verdict from fake classifier."""
    conn = get_conn(":memory:")

    # Setup: 2 providers, 2 sources (both RSS, enabled), baseline already exists
    conn.execute("INSERT INTO providers (slug, name) VALUES ('aws', 'AWS')")
    conn.execute("INSERT INTO providers (slug, name) VALUES ('gcp', 'GCP')")
    conn.execute(
        "INSERT INTO sources (provider_id, kind, url, enabled, last_success_at) VALUES (1, 'rss', 'http://aws/feed', 1, '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO sources (provider_id, kind, url, enabled, last_success_at) VALUES (2, 'rss', 'http://gcp/feed', 1, '2026-01-01T00:00:00Z')"
    )
    # Baseline entries so fetch recognizes it's not first ingestion
    conn.execute(
        "INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content) VALUES (1, 'e1', 'http://aws/e1', '2026-01-01T00:00:00Z', 'hash1', 'old content')"
    )
    conn.execute(
        "INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content) VALUES (2, 'e2', 'http://gcp/e2', '2026-01-01T00:00:00Z', 'hash2', 'stable content')"
    )
    conn.commit()

    # Mock fetch: AWS source has 1 edit, GCP source has no changes
    original_fetch = None
    try:
        from vigia import run as run_module
        original_fetch = run_module.fetch_source

        def mock_fetch(conn_inner, source_row, client, commit=True):
            if source_row["url"] == "http://aws/feed":
                # Edit to existing entry
                return {
                    "changed": True,
                    "new_entries": 0,
                    "edits": [{
                        "external_id": "e1",
                        "url": "http://aws/e1",
                        "old_content": "old content",
                        "new_content": "new content with price $10"
                    }],
                    "error": None
                }
            else:
                return {"changed": False, "new_entries": 0, "edits": [], "error": None}

        run_module.fetch_source = mock_fetch

        # Fake classifier returns pricing verdict
        def fake_classifier(diff_text, source_meta, **kwargs):
            return {"verdict": "pricing", "score": 7, "summary": "price change", "evidence": "$10"}

        # Mock httpx.Client to avoid real network
        original_client = httpx.Client
        httpx.Client = lambda **kwargs: None

        try:
            report = run_all(conn, None, classifier=fake_classifier, gate=True)
        finally:
            httpx.Client = original_client

    finally:
        if original_fetch:
            run_module.fetch_source = original_fetch

    # Verify: exactly 1 change row with pricing verdict
    changes = conn.execute("SELECT * FROM changes").fetchall()
    assert len(changes) == 1
    assert changes[0]["verdict"] == "pricing"
    assert changes[0]["source_id"] == 1
    assert "$10" in changes[0]["diff_text"]


def test_run_second_execution_no_new_changes():
    """Second run with no source changes → 0 new change rows."""
    conn = get_conn(":memory:")

    conn.execute("INSERT INTO providers (slug, name) VALUES ('aws', 'AWS')")
    conn.execute(
        "INSERT INTO sources (provider_id, kind, url, enabled, last_success_at) VALUES (1, 'rss', 'http://aws/feed', 1, '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content) VALUES (1, 'e1', 'http://aws/e1', '2026-01-01T00:00:00Z', 'hash1', 'content')"
    )
    conn.commit()

    original_fetch = None
    try:
        from vigia import run as run_module
        original_fetch = run_module.fetch_source

        def mock_fetch(conn_inner, source_row, client, commit=True):
            return {"changed": False, "new_entries": 0, "edits": [], "error": None}

        run_module.fetch_source = mock_fetch

        original_client = httpx.Client
        httpx.Client = lambda **kwargs: None

        try:
            run_all(conn, None)
            run_all(conn, None)
        finally:
            httpx.Client = original_client
    finally:
        if original_fetch:
            run_module.fetch_source = original_fetch

    changes = conn.execute("SELECT * FROM changes").fetchall()
    assert len(changes) == 0


def test_run_baseline_first_ingestion_no_changes():
    """First ingestion (baseline) → 0 change rows even with new entries."""
    conn = get_conn(":memory:")

    conn.execute("INSERT INTO providers (slug, name) VALUES ('aws', 'AWS')")
    conn.execute(
        "INSERT INTO sources (provider_id, kind, url, enabled) VALUES (1, 'rss', 'http://aws/feed', 1)"
    )
    conn.commit()

    original_fetch = None
    try:
        from vigia import run as run_module
        original_fetch = run_module.fetch_source

        def mock_fetch(conn_inner, source_row, client, commit=True):
            # Simulates first ingestion: new_entries but changed=False (baseline)
            return {"changed": False, "new_entries": 5, "edits": [], "error": None}

        run_module.fetch_source = mock_fetch

        original_client = httpx.Client
        httpx.Client = lambda **kwargs: None

        try:
            run_all(conn, None)
        finally:
            httpx.Client = original_client
    finally:
        if original_fetch:
            run_module.fetch_source = original_fetch

    changes = conn.execute("SELECT * FROM changes").fetchall()
    assert len(changes) == 0


def test_run_rss_edit_creates_change_with_diff():
    """RSS edit → change row with diff in diff_text."""
    conn = get_conn(":memory:")

    conn.execute("INSERT INTO providers (slug, name) VALUES ('aws', 'AWS')")
    conn.execute(
        "INSERT INTO sources (provider_id, kind, url, enabled, last_success_at) VALUES (1, 'rss', 'http://aws/feed', 1, '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content) VALUES (1, 'e1', 'http://aws/e1', '2026-01-01T00:00:00Z', 'hash1', 'old text')"
    )
    conn.commit()

    original_fetch = None
    try:
        from vigia import run as run_module
        original_fetch = run_module.fetch_source

        def mock_fetch(conn_inner, source_row, client, commit=True):
            return {
                "changed": True,
                "new_entries": 0,
                "edits": [{
                    "external_id": "e1",
                    "url": "http://aws/e1",
                    "old_content": "old text",
                    "new_content": "new text"
                }],
                "error": None
            }

        run_module.fetch_source = mock_fetch

        original_client = httpx.Client
        httpx.Client = lambda **kwargs: None

        try:
            run_all(conn, None)
        finally:
            httpx.Client = original_client
    finally:
        if original_fetch:
            run_module.fetch_source = original_fetch

    changes = conn.execute("SELECT * FROM changes").fetchall()
    assert len(changes) == 1
    assert "old text" in changes[0]["diff_text"] or "new text" in changes[0]["diff_text"]


def test_run_error_in_one_source_does_not_abort_others():
    """Error in one source → appears in errors, other sources still processed."""
    conn = get_conn(":memory:")

    conn.execute("INSERT INTO providers (slug, name) VALUES ('aws', 'AWS')")
    conn.execute("INSERT INTO providers (slug, name) VALUES ('gcp', 'GCP')")
    conn.execute(
        "INSERT INTO sources (provider_id, kind, url, enabled, last_success_at) VALUES (1, 'rss', 'http://aws/feed', 1, '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO sources (provider_id, kind, url, enabled, last_success_at) VALUES (2, 'rss', 'http://gcp/feed', 1, '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content) VALUES (1, 'e1', 'http://aws/e1', '2026-01-01T00:00:00Z', 'hash1', 'content')"
    )
    conn.execute(
        "INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content) VALUES (2, 'e2', 'http://gcp/e2', '2026-01-01T00:00:00Z', 'hash2', 'old content')"
    )
    conn.commit()

    original_fetch = None
    try:
        from vigia import run as run_module
        original_fetch = run_module.fetch_source

        def mock_fetch(conn_inner, source_row, client, commit=True):
            if source_row["url"] == "http://aws/feed":
                return {"changed": False, "new_entries": 0, "edits": [], "error": "network_timeout"}
            else:
                # GCP source succeeds with edit
                return {
                    "changed": True,
                    "new_entries": 0,
                    "edits": [{
                        "external_id": "e2",
                        "url": "http://gcp/e2",
                        "old_content": "old content",
                        "new_content": "new content"
                    }],
                    "error": None
                }

        run_module.fetch_source = mock_fetch

        original_client = httpx.Client
        httpx.Client = lambda **kwargs: None

        try:
            report = run_all(conn, None)
        finally:
            httpx.Client = original_client
    finally:
        if original_fetch:
            run_module.fetch_source = original_fetch

    # GCP source should have created a change
    changes = conn.execute("SELECT * FROM changes").fetchall()
    assert len(changes) == 1
    assert changes[0]["source_id"] == 2

    # AWS error should be in report
    assert len(report["errors"]) == 1
    assert "aws" in str(report["errors"][0]).lower() or "1" in str(report["errors"][0])


def test_run_concurrent_lock_fails_cleanly():
    """Second run while first is locked → fails with RuntimeError."""
    import fcntl
    from pathlib import Path
    import pytest

    conn = get_conn(":memory:")

    # Acquire lock manually to simulate concurrent run
    lockfile_path = Path("/tmp/vigia-run.lock")
    lockfile = lockfile_path.open("w")
    fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    try:
        original_client = httpx.Client
        httpx.Client = lambda **kwargs: None

        try:
            with pytest.raises(RuntimeError, match="lock"):
                run_all(conn, None)
        finally:
            httpx.Client = original_client
    finally:
        fcntl.flock(lockfile.fileno(), fcntl.LOCK_UN)
        lockfile.close()


def test_run_no_classifier_uses_needs_review():
    """classifier=None → all changes get needs_review verdict directly."""
    conn = get_conn(":memory:")

    conn.execute("INSERT INTO providers (slug, name) VALUES ('aws', 'AWS')")
    conn.execute(
        "INSERT INTO sources (provider_id, kind, url, enabled, last_success_at) VALUES (1, 'rss', 'http://aws/feed', 1, '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content) VALUES (1, 'e1', 'http://aws/e1', '2026-01-01T00:00:00Z', 'hash1', 'old content')"
    )
    conn.commit()

    original_fetch = None
    try:
        from vigia import run as run_module
        original_fetch = run_module.fetch_source

        def mock_fetch(conn_inner, source_row, client, commit=True):
            return {
                "changed": True,
                "new_entries": 0,
                "edits": [{
                    "external_id": "e1",
                    "url": "http://aws/e1",
                    "old_content": "old content",
                    "new_content": "new content"
                }],
                "error": None
            }

        run_module.fetch_source = mock_fetch

        original_client = httpx.Client
        httpx.Client = lambda **kwargs: None

        try:
            run_all(conn, None, classifier=None)
        finally:
            httpx.Client = original_client
    finally:
        if original_fetch:
            run_module.fetch_source = original_fetch

    changes = conn.execute("SELECT * FROM changes").fetchall()
    assert len(changes) == 1
    assert changes[0]["verdict"] == "needs_review"


def test_run_rss_new_entry_after_baseline_creates_change():
    """New RSS entry after baseline → should create a change row."""
    conn = get_conn(":memory:")

    conn.execute("INSERT INTO providers (slug, name) VALUES ('aws', 'AWS')")
    conn.execute(
        "INSERT INTO sources (provider_id, kind, url, enabled, last_success_at) VALUES (1, 'rss', 'http://aws/feed', 1, '2026-01-01T00:00:00Z')"
    )
    # Baseline entry exists
    conn.execute(
        "INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content) VALUES (1, 'e1', 'http://aws/e1', '2026-01-01T00:00:00Z', 'hash1', 'old content')"
    )
    conn.commit()

    original_fetch = None
    try:
        from vigia import run as run_module
        original_fetch = run_module.fetch_source

        def mock_fetch(conn_inner, source_row, client, commit=True):
            # Simulates new entry post-baseline
            return {
                "changed": True,
                "new_entries": 1,
                "edits": [],
                "new": [{
                    "external_id": "e2",
                    "url": "http://aws/e2",
                    "content": "New pricing: $20/month"
                }],
                "error": None
            }

        run_module.fetch_source = mock_fetch

        original_client = httpx.Client
        httpx.Client = lambda **kwargs: None

        try:
            report = run_all(conn, None)
        finally:
            httpx.Client = original_client
    finally:
        if original_fetch:
            run_module.fetch_source = original_fetch

    # Should create 1 change from the new entry
    changes = conn.execute("SELECT * FROM changes").fetchall()
    assert len(changes) == 1
    assert "New pricing" in changes[0]["diff_text"]


def test_run_idempotent_same_diff_creates_single_change():
    """Processing same source with same diff twice → only 1 change row (ON CONFLICT IGNORE)."""
    from pathlib import Path
    conn = get_conn(":memory:")

    conn.execute("INSERT INTO providers (slug, name) VALUES ('aws', 'AWS')")
    conn.execute(
        "INSERT INTO sources (id, provider_id, kind, url, enabled, last_success_at) VALUES (1, 1, 'rss', 'http://aws/feed', 1, '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content) VALUES (1, 'e1', 'http://aws/e1', '2026-01-01', 'hash1', 'old')"
    )
    conn.commit()

    # Mock feed with edit
    feed_xml = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel>
        <item><guid>e1</guid><link>http://aws/e1</link><title>new</title></item>
    </channel></rss>"""

    def handler(request):
        return httpx.Response(200, content=feed_xml, headers={"Content-Type": "application/rss+xml"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    # First run
    from vigia.fetch import fetch_source
    from vigia.classify import classify

    original_robots = None
    try:
        import vigia.fetch as fetch_module
        original_robots = fetch_module._robots_allowed
        fetch_module._robots_allowed = lambda url, client=None: (True, "")

        report = run_all(conn, client, classifier=classify, gate=True)
        assert report["changes_created"] == 1

        # Second run with same feed → 0 new changes (idempotence)
        report2 = run_all(conn, client, classifier=classify, gate=True)
        assert report2["changes_created"] == 0

        changes = conn.execute("SELECT * FROM changes").fetchall()
        assert len(changes) == 1
    finally:
        if original_robots:
            fetch_module._robots_allowed = original_robots
        client.close()


# --- Cierre bloque 3: atomicidad, idempotencia, limit, lock ---

import pytest

import vigia.fetch as fetch_module
from vigia import run as run_module
from vigia.fetch import fetch_source


def _source(conn, baseline=True):
    conn.execute("INSERT INTO providers (slug, name) VALUES ('aws', 'AWS')")
    conn.execute(
        "INSERT INTO sources (id, provider_id, kind, url, enabled, last_success_at) VALUES (1, 1, 'rss', 'http://aws/feed', 1, ?)",
        ("2026-01-01T00:00:00Z" if baseline else None,),
    )
    if baseline:
        conn.execute(
            "INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content) VALUES (1, 'e1', 'http://aws/e1', '2026-01-01', 'hash1', 'old')"
        )
    conn.commit()


def _feed_client(items):
    xml = "<?xml version='1.0'?><rss version='2.0'><channel>" + "".join(
        f"<item><guid>{g}</guid><link>http://aws/{g}</link><title>{t}</title></item>" for g, t in items
    ) + "</channel></rss>"
    return httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=xml.encode(), headers={"Content-Type": "application/rss+xml"})
    ))


def _ok(diff_text, source_meta, **kw):
    return {"verdict": "minor", "score": 2, "summary": "s", "evidence": ""}


def test_run_idempotent_real_conflict_does_not_count_ignored(monkeypatch):
    """changed=True dos veces con mismo external_id y mismo contenido → INSERT OR IGNORE no duplica ni cuenta."""
    conn = get_conn(":memory:")
    _source(conn)
    edit = {"external_id": "e1", "url": "http://aws/e1", "old_content": "old", "new_content": "new"}
    monkeypatch.setattr(run_module, "fetch_source", lambda c, s, cl, commit=True: {
        "changed": True, "new_entries": 0, "edits": [dict(edit)], "new": [], "error": None})

    assert run_all(conn, object(), classifier=_ok, gate=True)["changes_created"] == 1
    assert run_all(conn, object(), classifier=_ok, gate=True)["changes_created"] == 0
    assert conn.execute("SELECT COUNT(*) FROM changes").fetchone()[0] == 1


def test_run_limit_zero_processes_no_sources(monkeypatch):
    """--limit 0 → 0 fuentes (no todas)."""
    conn = get_conn(":memory:")
    _source(conn)
    calls = []
    monkeypatch.setattr(run_module, "fetch_source", lambda *a, **kw: calls.append(1))

    report = run_all(conn, object(), limit=0)

    assert calls == []
    assert report["sources_processed"] == 0


def test_run_classifier_exception_rolls_back_entries_and_next_run_recovers(monkeypatch):
    """Classifier que lanza tras fetch → entries nuevas no quedan; la siguiente pasada las procesa."""
    monkeypatch.setattr(fetch_module, "_robots_allowed", lambda url, client=None: (True, "2026-09-26T00:00:00Z"))
    conn = get_conn(":memory:")
    _source(conn)
    client = _feed_client([("e1", "old"), ("e2", "brand new entry")])

    def boom(diff_text, source_meta, **kw):
        raise RuntimeError("ollama down")

    report = run_all(conn, client, classifier=boom, gate=True)
    assert len(report["errors"]) == 1
    assert conn.execute("SELECT COUNT(*) FROM entries WHERE external_id = 'e2'").fetchone()[0] == 0
    assert conn.execute("SELECT robots_checked_at FROM sources WHERE id = 1").fetchone()[0] is None

    report = run_all(conn, client, classifier=_ok, gate=True)
    assert report["errors"] == []
    assert report["changes_created"] >= 1
    assert conn.execute("SELECT COUNT(*) FROM changes WHERE source_url = 'http://aws/e2'").fetchone()[0] == 1


def test_run_200_without_changes_persists_last_checked(monkeypatch):
    """200 sin cambios (baseline) vía run_all → last_checked_at/last_success_at confirmados."""
    monkeypatch.setattr(fetch_module, "_robots_allowed", lambda url, client=None: (True, ""))
    conn = get_conn(":memory:")
    _source(conn, baseline=False)

    report = run_all(conn, _feed_client([("e1", "hello")]), classifier=_ok)
    conn.rollback()  # si run_all dejó la transacción abierta, se pierde aquí

    row = conn.execute("SELECT last_checked_at, last_success_at FROM sources WHERE id = 1").fetchone()
    assert report["sources_processed"] == 1
    assert row["last_checked_at"] is not None
    assert row["last_success_at"] is not None


def test_fetch_robots_timestamp_obeys_commit_flag(monkeypatch):
    """Con commit=False el update de robots queda en la transacción abierta (rollback lo revierte)."""
    monkeypatch.setattr(fetch_module, "_robots_allowed", lambda url, client=None: (True, "2026-09-26T00:00:00Z"))
    conn = get_conn(":memory:")
    _source(conn)
    source = conn.execute("SELECT * FROM sources WHERE id = 1").fetchone()

    fetch_source(conn, source, _feed_client([("e1", "old")]), commit=False)
    conn.rollback()

    assert conn.execute("SELECT robots_checked_at FROM sources WHERE id = 1").fetchone()[0] is None


def test_run_lock_released_after_exception():
    """Un run_all que lanza no deja el lock tomado."""
    broken = get_conn(":memory:")
    broken.close()
    with pytest.raises(sqlite3.ProgrammingError):
        run_all(broken, object())

    conn = get_conn(":memory:")
    assert run_all(conn, object())["sources_processed"] == 0
