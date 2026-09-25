"""Tests de validación de fixtures capturados en preflight."""
import pytest
import feedparser
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Todos los feeds XML deben ser válidos
XML_FIXTURES = [
    "aws.xml",
    "aws-blog.xml",
    "gcp.xml",
    "github.xml",
    "github-status.xml",
    "twilio.xml",
    "cloudflare.xml",
    "sentry.xml",
]


@pytest.mark.parametrize("fixture_name", XML_FIXTURES)
def test_feed_fixture_is_valid(fixture_name):
    """Cada fixture XML debe parsear sin errores (bozo=False) y tener >=1 entrada."""
    fixture_path = FIXTURES_DIR / fixture_name
    assert fixture_path.exists(), f"Fixture {fixture_name} no existe"

    d = feedparser.parse(str(fixture_path))

    assert d.bozo == False, f"{fixture_name}: bozo={d.bozo}, error={getattr(d, 'bozo_exception', None)}"
    assert len(d.entries) >= 1, f"{fixture_name}: debe tener al menos 1 entrada, tiene {len(d.entries)}"


@pytest.mark.parametrize("fixture_name", XML_FIXTURES)
def test_feed_fixture_has_required_fields(fixture_name):
    """Cada entrada del feed debe tener título y enlace."""
    fixture_path = FIXTURES_DIR / fixture_name
    d = feedparser.parse(str(fixture_path))

    assert len(d.entries) > 0
    first_entry = d.entries[0]

    assert hasattr(first_entry, 'title') and first_entry.title, f"{fixture_name}: primera entrada sin título"
    assert hasattr(first_entry, 'link') and first_entry.link, f"{fixture_name}: primera entrada sin enlace"
