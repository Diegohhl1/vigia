"""Diff de texto a nivel de oración, con prioridad para cambios de impacto."""

from __future__ import annotations

from difflib import SequenceMatcher
import re


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_PRIORITY = re.compile(
    r"(?:\$|€|\b(?:USD|EUR)\b|\b\d+(?:[.,]\d+)?\s*(?:month|months|year|years)\b|"
    r"\b\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?\b|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2}(?:,?\s+\d{4})?\b|\b(?:deprecated|deprecat|remov|removed|removal|breaking|"
    r"sunset|end-of-life|EOL))",
    re.IGNORECASE,
)


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(text or "") if part.strip()]


def _prioritised(parts: list[str], limit: int = 4000) -> list[str]:
    ranked = sorted(enumerate(parts), key=lambda item: (not bool(_PRIORITY.search(item[1])), item[0]))
    selected: list[tuple[int, str]] = []
    size = 0
    for index, part in ranked:
        extra = len(part) if not selected else len(part) + 1
        remaining = limit - size - (1 if selected else 0)
        if remaining <= 0:
            continue
        selected.append((index, part[:remaining]))
        size += (1 if len(selected) > 1 else 0) + min(len(part), remaining)
    return [part for _, part in sorted(selected)]


def extract_diff(old: str, new: str) -> dict[str, list[str] | str]:
    """Devuelve frases añadidas/eliminadas y sus lados antes/después.

    Los bloques ``replace`` representan una edición: la frase anterior queda en
    ``removed`` y la nueva en ``added`` para que el clasificador vea ambos lados.
    """
    old_parts = _sentences(old)
    new_parts = _sentences(new)
    added: list[str] = []
    removed: list[str] = []
    matcher = SequenceMatcher(a=old_parts, b=new_parts, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(old_parts[i1:i2])
        if tag in ("replace", "insert"):
            added.extend(new_parts[j1:j2])
    combined = [("added", part) for part in added] + [("removed", part) for part in removed]
    ranked = sorted(enumerate(combined), key=lambda item: (not bool(_PRIORITY.search(item[1][1])), item[0]))
    selected: list[tuple[int, str, str]] = []
    size = 0
    for index, (kind, part) in ranked:
        remaining = 4000 - size - (1 if selected else 0)
        if remaining <= 0:
            continue
        clipped = part[:remaining]
        selected.append((index, kind, clipped))
        size += (1 if len(selected) > 1 else 0) + len(clipped)
    selected.sort()
    added = [part for _, kind, part in selected if kind == "added"]
    removed = [part for _, kind, part in selected if kind == "removed"]
    return {
        "added": added,
        "removed": removed,
        "before": " ".join(removed),
        "after": " ".join(added),
    }
