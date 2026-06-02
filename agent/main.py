"""CLI entrypoint for the Moodle teaching assistant.

Usage::

    python -m agent.main

Required environment variables (typically loaded from ``.env``):
    BASE_URL         - Moodle webservice REST endpoint
    WSTOKEN          - Moodle web-service token
    COURSE_ID        - Numeric Moodle course id
    OPENAI_API_KEY   - OpenAI API key

Optional:
    OPENAI_MODEL     - Model name (default: gpt-4o)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from moodle_client import MoodleClient

from .audit import AuditLog
from .loop import Agent

_DEFAULT_MODEL = "gpt-4o"
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system.md"

_console = Console()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        _console.print(f"[bold red]Missing environment variable:[/bold red] {name}")
        sys.exit(1)
    return value


def _load_system_prompt() -> str:
    if not _PROMPT_PATH.exists():
        _console.print(f"[bold red]System prompt not found at {_PROMPT_PATH}[/bold red]")
        sys.exit(1)
    return _PROMPT_PATH.read_text(encoding="utf-8")


def main() -> None:
    load_dotenv()

    base_url = _require_env("BASE_URL")
    wstoken = _require_env("WSTOKEN")
    course_id = int(_require_env("COURSE_ID"))
    _require_env("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", _DEFAULT_MODEL)

    system_prompt = _load_system_prompt()
    audit = AuditLog()

    _console.print(
        Panel(
            f"[bold]Moodle Teaching Assistant[/bold]\n"
            f"course_id = {course_id}\n"
            f"model     = {model}\n"
            f"audit log = {audit.path}\n\n"
            f"Type your request. Type [bold]/exit[/bold] to quit, "
            f"[bold]/reset[/bold] to clear the conversation.",
            border_style="green",
            title="ready",
        )
    )

    with MoodleClient(base_url=base_url, token=wstoken, courseid=course_id) as client:
        audit.write("session_start", course_id=course_id, model=model)
        openai_client = OpenAI()
        agent = Agent(
            client=client,
            openai_client=openai_client,
            model=model,
            system_prompt=system_prompt,
            audit=audit,
        )

        while True:
            try:
                user_msg = _console.input("\n[bold cyan]you[/bold cyan] > ").strip()
            except (EOFError, KeyboardInterrupt):
                _console.print("\n[dim]bye[/dim]")
                break

            if not user_msg:
                continue
            if user_msg in {"/exit", "/quit"}:
                _console.print("[dim]bye[/dim]")
                break
            if user_msg == "/reset":
                agent = Agent(
                    client=client,
                    openai_client=openai_client,
                    model=model,
                    system_prompt=system_prompt,
                    audit=audit,
                )
                _console.print("[dim]conversation reset[/dim]")
                continue

            try:
                reply = agent.send(user_msg)
            except Exception as exc:
                audit.write("agent_error", error=str(exc), error_type=type(exc).__name__)
                _console.print(
                    Panel(
                        f"[bold red]{type(exc).__name__}[/bold red]: {exc}",
                        border_style="red",
                        title="error",
                    )
                )
                continue

            _console.print(
                Panel(
                    Markdown(reply) if reply else "[dim](empty response)[/dim]",
                    border_style="blue",
                    title="assistant",
                )
            )

        audit.write("session_end")


if __name__ == "__main__":
    main()
