"""Agent loop tests using a scripted FakeOpenAI and FakeMoodleClient.

These cover the most important behaviors:
  * the loop calls tools the model requests and feeds results back,
  * write tools are gated by confirm_fn,
  * declines surface as ok=False results the model can react to,
  * tool errors surface as ok=False results,
  * unknown tools are handled gracefully,
  * the loop terminates at the iteration cap.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.audit import AuditLog
from agent.loop import Agent
from tests.fakes import (
    FakeOpenAI,
    assistant_text,
    assistant_tool_call,
    assistant_tool_calls,
)


@pytest.fixture
def audit(tmp_path: Path) -> AuditLog:
    return AuditLog(log_dir=tmp_path / "logs")


def _make_agent(fake_client, openai, audit, confirm_fn=None):
    return Agent(
        client=fake_client,
        openai_client=openai,
        model="test-model",
        system_prompt="you are a test agent",
        audit=audit,
        confirm_fn=confirm_fn or (lambda _name, _args: True),
    )


def test_simple_text_reply_no_tools(fake_client, audit):
    openai = FakeOpenAI([assistant_text("Hello teacher!")])
    agent = _make_agent(fake_client, openai, audit)

    reply = agent.send("hi")

    assert reply == "Hello teacher!"
    assert len(openai.calls) == 1


def test_read_tool_no_confirmation(fake_client, audit):
    """get_course_structure must NOT trigger the confirm_fn."""
    confirm_calls = []

    def confirm(name, args):
        confirm_calls.append(name)
        return True

    openai = FakeOpenAI(
        [
            assistant_tool_call("get_course_structure", {}),
            assistant_text("Done."),
        ]
    )
    agent = _make_agent(fake_client, openai, audit, confirm_fn=confirm)

    reply = agent.send("what is in the course?")

    assert reply == "Done."
    assert confirm_calls == []  # never asked for a read

    tool_msgs = [m for m in agent.history if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    result = json.loads(tool_msgs[0]["content"])
    assert result["ok"] is True
    assert result["result"][0]["sectionnum"] == 0


def test_write_tool_requires_confirmation_yes(fake_client, audit):
    confirm_calls = []

    def confirm(name, args):
        confirm_calls.append((name, args))
        return True

    openai = FakeOpenAI(
        [
            assistant_tool_call(
                "create_section",
                {"name": "Week 2", "summary": "<p>s</p>", "position": 3, "visible": 1},
            ),
            assistant_text("Section created."),
        ]
    )
    agent = _make_agent(fake_client, openai, audit, confirm_fn=confirm)

    reply = agent.send("create a section")

    assert reply == "Section created."
    assert confirm_calls == [
        ("create_section", {"name": "Week 2", "summary": "<p>s</p>", "position": 3, "visible": 1})
    ]
    assert len(fake_client.course) == 3


def test_write_tool_declined_returns_error_to_model(fake_client, audit):
    openai = FakeOpenAI(
        [
            assistant_tool_call(
                "create_section",
                {"name": "Week 2", "summary": "<p>s</p>", "position": 3},
            ),
            assistant_text("OK I won't do that."),
        ]
    )
    agent = _make_agent(fake_client, openai, audit, confirm_fn=lambda _n, _a: False)

    reply = agent.send("create a section")

    assert reply == "OK I won't do that."
    assert len(fake_client.course) == 2  # nothing was created

    tool_msgs = [m for m in agent.history if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    result = json.loads(tool_msgs[0]["content"])
    assert result["ok"] is False
    assert "declined" in result["error"].lower()


def test_tool_error_is_fed_back_to_model(fake_client, audit):
    """When a Moodle call fails (bad cmid), the model sees ok=False."""
    openai = FakeOpenAI(
        [
            assistant_tool_call("get_label", {"cmid": 99999}),
            assistant_text("That cmid does not exist; please double-check."),
        ]
    )
    agent = _make_agent(fake_client, openai, audit)

    reply = agent.send("show me cmid 99999")

    assert "does not exist" in reply
    tool_msgs = [m for m in agent.history if m.get("role") == "tool"]
    result = json.loads(tool_msgs[0]["content"])
    assert result["ok"] is False
    assert result["error_type"] == "MoodleAPIError"


def test_unknown_tool_name_handled(fake_client, audit):
    openai = FakeOpenAI(
        [
            assistant_tool_call("delete_universe", {"force": True}),
            assistant_text("Sorry, that tool is not available."),
        ]
    )
    agent = _make_agent(fake_client, openai, audit)

    reply = agent.send("destroy everything")

    tool_msgs = [m for m in agent.history if m.get("role") == "tool"]
    result = json.loads(tool_msgs[0]["content"])
    assert result["ok"] is False
    assert "Unknown tool" in result["error"]
    assert reply.startswith("Sorry")


def test_course_context_refreshes_after_successful_write(fake_client, audit):
    """After an approved write, history[1] should contain the new section name."""
    openai = FakeOpenAI(
        [
            assistant_tool_call(
                "create_section",
                {"name": "Brand New", "summary": "<p>x</p>", "position": 3},
            ),
            assistant_text("Created."),
        ]
    )
    agent = _make_agent(fake_client, openai, audit)

    initial_context = agent.history[1]["content"]
    assert "Brand New" not in initial_context

    agent.send("create it")

    refreshed_context = agent.history[1]["content"]
    assert "Brand New" in refreshed_context


def test_multiple_tool_calls_in_one_turn(fake_client, audit):
    openai = FakeOpenAI(
        [
            assistant_tool_calls(
                [
                    ("get_course_structure", {}),
                    ("get_label", {"cmid": 100}),
                ]
            ),
            assistant_text("Both read."),
        ]
    )
    agent = _make_agent(fake_client, openai, audit)

    reply = agent.send("what's there?")

    assert reply == "Both read."
    tool_msgs = [m for m in agent.history if m.get("role") == "tool"]
    assert len(tool_msgs) == 2


def test_iteration_cap_is_enforced(fake_client, audit):
    """An infinite tool-call loop should be stopped cleanly."""
    # 13 tool-call responses; the cap is 12.
    scripted = [assistant_tool_call("get_course_structure", {}) for _ in range(13)]
    openai = FakeOpenAI(scripted)
    agent = _make_agent(fake_client, openai, audit)

    reply = agent.send("loop forever")

    assert "maximum number of tool iterations" in reply


def test_audit_log_records_session(fake_client, audit, tmp_path):
    openai = FakeOpenAI(
        [
            assistant_tool_call("get_course_structure", {}),
            assistant_text("Done."),
        ]
    )
    agent = _make_agent(fake_client, openai, audit)
    agent.send("hello")

    log_lines = audit.path.read_text(encoding="utf-8").splitlines()
    events = [json.loads(line)["event"] for line in log_lines]
    assert "user_message" in events
    assert "assistant_message" in events
    assert "tool_call" in events
    assert "tool_result" in events
