"""Regression tests: sync must never silently discard one side's changes."""

from moodle_course_agent.models import ChangeKind
from moodle_course_agent.moodle import iter_moodle_methods
from moodle_course_agent.tools import build_tools


def _module_path(app, name):
    snapshot = app.refresh_workspace_snapshot()
    return next(m.local_id for s in snapshot.sections for m in s.modules if m.name == name)


def _cmid(app, name):
    return next(m["id"] for s in app.moodle.course for m in s["modules"] if m["name"] == name)


def _section(app, name):
    return next(s for s in app.moodle.course if s["name"] == name)


def test_moodle_write_keeps_unsynced_local_edit(app):
    app.bootstrap()
    path = _module_path(app, "Homework 1")
    app.workspace.write_text(path, app.workspace.read_text(path) + "\nLocal draft paragraph\n")

    # Two unrelated Moodle writes, each followed by the automatic workspace refresh.
    app.moodle.update_label(_cmid(app, "Welcome"), "Welcome", "<p>Remote welcome</p>")
    app.after_moodle_write()
    app.moodle.update_label(_cmid(app, "Welcome"), "Welcome", "<p>Remote welcome again</p>")
    app.after_moodle_write()

    assert "Local draft paragraph" in app.workspace.read_text(path)
    assert "Remote welcome again" in app.workspace.read_text(_module_path(app, "Welcome"))
    pending = app.preview_sync("to_moodle")
    assert any(
        a.kind == ChangeKind.UPDATE_ON_MOODLE and a.name == "Homework 1" for a in pending.actions
    ), pending.counts


def test_push_does_not_revert_moodle_only_change(app):
    app.bootstrap()
    app.moodle.update_page(
        _cmid(app, "Syllabus"), "Syllabus", "<p>Overview</p>", "<p>Remote syllabus edit</p>"
    )
    path = _module_path(app, "Homework 1")
    app.workspace.write_text(path, app.workspace.read_text(path) + "\nLocal homework edit\n")

    result = app.apply_sync("to_moodle", approved=True)
    assert result["ok"] is True

    assert "Remote syllabus edit" in app.moodle.get_page(_cmid(app, "Syllabus"))["pagecontent"]
    assert "Local homework edit" in app.moodle.get_assign(_cmid(app, "Homework 1"))["activity"]
    assert "Remote syllabus edit" in app.workspace.read_text(_module_path(app, "Syllabus"))
    assert app.preview_sync("preview").counts["total"] == 0


def test_pull_does_not_revert_local_only_change(app):
    app.bootstrap()
    path = _module_path(app, "Homework 1")
    app.workspace.write_text(path, app.workspace.read_text(path) + "\nLocal only\n")
    app.moodle.update_label(_cmid(app, "Welcome"), "Welcome", "<p>Remote welcome</p>")

    assert app.apply_sync("to_local", approved=True)["ok"] is True
    assert "Local only" in app.workspace.read_text(path)
    assert "Remote welcome" in app.workspace.read_text(_module_path(app, "Welcome"))


def test_conflict_survives_unrelated_moodle_write(app):
    app.bootstrap()
    path = _module_path(app, "Homework 1")
    app.workspace.write_text(path, app.workspace.read_text(path) + "\nLocal side\n")
    app.moodle.update_assign(_cmid(app, "Homework 1"), "Homework 1", "<p>Remote side</p>", "<p>x</p>")
    app.after_moodle_write()
    app.moodle.update_label(_cmid(app, "Welcome"), "Welcome", "<p>Unrelated</p>")
    app.after_moodle_write()

    assert "Local side" in app.workspace.read_text(path)
    plan = app.preview_sync("preview")
    assert any(a.kind == ChangeKind.CONFLICT and a.name == "Homework 1" for a in plan.actions)


