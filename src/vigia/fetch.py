"""Conectores HTTP para fuentes RSS/Atom y HTML."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
import sqlite3
import time
from urllib import robotparser
from urllib.parse import urlparse

import feedparser
from bs4 import BeautifulSoup
import httpx


USER_AGENT = "vigia/0.1 (+https://github.com/Diegohhl1/vigia)"
_ROBOTS: dict[str, tuple[robotparser.RobotFileParser | None, str]] = {}
_HOST_LAST_REQUEST: dict[str, float] = {}
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_RETRIES = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _value(row, key, default=None):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


class _ResponseTooLarge(Exception):
    """El cuerpo de la respuesta supera MAX_RESPONSE_BYTES.

    ``partial`` conserva el prefijo descargado (frontera de chunk), útil para
    feeds gigantes donde el prefijo truncado sigue siendo parseable.
    """

    def __init__(self, url: str, partial: bytes = b""):
        super().__init__(url)
        self.partial = partial


def _request(client, url: str, *, headers: dict[str, str]):
    host = urlparse(url).netloc
    for attempt in range(MAX_RETRIES + 1):
        now = time.monotonic()
        elapsed = now - _HOST_LAST_REQUEST[host] if host in _HOST_LAST_REQUEST else 2.0
        if host in _HOST_LAST_REQUEST and elapsed < 2.0:
            time.sleep(2.0 - elapsed)
        _HOST_LAST_REQUEST[host] = time.monotonic()
        try:
            # Lectura en streaming: aborta en cuanto el cuerpo excede el límite
            # en lugar de cargar la respuesta completa en memoria.
            with client.stream("GET", url, headers=headers, timeout=30.0) as resp:
                status = resp.status_code
                resp_headers = httpx.Headers(resp.headers)
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise _ResponseTooLarge(url, b"".join(chunks))
                    chunks.append(chunk)
                content = b"".join(chunks)
            if (status >= 500 or status == 429) and attempt < MAX_RETRIES:
                time.sleep(0.1 * (2 ** attempt))
                continue
            # iter_bytes() ya descomprimió el cuerpo: hay que eliminar los
            # headers de codificación o la Response reconstruida reintenta
            # descomprimir y lanza DecodingError.
            resp_headers = httpx.Headers(
                [(k, v) for k, v in resp_headers.raw if k.lower() not in (b"content-encoding", b"content-length")]
            )
            return httpx.Response(status, headers=resp_headers, content=content, request=resp.request)
        except _ResponseTooLarge:
            raise
        except Exception:
            if attempt >= MAX_RETRIES:
                raise
            time.sleep(0.1 * (2 ** attempt))


def _robots_allowed(url: str, client=None) -> tuple[bool, str]:
    """Comprueba robots.txt para esta URL concreta; cachea el PARSER por dominio.

    Devuelve (allowed, checked_at). Un parser None significa "sin robots.txt" (404):
    se permite todo.
    """
    parsed = urlparse(url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    entry = _ROBOTS.get(domain)
    if entry is None:
        if client is None:
            return True, ""
        response = _request(client, f"{domain}/robots.txt", headers={"User-Agent": USER_AGENT})
        checked_at = _now()
        if response.status_code == 404:
            parser = None
        else:
            response.raise_for_status()
            parser = robotparser.RobotFileParser()
            parser.parse(response.text.splitlines())
        _ROBOTS[domain] = (parser, checked_at)
        entry = (parser, checked_at)
    parser, checked_at = entry
    if parser is None:
        return True, checked_at
    return parser.can_fetch(USER_AGENT, url), checked_at


def _failure(conn, source_id, message: str, checked_at: str) -> dict:
    conn.execute(
        """UPDATE sources SET last_checked_at = ?, last_error = ?,
           failure_count = COALESCE(failure_count, 0) + 1 WHERE id = ?""",
        (checked_at, message, source_id),
    )
    conn.commit()
    return {"changed": False, "new_entries": 0, "edits": [], "error": message}


def _entry_content(entry) -> tuple[str, str]:
    title = _normalise(getattr(entry, "title", ""))
    summary = _normalise(getattr(entry, "summary", getattr(entry, "description", "")))
    content = _normalise(f"{title} {summary}")
    return content, hashlib.sha256(content.encode("utf-8")).hexdigest()


def _published(entry) -> str:
    value = getattr(entry, "published", None) or getattr(entry, "updated", None)
    return _normalise(value or _now())


def fetch_source(conn: sqlite3.Connection, source_row, client, commit: bool = True) -> dict:
    """Descarga una fuente y actualiza su baseline; nunca propaga errores de red/parseo.

    Args:
        commit: Si True, hace commit tras ingesta exitosa. Failure/304 siempre commitean.
    """
    source_id = _value(source_row, "id")
    checked_at = _now()
    url = _value(source_row, "url")
    try:
        allowed, robots_checked = _robots_allowed(url, client)
    except Exception as exc:
        return _failure(conn, source_id, str(exc), checked_at)
    if robots_checked:
        conn.execute(
            "UPDATE sources SET last_checked_at = ?, robots_checked_at = ? WHERE id = ?",
            (checked_at, robots_checked, source_id),
        )
        if commit:
            conn.commit()
    if not allowed:
        return _failure(conn, source_id, "robots_disallowed", checked_at)

    kind = _value(source_row, "kind")
    has_baseline = _value(source_row, "last_success_at") is not None
    if kind == "rss":
        has_baseline = has_baseline and conn.execute(
            "SELECT 1 FROM entries WHERE source_id = ? LIMIT 1", (source_id,)
        ).fetchone() is not None
    elif kind == "html":
        has_baseline = has_baseline and conn.execute(
            "SELECT 1 FROM snapshots WHERE source_id = ? LIMIT 1", (source_id,)
        ).fetchone() is not None
    headers = {"User-Agent": USER_AGENT}
    if has_baseline and _value(source_row, "etag"):
        headers["If-None-Match"] = source_row["etag"]
    if has_baseline and _value(source_row, "last_modified"):
        headers["If-Modified-Since"] = source_row["last_modified"]
    try:
        response = _request(client, url, headers=headers)
    except _ResponseTooLarge as exc:
        if kind == "rss" and exc.partial:
            # Feed gigante: parsea el prefijo truncado (recortado a frontera
            # de entrada) en vez de descartar la fuente.
            return _fetch_feed(conn, source_id, exc.partial, checked_at, None, commit)
        return _failure(conn, source_id, "response_too_large", checked_at)
    except Exception as exc:
        return _failure(conn, source_id, str(exc), checked_at)
    if response.status_code == 304:
        if not has_baseline:
            return _failure(conn, source_id, "not_modified_without_baseline", checked_at)
        conn.execute(
            "UPDATE sources SET last_checked_at = ?, last_success_at = ?, last_error = NULL, failure_count = 0 WHERE id = ?",
            (checked_at, checked_at, source_id),
        )
        if commit:
            conn.commit()
        return {"changed": False, "new_entries": 0, "edits": [], "error": None}
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
    if len(response.content) > MAX_RESPONSE_BYTES:
        return _failure(conn, source_id, "response_too_large", checked_at)
    if kind == "html" and content_type not in {"text/html", "application/xhtml+xml"}:
        return _failure(conn, source_id, "invalid_content_type", checked_at)
    if kind != "html" and content_type not in {
        "application/rss+xml", "application/atom+xml", "application/xml", "text/xml"
    }:
        return _failure(conn, source_id, "invalid_content_type", checked_at)
    if kind == "html":
        return _fetch_html(conn, source_id, source_row, response.content, checked_at, response.headers, commit)
    return _fetch_feed(conn, source_id, response.content, checked_at, response.headers, commit)


def _maybe_gunzip(payload: bytes) -> bytes:
    """Algunos CDNs sirven gzip crudo ignorando la negociación: descomprime si ve el magic number."""
    if payload[:2] == b"\x1f\x8b":
        import gzip
        try:
            return gzip.decompress(payload)
        except OSError:
            return payload
    return payload


def _fetch_feed(conn, source_id, payload: bytes, checked_at: str, response_headers=None, commit: bool = True) -> dict:
    payload = _maybe_gunzip(payload)
    parsed = feedparser.parse(payload)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        # Los feeds gigantes (p. ej. Cloudflare, 7+ MB) pueden llegar truncados
        # por el límite de descarga. Reintenta sobre el prefijo válido: recorta
        # a la última frontera de </item> o </entry> completa.
        cut = max(payload.rfind(b"</item>"), payload.rfind(b"</entry>"))
        if cut > 0:
            repaired = payload[:cut] + b"</channel></rss>"
            parsed = feedparser.parse(repaired)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            return _failure(conn, source_id, "feed_parse_error", checked_at)
    existing = {row[0]: row for row in conn.execute(
        "SELECT external_id, content_hash, content FROM entries WHERE source_id = ?", (source_id,)
    )}
    first_ingestion = conn.execute(
        "SELECT last_success_at FROM sources WHERE id = ?", (source_id,)
    ).fetchone()[0] is None
    changed = False
    new_entries = 0
    edits = []
    new = []
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
            if not first_ingestion:
                changed = True
                new.append({"external_id": external_id, "url": link, "content": content})
        elif existing[external_id][1] != content_hash:
            old_content = existing[external_id][2]
            conn.execute(
                """UPDATE entries SET url = ?, published_at = ?, content_hash = ?, content = ?
                   WHERE source_id = ? AND external_id = ?""",
                (link, _published(entry), content_hash, content, source_id, external_id),
            )
            changed = True
            edits.append({"external_id": external_id, "url": link, "old_content": old_content, "new_content": content})
    conn.execute(
        """UPDATE sources SET etag = COALESCE(?, etag), last_modified = COALESCE(?, last_modified),
           last_checked_at = ?, last_success_at = ?, last_error = NULL, failure_count = 0
           WHERE id = ?""",
        (response_headers.get("ETag") if response_headers else None,
         response_headers.get("Last-Modified") if response_headers else None,
         checked_at, checked_at, source_id),
    )
    if commit:
        conn.commit()
    return {"changed": changed, "new_entries": new_entries, "edits": edits, "new": new, "error": None}


def _fetch_html(conn, source_id, source_row, payload: bytes, checked_at: str, response_headers=None, commit: bool = True) -> dict:
    selector = _value(source_row, "selector")
    soup = BeautifulSoup(payload, "html.parser")
    selected = soup.select_one(selector) if selector else None
    content = _normalise(selected.get_text(" ", strip=True) if selected else "")
    if not content or len(content) < 200:
        return _failure(conn, source_id, "selector_empty_or_content_too_short", checked_at)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    previous = conn.execute(
        "SELECT content_hash, content FROM snapshots WHERE source_id = ? ORDER BY id DESC LIMIT 1", (source_id,)
    ).fetchone()
    if previous and previous[0] == content_hash:
        conn.execute(
            """UPDATE sources SET etag = COALESCE(?, etag), last_modified = COALESCE(?, last_modified),
               last_checked_at = ?, last_success_at = ?, last_error = NULL, failure_count = 0
               WHERE id = ?""",
            (response_headers.get("ETag") if response_headers else None,
             response_headers.get("Last-Modified") if response_headers else None,
             checked_at, checked_at, source_id),
        )
        if commit:
            conn.commit()
        return {"changed": False, "new_entries": 0, "edits": [], "error": None}
    conn.execute(
        "INSERT INTO snapshots (source_id, taken_at, content_hash, content) VALUES (?, ?, ?, ?)",
        (source_id, checked_at, content_hash, content),
    )
    conn.execute(
        """UPDATE sources SET etag = COALESCE(?, etag), last_modified = COALESCE(?, last_modified),
           last_checked_at = ?, last_success_at = ?, last_error = NULL, failure_count = 0
           WHERE id = ?""",
        (response_headers.get("ETag") if response_headers else None,
         response_headers.get("Last-Modified") if response_headers else None,
         checked_at, checked_at, source_id),
    )

    # Devolver edits con old/new content para HTML snapshots
    edits = []
    if previous:
        url = _value(source_row, "url")
        edits = [{
            "external_id": "html-snapshot",
            "url": url,
            "old_content": previous[1],
            "new_content": content
        }]

    if commit:
        conn.commit()
    return {"changed": bool(previous), "new_entries": 0, "edits": edits, "error": None}
