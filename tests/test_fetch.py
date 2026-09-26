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
    merged = {"Content-Type": "application/rss+xml"}
    merged.update(headers or {})
    def handler(request):
        return httpx.Response(status_code, content=payload, headers=merged, request=request)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_first_rss_ingestion_is_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url, client=None: (True, ""))
    conn = _db(tmp_path)
    client = _client(FIXTURE.read_bytes(), headers={"ETag": '"v1"', "Last-Modified": "yesterday"})

    result = fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), client)

    assert result == {"changed": False, "new_entries": 10, "edits": [], "new": [], "error": None}
    assert conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 10
    source = conn.execute("SELECT * FROM sources").fetchone()
    assert source["etag"] == '"v1"'
    assert source["last_modified"] == "yesterday"


def test_new_entry_and_edited_entry_are_detected(tmp_path, monkeypatch):
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url, client=None: (True, ""))
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
    assert result["edits"][0]["old_content"] != result["edits"][0]["new_content"]


def test_not_modified_is_clean_and_network_error_is_captured(tmp_path, monkeypatch):
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url, client=None: (True, ""))
    conn = _db(tmp_path)
    conn.execute("UPDATE sources SET etag = 'v1', last_success_at = 'baseline'")
    conn.execute("INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content) VALUES (1, 'old', ?, 'now', 'hash', 'old')", (URL,))
    conn.commit()
    result = fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), _client(b"", 304))
    assert result == {"changed": False, "new_entries": 0, "edits": [], "error": None}

    def broken(request):
        raise httpx.ConnectError("offline", request=request)
    result = fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), httpx.Client(transport=httpx.MockTransport(broken)))
    assert result["changed"] is False
    assert result["error"] == "offline"
    assert conn.execute("SELECT failure_count FROM sources").fetchone()[0] == 1


def test_html_empty_selector_does_not_create_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url, client=None: (True, ""))
    conn = _db(tmp_path)
    conn.execute("UPDATE sources SET kind='html', selector='main'")
    conn.commit()
    result = fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), _client(b"<html><body>short</body></html>", headers={"Content-Type": "text/html"}))
    assert result["error"] == "selector_empty_or_content_too_short"
    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0


def test_304_without_baseline_is_not_success_and_sends_no_validator(tmp_path, monkeypatch):
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url, client=None: (True, ""))
    conn = _db(tmp_path)
    conn.execute("UPDATE sources SET etag = 'v1'")
    conn.commit()
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(304, request=request)

    result = fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), httpx.Client(transport=httpx.MockTransport(handler)))
    assert result["error"] == "not_modified_without_baseline"
    assert "If-None-Match" not in seen
    assert conn.execute("SELECT last_success_at FROM sources").fetchone()[0] is None


def test_validator_is_not_saved_when_feed_parse_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url, client=None: (True, ""))
    conn = _db(tmp_path)
    result = fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), _client(b"not a feed", headers={"ETag": 'bad'}))
    assert result["error"] == "feed_parse_error"
    assert conn.execute("SELECT etag FROM sources").fetchone()[0] is None


def test_empty_feed_establishes_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url, client=None: (True, ""))
    conn = _db(tmp_path)
    assert fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), _client(b"<rss version='2.0'><channel><title>x</title></channel></rss>"))["changed"] is False
    result = fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), _client(FIXTURE.read_bytes()))
    assert result["changed"] is True


def test_html_json_content_type_and_oversize_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url, client=None: (True, ""))
    conn = _db(tmp_path)
    conn.execute("UPDATE sources SET kind='html', selector='main'")
    conn.commit()
    bad_type = _client(b"<main>" + b"x" * 300 + b"</main>", headers={"Content-Type": "application/json"})
    assert fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), bad_type)["error"] == "invalid_content_type"
    oversized = _client(b"x" * (2 * 1024 * 1024 + 1), headers={"Content-Type": "text/html"})
    assert fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), oversized)["error"] == "response_too_large"


def test_connect_error_is_retried_and_succeeds_on_second_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url, client=None: (True, ""))
    monkeypatch.setattr("vigia.fetch.time.sleep", lambda seconds: None)
    monkeypatch.setattr("vigia.fetch._HOST_LAST_REQUEST", {})
    conn = _db(tmp_path)
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, content=FIXTURE.read_bytes(), headers={"Content-Type": "application/rss+xml"}, request=request)

    result = fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), httpx.Client(transport=httpx.MockTransport(handler)))
    assert result["error"] is None
    assert calls == 2


