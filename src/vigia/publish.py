"""Generate the public static site and RSS feed from approved changes."""

from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin


_PUBLIC_VERDICTS = ("pricing", "breaking", "minor")
_VERDICT_CLASSES = {
    "pricing": "badge-pricing",
    "breaking": "badge-breaking",
    "minor": "badge-minor",
    "needs_review": "badge-needs-review",
}

_SITE_CSS = """
:root { color-scheme: dark; --bg: #09090b; --panel: #0e0e12; --panel-2: #131318; --text: #ececf1; --muted: #9d9daa; --faint: #5f5f6e; --line: rgba(255, 255, 255, .08); --line-strong: rgba(255, 255, 255, .16); --accent: #f5a623; --pricing: #f5c04a; --breaking: #ff5d5d; --minor: #58a6ff; --needs-review: #9d9daa; }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; background: var(--bg); color: var(--text); font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; line-height: 1.5; }
a { color: inherit; }
.mono, time, .clock, .side-count, .day-cell, .t { font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace; }
.topbar { display: flex; align-items: center; gap: 1rem; padding: .7rem 1.4rem; border-bottom: 1px solid var(--line); background: var(--panel); position: sticky; top: 0; z-index: 10; }
.brand { font-weight: 800; letter-spacing: -.02em; font-size: 1rem; display: flex; align-items: center; gap: .55rem; }
.brand .sq { width: 10px; height: 10px; background: var(--accent); border-radius: 3px; }
.clock { color: var(--faint); font-size: .75rem; }
.topnav { margin-left: auto; display: flex; gap: 1.2rem; font-size: .8rem; }
.topnav a { color: var(--muted); text-decoration: none; }
.topnav a:hover { color: var(--text); }
.live { display: inline-flex; align-items: center; gap: .45rem; color: #3fb950; font-size: .74rem; font-weight: 600; }
.live::before { content: ''; width: 7px; height: 7px; border-radius: 50%; background: #3fb950; animation: vigia-pulse 2s infinite; }
@keyframes vigia-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
.layout { display: grid; grid-template-columns: 230px 1fr; min-height: calc(100vh - 49px); }
.sidebar { border-right: 1px solid var(--line); background: var(--panel); padding: 1.1rem .7rem; }
.side-label { font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: .62rem; letter-spacing: .16em; text-transform: uppercase; color: var(--faint); padding: 0 .55rem; margin: 1.3rem 0 .6rem; }
.side-label:first-child { margin-top: 0; }
.side-item { display: flex; align-items: center; gap: .55rem; padding: .48rem .6rem; border-radius: 8px; font-size: .84rem; color: var(--muted); text-decoration: none; }
.side-item:hover { background: var(--panel-2); color: var(--text); }
.side-item.active { background: var(--panel-2); color: var(--text); font-weight: 600; }
.side-count { margin-left: auto; font-size: .68rem; color: var(--faint); }
.side-dot { width: 8px; height: 8px; border-radius: 3px; background: var(--faint); opacity: .5; }
.side-dot.hot { background: var(--accent); opacity: 1; }
.main { padding: 1.6rem 1.8rem 4rem; }
.main-head { display: flex; align-items: baseline; gap: 1rem; margin-bottom: 1.2rem; flex-wrap: wrap; }
.main-head h1 { margin: 0; font-size: 1.25rem; font-weight: 700; letter-spacing: -.02em; }
.head-meta { color: var(--faint); font-size: .78rem; }
.top-actions { margin-left: auto; display: flex; gap: .9rem; align-items: center; }
.legend { display: flex; gap: .9rem; font-size: .7rem; color: var(--faint); }
.legend i { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: .3rem; }
.read-toggle { background: var(--panel-2); color: var(--muted); border: 1px solid var(--line); border-radius: 7px; padding: .3rem .75rem; font-size: .76rem; font-weight: 500; cursor: pointer; }
.read-toggle:hover { color: var(--text); border-color: var(--line-strong); }
table.feed { width: 100%; border-collapse: collapse; }
table.feed td { padding: .68rem .6rem; vertical-align: top; font-size: .86rem; }
tr.change { border-bottom: 1px solid var(--line); }
tr.change:hover { background: var(--panel); }
tr.change.read { opacity: .38; }
tr.change.read .badge { filter: grayscale(1); }
td.t { width: 92px; color: var(--faint); font-size: .72rem; white-space: nowrap; padding-top: .78rem; }
td.v { width: 90px; padding-top: .7rem; }
td.src { width: 110px; text-align: right; }
td.src a { color: var(--faint); text-decoration: none; font-size: .76rem; }
td.src a:hover { color: var(--accent); }
.badge { display: inline-block; font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: .62rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; padding: .16rem .5rem; border-radius: 5px; }
.badge-minor { color: var(--minor); background: rgba(88, 166, 255, .1); }
.badge-breaking { color: var(--breaking); background: rgba(255, 93, 93, .1); }
.badge-pricing { color: var(--pricing); background: rgba(245, 192, 74, .1); }
.badge-needs-review { color: var(--needs-review); background: rgba(157, 157, 170, .1); }
.entry-title { font-weight: 600; letter-spacing: -.01em; line-height: 1.4; }
.new-pill { display: none; margin-left: .5rem; font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: .58rem; font-weight: 700; letter-spacing: .08em; color: var(--minor); background: rgba(88, 166, 255, .12); border-radius: 5px; padding: .1rem .4rem; vertical-align: 2px; }
.change:not(.read) .new-pill { display: inline-block; }
.entry-evidence { color: var(--muted); font-size: .8rem; margin-top: .15rem; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
tr.day-row td { padding: 1.2rem .6rem .4rem; font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: .66rem; letter-spacing: .16em; text-transform: uppercase; color: var(--faint); }
tr.day-row + tr.change td { border-top: 1px solid var(--line-strong); }
body.hide-read tr.change.read { display: none; }
@media (max-width: 760px) {
  .layout { grid-template-columns: 1fr; }
  .sidebar { border-right: 0; border-bottom: 1px solid var(--line); display: flex; flex-wrap: wrap; gap: .35rem; }
  .side-label { width: 100%; margin: .8rem 0 .3rem; }
  .side-label:first-child { margin-top: 0; }
  .side-count { margin-left: auto; }
  td.src { display: none; }
}
"""


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
    ET.SubElement(channel, "title").text = "Vigía — provider changes"
    ET.SubElement(channel, "link").text = base_url
    ET.SubElement(channel, "description").text = "Relevant changes in SaaS and cloud services"
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


