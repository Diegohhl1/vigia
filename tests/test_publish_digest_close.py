"""Cierre ronda 2: límite duro de Telegram y GUID estable entre dos builds completos."""
from datetime import datetime, timezone

from vigia.digest import build_digest, _MAX_MESSAGE
from vigia.db import get_conn
from vigia.publish import build_site


def _db_with_changes(summaries):
    conn = get_conn(":memory:")
    conn.execute("INSERT INTO providers (slug, name) VALUES ('acme', 'Acme')")
    conn.execute("INSERT INTO sources (provider_id, kind, url) VALUES (1, 'rss', 'https://acme.test/feed')")
    for i, summary in enumerate(summaries):
        conn.execute(
            "INSERT INTO changes (source_id, detected_at, verdict, summary, diff_text, source_url) VALUES (1, '2026-09-26T00:00:00Z', 'pricing', ?, ?, ?)",
            (summary, f"d-{i}", f"https://acme.test/change/{i}"),
        )
    conn.commit()
    return conn


def test_digest_never_exceeds_telegram_limit():
    """Proveedor gigante + proveedor pequeño → el digest final cabe en 4000 y no está vacío."""
    huge = "x" * 5000
    conn = _db_with_changes([huge, "small price change"])
    text = build_digest(conn, datetime(2026, 9, 25, tzinfo=timezone.utc))
    assert 0 < len(text) <= _MAX_MESSAGE, f"len={len(text)}"


def test_guid_stable_across_two_full_builds(tmp_path):
    """Dos ejecuciones completas de build_site producen los mismos GUIDs en rss.xml."""
    import sqlite3
    import xml.etree.ElementTree as ET

    def fresh_db():
        conn = get_conn(":memory:")
        conn.execute("INSERT INTO providers (slug, name) VALUES ('acme', 'Acme')")
        conn.execute("INSERT INTO sources (provider_id, kind, url) VALUES (1, 'rss', 'https://acme.test/feed')")
        conn.execute(
            "INSERT INTO changes (source_id, detected_at, verdict, summary, diff_text, source_url) VALUES (1, '2026-09-26T00:00:00Z', 'pricing', 'price change', 'd-0', 'https://acme.test/change/0')"
        )
        conn.commit()
        return conn

    guids = []
    for run in (1, 2):
        out = tmp_path / f"site-{run}"
        conn = fresh_db()
        build_site(conn, out)
        root = ET.fromstring((out / "rss.xml").read_text())
        guids.extend(e.text for e in root.iter("guid"))

    assert len(guids) >= 2
    assert guids[: len(guids) // 2] == guids[len(guids) // 2 :], "GUIDs deben ser idénticos entre builds"
