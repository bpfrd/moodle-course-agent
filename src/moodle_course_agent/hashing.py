"""Deterministic content hashing for snapshots and conflict detection."""

from __future__ import annotations

import hashlib
import json
from typing import Any

_HTML_KEYS = {
    "summary",
    "labelcontent",
    "pagecontent",
    "intro",
    "activity",
}


def normalize_text(value: str) -> str:
    """Collapse HTML/Markdown to comparable plaintext so export round-trips match."""
    if not value:
        return ""
    text = value
    if "<" in value and ">" in value:
        from markdownify import markdownify as to_md

        text = to_md(value, heading_style="ATX")
    return " ".join(text.split()).strip().lower()


def normalize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                normalize_text(val)
                if key in _HTML_KEYS and isinstance(val, str)
                else normalize_payload(val)
            )
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [normalize_payload(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(normalize_payload(value), ensure_ascii=False, sort_keys=True, default=str)


def content_hash(value: Any) -> str:
    payload = canonical_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
