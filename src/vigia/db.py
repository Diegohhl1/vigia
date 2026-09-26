"""Gestión de la base de datos SQLite de Vigía."""
import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS providers (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY,
  provider_id INTEGER NOT NULL REFERENCES providers(id),
  kind TEXT NOT NULL CHECK(kind IN ('rss','html')),
  url TEXT UNIQUE NOT NULL,
  selector TEXT,
  etag TEXT,
  last_hash TEXT,
  enabled INTEGER DEFAULT 1,
  last_modified TEXT,
  last_checked_at TEXT,
  last_success_at TEXT,
  failure_count INTEGER DEFAULT 0,
  last_error TEXT,
  robots_checked_at TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  taken_at TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  external_id TEXT NOT NULL,
  url TEXT NOT NULL,
  published_at TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  content TEXT NOT NULL,
  UNIQUE(source_id, external_id)
);

CREATE TABLE IF NOT EXISTS changes (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  detected_at TEXT NOT NULL,
  verdict TEXT NOT NULL CHECK(verdict IN ('noise','minor','pricing','breaking','needs_review')),
  score INTEGER NOT NULL DEFAULT 0,
  summary TEXT NOT NULL DEFAULT '',
  evidence TEXT NOT NULL DEFAULT '',
  diff_text TEXT NOT NULL,
  old_excerpt TEXT,
  new_excerpt TEXT,
  source_url TEXT,
  model TEXT,
  prompt_version TEXT,
  review_status TEXT
);

CREATE TABLE IF NOT EXISTS digests (
  id INTEGER PRIMARY KEY,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  sent_at TEXT,
  content TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_changes_source ON changes(source_id, detected_at);
CREATE INDEX IF NOT EXISTS idx_entries_source ON entries(source_id, external_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_changes_dedupe ON changes(source_id, IFNULL(source_url,''), diff_text);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Inicializa el esquema de la base de datos.

    Configura PRAGMAs (foreign_keys, WAL, busy_timeout) y crea todas las tablas.
    """
    conn.executescript(SCHEMA)
    conn.commit()


def get_conn(path: str = "vigia.sqlite3") -> sqlite3.Connection:
    """Obtiene una conexión a la BD, creándola e inicializándola si no existe.

    Args:
        path: Ruta al fichero de base de datos.

    Returns:
        Conexión SQLite con Row factory configurado.
    """
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    # Siempre inicializar schema (CREATE TABLE IF NOT EXISTS es idempotente)
    init_db(conn)

    return conn
