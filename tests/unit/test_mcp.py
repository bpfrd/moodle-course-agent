from moodle_course_agent.mcp import _mcp_fn, build_mcp_server


def test_mcp_write_requires_approval(app):
    fn = _mcp_fn(app.moodle.create_section, write=True, after=lambda: [])
    denied = fn("X", "<p></p>", 1, approved=False)
    assert denied["ok"] is False
    assert "approved" in denied["error"].lower()


def test_mcp_server_builds(app):
    server = build_mcp_server(app)
    assert server is not None
