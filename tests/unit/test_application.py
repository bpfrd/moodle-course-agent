from moodle_course_agent.moodle.templates import get_assign_templates


def test_bootstrap_exports_workspace(app):
    summary = app.bootstrap()
    assert summary.course_id == 42
    assert summary.exported_moodle_to_workspace is True
    assert app.workspace.exists("course.yaml")
    assert summary.moodle_modules >= 4
    assert summary.template_sections


def test_second_bootstrap_does_not_wipe_local_edits(app):
    app.bootstrap()
    app.workspace.write_text("course.yaml", app.workspace.read_text("course.yaml") + "# kept\n")
    summary = app.bootstrap()
    assert summary.exported_moodle_to_workspace is False
    assert "# kept" in app.workspace.read_text("course.yaml")


def test_moodle_write_then_snapshot_updates(app):
    app.bootstrap()
    before = len(app.moodle_snapshot.sections)
    app.moodle.create_section("Week 2", "<p>x</p>", position=before + 1)
    snap = app.refresh_moodle_snapshot()
    assert any(s.name == "Week 2" for s in snap.sections)


def test_assign_templates_found(app):
    mapping = get_assign_templates(app.moodle)
    assert "ohne_abgabe" in mapping
    assert "mit_abgabe" in mapping


def test_apply_sync_to_moodle_requires_approval(app):
    app.bootstrap()
    app.workspace.write_text(
        "sections/01-week-1/09-extra.md",
        "---\ntype: page\nname: Extra notes\nvisible: 1\n---\n\nHello\n",
    )
    app.refresh_workspace_snapshot()
    denied = app.apply_sync("to_moodle", approved=False)
    assert denied["ok"] is False
    names = [m["name"] for s in app.moodle.course for m in s.get("modules", [])]
    assert "Extra notes" not in names


def test_apply_sync_to_moodle_when_approved(app):
    app.bootstrap()
    app.workspace.write_text(
        "sections/01-week-1/09-extra.md",
        "---\ntype: page\nname: Extra notes\nvisible: 1\n---\n\nHello\n",
    )
    result = app.apply_sync("to_moodle", approved=True)
    assert result["ok"] is True
    names = [m["name"] for s in app.moodle.course for m in s.get("modules", [])]
    assert "Extra notes" in names
    text = app.workspace.read_text("sections/01-week-1/09-extra.md")
    assert "moodle_cmid:" in text


def test_moodle_write_updates_workspace(app):
    app.bootstrap()
    before = len(app.moodle.course)
    app.moodle.create_section("Week 2", "<p>x</p>", position=before + 1)
    written = app.after_moodle_write()
    files = " ".join(app.workspace.list_files()).lower()
    assert "week-2" in files or any("week 2" in app.workspace.read_text(p).lower() for p in app.workspace.list_files())
    assert written
