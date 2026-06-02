"""OpenAI tool-calling loop.

``Agent`` keeps the conversation history, exposes the MoodleClient as tools,
and routes each model turn through:

    1. send history + tools to the model
    2. if the model returned tool_calls:
       - confirm each *write* tool with the user
       - execute it (or skip if declined)
       - append the tool result and continue the loop
    3. otherwise return the assistant's final text

The loop is deliberately small and synchronous so it is easy to read, debug,
and unit-test against a fake OpenAI client.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Iterable, Protocol

from moodle_client import MoodleClient

from .audit import AuditLog
from .confirm import confirm_write
from .summaries import course_summary
from .tools import TOOLS, openai_schemas

_MAX_TOOL_ITERATIONS = 12

ConfirmFn = Callable[[str, dict[str, Any]], bool]


class _OpenAILike(Protocol):
    """Anything that exposes ``chat.completions.create`` with the OpenAI shape.

    Defined as a Protocol so tests can pass a FakeOpenAI without importing the
    real SDK.
    """

    chat: Any


class Agent:
    def __init__(
        self,
        client: MoodleClient,
        openai_client: _OpenAILike,
        model: str,
        system_prompt: str,
        audit: AuditLog,
        confirm_fn: ConfirmFn | None = None,
    ) -> None:
        self.client = client
        self.openai = openai_client
        self.model = model
        self.audit = audit
        self.confirm_fn: ConfirmFn = confirm_fn or confirm_write
        self.history: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "system",
                "content": self._course_context_message(),
            },
        ]

    def _course_context_message(self) -> str:
        summary = course_summary(self.client.course)
        return (
            "Current course structure (refreshed after every write):\n"
            f"{json.dumps(summary, ensure_ascii=False, indent=2)}"
        )

    def _refresh_course_context(self) -> None:
        """Replace the second system message with the latest summary."""
        self.history[1] = {
            "role": "system",
            "content": self._course_context_message(),
        }

    def send(self, user_message: str) -> str:
        """Send one user message and run the tool loop until the model is done."""
        self.history.append({"role": "user", "content": user_message})
        self.audit.write("user_message", content=user_message)

        for _ in range(_MAX_TOOL_ITERATIONS):
            response = self.openai.chat.completions.create(
                model=self.model,
                messages=self.history,
                tools=openai_schemas(),
                tool_choice="auto",
            )
            message = response.choices[0].message
            self.history.append(_message_to_dict(message))
            self.audit.write(
                "assistant_message",
                content=message.content,
                tool_calls=[
                    {"id": c.id, "name": c.function.name, "arguments": c.function.arguments}
                    for c in (message.tool_calls or [])
                ],
            )

            if not message.tool_calls:
                return message.content or ""

            any_writes = False
            for call in message.tool_calls:
                result = self._execute_tool_call(call)
                tool = TOOLS.get(call.function.name)
                if tool and tool.write and result.get("ok"):
                    any_writes = True
                self.history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

            if any_writes:
                self._refresh_course_context()

        return (
            "(Agent stopped: reached the maximum number of tool iterations. "
            "Try restating your request more narrowly.)"
        )

    def _execute_tool_call(self, call: Any) -> dict[str, Any]:
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"Invalid JSON arguments: {exc}"}

        tool = TOOLS.get(name)
        if tool is None:
            return {"ok": False, "error": f"Unknown tool: {name}"}

        if tool.write:
            approved = self.confirm_fn(name, args)
            self.audit.write("confirm", tool=name, args=args, approved=approved)
            if not approved:
                return {
                    "ok": False,
                    "error": "Teacher declined the change. Ask for clarification or adjust the plan.",
                }

        self.audit.write("tool_call", tool=name, args=args)
        result = tool.handler(self.client, args)
        self.audit.write("tool_result", tool=name, result=result)
        return result


def _message_to_dict(message: Any) -> dict[str, Any]:
    """Normalize an OpenAI ChatCompletionMessage into a JSON-serializable dict.

    The OpenAI SDK accepts the model's own message object back as a history
    entry, but we want history to be dict-only so it round-trips through
    audit logs and (later) on-disk session storage.
    """
    out: dict[str, Any] = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        out["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {
                    "name": c.function.name,
                    "arguments": c.function.arguments,
                },
            }
            for c in message.tool_calls
        ]
    return out


def history_preview(history: Iterable[dict[str, Any]]) -> str:
    """Compact debug rendering of a conversation history."""
    lines = []
    for msg in history:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "tool":
            content = f"tool_call_id={msg.get('tool_call_id')} {content}"
        if msg.get("tool_calls"):
            calls = ", ".join(c["function"]["name"] for c in msg["tool_calls"])
            content = (content or "") + f"  [tool_calls: {calls}]"
        lines.append(f"[{role}] {content[:200]}")
    return "\n".join(lines)
