"""Carga y sincronización del catálogo de proveedores y fuentes."""

from pathlib import Path
import sqlite3

import yaml


def load_providers(conn: sqlite3.Connection, path: Path | str) -> dict[str, int]:
    """Sincroniza ``providers.yaml`` con SQLite de forma idempotente.

    Las fuentes ausentes del YAML se conservan para no romper referencias históricas,
    pero quedan deshabilitadas. Una fuente que vuelve a aparecer se reactiva.
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    providers = data.get("providers", [])
    result = {"providers_added": 0, "sources_added": 0, "updated": 0, "disabled": 0}
    configured_urls: set[str] = set()

    with conn:
        for provider in providers:
            slug = provider["slug"]
            existing = conn.execute("SELECT id, name FROM providers WHERE slug = ?", (slug,)).fetchone()
            if existing is None:
                cursor = conn.execute("INSERT INTO providers (slug, name) VALUES (?, ?)", (slug, provider["name"]))
                provider_id = cursor.lastrowid
                result["providers_added"] += 1
            else:
                provider_id = existing[0]
                if existing[1] != provider["name"]:
                    conn.execute("UPDATE providers SET name = ? WHERE id = ?", (provider["name"], provider_id))
                    result["updated"] += 1

            for source in provider.get("sources", []):
                url = source["url"]
                configured_urls.add(url)
                enabled = 1 if source.get("enabled", True) else 0
                existing_source = conn.execute(
                    "SELECT id, provider_id, kind, selector, enabled FROM sources WHERE url = ?", (url,)
                ).fetchone()
                if existing_source is None:
                    conn.execute(
                        """INSERT INTO sources (provider_id, kind, url, selector, enabled)
                           VALUES (?, ?, ?, ?, ?)""",
                        (provider_id, source["kind"], url, source.get("selector"), enabled),
                    )
                    result["sources_added"] += 1
                else:
                    values = (provider_id, source["kind"], source.get("selector"), enabled)
                    current = existing_source[1:]
                    if current != values:
                        conn.execute(
                            """UPDATE sources SET provider_id = ?, kind = ?, selector = ?, enabled = ?
                               WHERE id = ?""",
                            (*values, existing_source[0]),
                        )
                        result["updated"] += 1

        rows = conn.execute("SELECT id, url FROM sources WHERE enabled = 1").fetchall()
        for source_id, url in rows:
            if url not in configured_urls:
                conn.execute("UPDATE sources SET enabled = 0 WHERE id = ?", (source_id,))
                result["disabled"] += 1

    return result
