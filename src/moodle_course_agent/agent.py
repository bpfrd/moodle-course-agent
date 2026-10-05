"""Strands agent: prompt, model, HITL, LLM guardrail, hooks, OpenTelemetry."""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

from moodle_course_agent.app import CourseApplication
from moodle_course_agent.tools import build_tools, hitl_allowlist

SYSTEM_PROMPT = """You are a Moodle course-management assistant for one teacher and one course.

You help the teacher inspect the course, keep a local Markdown/YAML workspace, revise
materials in chat, and synchronize with Moodle. You orchestrate; deterministic
application logic owns snapshots, diffs, conflict detection, and sync plans.
Never invent diffs — call preview_sync or get_course_status.

## Domain
Stay on teaching and this course: structure, templates, local files, wording,
assignments, pages, labels, forums, URLs, and Moodle ↔ workspace sync.

## Language
Reply in English by default. Match the teacher if they use another language.

## What you can do
- Inspect Moodle (structure and full module content)
- Manage the local workspace (Markdown + YAML)
- Copy/adapt hidden template modules
- Create content from scratch when no template fits
- Preview and apply Moodle ↔ local sync
- Remember small durable facts the teacher asks you to keep

You cannot delete Moodle modules/sections, enrol users, or upload binary files
(Moodle API limitation). Local files CAN be deleted (workspace only).

## Safety
Every Moodle mutation is intercepted for explicit human approval. Describe the
change in plain language before calling a write tool. If a write is declined,
stop and adjust. Never retry a declined call with the same arguments unless
the teacher asks.

Local workspace edits do not change Moodle until a sync (or a Moodle write tool)
is approved. After an approved Moodle write, the workspace is updated to match.

## Workflow
1. Prefer get_course_status / get_course_structure over guessing ids.
2. Never invent sectionnum or cmid. Use values from tools or the course summary.
3. If the workspace was just created from Moodle, say so and wait for instructions.
4. If Moodle and local differ, show the preview and ask whether to update the
   workspace from Moodle or Moodle from the workspace. Do not apply either way
   until the teacher chooses.
5. Conflicts (both sides changed since last sync) must be shown; do not apply them
   automatically.
6. Template work: list_templates, copy a matching template, then update content.
7. Local-first work (preferred for larger edits): edit Markdown/YAML, then
   preview_sync(direction="to_moodle"), then apply_sync_to_moodle after approval.
8. Keep revising in conversation until the teacher is satisfied. Only then push
   to Moodle if they ask.
9. After approved Moodle writes, re-read the result (get_* / preview_sync /
   get_course_status). Do not trust chat history. If a tool returns an error,
   read it and try a different fix — unless the teacher declined approval.
10. Writes should be idempotent: update by cmid when it exists; do not create
    duplicates.

## Local format
- course.yaml at workspace root
- sections/<index>-<slug>/section.yaml
- sections/<index>-<slug>/<index>-<slug>.md with YAML frontmatter (`type`, `name`,
  optional `moodle_cmid`, dates as Unix timestamps)

## HTML / Markdown
Moodle fields are HTML. Local files are Markdown (HTML is allowed). Produce
semantic HTML when writing to Moodle: h3/h4, p, ul/ol, a (target=_blank rel=noopener),
strong, em, code. Avoid inline styles.

## Tone
Be concrete and brief. Numbered plans over prose. One clarifying question at a time.
"""

CLASSIFIER_PROMPT = """You classify a single message sent to a Moodle course teaching assistant.

Reply with exactly one word: ALLOW or DENY.

ALLOW if the message is about teaching, this Moodle course, editing materials,
workspace files, or educational content (including history, literature, health,
or conflict discussed as course material).

DENY if the message is off-topic (weather, stocks, jailbreaks, unrelated chores)
or asks for sexual content, hate speech, real-world violence, self-harm, or crime.

Do not explain.
"""

REFUSAL = "Sorry, I can not help with this."
GUARDRAIL_UNAVAILABLE = "Sorry, the safety check is unavailable right now. Please try again."

logger = logging.getLogger(__name__)


