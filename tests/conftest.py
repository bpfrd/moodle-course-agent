"""Shared pytest fixtures.

The files listed in ``collect_ignore`` are integration scripts (they execute
real API calls on import) - they are meant to be run with
``python tests/test_xxx.py``, NOT picked up automatically by ``pytest``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the project root importable so ``moodle_client`` and ``agent`` resolve.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tests.fakes import FakeMoodleClient  # noqa: E402

# Integration scripts that hit a real Moodle server. Pytest must skip them
# during collection so it does not accidentally create test content on
# Moodle just by running `pytest`.
collect_ignore = [
    "test_sections.py",
    "test_labels.py",
    "test_pages.py",
    "test_urls.py",
    "test_assigns.py",
    "test_forums.py",
]


@pytest.fixture
def fake_client() -> FakeMoodleClient:
    """A FakeMoodleClient seeded with a small but realistic course."""
    initial = [
        {
            "id": 1,
            "section": 0,
            "name": "General",
            "summary": "<p>intro</p>",
            "visible": 1,
            "modules": [
                {
                    "id": 100,
                    "modname": "label",
                    "name": "Welcome label",
                    "visible": 1,
                    "visibleoncoursepage": 1,
                },
            ],
        },
        {
            "id": 2,
            "section": 1,
            "name": "Week 1",
            "summary": "<p>week one</p>",
            "visible": 1,
            "modules": [
                {
                    "id": 101,
                    "modname": "page",
                    "name": "Syllabus",
                    "visible": 1,
                    "visibleoncoursepage": 1,
                },
                {
                    "id": 102,
                    "modname": "assign",
                    "name": "Homework 1",
                    "visible": 1,
                    "visibleoncoursepage": 1,
                },
            ],
        },
    ]
    client = FakeMoodleClient(courseid=42, initial_course=initial)
    client._module_bodies = {
        100: {"labelcontent": "<p>welcome</p>"},
        101: {
            "intro": "<p>intro</p>",
            "pagecontent": "<p>syllabus body</p>",
            "showdescription": 0,
        },
        102: {
            "intro": "<p>do this</p>",
            "activity": "<p>questions</p>",
            "duedate": 0,
        },
    }
    client._next_cmid = 103
    return client
