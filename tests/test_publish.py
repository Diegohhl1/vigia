import json
import sqlite3
import xml.etree.ElementTree as ET

from vigia.db import init_db
from vigia.publish import _rss, build_site


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO providers (slug, name) VALUES ('acme', 'Acme <Cloud>')")
    conn.execute("INSERT INTO sources (provider_id, kind, url) VALUES (1, 'rss', 'https://acme.test/feed')")
    for i, (verdict, date, summary) in enumerate([
        ("minor", "2026-09-26T03:00:00Z", "newer"),
        ("pricing", "2026-09-25T03:00:00Z", "price <script>alert(1)</script>"),
        ("needs_review", "2026-09-27T03:00:00Z", "private"),
    ], 1):
        conn.execute(
            "INSERT INTO changes (source_id, detected_at, verdict, summary, diff_text, source_url) VALUES (1, ?, ?, ?, ?, ?)",
            (date, verdict, summary, f"diff-{i}", f"https://acme.test/change/{i}"),
        )
    conn.commit()
    return conn


def test_build_site_publishes_only_approved_and_is_parseable(tmp_path):
    conn = _db()
    assert build_site(conn, tmp_path / "site", "https://example.test") == 4
    site = tmp_path / "site"
    assert {"index.html", "rss.xml", "providers/acme/index.html", "providers/acme/history.json"} <= {
        str(p.relative_to(site)) for p in site.rglob("*") if p.is_file()
    }
    html = (site / "providers/acme/index.html").read_text()
    assert html.index("newer") < html.index("price")
    assert "&lt;script&gt;" in html
    assert "private" not in html
    assert "private" not in (site / "providers/acme/history.json").read_text()
    assert "private" not in (site / "rss.xml").read_text()
    ET.fromstring((site / "rss.xml").read_text())
    assert len(json.loads((site / "providers/acme/history.json").read_text())) == 2


def test_rss_resolves_relative_source_url_and_guid_is_stable():
    row = {
        "source_url": "/changes/1",
        "detected_at": "2026-09-26T03:00:00Z",
        "id": 1,
        "provider_name": "Acme",
        "summary": "newer",
    }
    first = ET.fromstring(_rss([row], "https://example.test/"))
    second = ET.fromstring(_rss([row], "https://example.test/"))
    assert first.find("./channel/item/link").text == "https://example.test/changes/1"
    assert first.find("./channel/item/guid").text == second.find("./channel/item/guid").text


def test_build_site_keeps_previous_tree_on_write_error(tmp_path, monkeypatch):
    conn = _db()
    out = tmp_path / "site"
    build_site(conn, out)
    old = (out / "providers/acme/index.html").read_text()
    original = __import__("pathlib").Path.write_text

    def fail(path, data, *args, **kwargs):
        if path.name == "rss.xml":
            raise OSError("disk full")
        return original(path, data, *args, **kwargs)

    monkeypatch.setattr("pathlib.Path.write_text", fail)
    try:
        build_site(conn, out)
    except OSError:
        pass
    assert (out / "providers/acme/index.html").read_text() == old


def test_build_site_restores_previous_tree_when_swap_fails(tmp_path, monkeypatch):
    conn = _db()
    out = tmp_path / "site"
    build_site(conn, out)
    old = (out / "index.html").read_text()
    original = __import__("vigia.publish", fromlist=["os"]).os.replace
    calls = 0

    def fail_after_backup(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("swap failed")
        return original(source, target)

    monkeypatch.setattr("vigia.publish.os.replace", fail_after_backup)
    try:
        build_site(conn, out)
    except OSError as error:
        assert str(error) == "swap failed"
    else:
        raise AssertionError("expected swap failure")
    assert (out / "index.html").read_text() == old
