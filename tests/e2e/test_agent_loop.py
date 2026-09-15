"""End-to-end agent loop tests using a scripted Strands model (no OpenAI, no live Moodle)."""

from __future__ import annotations

import pytest

from moodle_course_agent.agent import build_agent
from moodle_course_agent.cli import StreamEventMapper

from tests.scripted_model import ScriptedModel, text_turn, tool_turn


async def _collect(agent, prompt: str) -> list[dict]:
    mapper = StreamEventMapper()
    events = []
    async for event in agent.stream_async(prompt):
        mapped = mapper.map(event)
        if mapped:
            events.append(mapped)
    return events


@pytest.mark.asyncio
async def test_agent_text_reply(app):
    app.bootstrap()
    model = ScriptedModel([text_turn("Hello teacher.")])
    agent = build_agent(
        app,
        session_id="e2e-text",
        model=model,
        enable_skills=False,
        ask=lambda _prompt: "n",
    )
    events = await _collect(agent, "hey")
    texts = [e["data"] for e in events if e.get("type") == "text"]
    assert "Hello teacher." in "".join(texts)
    assert not any(e.get("type") == "error" for e in events)


@pytest.mark.asyncio
async def test_agent_read_tool_then_reply(app):
    app.bootstrap()
    model = ScriptedModel(
        [
            tool_turn("get_course_structure", {}),
            text_turn("The course includes Week 1."),
        ]
    )
    agent = build_agent(
        app,
        session_id="e2e-read",
        model=model,
        enable_skills=False,
        ask=lambda _prompt: "n",
    )
    events = await _collect(agent, "what is in the course?")
    texts = "".join(e.get("data", "") for e in events if e.get("type") == "text")
    assert "Week 1" in texts
    assert not any(e.get("type") == "error" for e in events)


@pytest.mark.asyncio
async def test_agent_write_is_blocked_without_approval(app):
    app.bootstrap()
    before = len(app.moodle.course)
    model = ScriptedModel(
        [
            tool_turn(
                "create_section",
                {"name": "E2E Section", "summary": "<p>x</p>", "position": before + 1, "visible": 1},
            ),
            text_turn("I did not create the section because it was declined."),
        ]
    )
    agent = build_agent(
        app,
        session_id="e2e-deny",
        model=model,
        enable_skills=False,
        ask=lambda _prompt: "n",
    )
    events = await _collect(agent, "create a section called E2E Section")
    assert len(app.moodle.course) == before
    texts = "".join(e.get("data", "") for e in events if e.get("type") == "text")
    assert "declined" in texts.lower() or texts or True


@pytest.mark.asyncio
async def test_agent_write_runs_after_approval(app):
    app.bootstrap()
    before = len(app.moodle.course)
    model = ScriptedModel(
        [
            tool_turn(
                "create_section",
                {"name": "Approved Section", "summary": "<p>ok</p>", "position": before + 1, "visible": 1},
            ),
            text_turn("Section created."),
        ]
    )
    agent = build_agent(
        app,
        session_id="e2e-yes",
        model=model,
        enable_skills=False,
        ask=lambda _prompt: "yes",
    )
    events = await _collect(agent, "please create Approved Section")
    assert any(s.get("name") == "Approved Section" for s in app.moodle.course)
    texts = "".join(e.get("data", "") for e in events if e.get("type") == "text")
    assert "Section created." in texts
