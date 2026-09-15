from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from moodle_course_agent.app import CourseApplication, seed_demo_client
from moodle_course_agent.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    skills = ROOT / "skills"
    return Settings(
        moodle_mock=True,
        course_id=42,
        workspace_dir=tmp_path / "workspace",
        data_dir=tmp_path / "data",
        skills_dir=skills,
        openai_api_key="test",
    ).resolve(tmp_path)


@pytest.fixture
def moodle():
    return seed_demo_client()


@pytest.fixture
def app(settings, moodle) -> CourseApplication:
    return CourseApplication(settings, moodle=moodle)
