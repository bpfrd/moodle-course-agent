from moodle_course_agent.tools import ALLOWED_WITHOUT_APPROVAL, build_tools, hitl_allowlist


def _by_name(tools):
    mapping = {}
    for tool in tools:
        spec = getattr(tool, "tool_spec", None) or {}
        name = spec.get("name") or getattr(tool, "__name__", "")
        mapping[name] = tool
    return mapping


def test_read_tool_and_template_list(app):
    app.bootstrap()
    tools = _by_name(build_tools(app))
    structure = tools["get_course_structure"]()
    assert structure["ok"] is True
    names = {s["name"] for s in structure["result"]}
    assert "Week 1" in names
    templates = tools["list_templates"]()
    assert templates["ok"] is True
    assert templates["result"]["named_assign_templates"]


def test_workspace_tool_stays_sandboxed(app):
    app.bootstrap()
    tools = _by_name(build_tools(app))
    bad = tools["read_workspace_file"]("../secret.txt")
    assert bad["ok"] is False


def test_hitl_allow_list_excludes_moodle_writes():
    assert "get_course_structure" in ALLOWED_WITHOUT_APPROVAL
    assert "write_workspace_file" in ALLOWED_WITHOUT_APPROVAL
    assert "apply_sync_to_moodle" not in ALLOWED_WITHOUT_APPROVAL
    assert "create_section" not in ALLOWED_WITHOUT_APPROVAL


def test_moodle_read_tools_are_allowlisted_when_client_present(app):
    names = hitl_allowlist(app.moodle)
    assert "get_page" in names
    assert "create_page" not in names
