from moodle_course_agent.agent import _clear_stale_skills_injection, build_model
from moodle_course_agent.cli import _friendly_error, build_parser
from moodle_course_agent.config import Settings


def test_build_model_uses_openai(monkeypatch):
    created = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            created.update(kwargs)

    monkeypatch.setattr("strands.models.openai.OpenAIModel", FakeOpenAI)
    model = build_model(Settings(model_provider="openai", openai_api_key="sk-test", openai_model="gpt-4o"))
    assert isinstance(model, FakeOpenAI)
    assert created["model_id"] == "gpt-4o"
    assert created["client_args"]["api_key"] == "sk-test"


def test_build_model_uses_bedrock(monkeypatch):
    created = {}

    class FakeBedrock:
        def __init__(self, **kwargs):
            created.update(kwargs)

    monkeypatch.setattr("strands.models.bedrock.BedrockModel", FakeBedrock)
    model = build_model(
        Settings(
            model_provider="bedrock",
            bedrock_model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            aws_region="us-east-1",
            aws_access_key_id="AKIATEST",
        )
    )
    assert isinstance(model, FakeBedrock)
    assert created["model_id"].startswith("us.anthropic")
    assert created["region_name"] == "us-east-1"


def test_friendly_error_rewrites_openai_401():
    message = _friendly_error(RuntimeError("Error code: 401 - invalid_api_key"))
    assert "OpenAI rejected" in message
    assert "MODEL_PROVIDER=bedrock" in message


class _FakeState:
    def __init__(self, data):
        self._data = data

    def get(self, key=None):
        if key is None:
            return self._data
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value


def test_stale_skills_xml_is_cleared_after_session_restore():
    agent = type("Agent", (), {})()
    agent.state = _FakeState(
        {"agent_skills": {"last_injected_xml": "<available_skills/>", "activated_skills": ["inspect-course"]}}
    )
    _clear_stale_skills_injection(agent)
    remaining = agent.state.get("agent_skills")
    assert "last_injected_xml" not in remaining
    assert remaining["activated_skills"] == ["inspect-course"]


def test_parser_defaults_and_commands():
    parser = build_parser()
    args = parser.parse_args(["status"])
    assert args.command == "status"
    args = parser.parse_args(["chat", "--session", "abc", "--once", "hey"])
    assert args.session == "abc"
    args = parser.parse_args(["mcp"])
    assert args.command == "mcp"


def _event(text):
    return type("Event", (), {"messages": [{"role": "user", "content": [{"text": text}]}]})()


def test_guardrail_fails_closed_by_default(monkeypatch):
    from strands.interventions import Deny, Proceed

    from moodle_course_agent import agent as agent_module

    def boom(model, text):
        raise RuntimeError("classifier down")

    monkeypatch.setattr(agent_module, "classify_with_llm", boom)
    closed = agent_module.LlmGuardrail(object()).before_invocation(_event("Revise week 1"))
    assert isinstance(closed, Deny)
    assert closed.reason == agent_module.GUARDRAIL_UNAVAILABLE
    opened = agent_module.LlmGuardrail(object(), fail_open=True).before_invocation(_event("Revise week 1"))
    assert isinstance(opened, Proceed)


def test_guardrail_denies_and_allows_by_verdict(monkeypatch):
    from strands.interventions import Deny, Proceed

    from moodle_course_agent import agent as agent_module

    monkeypatch.setattr(agent_module, "classify_with_llm", lambda model, text: "DENY" if "stocks" in text else "ALLOW")
    guard = agent_module.LlmGuardrail(object())
    assert isinstance(guard.before_invocation(_event("Which stocks to buy?")), Deny)
    assert isinstance(guard.before_invocation(_event("Add a WWII reading to week 3")), Proceed)


def test_guardrail_model_override(monkeypatch):
    from moodle_course_agent.agent import build_guardrail_model

    created = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            created.append(kwargs["model_id"])

    monkeypatch.setattr("strands.models.openai.OpenAIModel", FakeOpenAI)
    chat = object()
    assert build_guardrail_model(Settings(openai_api_key="sk-test"), chat) is chat
    build_guardrail_model(
        Settings(model_provider="openai", openai_api_key="sk-test", guardrail_model="gpt-4o-mini"), chat
    )
    assert created == ["gpt-4o-mini"]
