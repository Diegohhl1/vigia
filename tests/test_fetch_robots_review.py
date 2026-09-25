import sqlite3

import httpx

import vigia.fetch as fetch
from vigia.db import init_db


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "robots.sqlite3")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO providers (slug, name) VALUES ('test', 'Test')")
    conn.execute("INSERT INTO sources (provider_id, kind, url, selector) VALUES (1, 'html', 'https://example.test/public', 'main')")
    conn.commit()
    return conn


def test_robots_parser_is_cached_but_checked_per_url_and_timestamp_not_overwritten(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(fetch, "_ROBOTS", {})
    monkeypatch.setattr(fetch, "_HOST_LAST_REQUEST", {})
    robots_calls = 0
    page_calls = []

    def handler(request):
        nonlocal robots_calls
        if request.url.path == "/robots.txt":
            robots_calls += 1
            assert request.headers["user-agent"] == fetch.USER_AGENT
            return httpx.Response(200, text="User-agent: *\nAllow: /public\nDisallow: /private\n", request=request)
        page_calls.append(request.url.path)
        return httpx.Response(200, text="<main>" + ("x" * 250) + "</main>", headers={"Content-Type": "text/html"}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    public = conn.execute("SELECT * FROM sources WHERE id=1").fetchone()
    result = fetch.fetch_source(conn, public, client)
    assert result["error"] is None
    first_checked = conn.execute("SELECT robots_checked_at FROM sources WHERE id=1").fetchone()[0]
    assert first_checked

    private_url = "https://example.test/private"
    assert fetch._robots_allowed(private_url, client)[0] is False
    assert robots_calls == 1
    assert page_calls == ["/public"]


def test_stream_limit_applies_to_non_200_responses(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "_ROBOTS", {"https://example.test": (None, "cached")})
    monkeypatch.setattr(fetch, "_HOST_LAST_REQUEST", {})
    conn = _conn(tmp_path)

    def handler(request):
        return httpx.Response(500, content=b"x" * (fetch.MAX_RESPONSE_BYTES + 1), request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch.fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), client)
    assert result["error"] == "response_too_large"


def test_server_error_retries_three_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "_ROBOTS", {"https://example.test": (None, "cached")})
    monkeypatch.setattr(fetch, "_HOST_LAST_REQUEST", {})
    monkeypatch.setattr(fetch.time, "sleep", lambda seconds: None)
    conn = _conn(tmp_path)
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        status = 500 if calls < 3 else 200
        return httpx.Response(status, text="ok" if status == 500 else "<main>" + "x" * 250 + "</main>", headers={"Content-Type": "text/html"}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch.fetch_source(conn, conn.execute("SELECT * FROM sources").fetchone(), client)
    assert result["error"] is None
    assert calls == 3