_SITE_READ_TRACKER = """
(function () {
  var KEY = 'vigia_read';
  var HIDE_KEY = 'vigia_hide_read';
  var MAX_TRACKED = 500;
  var readIds = {};
  try {
    JSON.parse(localStorage.getItem(KEY) || '[]').forEach(function (id) { readIds[id] = true; });
  } catch (e) { /* lista corrupta: se empieza de cero */ }

  function persist() {
    var ids = Object.keys(readIds).slice(-MAX_TRACKED);
    try { localStorage.setItem(KEY, JSON.stringify(ids)); } catch (e) { /* modo privado */ }
  }

  function markRead(el, id) {
    if (readIds[id]) return;
    readIds[id] = true;
    el.classList.add('read');
    persist();
  }

  function applyHide(state) {
    document.body.classList.toggle('hide-read', state);
    var btn = document.getElementById('toggle-read');
    if (btn) btn.textContent = state ? 'Show read' : 'Hide read';
  }

  function setup() {
    var items = document.querySelectorAll('.change[data-change-id]');
    items.forEach(function (el) {
      if (readIds[el.getAttribute('data-change-id')]) el.classList.add('read');
    });
    var seen = {};
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        if (seen[el]) return;
        seen[el] = true;
        setTimeout(function () {
          // solo cuenta como leída si sigue en pantalla un momento
          var box = el.getBoundingClientRect();
          if (box.bottom > 0 && box.top < window.innerHeight) markRead(el, el.getAttribute('data-change-id'));
        }, 1000);
      });
    }, { threshold: 0.5 });
    items.forEach(function (el) { observer.observe(el); });
    var btn = document.getElementById('toggle-read');
    applyHide(localStorage.getItem(HIDE_KEY) === '1');
    if (btn) btn.addEventListener('click', function () {
      var next = !document.body.classList.contains('hide-read');
      applyHide(next);
      try { localStorage.setItem(HIDE_KEY, next ? '1' : '0'); } catch (e) { /* modo privado */ }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setup);
  } else {
    setup();
  }
})();
"""


