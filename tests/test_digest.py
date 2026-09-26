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


def test_build_digest_includes_only_needs_review_without_emoji_error():
    conn = _db()
    conn.execute("DELETE FROM changes WHERE verdict != 'needs_review'")
    conn.commit()
    text = build_digest(conn, datetime(2026, 9, 25, tzinfo=timezone.utc))
    assert "Acme" in text and "needs_review review" in text


def test_build_digest_keeps_giant_provider_and_following_provider():
    conn = _db()
    conn.execute("DELETE FROM changes")
    conn.execute("INSERT INTO providers (slug, name) VALUES ('beta', 'Beta')")
    conn.execute("INSERT INTO sources (provider_id, kind, url) VALUES (2, 'rss', 'https://beta.test/feed')")
    giant = "x" * 5000
    conn.execute(
        "INSERT INTO changes (source_id, detected_at, verdict, summary, diff_text) VALUES (1, ?, 'pricing', ?, 'giant')",
        ("2026-09-26T00:00:00+00:00", giant),
    )
    conn.execute(
        "INSERT INTO changes (source_id, detected_at, verdict, summary, diff_text) VALUES (2, ?, 'minor', 'small', 'small')",
        ("2026-09-26T00:00:00+00:00",),
    )
    conn.commit()
    text = build_digest(conn, datetime(2026, 9, 25, tzinfo=timezone.utc))
    assert len(build_digest(conn, datetime(2026, 9, 25, tzinfo=timezone.utc))) > 0
    assert "Beta" in text and "small" in text
    assert len(text.split("\n\n")[0]) <= 4000


def test_record_delivery_default_records_digest():
    conn = _db()
    record_delivery(conn, "hello")
    assert conn.execute("SELECT COUNT(*) FROM digests").fetchone()[0] == 1


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
    conn = _db()
    assert conn.execute("SELECT COUNT(*) FROM digests").fetchone()[0] == 0


def test_send_without_token_is_false(monkeypatch):
    monkeypatch.delenv("VIGIA_TG_TOKEN", raising=False)
    assert send_digest("hello", "", "chat") is False
