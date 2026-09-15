from moodle_course_agent.config import Settings, project_root


def test_project_root_finds_app():
    root = project_root()
    assert (root / "pyproject.toml").exists()
    assert (root / "src" / "moodle_course_agent").is_dir()


def test_placeholder_key_is_rejected(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    settings = Settings(openai_api_key="sk-...", model_provider="openai")
    assert settings.openai_key_is_placeholder
    try:
        settings.require_llm()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "OPENAI_API_KEY" in str(exc)


def test_api_key_quotes_are_stripped():
    stripped = Settings(openai_api_key='  "sk-abc"  ')
    assert stripped.openai_api_key == "sk-abc"


def test_bedrock_does_not_require_openai_key(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "bedrock")
    settings = Settings(
        model_provider="bedrock",
        openai_api_key="",
        aws_access_key_id="AKIATEST",
        aws_secret_access_key="secret",
    )
    assert settings.uses_bedrock
    settings.require_llm()
    assert "bedrock" in settings.llm_status()


def test_bedrock_requires_aws_keys(monkeypatch):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    settings = Settings(model_provider="bedrock", openai_api_key="", aws_access_key_id="")
    try:
        settings.require_llm()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "AWS_ACCESS_KEY_ID" in str(exc)