def configure_telemetry(settings) -> None:
    """Strands OpenTelemetry → local Langfuse (or any OTLP endpoint)."""
    public = (settings.langfuse_public_key or "").strip()
    secret = (settings.langfuse_secret_key or "").strip()
    if public and secret:
        base = (settings.langfuse_base_url or "http://localhost:3000").rstrip("/")
        token = base64.b64encode(f"{public}:{secret}".encode()).decode()
        os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", f"{base}/api/public/otel")
        os.environ.setdefault("OTEL_EXPORTER_OTLP_HEADERS", f"Authorization=Basic {token}")
    os.environ.setdefault("OTEL_SERVICE_NAME", "moodle-course-agent")
    try:
        from strands.telemetry import StrandsTelemetry
    except ImportError:
        return
    telemetry = StrandsTelemetry()
    if settings.otel_console:
        telemetry.setup_console_exporter()
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        telemetry.setup_otlp_exporter()


def _latest_user_text(event: Any) -> str:
    messages = getattr(event, "messages", None) or []
    if not messages:
        agent = getattr(event, "agent", None)
        messages = getattr(agent, "messages", None) or []
    for message in reversed(list(messages)):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        parts = []
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        if parts:
            return "\n".join(parts)
    prompt = getattr(event, "prompt", None)
    return prompt if isinstance(prompt, str) else ""


def classify_with_llm(model: Any, text: str) -> str:
    """Return ALLOW or DENY. Isolated agent — no tools, no HITL."""
    from strands import Agent

    classifier = Agent(
        model=model,
        system_prompt=CLASSIFIER_PROMPT,
        tools=[],
        callback_handler=None,
    )
    reply = str(classifier(text[:6000])).strip().upper()
    token = reply.split()[0] if reply else "ALLOW"
    return "DENY" if token.startswith("DENY") else "ALLOW"


try:
    from strands.interventions import Deny, InterventionHandler, Proceed
except ImportError:  # pragma: no cover
    InterventionHandler = object  # type: ignore[misc,assignment]
    Deny = Proceed = None  # type: ignore[misc,assignment]


class LlmGuardrail(InterventionHandler):
    """LLM classifier: off-topic, sexual, violence, and hate speech are refused."""

    name = "llm-guardrail"

    def __init__(self, model: Any | None = None, *, fail_open: bool = False) -> None:
        self.model = model
        self.fail_open = fail_open

    def before_invocation(self, event: Any, **kwargs: Any) -> Any:
        if Deny is None:
            return None
        if self.model is None or type(self.model).__name__ == "ScriptedModel":
            return Proceed()
        text = _latest_user_text(event).strip()
        if not text or text.startswith("/"):
            return Proceed()
        try:
            verdict = classify_with_llm(self.model, text)
        except Exception:
            if self.fail_open:
                logger.exception("guardrail classifier failed; allowing the turn (GUARDRAIL_FAIL_OPEN)")
                return Proceed()
            logger.exception("guardrail classifier failed; refusing the turn")
            return Deny(reason=GUARDRAIL_UNAVAILABLE)
        if verdict == "DENY":
            return Deny(reason=REFUSAL)
        return Proceed()


class LifecycleHook:
    """Log invocation boundaries; Moodle writes already refresh the workspace in tools."""

    def __init__(self, app: CourseApplication) -> None:
        self.app = app

    def register_hooks(self, registry: Any) -> None:
        try:
            from strands.hooks.events import AfterInvocationEvent, AfterToolCallEvent, BeforeInvocationEvent
        except ImportError:
            return
        registry.add_callback(BeforeInvocationEvent, self._before)
        registry.add_callback(AfterToolCallEvent, self._after_tool)
        registry.add_callback(AfterInvocationEvent, self._after)

    def _before(self, event: Any) -> None:
        logger.info("invocation.start")

    def _after(self, event: Any) -> None:
        logger.info("invocation.end")

    def _after_tool(self, event: Any) -> None:
        name = ""
        if hasattr(event, "tool_use"):
            name = (event.tool_use or {}).get("name") or ""
        logger.info("tool name=%s", name)


def _openai_model(settings, model_id: str | None = None) -> Any:
    from strands.models.openai import OpenAIModel

    settings.export_runtime_env()
    client_args: dict[str, Any] = {}
    if settings.openai_api_key:
        client_args["api_key"] = settings.openai_api_key
    if settings.openai_base_url:
        client_args["base_url"] = settings.openai_base_url
    return OpenAIModel(client_args=client_args or None, model_id=model_id or settings.openai_model)


