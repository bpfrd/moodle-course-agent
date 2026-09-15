from moodle_course_agent.moodle.snapshot import build_moodle_snapshot, compact_summary


def test_snapshot_includes_bodies(moodle):
    snap = build_moodle_snapshot(moodle, template_section_name="Modulentwicklung [RK only]")
    assert snap.course_id == 42
    assert len(snap.sections) == 3
    homework = next(m for s in snap.sections for m in s.modules if m.name == "Homework 1")
    assert homework.modname == "assign"
    assert homework.cmid is not None
    assert homework.content_hash
    assert "First assignment" in (homework.fields.get("intro") or "")


def test_template_section_flagged(moodle):
    snap = build_moodle_snapshot(moodle, template_section_name="Modulentwicklung [RK only]")
    templates = [s for s in snap.sections if s.is_template_section]
    assert templates
    names = {m.name for m in templates[0].modules}
    assert "Vorlage: Aufgabe ohne Abgabe" in names


def test_compact_summary_omits_html(moodle):
    snap = build_moodle_snapshot(moodle, template_section_name="Modulentwicklung [RK only]")
    summary = compact_summary(snap)
    blob = str(summary)
    assert "labelcontent" not in blob
    assert "pagecontent" not in blob
    assert any(s["name"] == "Week 1" for s in summary)
