from datetime import datetime, timezone
import sqlite3

import httpx

from vigia.db import init_db
from vigia.digest import build_digest, record_delivery, send_digest


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO providers (slug, name) VALUES ('acme', 'Acme')")
    conn.execute("INSERT INTO sources (provider_id, kind, url) VALUES (1, 'rss', 'https://acme.test/feed')")
    for i, (verdict, summary) in enumerate((("pricing", "price"), ("noise", "noise"), ("needs_review", "review"))):
        conn.execute(
            "INSERT INTO changes (source_id, detected_at, verdict, summary, diff_text, source_url) VALUES (1, '2026-09-26T00:00:00+00:00', ?, ?, ?, ?)",
            (verdict, summary, f"diff-{i}", f"https://acme.test/change/{i}"),
        )
    conn.commit()
    return conn


def test_build_digest_filters_and_groups():
    text = build_digest(_db(), datetime(2026, 9, 25, tzinfo=timezone.utc))
    assert "Acme" in text and "💰 price" in text
    assert "noise" not in text and "review" not in text


def test_send_and_record_delivery(monkeypatch):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    monkeypatch.setenv("VIGIA_TG_TOKEN", "token")
    original_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(transport=transport, **kwargs))
    assert send_digest("hello", "token", "chat") is True
    conn = _db()
    record_delivery(conn, "hello", datetime(2026, 9, 26, tzinfo=timezone.utc), datetime(2026, 9, 27, tzinfo=timezone.utc))
    assert conn.execute("SELECT COUNT(*) FROM digests").fetchone()[0] == 1


def test_send_failure_does_not_raise(monkeypatch):
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    original_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(transport=transport, **kwargs))
    assert send_digest("hello", "token", "chat") is False


def test_send_without_token_is_false(monkeypatch):
    monkeypatch.delenv("VIGIA_TG_TOKEN", raising=False)
    assert send_digest("hello", "", "chat") is False