def test_push_keeps_hidden_sections_hidden(app):
    app.bootstrap()
    app.workspace.write_text(
        "sections/09-drafts/section.yaml", "name: Drafts\nsummary: ''\nvisible: 0\n"
    )
    app.workspace.write_text(
        "sections/09-drafts/01-note.md", "---\ntype: label\nname: Note\nvisible: 0\n---\n\nHidden note\n"
    )
    template_dir = next(
        s.local_id for s in app.refresh_workspace_snapshot().sections if s.is_template_section
    )
    yaml_path = f"{template_dir}/section.yaml"
    app.workspace.write_text(
        yaml_path, app.workspace.read_text(yaml_path).replace("Templates", "Templates (edited)")
    )

    assert app.apply_sync("to_moodle", approved=True)["ok"] is True
    assert _section(app, "Drafts")["visible"] == 0
    template = _section(app, app.settings.template_section_name)
    assert "edited" in template["summary"]
    assert template["visible"] == 0


def test_push_keeps_zero_grade(app):
    app.bootstrap()
    path = _module_path(app, "Homework 1")
    text = app.workspace.read_text(path).replace("grade: 100", "grade: 0")
    app.workspace.write_text(path, text)
    assert app.apply_sync("to_moodle", approved=True)["ok"] is True
    assert app.moodle.get_assign(_cmid(app, "Homework 1"))["grade"] == 0


def test_new_assign_uses_requested_template(app):
    app.bootstrap()
    app.workspace.write_text(
        "sections/01-week-1/07-essay.md",
        "---\ntype: assign\nname: Essay\ntemplate: mit_abgabe\n---\n\nWrite it\n\n"
        "<!-- moodle:activity -->\n\nSubmit a PDF\n",
    )
    assert app.apply_sync("to_moodle", approved=True)["ok"] is True
    copies = [c for c in app.moodle.calls if c["method"] == "copy_module"]
    assert copies and copies[-1]["cmid"] == _cmid(app, "Vorlage: Aufgabe mit Abgabe")
    essay_section = next(s for s in app.moodle.course if any(m["name"] == "Essay" for m in s["modules"]))
    assert essay_section["name"] == "Week 1"


def test_new_assign_in_empty_section_lands_in_that_section(app):
    app.bootstrap()
    app.workspace.write_text("sections/09-extra/section.yaml", "name: Extra\nsummary: ''\nvisible: 1\n")
    app.workspace.write_text(
        "sections/09-extra/01-task.md",
        "---\ntype: assign\nname: Extra task\n---\n\nIntro\n\n<!-- moodle:activity -->\n\nDo it\n",
    )
    copies_before = len([c for c in app.moodle.calls if c["method"] == "copy_module"])
    assert app.apply_sync("to_moodle", approved=True)["ok"] is True
    # copy_module(beforemod=0) cannot target an empty section, so create directly there.
    assert len([c for c in app.moodle.calls if c["method"] == "copy_module"]) == copies_before
    assert [m["name"] for m in _section(app, "Extra")["modules"]] == ["Extra task"]
    template = _section(app, app.settings.template_section_name)
    assert "Extra task" not in [m["name"] for m in template["modules"]]


def test_failed_template_update_does_not_create_duplicate(app, monkeypatch):
    app.bootstrap()
    app.workspace.write_text(
        "sections/01-week-1/07-essay.md",
        "---\ntype: assign\nname: Essay\n---\n\nIntro\n\n<!-- moodle:activity -->\n\nBody\n",
    )

    def broken_update(*args, **kwargs):
        raise RuntimeError("update failed")

    monkeypatch.setattr(app.moodle, "update_assign", broken_update)
    result = app.apply_sync("to_moodle", approved=True)
    assert result["ok"] is False
    assert not [c for c in app.moodle.calls if c["method"] == "create_assign" and c.get("name") == "Essay"]
    error = next(r["error"] for r in result["results"] if r.get("ok") is False)
    assert "copied template" in error.lower()


def test_delete_module_is_not_exposed(app):
    names = {name for name, *_ in iter_moodle_methods(app.moodle)}
    assert "delete_module" not in names
    tool_names = {getattr(t, "tool_name", None) or t.tool_spec["name"] for t in build_tools(app)}
    assert "delete_module" not in tool_names