def test_rate_limit_waits_two_seconds_per_host(monkeypatch):
    import vigia.fetch as fetch
    monkeypatch.setattr(fetch, "_HOST_LAST_REQUEST", {})
    clock = iter([0.0, 0.0, 1.0, 1.0, 3.0, 3.0])
    sleeps = []
    monkeypatch.setattr(fetch.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(fetch.time, "sleep", sleeps.append)
    client = _client(b"ok")
    fetch._request(client, URL, headers={"User-Agent": fetch.USER_AGENT})
    fetch._request(client, URL, headers={"User-Agent": fetch.USER_AGENT})
    assert sleeps == [1.0]


def test_fetch_rss_new_entries_post_baseline_returns_new_field():
    """New entries after baseline should be returned in 'new' field."""


def test_fetch_rss_new_entries_post_baseline_returns_new_field(tmp_path):
    """New entries after baseline should be returned in 'new' field."""
    conn = sqlite3.connect(tmp_path / "t.sqlite3")
    init_db(conn)
    conn.row_factory = sqlite3.Row

    conn.execute("INSERT INTO providers (slug, name) VALUES ('test', 'Test')")
    conn.execute(
        """INSERT INTO sources (id, provider_id, kind, url, enabled, last_success_at)
           VALUES (1, 1, 'rss', 'http://test.com/feed', 1, '2026-01-01T00:00:00Z')"""
    )
    # Baseline entry
    conn.execute(
        """INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content)
           VALUES (1, 'e1', 'http://test.com/e1', '2026-01-01', 'hash1', 'old entry')"""
    )
    conn.commit()

    source_row = conn.execute("SELECT * FROM sources WHERE id = 1").fetchone()

    # Mock feed with one old entry (unchanged) and one new entry
    feed_xml = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel>
        <item>
            <guid>e1</guid>
            <link>http://test.com/e1</link>
            <title>old entry</title>
        </item>
        <item>
            <guid>e2</guid>
            <link>http://test.com/e2</link>
            <title>New pricing announcement</title>
        </item>
    </channel></rss>"""

    def handler(request):
        return httpx.Response(200, content=feed_xml, headers={"Content-Type": "application/rss+xml"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    result = fetch_source(conn, source_row, client)

    assert result["changed"] is True
    assert result["new_entries"] == 1
    assert "new" in result
    assert len(result["new"]) == 1
    assert result["new"][0]["external_id"] == "e2"
    assert "pricing" in result["new"][0]["content"].lower()


def test_fetch_rss_baseline_integration(tmp_path, monkeypatch):
    """Baseline ingestion with real fetch_source: changed=False, entries saved, no edits."""
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url, client=None: (True, ""))
    conn = _db(tmp_path)
    client = _client(FIXTURE.read_bytes())

    source_row = conn.execute("SELECT * FROM sources").fetchone()
    result = fetch_source(conn, source_row, client)

    # First ingestion is baseline
    assert result["changed"] is False
    assert result["new_entries"] == 10
    assert result["edits"] == []
    assert result["new"] == []

    # Entries are saved
    entries = conn.execute("SELECT * FROM entries").fetchall()
    assert len(entries) == 10


def test_fetch_html_baseline_and_edit_integration(tmp_path, monkeypatch):
    """HTML baseline + subsequent edit with real fetch_source."""
    monkeypatch.setattr("vigia.fetch._robots_allowed", lambda url, client=None: (True, ""))
    conn = _db(tmp_path)
    conn.execute("UPDATE sources SET kind='html', selector='main'")
    conn.commit()

    # First fetch: baseline
    html1 = b"<main>" + b"x" * 300 + b"</main>"
    client1 = _client(html1, headers={"Content-Type": "text/html"})
    source_row = conn.execute("SELECT * FROM sources").fetchone()
    result1 = fetch_source(conn, source_row, client1)

    assert result1["changed"] is False
    assert result1["edits"] == []

    # Second fetch: edit
    html2 = b"<main>" + b"y" * 300 + b"</main>"
    client2 = _client(html2, headers={"Content-Type": "text/html"})
    source_row = conn.execute("SELECT * FROM sources").fetchone()
    result2 = fetch_source(conn, source_row, client2)

    assert result2["changed"] is True
    assert len(result2["edits"]) == 1
    assert result2["edits"][0]["old_content"] != result2["edits"][0]["new_content"]