def _source_link(row) -> str:
    # Solo esquemas http/https en href: un feed controla source_url y podría inyectar javascript:...
    source_url_raw = row["source_url"] or ""
    if source_url_raw.lower().startswith(("http://", "https://")):
        source = html.escape(source_url_raw, quote=True)
        return f'<a class="source" href="{source}" aria-label="source">source ↗</a>'
    return ""


def _feed_rows(rows) -> str:
    """Filas de la tabla feed, agrupadas por día (los rows ya vienen DESC)."""
    trs = []
    last_day = None
    for row in rows:
        detected_value = row["detected_at"] or ""
        day = detected_value[:10]
        if day != last_day:
            last_day = day
            trs.append(f'<tr class="day-row"><td colspan="4">{html.escape(day)}</td></tr>')
        summary = html.escape(row["summary"] or "")
        evidence = html.escape(row["evidence"] or "")
        verdict_value = row["verdict"] or ""
        verdict = html.escape(verdict_value)
        verdict_class = _VERDICT_CLASSES.get(verdict_value, "badge-needs-review")
        detected = html.escape(detected_value)
        change_id = int(row["id"])
        trs.append(
            f'<tr class="change" data-change-id="{change_id}">'
            f'<td class="t"><time datetime="{detected}">{html.escape(detected_value[11:16])}</time></td>'
            f'<td class="v"><span class="badge {verdict_class}">{verdict}</span></td>'
            f'<td><div class="entry-title">{summary}<span class="new-pill">NEW</span></div>'
            f'<div class="entry-evidence">{evidence}</div></td>'
            f'<td class="src">{_source_link(row)}</td></tr>'
        )
    return "".join(trs)


def _sidebar(providers, active_slug: str | None, prefix: str = "../") -> str:
    """Navegación lateral: proveedores + leyenda de impacto.

    ``prefix`` resuelve las rutas relativas: ``"../"`` desde /providers/<slug>/,
    ``""`` desde el index en la raíz.
    """
    items = []
    for slug, name, count in providers:
        active = " active" if slug == active_slug else ""
        hot = " hot" if count >= 10 else ""
        url = prefix + html.escape(slug, quote=True) + "/"
        items.append(
            f'<a class="side-item{active}" href="{url}">'
            f'<span class="side-dot{hot}"></span>{html.escape(name)}'
            f'<span class="side-count">{count}</span></a>'
        )
    return (
        f'<aside class="sidebar"><div class="side-label">Providers</div>{"".join(items)}'
        f'<div class="side-label">Impact</div>'
        f'<span class="side-item" style="font-size:.78rem"><span class="side-dot" style="background:var(--breaking);opacity:1"></span>Breaking</span>'
        f'<span class="side-item" style="font-size:.78rem"><span class="side-dot" style="background:var(--pricing);opacity:1"></span>Pricing</span>'
        f'<span class="side-item" style="font-size:.78rem"><span class="side-dot" style="background:var(--minor);opacity:1"></span>Minor</span></aside>'
    )


