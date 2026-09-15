"""Optional live smoke tests. Skipped unless RUN_LIVE_SMOKE=1.

These hit real Moodle / LLM endpoints using moodle-course-app/.env.
They never print secrets.
"""

from __future__ import annotations

import os

import pytest

from moodle_course_agent.app import CourseApplication
from moodle_course_agent.config import load_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_SMOKE") != "1",
    reason="Set RUN_LIVE_SMOKE=1 to hit live Moodle / LLM",
)


def test_live_moodle_bootstrap():
    settings = load_settings()
    if settings.moodle_mock:
        pytest.skip("MOODLE_MOCK is enabled")
    settings.require_moodle()
    app = CourseApplication(settings)
    summary = app.bootstrap()
    assert app.moodle_snapshot is not None
    assert app.moodle_snapshot.course_id == settings.course_id
    assert summary.moodle_sections >= 1
