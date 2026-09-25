import sqlite3
from pathlib import Path

import httpx

from vigia.db import init_db
from vigia.fetch import fetch_source


FIXTURE = Path(__file__).parent / "fixtures" / "github.xml"
URL = "https://example.test/feed.xml"


def _db(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.sqlite3")
    init_db(conn)
    conn.row_factory = sqlite3.Row
    conn.execute("INSERT INTO providers (slug, name) VALUES ('test', 'Test')")
    conn.execute("INSERT INTO sources (provider_id, kind, url) VALUES (1, 'rss', ?)", (URL,))
    conn.commit()
    return conn


def _client(payload, status_code=200, headers=None):
    def handler(request):
        return httpx.Response(status_code, content=payload, headers=headers or {}, request=request)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_first_rss_ingestion_is_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url: True)
    conn = _db(tmp_path)
    client = _client(FIXTURE.read_bytes(), headers={"ETag": '"v1"', "Last-Modified": "yesterday"})

    result = fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), client)

    assert result == {"changed": False, "new_entries": 10, "error": None}
    assert conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 10
    source = conn.execute("SELECT * FROM sources").fetchone()
    assert source["etag"] == '"v1"'
    assert source["last_modified"] == "yesterday"


def test_new_entry_and_edited_entry_are_detected(tmp_path, monkeypatch):
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url: True)
    conn = _db(tmp_path)
    original = FIXTURE.read_bytes()
    first = _client(original)
    assert fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), first)["changed"] is False

    extra = original.replace(b"</rss>", b"<item><guid>extra-1</guid><title>Extra entry</title><link>https://example.test/extra</link><description>New item</description></item></rss>")
    assert fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), _client(extra))["new_entries"] == 1

    edited = original.replace(b"GitHub Copilot weekly releases", b"Edited GitHub Copilot weekly releases", 1)
    result = fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), _client(edited))
    assert result["changed"] is True
    assert result["new_entries"] == 0


def test_not_modified_is_clean_and_network_error_is_captured(tmp_path, monkeypatch):
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url: True)
    conn = _db(tmp_path)
    conn.execute("UPDATE sources SET etag = 'v1'")
    conn.commit()
    result = fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), _client(b"", 304))
    assert result == {"changed": False, "new_entries": 0, "error": None}

    def broken(request):
        raise httpx.ConnectError("offline", request=request)
    result = fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), httpx.Client(transport=httpx.MockTransport(broken)))
    assert result["changed"] is False
    assert result["error"] == "offline"
    assert conn.execute("SELECT failure_count FROM sources").fetchone()[0] == 1


def test_html_empty_selector_does_not_create_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url: True)
    conn = _db(tmp_path)
    conn.execute("UPDATE sources SET kind='html', selector='main'")
    conn.commit()
    result = fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), _client(b"<html><body>short</body></html>"))
    assert result["error"] == "selector_empty_or_content_too_short"
    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0