def _page(title: str, head_meta: str, sidebar: str, table_rows: str, with_script: bool, prefix: str = "../") -> str:
    topnav = f'<nav class="topnav"><a href="{prefix}">All providers</a><a href="{prefix}rss.xml">RSS</a></nav>'
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f'<meta name="viewport" content="width=device-width, initial-scale=1"><style>{_SITE_CSS}</style>'
        f"<title>{title} — Vigía</title></head><body>"
        f'<div class="topbar"><span class="brand"><span class="sq"></span>vigía</span>'
        f'<span class="clock">change radar for cloud/SaaS providers</span>{topnav}'
        f'<span class="live">LIVE</span></div>'
        f'<div class="layout">{sidebar}<main class="main">'
        f'<div class="main-head"><h1>{title}</h1><span class="head-meta">{head_meta}</span>'
        f'<div class="top-actions"><div class="legend">'
        f'<span><i style="background:var(--breaking)"></i>breaking</span>'
        f'<span><i style="background:var(--pricing)"></i>pricing</span>'
        f'<span><i style="background:var(--minor)"></i>minor</span></div>'
        + ('<button id="toggle-read" class="read-toggle" type="button">Hide read</button>' if with_script else "")
        + "</div></div>"
        f'<table class="feed">{table_rows}</table>'
        f"</main></div>"
        + (f"<script>{_SITE_READ_TRACKER}</script>" if with_script else "")
        + "</body></html>"
    )


def _provider_html(name: str, slug: str, changes, providers) -> str:
    title = html.escape(name)
    rows = _feed_rows(changes)
    counts = {s: c for s, _, c in providers}
    total = counts.get(slug, len(changes))
    sidebar = _sidebar(providers, slug)
    return _page(title, f"{total} entries", sidebar, rows, with_script=True)


def _index_html(providers, changes) -> str:
    total = sum(count for _, _, count in providers)
    sidebar = _sidebar(providers, None, prefix="providers/")
    return _page(
        "All changes",
        f"{total} entries · {len(providers)} providers",
        sidebar,
        _feed_rows(changes),
        with_script=False,
        prefix="",
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_site(conn, out_dir: Path, base_url: str = "https://vigia.pages.dev") -> int:
    """Build a temporary tree, then swap it into ``out_dir``.

    Directory replacement on POSIX cannot exchange two non-empty directories in
    one atomic operation, so ``out_dir`` is a *symlink* to a versioned tree
    (``.site-<timestamp>``) and publication swaps the symlink with a single
    ``os.replace`` — readers always see a complete tree. Old versions are
    removed after a successful swap; a failed swap leaves the previous version
    untouched.
    """
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
        _write(tmp_dir / "index.html", _index_html([(r["slug"], r["name"], len(grouped.get(r["slug"], []))) for r in providers], changes))
        _write(tmp_dir / "rss.xml", _rss(changes, base_url))
        count = 2
        for row in providers:
            slug, name = row["slug"], row["name"]
            provider_changes = grouped.get(slug, [])
            provider_list = [(r["slug"], r["name"], len(grouped.get(r["slug"], []))) for r in providers]
            _write(tmp_dir / "providers" / slug / "index.html", _provider_html(name, slug, provider_changes, provider_list))
            _write(
                tmp_dir / "providers" / slug / "history.json",
                json.dumps([_change_dict(change) for change in provider_changes], ensure_ascii=False, indent=2),
            )
            count += 2
        # Publicación atómica vía symlink: out_dir apunta a una versión con nombre,
        # y el swap es un único os.replace sobre el symlink (crash-safe).
        version_dir = parent / f".{out_dir.name}-{os.getpid()}-{time.time_ns()}"
        os.replace(tmp_dir, version_dir)
        link_tmp = parent / f".{out_dir.name}.link-{os.getpid()}-{time.time_ns()}"
        link_tmp.symlink_to(version_dir.name, target_is_directory=True)
        if out_dir.is_symlink() or out_dir.exists():
            old_target = os.readlink(out_dir) if out_dir.is_symlink() else None
            if old_target is None:
                # Directorio real preexistente (primera migración al esquema symlink):
                # moverlo a versión con nombre y dejar el symlink en su sitio.
                legacy_dir = parent / f".{out_dir.name}-legacy-{os.getpid()}-{time.time_ns()}"
                os.replace(out_dir, legacy_dir)
                os.replace(link_tmp, out_dir)
                shutil.rmtree(legacy_dir, ignore_errors=True)
            else:
                os.replace(link_tmp, out_dir)  # swap atómico del symlink
                old_path = parent / old_target
                if old_path.is_dir() and not old_path.is_symlink():
                    shutil.rmtree(old_path, ignore_errors=True)
        else:
            os.replace(link_tmp, out_dir)
        return count
    except Exception:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        raise
