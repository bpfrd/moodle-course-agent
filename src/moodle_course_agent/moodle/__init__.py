"""Moodle REST client exports and a small API surface helper."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from moodle_course_agent.moodle.client import MoodleAPIError, MoodleClient
from moodle_course_agent.moodle.fakes import FakeMoodleClient

__all__ = [
    "MoodleAPIError",
    "MoodleClient",
    "FakeMoodleClient",
    "is_moodle_write",
    "iter_moodle_methods",
]

_SKIP = {"call", "dump", "close", "course"}
_WRITE_PREFIXES = ("create_", "update_", "move_", "copy_", "delete_")

_DOCS: dict[str, str] = {
    "create_section": "Create a Moodle section. position is 1-indexed.",
    "update_section": "Update a Moodle section name, summary, and visibility.",
    "move_section": "Move a Moodle section to a 1-indexed position.",
    "get_module": "Raw Moodle course-module record by cmid.",
    "get_label": "Full label content by cmid.",
    "get_page": "Full page content by cmid.",
    "get_url": "Full URL resource by cmid.",
    "get_forum": "Full forum by cmid.",
    "get_assign": "Full assignment by cmid.",
    "create_label": "Create a label in a section.",
    "update_label": "Update a label.",
    "create_page": "Create a page in a section.",
    "update_page": "Update a page.",
    "create_url": "Create a URL resource in a section.",
    "update_url": "Update a URL resource.",
    "create_forum": "Create a forum in a section.",
    "update_forum": "Update a forum.",
    "create_assign": "Create an assignment from scratch.",
    "update_assign": "Update an assignment.",
    "move_module": "Move a module. beforemod=0 appends.",
    "copy_module": "Duplicate a module. beforemod=0 appends.",
    "delete_module": "Delete a module if the Moodle plugin supports it.",
}


def is_moodle_write(name: str) -> bool:
    return name.startswith(_WRITE_PREFIXES)


def iter_moodle_methods(client: Any) -> list[tuple[str, Callable[..., Any], bool, str]]:
    """Public Moodle client methods: (name, bound method, writes_moodle, doc)."""
    items: list[tuple[str, Callable[..., Any], bool, str]] = []
    for name, method in inspect.getmembers(client, inspect.ismethod):
        if name.startswith("_") or name in _SKIP:
            continue
        doc = inspect.getdoc(method) or _DOCS.get(name) or f"Moodle API: {name}"
        items.append((name, method, is_moodle_write(name), doc))
    return items
