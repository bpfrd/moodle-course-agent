from moodle_course_agent.models import ChangeKind, SyncRecord, utcnow
from moodle_course_agent.moodle.snapshot import build_moodle_snapshot
from moodle_course_agent.sync import build_sync_plan, record_from_snapshots
from moodle_course_agent.workspace import build_workspace_snapshot, export_snapshot_to_workspace


def _snaps(app):
    moodle = build_moodle_snapshot(app.moodle, template_section_name=app.settings.template_section_name)
    export_snapshot_to_workspace(app.workspace, moodle, overwrite=True)
    local = build_workspace_snapshot(app.workspace, course_id=42)
    return moodle, local


def test_matching_export_has_no_meaningful_diff(app):
    moodle, local = _snaps(app)
    plan = build_sync_plan(moodle, local, SyncRecord(updated_at=utcnow(), items={}))
    local_only = [a for a in plan.actions if a.kind == ChangeKind.LOCAL_ONLY]
    assert local_only == []
    updates = [a for a in plan.actions if a.kind == ChangeKind.UPDATE_ON_MOODLE]
    assert updates == [], [a.summary for a in updates]


def test_local_only_module_becomes_create_on_moodle(app):
    moodle, _ = _snaps(app)
    app.workspace.write_text(
        "sections/01-week-1/09-extra.md",
        "---\ntype: page\nname: Extra notes\nvisible: 1\n---\n\nHello\n",
    )
    local = build_workspace_snapshot(app.workspace, course_id=42)
    plan = build_sync_plan(moodle, local, SyncRecord(updated_at=utcnow(), items={}), direction="to_moodle")
    creates = [a for a in plan.actions if a.kind == ChangeKind.CREATE_ON_MOODLE and a.name == "Extra notes"]
    assert creates
    assert creates[0].mutates_moodle is True


def test_conflict_when_both_sides_change(app):
    moodle, local = _snaps(app)
    record = record_from_snapshots(moodle, local)
    # Change local homework
    path = next(m.local_id for s in local.sections for m in s.modules if m.name == "Homework 1")
    text = app.workspace.read_text(path)
    app.workspace.write_text(path, text + "\n\nLocal edit\n")
    # Change Moodle homework
    hw = next(m for s in moodle.sections for m in s.modules if m.name == "Homework 1")
    app.moodle.update_assign(
        hw.cmid,
        name="Homework 1",
        intro="<p>Remote edit</p>",
        activity="<p>changed</p>",
    )
    moodle2 = build_moodle_snapshot(app.moodle, template_section_name=app.settings.template_section_name)
    local2 = build_workspace_snapshot(app.workspace, course_id=42)
    plan = build_sync_plan(moodle2, local2, record, direction="preview")
    conflicts = [a for a in plan.actions if a.kind == ChangeKind.CONFLICT]
    assert conflicts, plan.counts
