"""Daily internal Telegram digest."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx


_RELEVANT = ("pricing", "breaking", "minor")
_EMOJI = {"pricing": "💰", "breaking": "🚨", "minor": "ℹ️"}
_MAX_MESSAGE = 4000


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _blocks(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row["provider_name"], []).append(row)
    result = []
    for provider, changes in groups.items():
        lines = [f"{provider}"]
        for row in changes:
            label = _EMOJI.get(row["verdict"], row["verdict"])
            lines.append(f"{label} {row['summary']}")
        result.append("\n".join(lines))
    return result


def build_digest(conn, since: datetime) -> str:
    """Build a plain-text digest, preserving complete provider blocks."""
    rows = conn.execute(
        """
        SELECT c.*, p.name AS provider_name
        FROM changes c
        JOIN sources s ON s.id = c.source_id
        JOIN providers p ON p.id = s.provider_id
        WHERE c.detected_at >= ?
        ORDER BY p.name, c.detected_at DESC, c.id DESC
        """,
        (_iso(since),),
    ).fetchall()
    relevant = [row for row in rows if row["verdict"] in _RELEVANT]
    if relevant:
        rows = relevant
    else:
        rows = [row for row in rows if row["verdict"] == "needs_review"]
    if not rows:
        return "Sin cambios relevantes en las últimas 24h"
    blocks = _blocks(rows)
    selected = []
    length = 0
    oversized = False
    for block in blocks:
        if len(block) > _MAX_MESSAGE:
            # Keep a huge provider visible, then keep evaluating later providers.
            selected.append(block[:_MAX_MESSAGE])
            oversized = True
            continue
        added = len(block) if not selected else len(block) + 2
        if not oversized and length + added > _MAX_MESSAGE:
            break
        selected.append(block)
        length += added
    return "\n\n".join(selected)


def send_digest(text: str, token: str, chat_id: str) -> bool:
    """Send a Telegram message; transport/API failures are reported as False."""
    if not token or not os.environ.get("VIGIA_TG_TOKEN", token):
        return False
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
        return response.is_success
    except Exception:
        return False


def record_delivery(
    conn,
    text: str,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    sent_at: datetime | None = None,
    sent: bool = True,
) -> bool:
    """Record a successful delivery; call this only after ``send_digest`` returns True."""
    if not sent:
        return False
    period_end = period_end or datetime.now(timezone.utc)
    period_start = period_start or period_end
    conn.execute(
        "INSERT INTO digests (period_start, period_end, sent_at, content) VALUES (?, ?, ?, ?)",
        (_iso(period_start), _iso(period_end), _iso(sent_at or datetime.now(timezone.utc)), text),
    )
    conn.commit()
    return True
