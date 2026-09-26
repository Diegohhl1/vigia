"""Tests for vigia smoke subcommand."""

from __future__ import annotations

import sys
from io import StringIO
from unittest.mock import patch, MagicMock

from vigia.cli import main


def test_smoke_with_limit():
    """vigia smoke --limit 2 calls run_all and prints summary."""
    fake_report = {
        "sources_processed": 2,
        "changes_created": 1,
        "errors": [],
    }

    with patch("vigia.cli.run_all", return_value=fake_report) as mock_run, \
         patch("vigia.cli.get_conn") as mock_conn, \
         patch("httpx.Client") as mock_client, \
         patch("sys.argv", ["vigia", "smoke", "--limit", "2"]):

        stdout = StringIO()
        with patch("sys.stdout", stdout):
            main()

        output = stdout.getvalue()
        assert "Sources processed: 2" in output
        assert "Changes created: 1" in output
        assert "Errors: 0" in output
        assert "Duration:" in output
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["limit"] == 2


def test_smoke_exit_code_on_errors():
    """vigia smoke exits with code 1 if errors exist."""
    fake_report = {
        "sources_processed": 2,
        "changes_created": 0,
        "errors": [{"source_id": 1, "error": "timeout"}],
    }

    with patch("vigia.cli.run_all", return_value=fake_report), \
         patch("vigia.cli.get_conn"), \
         patch("httpx.Client"), \
         patch("sys.argv", ["vigia", "smoke", "--limit", "1"]), \
         patch("sys.exit") as mock_exit:

        main()
        mock_exit.assert_called_once_with(1)
