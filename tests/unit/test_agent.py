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
