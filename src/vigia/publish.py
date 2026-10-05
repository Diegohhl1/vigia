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
:root { color-scheme: dark; --bg: #0a0a0a; --surface: #111113; --surface-2: #17171a; --text: #ededed; --muted: #a1a1a1; --faint: #707070; --line: rgba(255, 255, 255, .09); --pricing: #e2b344; --breaking: #ff5b4f; --minor: #4da3ff; --needs-review: #a1a1a1; }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; background: var(--bg); color: var(--text); font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; line-height: 1.55; }
a { color: var(--minor); text-decoration: none; }
a:hover { text-decoration: underline; }
.shell { max-width: 760px; margin: 0 auto; padding: 3rem 1.25rem 4.5rem; }
header { margin-bottom: 2.5rem; }
h1, h2, h3, p { margin-top: 0; }
h1 { margin-bottom: .4rem; font-size: 2.25rem; font-weight: 600; letter-spacing: -.045em; line-height: 1.1; }
.tagline, .generated, .meta, .count { color: var(--muted); }
.generated, time, code, .day-label { font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace; }
.generated { font-size: .8rem; color: var(--faint); }
.badge { display: inline-flex; align-items: center; border-radius: 999px; padding: .14rem .6rem; font-size: .7rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
.badge-pricing { color: var(--pricing); background: rgba(226, 179, 68, .12); }
.badge-breaking { color: var(--breaking); background: rgba(255, 91, 79, .12); }
.badge-minor { color: var(--minor); background: rgba(77, 163, 255, .12); }
.badge-needs-review { color: var(--needs-review); background: rgba(161, 161, 161, .12); }
.provider-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(215px, 1fr)); gap: .9rem; margin-top: 2.25rem; }
.card { display: flex; flex-direction: column; min-height: 8.5rem; padding: 1.15rem 1.2rem; background: var(--surface); border-radius: 10px; box-shadow: inset 0 0 0 1px var(--line); transition: box-shadow .15s ease; }
.card:hover { box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .2); }
.card h2 { margin-bottom: .3rem; font-size: 1.05rem; font-weight: 600; letter-spacing: -.02em; }
.card .count { margin-bottom: 1rem; font-size: .85rem; }
.card a { margin-top: auto; font-size: .85rem; font-weight: 600; }
.provider-heading { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }
.provider-heading .badge { margin-left: auto; }
.day { position: relative; margin-bottom: 2.25rem; padding-left: 1.4rem; border-left: 1px solid var(--line); }
.day-label { display: block; margin-bottom: .9rem; font-size: .72rem; font-weight: 500; letter-spacing: .1em; text-transform: uppercase; color: var(--faint); }
.day .change::before { content: ''; position: absolute; left: -1.71rem; top: 1.45rem; width: 7px; height: 7px; border-radius: 50%; background: var(--faint); }
.changes { display: grid; gap: .8rem; }
.change { position: relative; padding: 1.05rem 1.2rem; background: var(--surface); border-radius: 10px; box-shadow: inset 0 0 0 1px var(--line); }
.change h2 { margin: .7rem 0 .3rem; font-size: 1rem; font-weight: 600; letter-spacing: -.01em; line-height: 1.45; }
.change .meta { display: flex; align-items: center; gap: .65rem; flex-wrap: wrap; font-size: .8rem; }
.change code { display: block; overflow-x: auto; margin: .8rem 0 0; padding: .75rem .85rem; background: var(--bg); border-radius: 7px; box-shadow: inset 0 0 0 1px var(--line); color: var(--muted); font-size: .82rem; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }
.source { font-size: .8rem; }
.change.read { opacity: .38; }
.change.read .badge { filter: grayscale(1); }
.change .new-pill { display: none; margin-left: auto; border-radius: 999px; padding: .08rem .5rem; font-size: .65rem; font-weight: 600; letter-spacing: .08em; color: var(--minor); background: rgba(77, 163, 255, .12); }
.change:not(.read) .new-pill { display: inline-block; }
body.hide-read .change.read { display: none; }
.read-toggle { margin-top: .9rem; background: var(--surface); color: var(--muted); border: 0; border-radius: 7px; box-shadow: inset 0 0 0 1px var(--line); padding: .38rem .85rem; font-size: .82rem; font-weight: 500; cursor: pointer; }
.read-toggle:hover { color: var(--text); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .2); }
@media (max-width: 560px) { h1 { font-size: 1.7rem; } .shell { padding-top: 2.25rem; } }
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


def _provider_html(name: str, slug: str, changes) -> str:
    title = html.escape(name)
    # Timeline estilo changelog: agrupar por día (las changes ya vienen DESC)
    days = []
    for row in changes:
        day = (row["detected_at"] or "")[:10]
        if not days or days[-1][0] != day:
            days.append((day, []))
        days[-1][1].append(row)
    day_blocks = []
    for day, day_changes in days:
        items = []
        for row in day_changes:
            summary = html.escape(row["summary"] or "")
            evidence = html.escape(row["evidence"] or "")
            verdict_value = row["verdict"] or ""
            verdict = html.escape(verdict_value)
            verdict_class = _VERDICT_CLASSES.get(verdict_value, "badge-needs-review")
            detected_value = row["detected_at"] or ""
            detected = html.escape(detected_value)
            change_id = int(row["id"])
            source = html.escape(row["source_url"] or "", quote=True)
            # Solo esquemas http/https en href: un feed controla source_url y podría inyectar javascript:...
            source_url_raw = row["source_url"] or ""
            if source_url_raw.lower().startswith(("http://", "https://")):
                link = f'<a class="source" href="{source}" aria-label="source">source</a>'
            else:
                link = ""
            items.append(
                f'<article class="change" data-change-id="{change_id}"><div class="meta"><span class="badge {verdict_class}">{verdict}</span>'
                f'<time datetime="{detected}">{html.escape(detected_value[11:16])}</time> {link}<span class="new-pill">NEW</span></div>'
                f"<h2>{summary}</h2><code>{evidence}</code></article>"
            )
        day_blocks.append(f'<section class="day"><span class="day-label">{html.escape(day)}</span>{"".join(items)}</section>')
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><style>{_SITE_CSS}</style>"
        f"<title>{title} — Vigía</title></head><body><div class=\"shell\"><header>"
        f'<div class="provider-heading"><h1>{title}</h1><span class="badge">{len(changes)} changes</span></div>'
        '<button id="toggle-read" class="read-toggle" type="button">Hide read</button>'
        f"</header><main class=\"timeline\">{''.join(day_blocks)}</main></div>"
        f"<script>{_SITE_READ_TRACKER}</script></body></html>"
    )


def _index_html(providers) -> str:
    links = "".join(
        f'<article class="card"><h2>{html.escape(provider[1])}</h2><p class="count">{provider[2] if len(provider) > 2 else 0} recent changes</p>'
        f'<a href="providers/{html.escape(provider[0], quote=True)}/">view changes</a></article>'
        for provider in providers
    )
    generated = html.escape(datetime.now(timezone.utc).date().isoformat())
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><style>{_SITE_CSS}</style>"
        "<title>Vigía — Change radar for cloud/SaaS providers</title></head><body><div class=\"shell\"><header>"
        '<h1>Vigía</h1><p class="tagline">Change radar for cloud/SaaS providers</p>'
        f'<p class="generated">Generated: <time datetime="{generated}">{generated}</time></p>'
        f"</header><main class=\"provider-grid\">{links}</main></div></body></html>"
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
        _write(tmp_dir / "index.html", _index_html([(r["slug"], r["name"], len(grouped.get(r["slug"], []))) for r in providers]))
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
