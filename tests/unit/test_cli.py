from moodle_course_agent.cli import APPROVAL_HINT, StreamEventMapper


def test_approval_hint_names_keys_without_rich_tags():
    assert "y = apply" in APPROVAL_HINT
    assert "n = skip" in APPROVAL_HINT
    assert "[" not in APPROVAL_HINT


def test_tool_stream_chunks_are_deduped():
    mapper = StreamEventMapper()
    chunks = [
        {"current_tool_use": {"name": "create_page", "toolUseId": "t1", "input": "{"}},
        {"current_tool_use": {"name": "create_page", "toolUseId": "t1", "input": '{"name":'}},
    ]
    mapped = [mapper.map(chunk) for chunk in chunks]
    tools = [event for event in mapped if event]
    assert len(tools) == 1
    assert tools[0]["name"] == "create_page"
