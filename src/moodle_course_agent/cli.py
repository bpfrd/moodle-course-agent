"""Rich shell: chat is the default entry. Also status and MCP."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from moodle_course_agent.app import CourseApplication
from moodle_course_agent.config import load_env_files, load_settings

console = Console()

APPROVAL_HINT = "y = apply this Moodle change, n = skip (default)"
_MOODLE_WRITES = ("create_", "update_", "move_", "copy_", "delete_", "apply_sync_to_moodle")


def _app() -> CourseApplication:
    return CourseApplication(load_settings())


def _prompt_yes_no(question: str) -> str:
    try:
        return console.input(f"[bold]{question}[/bold]  {APPROVAL_HINT}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "n"


def _cli_ask(prompt: str) -> str:
    console.print(
        Panel(f"{prompt}\n\n{APPROVAL_HINT}.", title="Approval needed", border_style="yellow")
    )
    return _prompt_yes_no("Apply this Moodle change?")


def _print_status(app: CourseApplication, summary) -> None:
    console.print(Panel(summary.message, title="Moodle Course Agent", border_style="green"))
    table = Table(title="Sync preview", box=None, show_header=True)
    table.add_column("Kind")
    table.add_column("Count", justify="right")
    for key, value in summary.sync_preview_counts.items():
        table.add_row(str(key), str(value))
    console.print(table)
    tree = Tree("[bold]workspace[/bold]")
    for line in app.workspace.tree()[1:]:
        tree.add(line)
    console.print(tree)


def cmd_status(_args: argparse.Namespace | None = None) -> int:
    app = _app()
    _print_status(app, app.bootstrap())
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    from moodle_course_agent.agent import build_agent

    settings = load_settings()
    try:
        settings.require_llm()
    except ValueError as exc:
        console.print(Panel(str(exc), title="configuration", border_style="red"))
        return 1

    app = CourseApplication(settings)
    summary = app.bootstrap()
    session_id = args.session or app.store.last_session_id() or app.new_session_id()
    app.store.set_last_session_id(session_id)
    console.print(
        Panel(
            f"{summary.message}\n\n{app.settings.llm_status()}\n"
            f"session = {session_id}\n"
            "Commands: /exit  /status  /reset  /help",
            title="Moodle Course Agent",
            border_style="green",
        )
    )
    agent = build_agent(app, session_id=session_id, ask=_cli_ask)

    once = getattr(args, "once", None)
    if once:
        return _stream_turn(agent, once)

    while True:
        try:
            user = console.input("\n[bold cyan]you[/bold cyan] › ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            return 0
        if not user:
            continue
        if user in {"/exit", "/quit"}:
            console.print("[dim]bye[/dim]")
            return 0
        if user == "/help":
            console.print("Commands: /exit  /status  /reset  /help")
            continue
        if user == "/status":
            cmd_status()
            continue
        if user == "/reset":
            session_id = app.new_session_id()
            agent = build_agent(app, session_id=session_id, ask=_cli_ask)
            console.print(f"[dim]new session {session_id}[/dim]")
            continue
        _stream_turn(agent, user)
    return 0


def _fmt_args(data: Any) -> str:
    if not data:
        return ""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return data[:80]
    if not isinstance(data, dict):
        return str(data)[:80]
    parts = []
    for key, value in data.items():
        text = str(value).replace("\n", " ")
        if len(text) > 48:
            text = text[:45] + "…"
        parts.append(f"{key}={text}")
    return ", ".join(parts)


def _stream_turn(agent: Any, user: str) -> int:
    async def _run() -> bool:
        mapper = StreamEventMapper()
        ok = True
        console.print(Rule("[dim]assistant[/dim]", style="dim"))
        try:
            async for event in agent.stream_async(user):
                mapped = mapper.map(event)
                if not mapped:
                    continue
                kind = mapped.get("type")
                if kind == "text":
                    console.print(mapped.get("data") or "", end="")
                elif kind == "tool":
                    name = mapped.get("name") or "tool"
                    args = _fmt_args(mapped.get("input"))
                    write = name.startswith(_MOODLE_WRITES)
                    style = "yellow" if write else "cyan"
                    label = "Moodle write" if write else "tool"
                    if name.startswith("write_workspace") or name.startswith("create_workspace"):
                        style, label = "green", "workspace"
                    line = Text.assemble((f"▸ {label}  ", f"bold {style}"), (name, style))
                    if args:
                        line.append(f"  {args}", style="dim")
                    console.print()
                    console.print(line)
                elif kind == "error":
                    ok = False
                    console.print(Panel(str(mapped.get("message")), title="error", border_style="red"))
            console.print()
            return ok
        except Exception as exc:  # noqa: BLE001
            message = _friendly_error(exc)
            if "Sorry, I can not help with this" in message:
                console.print(Panel(message, border_style="red"))
            else:
                console.print(Panel(message, title="error", border_style="red"))
            return False

    return 0 if asyncio.run(_run()) else 1


def cmd_mcp(_args: argparse.Namespace) -> int:
    from moodle_course_agent.mcp import main as mcp_main

    mcp_main()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moodle-agent",
        description="Moodle course agent. Default command: chat.",
    )
    sub = parser.add_subparsers(dest="command")

    chat = sub.add_parser("chat", help="Interactive teaching assistant (default)")
    chat.add_argument("--session", default=None)
    chat.add_argument("--once", default=None, help="Send one prompt and exit")
    chat.set_defaults(func=cmd_chat)

    status = sub.add_parser("status", help="Show Moodle + workspace summary")
    status.set_defaults(func=cmd_status)

    mcp = sub.add_parser("mcp", help="Moodle API MCP server (stdio)")
    mcp.set_defaults(func=cmd_mcp)
    return parser


def main(argv: list[str] | None = None) -> int:
    load_env_files()
    raw = list(sys.argv[1:] if argv is None else argv)
    known = {"chat", "status", "mcp"}
    if raw and raw[0] not in known and raw[0] not in {"-h", "--help"}:
        raw = ["chat", *raw]
    elif not raw:
        raw = ["chat"]
    parser = build_parser()
    args = parser.parse_args(raw)
    return args.func(args)


class StreamEventMapper:
    def __init__(self) -> None:
        self._seen_tool_ids: set[str] = set()

    def map(self, event: Any) -> dict[str, Any] | None:
        if not isinstance(event, dict):
            return {"type": "event", "data": str(event)}
        if "data" in event and event["data"]:
            return {"type": "text", "data": event["data"]}
        current = event.get("current_tool_use") or event.get("tool_use")
        if not current:
            return None
        name = current.get("name")
        if not name:
            return None
        tool_id = str(current.get("toolUseId") or current.get("tool_use_id") or name)
        if tool_id in self._seen_tool_ids:
            return None
        self._seen_tool_ids.add(tool_id)
        return {
            "type": "tool",
            "name": name,
            "id": tool_id,
            "input": current.get("input") or current.get("arguments"),
        }


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "sorry, i can not help with this" in lowered:
        return "Sorry, I can not help with this."
    if "401" in text or "invalid_api_key" in lowered or "incorrect api key" in lowered:
        return (
            "OpenAI rejected the API key (HTTP 401). "
            "Set a valid OPENAI_API_KEY in .env, or MODEL_PROVIDER=bedrock. "
            f"Original error: {text}"
        )
    if any(
        token in lowered
        for token in (
            "unrecognizedclientexception",
            "invalidclienttokenid",
            "expiredtoken",
            "security token included in the request is invalid",
        )
    ):
        return (
            "AWS Bedrock rejected the credentials. Set AWS_ACCESS_KEY_ID, "
            "AWS_SECRET_ACCESS_KEY, AWS_REGION, and BEDROCK_MODEL in .env. "
            f"Original error: {text}"
        )
    return text


if __name__ == "__main__":
    sys.exit(main())
