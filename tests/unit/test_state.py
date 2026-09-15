from moodle_course_agent.models import CourseSnapshot, utcnow
from moodle_course_agent.state import StateStore


def test_snapshot_and_memory_roundtrip(tmp_path):
    store = StateStore(tmp_path / "data")
    snap = CourseSnapshot(
        course_id=1,
        title="T",
        source="moodle",
        fetched_at=utcnow(),
        sections=[],
    )
    store.save_moodle_snapshot(snap)
    loaded = store.load_moodle_snapshot()
    assert loaded is not None
    assert loaded.course_id == 1
    store.remember("lang", "de")
    memory = store.load_memory()
    assert memory.facts[-1].value == "de"
    store.set_last_session_id("abc")
    assert store.last_session_id() == "abc"
