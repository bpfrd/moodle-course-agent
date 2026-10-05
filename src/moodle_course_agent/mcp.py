"""One MCP server: every Moodle API method, plus workspace and sync.

Moodle writes ask the human directly through MCP elicitation when the client
supports it, so the calling model cannot approve its own changes. Clients
without elicitation fall back to ``approved=true``; those tools are annotated
as destructive so hosts can show their own permission prompt.
"""

from __future__ import annotations

import inspect
from typing import Any

from mcp.server.fastmcp import Context
from mcp.types import ClientCapabilities, ElicitationCapability, ToolAnnotations
from pydantic import BaseModel, Field

from moodle_course_agent.app import CourseApplication
from moodle_course_agent.config import load_settings
from moodle_course_agent.moodle import iter_moodle_methods

NOT_APPROVED = "Not approved by the teacher. No Moodle change was made."
NEEDS_APPROVED_FLAG = (
    "This MCP client cannot ask the teacher directly (no elicitation support). "
    "Ask the teacher, then call again with approved=true."
)

READ_ONLY = ToolAnnotations(readOnlyHint=True)
LOCAL_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False)
MOODLE_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)


class Approval(BaseModel):
    approve: bool = Field(description="Apply this change to the live Moodle course?")


def _describe(name: str, kwargs: dict[str, Any]) -> str:
    parts = []
    for key, value in kwargs.items():
        text = " ".join(str(value).split())
        parts.append(f"  {key}: {text[:200] + '…' if len(text) > 200 else text}")
    return f"Moodle change: {name}\n" + "\n".join(parts)


async def confirm_moodle_write(ctx: Context, name: str, kwargs: dict[str, Any], approved: bool) -> str | None:
    """Return None when the write may proceed, otherwise the refusal message."""
    session = ctx.request_context.session
    if not session.check_client_capability(ClientCapabilities(elicitation=ElicitationCapability())):
        return None if approved else NEEDS_APPROVED_FLAG
    result = await ctx.elicit(f"Apply this change to Moodle?\n\n{_describe(name, kwargs)}", Approval)
    if result.action == "accept" and result.data is not None and result.data.approve:
        return None
    return NOT_APPROVED


def build_mcp_server(app: CourseApplication | None = None):
    from mcp.server.fastmcp import FastMCP

    application = app or CourseApplication(load_settings())
    application.bootstrap()
    client = application.moodle
    mcp = FastMCP("moodle-course")

    def add(fn, *, name: str, description: str, annotations: ToolAnnotations = READ_ONLY):
        mcp.add_tool(fn, name=name, description=description, annotations=annotations)

    for name, method, write, doc in iter_moodle_methods(client):
        add(
            _mcp_fn(method, write=write, after=application.after_moodle_write if write else None),
            name=name,
            description=doc + (" Asks the teacher for approval." if write else ""),
            annotations=MOODLE_WRITE if write else READ_ONLY,
        )

    async def apply_sync_to_moodle(ctx: Context, approved: bool = False) -> dict[str, Any]:
        plan = application.preview_sync("to_moodle")
        summary = {"actions": [a.summary for a in plan.actions], "counts": plan.counts}
        refusal = await confirm_moodle_write(ctx, "apply_sync_to_moodle", summary, approved)
        if refusal:
            return {"ok": False, "error": refusal}
        return application.apply_sync("to_moodle", approved=True)

    add(lambda: (application.moodle_snapshot or application.refresh_moodle_snapshot()).summary()["sections"],
        name="get_course_structure",
        description="Section/module ids, names, and types.")
    add(lambda: application.status(),
        name="get_course_status",
        description="Moodle + workspace + sync status.")
    add(lambda direction="preview": application.preview_sync(direction).model_dump(mode="json"),
        name="preview_sync",
        description="Deterministic Moodle ↔ local diff.")
    add(apply_sync_to_moodle,
        name="apply_sync_to_moodle",
        description="Push local files to Moodle. Asks the teacher for approval. Updates the workspace after.",
        annotations=MOODLE_WRITE)
    add(lambda: application.apply_sync("to_local", approved=True),
        name="apply_sync_to_local",
        description="Pull Moodle-side changes into local Markdown/YAML files. Keeps unpushed local edits.",
        annotations=LOCAL_WRITE)
    add(lambda path=".": application.workspace.list_dir(path),
        name="list_workspace",
        description="List workspace files.")
    add(lambda path: application.workspace.read_text(path),
        name="read_workspace_file",
        description="Read a workspace file.")
    add(lambda path, content: _write_workspace(application, path, content),
        name="write_workspace_file",
        description="Write a local workspace file. Does not change Moodle.",
        annotations=LOCAL_WRITE)
    return mcp


def _write_workspace(application: CourseApplication, path: str, content: str) -> str:
    rel = application.workspace.write_text(path, content)
    application.refresh_workspace_snapshot()
    return rel


def _mcp_fn(method, *, write: bool, after):
    sig = inspect.signature(method)
    if write:
        params = list(sig.parameters.values())
        params.append(inspect.Parameter("approved", inspect.Parameter.KEYWORD_ONLY, default=False, annotation=bool))
        params.append(inspect.Parameter("ctx", inspect.Parameter.KEYWORD_ONLY, annotation=Context))
        new_sig = sig.replace(parameters=params)

        async def fn(*args, ctx: Context, approved: bool = False, **kwargs):
            bound = sig.bind(*args, **kwargs)
            refusal = await confirm_moodle_write(ctx, method.__name__, dict(bound.arguments), approved)
            if refusal:
                return {"ok": False, "error": refusal}
            result = method(*args, **kwargs)
            extra = after() if after else None
            payload = {"ok": True, "result": result}
            if extra:
                payload["workspace_updated"] = extra
            return payload

        fn.__signature__ = new_sig  # type: ignore[attr-defined]
        # FastMCP finds the Context parameter through type hints, not the signature.
        fn.__annotations__ = {"ctx": Context, "approved": bool}
    else:
        def fn(*args, **kwargs):
            return method(*args, **kwargs)

        fn.__signature__ = sig  # type: ignore[attr-defined]
    fn.__name__ = method.__name__
    fn.__doc__ = inspect.getdoc(method) or method.__name__
    return fn


def main() -> None:
    build_mcp_server().run()


if __name__ == "__main__":
    main()
