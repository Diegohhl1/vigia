"""Proxy que cuenta commits/rollbacks sin tocar sqlite3.Connection."""
import sqlite3

import httpx

import vigia.fetch as fetch_module
from vigia import run as run_module
from vigia.db import get_conn
from vigia.run import run_all


class _CountingConn:
    def __init__(self, inner):
        self._inner = inner
        self.counts = {"commit": 0, "rollback": 0}

    def execute(self, *a, **kw):
        return self._inner.execute(*a, **kw)

    def commit(self):
        self.counts["commit"] += 1
        return self._inner.commit()

    def rollback(self):
        self.counts["rollback"] += 1
        return self._inner.rollback()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _setup_source(conn):
    conn.execute("INSERT INTO providers (slug, name) VALUES ('aws', 'AWS')")
    conn.execute(
        "INSERT INTO sources (id, provider_id, kind, url, enabled, last_success_at) VALUES (1, 1, 'rss', 'http://aws/feed', 1, '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content) VALUES (1, 'e1', 'http://aws/e1', '2026-01-01', 'hash1', 'old')"
    )
    conn.commit()


def test_run_304_commits_once_per_source(monkeypatch):
    """Ruta 304: fetch_source con commit=False NO commitea; run_all hace exactamente 1 commit."""
    monkeypatch.setattr(fetch_module, "_robots_allowed", lambda url, client=None: (True, "cached"))
    conn = get_conn(":memory:")
    _setup_source(conn)
    counting = _CountingConn(conn)

    etag = '"v1"'

    def handler(request):
        if request.headers.get("if-none-match") == etag:
            return httpx.Response(304, request=request)
        xml = "<?xml version='1.0'?><rss version='2.0'><channel></channel></rss>"
        return httpx.Response(200, content=xml.encode(), headers={"Content-Type": "application/rss+xml", "ETag": etag}, request=request)

    client304 = httpx.Client(transport=httpx.MockTransport(handler))
    report = run_all(counting, client304, classifier=lambda d, m, **kw: {"verdict": "minor", "score": 2, "summary": "s", "evidence": ""})

    assert report["sources_processed"] == 1
    assert counting.counts["commit"] == 1, f"esperado 1 commit, hubo {counting.counts['commit']}"
    assert counting.counts["rollback"] == 0


def test_run_changes_created_not_counted_when_rolled_back(monkeypatch):
    """Dos edits y el classifier falla en el segundo → changes_created == 0 (todo revertido)."""
    conn = get_conn(":memory:")
    _setup_source(conn)
    monkeypatch.setattr(run_module, "fetch_source", lambda c, s, cl, commit=True: {
        "changed": True, "new_entries": 0, "new": [],
        "edits": [
            {"external_id": "e1", "url": "http://aws/e1", "old_content": "old", "new_content": "n1"},
            {"external_id": "e2", "url": "http://aws/e2", "old_content": "old2", "new_content": "n2"},
        ], "error": None})

    calls = {"n": 0}

    def flaky(diff_text, source_meta, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom on second")
        return {"verdict": "minor", "score": 2, "summary": "s", "evidence": ""}

    report = run_all(conn, object(), classifier=flaky, gate=True)
    assert report["changes_created"] == 0, "lo revertido no debe contar"
    assert conn.execute("SELECT COUNT(*) FROM changes").fetchone()[0] == 0
