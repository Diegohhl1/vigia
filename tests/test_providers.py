import sqlite3
from pathlib import Path

from vigia.db import init_db
from vigia.providers import load_providers


def test_load_is_idempotent_and_upserts_catalog(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.sqlite3")
    init_db(conn)
    yaml_path = Path("config/providers.yaml")

    first = load_providers(conn, yaml_path)
    second = load_providers(conn, yaml_path)

    assert first == {"providers_added": 6, "sources_added": 8, "updated": 0, "disabled": 0}
    assert second == {"providers_added": 0, "sources_added": 0, "updated": 0, "disabled": 0}


def test_removed_source_is_disabled_and_readded_source_is_reactivated(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.sqlite3")
    init_db(conn)
    original = Path("config/providers.yaml").read_text()
    yaml_path = tmp_path / "providers.yaml"
    yaml_path.write_text(original)
    load_providers(conn, yaml_path)

    removed_source = "      - kind: rss\n        url: https://aws.amazon.com/blogs/aws/feed/\n        enabled: true\n"
    yaml_path.write_text(original.replace(removed_source, ""))
    result = load_providers(conn, yaml_path)
    assert result["disabled"] == 1
    assert conn.execute("SELECT enabled FROM sources WHERE url = 'https://aws.amazon.com/blogs/aws/feed/'").fetchone()[0] == 0

    yaml_path.write_text(original)
    result = load_providers(conn, yaml_path)
    assert result["disabled"] == 0
    assert conn.execute("SELECT enabled FROM sources WHERE url = 'https://aws.amazon.com/blogs/aws/feed/'").fetchone()[0] == 1