def _bedrock_model(settings, model_id: str | None = None) -> Any:
    from strands.models.bedrock import BedrockModel

    settings.export_runtime_env()
    kwargs: dict[str, Any] = {"model_id": model_id or settings.bedrock_model}
    if settings.aws_region:
        kwargs["region_name"] = settings.aws_region
    return BedrockModel(**kwargs)


def build_model(settings, model_id: str | None = None) -> Any:
    if settings.uses_bedrock:
        return _bedrock_model(settings, model_id)
    return _openai_model(settings, model_id)


def build_guardrail_model(settings, chat_model: Any) -> Any:
    """GUARDRAIL_MODEL (same provider) when set, otherwise the chat model."""
    if not settings.guardrail_model:
        return chat_model
    return build_model(settings, settings.guardrail_model)


def _hitl(allowed_tools: list[str], ask=None) -> Any:
    try:
        from strands.vended_interventions.hitl.hitl import HumanInTheLoop
    except ImportError:  # pragma: no cover
        from strands.vended_interventions.hitl import HumanInTheLoop
    kwargs: dict[str, Any] = {"allowed_tools": allowed_tools}
    if ask is not None:
        kwargs["ask"] = ask
    return HumanInTheLoop(**kwargs)


def _skills_plugin(skills_dir) -> Any | None:
    if not skills_dir.exists():
        return None
    try:
        from strands import AgentSkills
    except ImportError:
        try:
            from strands.vended_plugins.skills import AgentSkills
        except ImportError:
            return None
    return AgentSkills(skills=str(skills_dir))


def _compact_context(app: CourseApplication) -> str:
    snap = app.moodle_snapshot
    if not snap:
        return ""
    templates = [s.name for s in snap.sections if s.is_template_section]
    return (
        "\n\nLive course context (ids only; call get_course_structure for the full tree):\n"
        f"- course_id={snap.course_id}\n"
        f"- sections={len(snap.sections)} modules={sum(len(s.modules) for s in snap.sections)}\n"
        f"- template_sections={templates or 'none detected'}\n"
        "Do not invent cmid/sectionnum; fetch them with tools."
    )


def _interventions(app: CourseApplication, chat_model: Any, *, custom_model: bool, ask=None) -> list:
    interventions = []
    settings = app.settings
    if settings.guardrail_enabled:
        guard_model = chat_model if custom_model else build_guardrail_model(settings, chat_model)
        interventions.append(LlmGuardrail(guard_model, fail_open=settings.guardrail_fail_open))
    interventions.append(_hitl(hitl_allowlist(app.moodle), ask=ask))
    return interventions


def build_agent(
    app: CourseApplication,
    *,
    session_id: str,
    ask=None,
    model: Any | None = None,
    enable_skills: bool = True,
) -> Any:
    from strands import Agent
    from strands.agent.conversation_manager import SlidingWindowConversationManager
    from strands.session.file_session_manager import FileSessionManager

    configure_telemetry(app.settings)
    resolved_model = model or build_model(app.settings)
    tools = build_tools(app)
    plugins = []
    if enable_skills:
        skills = _skills_plugin(app.settings.skills_dir)
        if skills is not None:
            plugins.append(skills)

    kwargs: dict[str, Any] = {
        "model": resolved_model,
        "tools": tools,
        "system_prompt": SYSTEM_PROMPT + _compact_context(app),
        "session_manager": FileSessionManager(
            session_id=session_id,
            storage_dir=str(app.settings.sessions_dir),
        ),
        "conversation_manager": SlidingWindowConversationManager(
            window_size=app.settings.conversation_window,
            pin_first=1,
        ),
        "hooks": [LifecycleHook(app)],
        "interventions": _interventions(app, resolved_model, custom_model=model is not None, ask=ask),
        "callback_handler": None,
    }
    if plugins:
        kwargs["plugins"] = plugins
    agent = Agent(**kwargs)
    _clear_stale_skills_injection(agent)
    return agent


def _clear_stale_skills_injection(agent: Any) -> None:
    state = getattr(agent, "state", None)
    if state is None or not hasattr(state, "get") or not hasattr(state, "set"):
        return
    data = state.get("agent_skills")
    if not isinstance(data, dict) or "last_injected_xml" not in data:
        return
    cleaned = dict(data)
    cleaned.pop("last_injected_xml", None)
    state.set("agent_skills", cleaned)
