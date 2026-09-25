"""Tests para el esquema de base de datos."""
import sqlite3
from pathlib import Path
from vigia.db import init_db, get_conn


def test_init_db_creates_all_tables(tmp_path):
    """Verifica que init_db crea todas las tablas requeridas."""
    conn = sqlite3.connect(tmp_path / "t.sqlite3")
    init_db(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"providers", "sources", "snapshots", "entries", "changes", "digests"} <= names


def test_changes_has_expected_columns(tmp_path):
    """Verifica que changes tiene todas las columnas requeridas, incluyendo las de v2."""
    conn = sqlite3.connect(tmp_path / "t.sqlite3")
    init_db(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(changes)")}
    required = {
        "id", "source_id", "detected_at", "verdict", "score", "summary",
        "evidence", "diff_text", "old_excerpt", "new_excerpt", "source_url",
        "model", "prompt_version", "review_status"
    }
    assert required <= cols


def test_sources_has_extra_columns_v2(tmp_path):
    """Verifica que sources tiene las columnas extra de la revisión v2."""
    conn = sqlite3.connect(tmp_path / "t.sqlite3")
    init_db(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sources)")}
    extra = {
        "last_modified", "last_checked_at", "last_success_at",
        "failure_count", "last_error", "robots_checked_at"
    }
    assert extra <= cols


def test_entries_table_exists_with_unique_constraint(tmp_path):
    """Verifica que entries existe con external_id y constraint UNIQUE(source_id, external_id)."""
    conn = sqlite3.connect(tmp_path / "t.sqlite3")
    init_db(conn)

    # Verificar que la tabla existe
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "entries" in names

    # Verificar columnas
    cols = {r[1] for r in conn.execute("PRAGMA table_info(entries)")}
    required = {"id", "source_id", "external_id", "url", "published_at", "content_hash", "content"}
    assert required <= cols

    # Verificar constraint UNIQUE - intentar insertar duplicado debe fallar
    conn.execute("INSERT INTO providers (slug, name) VALUES ('test', 'Test')")
    conn.execute("INSERT INTO sources (provider_id, kind, url) VALUES (1, 'rss', 'http://test')")
    conn.execute("""
        INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content)
        VALUES (1, 'ext-123', 'http://test/1', '2026-01-01', 'hash1', 'content1')
    """)

    try:
        conn.execute("""
            INSERT INTO entries (source_id, external_id, url, published_at, content_hash, content)
            VALUES (1, 'ext-123', 'http://test/2', '2026-01-02', 'hash2', 'content2')
        """)
        assert False, "Debería fallar por UNIQUE constraint"
    except sqlite3.IntegrityError:
        pass  # Esperado


def test_pragmas_are_set(tmp_path):
    """Verifica que los PRAGMAs requeridos están activos."""
    db_path = tmp_path / "t.sqlite3"
    conn = get_conn(str(db_path))

    # foreign_keys debe estar ON
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1, "foreign_keys debe estar ON"

    # journal_mode debe ser WAL
    jm = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert jm.upper() == "WAL", "journal_mode debe ser WAL"

    # busy_timeout debe estar configurado (>0)
    bt = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert bt > 0, "busy_timeout debe estar configurado"


def test_get_conn_creates_and_initializes_db(tmp_path):
    """Verifica que get_conn crea e inicializa la BD si no existe."""
    db_path = tmp_path / "new.sqlite3"
    assert not db_path.exists()

    conn = get_conn(str(db_path))
    assert db_path.exists()

    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "providers" in names
