"""Application configuration from environment / .env."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_KEYS = {"", "sk-...", "your-openai-api-key", "changeme"}


def project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "pyproject.toml").exists() and (parent / "src").exists():
            return parent
    return Path.cwd()


def load_env_files(root: Path | None = None) -> Path | None:
    base = root or project_root()
    loaded = None
    for path in (base / ".env", Path.cwd() / ".env"):
        if path.exists():
            load_dotenv(path, override=False)
            loaded = path
    return loaded


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(project_root() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = Field(default="", validation_alias="BASE_URL")
    wstoken: str = Field(default="", validation_alias="WSTOKEN")
    course_id: int = Field(default=0, validation_alias="COURSE_ID")
    moodle_timeout: int = Field(default=60, validation_alias="MOODLE_TIMEOUT")
    moodle_mock: bool = Field(default=False, validation_alias="MOODLE_MOCK")

    model_provider: str = Field(default="openai", validation_alias="MODEL_PROVIDER")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", validation_alias="OPENAI_MODEL")
    openai_base_url: str = Field(default="", validation_alias="OPENAI_BASE_URL")
    bedrock_model: str = Field(
        default="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        validation_alias="BEDROCK_MODEL",
    )
    aws_region: str = Field(default="us-east-1", validation_alias="AWS_REGION")
    aws_access_key_id: str = Field(default="", validation_alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(default="", validation_alias="AWS_SECRET_ACCESS_KEY")
    aws_session_token: str = Field(default="", validation_alias="AWS_SESSION_TOKEN")

    workspace_dir: Path = Field(default=Path("workspace"), validation_alias="WORKSPACE_DIR")
    data_dir: Path = Field(default=Path("data"), validation_alias="DATA_DIR")
    skills_dir: Path = Field(default=Path("skills"), validation_alias="SKILLS_DIR")

    template_section_name: str = Field(
        default="Modulentwicklung [RK only]",
        validation_alias="TEMPLATE_SECTION_NAME",
    )
    conversation_window: int = Field(default=24, validation_alias="CONVERSATION_WINDOW")

    langfuse_public_key: str = Field(default="", validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", validation_alias="LANGFUSE_SECRET_KEY")
    langfuse_base_url: str = Field(
        default="http://localhost:3000",
        validation_alias="LANGFUSE_BASE_URL",
    )
    otel_console: bool = Field(default=False, validation_alias="OTEL_CONSOLE")

    @field_validator(
        "openai_api_key",
        "wstoken",
        "base_url",
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        "model_provider",
        "langfuse_public_key",
        "langfuse_secret_key",
        mode="before",
    )
    @classmethod
    def _strip_secret(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().strip("'").strip('"')
        return value

    def resolve(self, root: Path | None = None) -> "Settings":
        base = root or project_root()
        object.__setattr__(self, "workspace_dir", _as_abs(self.workspace_dir, base))
        object.__setattr__(self, "data_dir", _as_abs(self.data_dir, base))
        skills = self.skills_dir
        if not Path(skills).is_absolute():
            object.__setattr__(self, "skills_dir", (base / skills).resolve())
        return self

    @property
    def uses_bedrock(self) -> bool:
        return (self.model_provider or "openai").strip().lower() in {"bedrock", "aws", "amazon"}

    def export_runtime_env(self) -> None:
        if self.openai_api_key:
            os.environ["OPENAI_API_KEY"] = self.openai_api_key
        if self.openai_base_url:
            os.environ["OPENAI_BASE_URL"] = self.openai_base_url
        if self.aws_region:
            os.environ.setdefault("AWS_REGION", self.aws_region)
            os.environ.setdefault("AWS_DEFAULT_REGION", self.aws_region)
        if self.aws_access_key_id:
            os.environ["AWS_ACCESS_KEY_ID"] = self.aws_access_key_id
        if self.aws_secret_access_key:
            os.environ["AWS_SECRET_ACCESS_KEY"] = self.aws_secret_access_key
        if self.aws_session_token:
            os.environ["AWS_SESSION_TOKEN"] = self.aws_session_token

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def openai_key_is_placeholder(self) -> bool:
        key = (self.openai_api_key or "").strip()
        return key.lower() in _PLACEHOLDER_KEYS or key in {"sk-...", "sk-proj-..."}

    def require_llm(self) -> None:
        if self.uses_bedrock:
            has_keys = bool(self.aws_access_key_id) or bool(os.environ.get("AWS_ACCESS_KEY_ID"))
            if not has_keys:
                raise ValueError(
                    "MODEL_PROVIDER=bedrock but AWS_ACCESS_KEY_ID is missing. "
                    "Set AWS credentials and BEDROCK_MODEL in .env"
                )
            return
        if self.openai_key_is_placeholder:
            raise ValueError(
                "OPENAI_API_KEY is missing or still a placeholder. "
                "Set a live key in .env, or use MODEL_PROVIDER=bedrock."
            )

    def require_moodle(self) -> None:
        if self.moodle_mock:
            return
        missing = [
            name
            for name, value in (
                ("BASE_URL", self.base_url),
                ("WSTOKEN", self.wstoken),
                ("COURSE_ID", self.course_id),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing Moodle configuration: {', '.join(missing)}")

    def llm_status(self) -> str:
        if self.uses_bedrock:
            return f"LLM=bedrock model={self.bedrock_model} region={self.aws_region}"
        key = self.openai_api_key or ""
        if self.openai_key_is_placeholder:
            return "OpenAI key: not set"
        return f"LLM=openai model={self.openai_model} key=…{key[-4:]} ({len(key)} chars)"


def _as_abs(path: Path, root: Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return (root / path).resolve()


def load_settings(root: Path | None = None) -> Settings:
    load_env_files(root)
    settings = Settings().resolve(root)
    settings.export_runtime_env()
    return settings
