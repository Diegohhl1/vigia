"""Generate the public static site and RSS feed from approved changes."""

from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin


_PUBLIC_VERDICTS = ("pricing", "breaking", "minor")


def _approved_changes(conn):
    return conn.execute(
        """
        SELECT c.*, p.slug AS provider_slug, p.name AS provider_name
        FROM changes AS c
        JOIN sources AS s ON s.id = c.source_id
        JOIN providers AS p ON p.id = s.provider_id
        WHERE c.verdict IN ('pricing', 'breaking', 'minor')
        ORDER BY c.detected_at DESC, c.id DESC
        """
    ).fetchall()


def _change_dict(row):
    return {
        "id": row["id"],
        "source_id": row["source_id"],
        "detected_at": row["detected_at"],
        "verdict": row["verdict"],
        "score": row["score"],
        "summary": row["summary"],
        "evidence": row["evidence"],
        "diff_text": row["diff_text"],
        "old_excerpt": row["old_excerpt"],
        "new_excerpt": row["new_excerpt"],
        "source_url": row["source_url"],
        "provider_slug": row["provider_slug"],
        "provider_name": row["provider_name"],
    }


def _rss(changes, base_url: str) -> str:
    root = ET.Element("rss", version="2.0")
    channel = ET.SubElement(root, "channel")
    ET.SubElement(channel, "title").text = "Vigía — cambios de proveedores"
    ET.SubElement(channel, "link").text = base_url
    ET.SubElement(channel, "description").text = "Cambios relevantes en servicios SaaS y cloud"
    for row in changes:
        item = ET.SubElement(channel, "item")
        source_url = row["source_url"] or ""
        link = urljoin(base_url.rstrip("/") + "/", source_url)
        ET.SubElement(item, "title").text = f"{row['provider_name']}: {row['summary']}"
        ET.SubElement(item, "link").text = link
        ET.SubElement(item, "guid", isPermaLink="false").text = hashlib.sha256(
            f"{row['id']}|{source_url}|{row['detected_at']}".encode("utf-8")
        ).hexdigest()
        ET.SubElement(item, "pubDate").text = row["detected_at"]
        ET.SubElement(item, "description").text = row["summary"]
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _provider_html(name: str, slug: str, changes) -> str:
    title = html.escape(name)
    items = []
    for row in changes:
        summary = html.escape(row["summary"] or "")
        verdict = html.escape(row["verdict"] or "")
        detected = html.escape(row["detected_at"] or "")
        source = html.escape(row["source_url"] or "", quote=True)
        link = f'<a href="{source}">Fuente</a>' if source else ""
        items.append(
            f"<article><h2>{summary}</h2><p><time datetime=\"{detected}\">{detected}</time> "
            f"<span>{verdict}</span> {link}</p></article>"
        )
    return (
        "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
        f"<title>{title} — Vigía</title></head><body><header><h1>{title}</h1></header>"
        f"<main>{''.join(items)}</main></body></html>"
    )


def _index_html(providers) -> str:
    links = "".join(
        f'<li><a href="providers/{html.escape(slug, quote=True)}/">{html.escape(name)}</a></li>'
        for slug, name in providers
    )
    return (
        "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
        "<title>Vigía</title></head><body><header><h1>Vigía</h1></header>"
        f"<main><ul>{links}</ul></main></body></html>"
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_site(conn, out_dir: Path, base_url: str = "https://vigia.pages.dev") -> int:
    """Build all site files in a temporary tree and atomically replace ``out_dir``."""
    out_dir = Path(out_dir)
    changes = _approved_changes(conn)
    providers = conn.execute("SELECT slug, name FROM providers ORDER BY name, slug").fetchall()
    grouped = {row["slug"]: [] for row in providers}
    for row in changes:
        grouped.setdefault(row["provider_slug"], []).append(row)

    parent = out_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp_name = tempfile.mkdtemp(prefix=f".{out_dir.name}.", dir=parent)
    tmp_dir = Path(tmp_name)
    try:
        _write(tmp_dir / "index.html", _index_html([(r["slug"], r["name"]) for r in providers]))
        _write(tmp_dir / "rss.xml", _rss(changes, base_url))
        count = 2
        for row in providers:
            slug, name = row["slug"], row["name"]
            provider_changes = grouped.get(slug, [])
            _write(tmp_dir / "providers" / slug / "index.html", _provider_html(name, slug, provider_changes))
            _write(
                tmp_dir / "providers" / slug / "history.json",
                json.dumps([_change_dict(change) for change in provider_changes], ensure_ascii=False, indent=2),
            )
            count += 2
        backup = None
        if out_dir.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}.old.", dir=parent))
            backup.rmdir()
            os.replace(out_dir, backup)
        try:
            os.replace(tmp_dir, out_dir)
        except Exception:
            if backup is not None and not out_dir.exists():
                os.replace(backup, out_dir)
            raise
        if backup is not None:
            shutil.rmtree(backup)
        return count
    except Exception:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        raise
