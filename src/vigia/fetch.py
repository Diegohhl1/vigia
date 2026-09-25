"""Conectores HTTP para fuentes RSS/Atom y HTML."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
import sqlite3
from urllib.parse import urlparse
from urllib import robotparser

import feedparser
from bs4 import BeautifulSoup


USER_AGENT = "vigia/0.1 (+https://github.com/Diegohhl1/vigia)"
_ROBOTS: dict[str, robotparser.RobotFileParser] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _value(row, key, default=None):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _robots_allowed(url: str) -> bool:
    parsed = urlparse(url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    parser = _ROBOTS.get(domain)
    if parser is None:
        parser = robotparser.RobotFileParser(f"{domain}/robots.txt")
        parser.set_url(f"{domain}/robots.txt")
        parser.read()
        _ROBOTS[domain] = parser
    return parser.can_fetch(USER_AGENT, url)


def _failure(conn, source_id, message: str, checked_at: str) -> dict:
    conn.execute(
        """UPDATE sources SET last_checked_at = ?, last_error = ?,
           failure_count = COALESCE(failure_count, 0) + 1 WHERE id = ?""",
        (checked_at, message, source_id),
    )
    conn.commit()
    return {"changed": False, "new_entries": 0, "error": message}


def _entry_content(entry) -> tuple[str, str]:
    title = _normalise(getattr(entry, "title", ""))
    summary = _normalise(getattr(entry, "summary", getattr(entry, "description", "")))
    content = _normalise(f"{title} {summary}")
    return content, hashlib.sha256(content.encode("utf-8")).hexdigest()


def _published(entry) -> str:
    value = getattr(entry, "published", None) or getattr(entry, "updated", None)
    return _normalise(value or _now())


def fetch_source(conn: sqlite3.Connection, source_row, client) -> dict:
    """Descarga una fuente y actualiza su baseline; nunca propaga errores de red/parseo."""
    source_id = _value(source_row, "id")
    checked_at = _now()
    url = _value(source_row, "url")
    try:
        allowed = _robots_allowed(url)
    except Exception as exc:
        return _failure(conn, source_id, str(exc), checked_at)
    if not allowed:
        return _failure(conn, source_id, "robots_disallowed", checked_at)

    headers = {"User-Agent": USER_AGENT}
    if _value(source_row, "etag"):
        headers["If-None-Match"] = source_row["etag"]
    if _value(source_row, "last_modified"):
        headers["If-Modified-Since"] = source_row["last_modified"]
    try:
        response = client.get(url, headers=headers, timeout=30.0)
        if response.status_code == 304:
            conn.execute(
                "UPDATE sources SET last_checked_at = ?, last_success_at = ?, last_error = NULL, failure_count = 0 WHERE id = ?",
                (checked_at, checked_at, source_id),
            )
            conn.commit()
            return {"changed": False, "new_entries": 0, "error": None}
        response.raise_for_status()
    except Exception as exc:
        return _failure(conn, source_id, str(exc), checked_at)

    conn.execute(
        """UPDATE sources SET etag = COALESCE(?, etag), last_modified = COALESCE(?, last_modified),
           last_checked_at = ? WHERE id = ?""",
        (response.headers.get("ETag"), response.headers.get("Last-Modified"), checked_at, source_id),
    )
    if _value(source_row, "kind") == "html":
        return _fetch_html(conn, source_id, source_row, response.content, checked_at)
    return _fetch_feed(conn, source_id, response.content, checked_at)


def _fetch_feed(conn, source_id, payload: bytes, checked_at: str) -> dict:
    parsed = feedparser.parse(payload)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        return _failure(conn, source_id, "feed_parse_error", checked_at)
    existing = {row[0]: row for row in conn.execute(
        "SELECT external_id, content_hash, content FROM entries WHERE source_id = ?", (source_id,)
    )}
    first_ingestion = not existing
    changed = False
    new_entries = 0
    for entry in parsed.entries:
        external_id = _normalise(getattr(entry, "id", "") or getattr(entry, "link", ""))
        link = _normalise(getattr(entry, "link", "") or external_id)
        if not external_id:
            continue
        content, content_hash = _entry_content(entry)
        if external_id not in existing:
            conn.execute(
                """INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (source_id, external_id, link, _published(entry), content_hash, content),
            )
            new_entries += 1
            changed = not first_ingestion
        elif existing[external_id][1] != content_hash:
            conn.execute(
                """UPDATE entries SET url = ?, published_at = ?, content_hash = ?, content = ?
                   WHERE source_id = ? AND external_id = ?""",
                (link, _published(entry), content_hash, content, source_id, external_id),
            )
            changed = True
    conn.execute(
        "UPDATE sources SET last_success_at = ?, last_error = NULL, failure_count = 0 WHERE id = ?",
        (checked_at, source_id),
    )
    conn.commit()
    return {"changed": changed, "new_entries": new_entries, "error": None}


def _fetch_html(conn, source_id, source_row, payload: bytes, checked_at: str) -> dict:
    selector = _value(source_row, "selector")
    soup = BeautifulSoup(payload, "html.parser")
    selected = soup.select_one(selector) if selector else None
    content = _normalise(selected.get_text(" ", strip=True) if selected else "")
    if not content or len(content) < 200:
        return _failure(conn, source_id, "selector_empty_or_content_too_short", checked_at)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    previous = conn.execute(
        "SELECT content_hash FROM snapshots WHERE source_id = ? ORDER BY id DESC LIMIT 1", (source_id,)
    ).fetchone()
    if previous and previous[0] == content_hash:
        conn.execute(
            "UPDATE sources SET last_success_at = ?, last_error = NULL, failure_count = 0 WHERE id = ?",
            (checked_at, source_id),
        )
        conn.commit()
        return {"changed": False, "new_entries": 0, "error": None}
    conn.execute(
        "INSERT INTO snapshots (source_id, taken_at, content_hash, content) VALUES (?, ?, ?, ?)",
        (source_id, checked_at, content_hash, content),
    )
    conn.execute(
        "UPDATE sources SET last_success_at = ?, last_error = NULL, failure_count = 0 WHERE id = ?",
        (checked_at, source_id),
    )
    conn.commit()
    return {"changed": bool(previous), "new_entries": 0, "error": None}
