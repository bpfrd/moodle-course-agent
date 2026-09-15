from moodle_course_agent.models import ModuleSnapshot
from moodle_course_agent.workspace import (
    build_workspace_snapshot,
    export_snapshot_to_workspace,
    parse_module_file,
    module_to_markdown,
)
from moodle_course_agent.moodle.snapshot import build_moodle_snapshot


def test_page_roundtrip_frontmatter():
    original = ModuleSnapshot(
        local_id="x.md",
        modname="page",
        name="Syllabus",
        fields={"intro": "<p>Intro</p>", "pagecontent": "<h3>Body</h3>", "showdescription": 0},
        cmid=9,
        source="moodle",
    )
    text = module_to_markdown(original)
    parsed = parse_module_file("x.md", text, 1, "Week 1")
    assert parsed.name == "Syllabus"
    assert parsed.cmid == 9
    assert parsed.modname == "page"
    assert "Body" in parsed.fields["pagecontent"] or "body" in parsed.fields["pagecontent"].lower()


def test_export_and_reload(app):
    moodle_snap = build_moodle_snapshot(app.moodle, template_section_name=app.settings.template_section_name)
    written = export_snapshot_to_workspace(app.workspace, moodle_snap, overwrite=True)
    assert "course.yaml" in written
    local = build_workspace_snapshot(app.workspace, course_id=42)
    names = {s.name for s in local.sections}
    assert "Week 1" in names
    modules = [m.name for s in local.sections for m in s.modules]
    assert "Syllabus" in modules
    assert "Homework 1" in modules
