"""Interactive confirmation for write tool calls.

The agent loop calls ``confirm_write`` before executing any tool flagged as
``write=True``. We render a compact, human-readable summary of the proposed
call (truncating long HTML fields) and require an explicit 'y' to proceed.

``rich`` is imported lazily inside the functions so that this module - and
therefore ``agent.loop`` - can be imported in environments where rich is not
installed (notably the test environment, which injects its own confirm_fn).
"""

from __future__ import annotations

from typing import Any

_HTML_FIELDS = {
    "summary",
    "labelcontent",
    "pagecontent",
    "intro",
    "activity",
}

_MAX_HTML_PREVIEW = 800


def _format_args(args: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in args.items():
        if key in _HTML_FIELDS and isinstance(value, str) and len(value) > _MAX_HTML_PREVIEW:
            preview = value[:_MAX_HTML_PREVIEW].rstrip() + "\n... [truncated]"
            lines.append(f"  {key}:\n{_indent(preview, 4)}")
        elif isinstance(value, str) and "\n" in value:
            lines.append(f"  {key}:\n{_indent(value, 4)}")
        else:
            lines.append(f"  {key}: {value!r}")
    return "\n".join(lines)


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line for line in text.splitlines())


def confirm_write(tool_name: str, args: dict[str, Any]) -> bool:
    """Show the proposed call and prompt the teacher for explicit approval."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    body = _format_args(args) if args else "  (no arguments)"
    console.print(
        Panel(
            f"[bold yellow]Proposed write[/bold yellow]: [bold]{tool_name}[/bold]\n\n{body}",
            border_style="yellow",
            title="confirm",
        )
    )
    try:
        answer = console.input("[bold]Apply this change? [y/N]: [/bold]").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in {"y", "yes"}


def render_html_preview(html: str, label: str = "HTML preview") -> None:
    """Optional helper to render an HTML snippet to the terminal as syntax."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax

    console = Console()
    console.print(
        Panel(
            Syntax(html, "html", theme="monokai", word_wrap=True),
            title=label,
            border_style="cyan",
        )
    )
