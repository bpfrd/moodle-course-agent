"""End-to-end workflow: inspect, edit locally, preview, reject, approve, persist."""

from moodle_course_agent.models import ChangeKind


def test_full_sync_approval_and_state(app):
    summary = app.bootstrap()
    assert app.store.load_moodle_snapshot() is not None
    assert app.store.load_workspace_snapshot() is not None
    record = app.store.load_sync_record()
    assert record.items

    app.workspace.write_text(
        "sections/01-week-1/08-lab.md",
        "---\ntype: page\nname: Lab notes\nvisible: 1\n---\n\nLab body\n",
    )
    plan = app.preview_sync("to_moodle")
    creates = [a for a in plan.actions if a.kind == ChangeKind.CREATE_ON_MOODLE]
    assert any(a.name == "Lab notes" for a in creates)
    assert plan.counts.get("moodle_mutations", 0) >= 1

    denied = app.apply_sync("to_moodle", approved=False)
    assert denied["ok"] is False
    assert "Lab notes" not in [m["name"] for s in app.moodle.course for m in s["modules"]]

    approved = app.apply_sync("to_moodle", approved=True)
    assert approved["ok"] is True
    assert "Lab notes" in [m["name"] for s in app.moodle.course for m in s["modules"]]

    persisted = app.store.load_moodle_snapshot()
    names = [m.name for s in persisted.sections for m in s.modules]
    assert "Lab notes" in names

    # Pull direction writes files without Moodle mutation count
    app.moodle.create_label(1, "<p>New remote label</p>", name="Remote banner")
    app.refresh_moodle_snapshot()
    pulled = app.apply_sync("to_local", approved=True)
    assert pulled["ok"] is True
    files = " ".join(app.workspace.list_files())
    assert "remote-banner" in files or any("Remote" in app.workspace.read_text(p) for p in app.workspace.list_files() if p.endswith(".md"))
