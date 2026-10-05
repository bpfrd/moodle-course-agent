import json

from mcp import types
from mcp.shared.memory import create_connected_server_and_client_session

from moodle_course_agent.mcp import NEEDS_APPROVED_FLAG, NOT_APPROVED, build_mcp_server


def _payload(result):
    return json.loads(result.content[0].text)


def _answer(approve):
    prompts = []

    async def callback(context, params):
        prompts.append(params.message)
        return types.ElicitResult(action="accept", content={"approve": approve})

    return callback, prompts


def _section_names(app):
    return [s["name"] for s in app.moodle.course]


def test_mcp_server_builds(app):
    assert build_mcp_server(app) is not None


async def test_write_tools_are_annotated(app):
    async with create_connected_server_and_client_session(build_mcp_server(app)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert tools["create_section"].annotations.destructiveHint is True
    assert tools["apply_sync_to_moodle"].annotations.destructiveHint is True
    assert tools["get_page"].annotations.readOnlyHint is True
    assert "delete_module" not in tools
    assert "ctx" not in tools["create_section"].inputSchema["properties"]


async def test_elicitation_decline_blocks_write_even_with_approved_flag(app):
    callback, prompts = _answer(False)
    server = build_mcp_server(app)
    async with create_connected_server_and_client_session(server, elicitation_callback=callback) as client:
        result = await client.call_tool(
            "create_section", {"name": "Sneaky", "summary": "", "position": 1, "approved": True}
        )
    assert _payload(result) == {"ok": False, "error": NOT_APPROVED}
    assert prompts and "create_section" in prompts[0] and "Sneaky" in prompts[0]
    assert "Sneaky" not in _section_names(app)


async def test_elicitation_accept_applies_write_and_updates_workspace(app):
    callback, _ = _answer(True)
    server = build_mcp_server(app)
    async with create_connected_server_and_client_session(server, elicitation_callback=callback) as client:
        result = await client.call_tool("create_section", {"name": "Week 9", "summary": "", "position": 4})
    assert _payload(result)["ok"] is True
    assert "Week 9" in _section_names(app)
    assert any("week-9" in path for path in app.workspace.list_files())


async def test_client_without_elicitation_needs_approved_flag(app):
    server = build_mcp_server(app)
    async with create_connected_server_and_client_session(server) as client:
        denied = await client.call_tool("create_section", {"name": "X", "summary": "", "position": 1})
        allowed = await client.call_tool(
            "create_section", {"name": "Y", "summary": "", "position": 1, "approved": True}
        )
    assert _payload(denied) == {"ok": False, "error": NEEDS_APPROVED_FLAG}
    assert _payload(allowed)["ok"] is True
    assert "X" not in _section_names(app) and "Y" in _section_names(app)


async def test_apply_sync_to_moodle_asks_with_plan(app):
    callback, prompts = _answer(False)
    server = build_mcp_server(app)
    app.workspace.write_text(
        "sections/01-week-1/09-extra.md", "---\ntype: page\nname: Extra\n---\n\nBody\n"
    )
    async with create_connected_server_and_client_session(server, elicitation_callback=callback) as client:
        result = await client.call_tool("apply_sync_to_moodle", {"approved": True})
    assert _payload(result)["ok"] is False
    assert "Extra" in prompts[0]
    assert "Extra" not in [m["name"] for s in app.moodle.course for m in s["modules"]]
