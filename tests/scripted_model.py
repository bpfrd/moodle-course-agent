"""Scripted Strands model used by end-to-end tests (no live LLM)."""

from __future__ import annotations

import json
import threading
from collections.abc import AsyncIterable
from typing import Any
from uuid import uuid4

from strands.models.model import Model
from strands.types.content import Messages, SystemContentBlock
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolChoice, ToolSpec


def text_turn(text: str) -> list[StreamEvent]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {}}},
        {"contentBlockDelta": {"delta": {"text": text}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "end_turn"}},
        {
            "metadata": {
                "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                "metrics": {"latencyMs": 1},
            }
        },
    ]


def tool_turn(name: str, arguments: dict[str, Any] | None = None) -> list[StreamEvent]:
    payload = json.dumps(arguments or {})
    tool_id = f"tool_{uuid4().hex[:8]}"
    return [
        {"messageStart": {"role": "assistant"}},
        {
            "contentBlockStart": {
                "start": {"toolUse": {"name": name, "toolUseId": tool_id}}
            }
        },
        {"contentBlockDelta": {"delta": {"toolUse": {"input": payload}}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "tool_use"}},
        {
            "metadata": {
                "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                "metrics": {"latencyMs": 1},
            }
        },
    ]


class ScriptedModel(Model):
    """Yields pre-recorded Strands stream events, one agent turn at a time."""

    def __init__(self, scripts: list[list[StreamEvent]]) -> None:
        self._scripts = list(scripts)
        self.calls: list[dict[str, Any]] = []

    def update_config(self, **model_config: Any) -> None:
        return None

    def get_config(self) -> dict[str, Any]:
        return {"model_id": "scripted-test"}

    async def structured_output(self, *args: Any, **kwargs: Any):  # noqa: ANN201
        if False:
            yield {}
        raise NotImplementedError("ScriptedModel does not support structured output")

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        *,
        tool_choice: ToolChoice | None = None,
        system_prompt_content: list[SystemContentBlock] | None = None,
        invocation_state: dict[str, Any] | None = None,
        cancel_signal: threading.Event | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[StreamEvent]:
        self.calls.append({"messages": messages, "system_prompt": system_prompt})
        if not self._scripts:
            raise AssertionError("ScriptedModel has no remaining turns")
        events = self._scripts.pop(0)
        for event in events:
            yield event
