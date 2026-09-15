"""One MCP server: every Moodle API method, plus workspace and sync."""

from __future__ import annotations

import inspect

from moodle_course_agent.app import CourseApplication
from moodle_course_agent.config import load_settings
from moodle_course_agent.moodle import iter_moodle_methods


def build_mcp_server(app: CourseApplication | None = None):
    from mcp.server.fastmcp import FastMCP

    application = app or CourseApplication(load_settings())
    application.bootstrap()
    client = application.moodle
    mcp = FastMCP("moodle-course")

    def add(fn, *, name: str, description: str):
        mcp.add_tool(fn, name=name, description=description)

    for name, method, write, doc in iter_moodle_methods(client):
        add(_mcp_fn(method, write=write, after=application.after_moodle_write if write else None), name=name, description=doc)

    add(lambda: (application.moodle_snapshot or application.refresh_moodle_snapshot()).summary()["sections"],
        name="get_course_structure",
        description="Section/module ids, names, and types.")
    add(lambda: application.status(),
        name="get_course_status",
        description="Moodle + workspace + sync status.")
    add(lambda direction="preview": application.preview_sync(direction).model_dump(mode="json"),
        name="preview_sync",
        description="Deterministic Moodle ↔ local diff.")
    add(
        lambda approved=False: (
            {"ok": False, "error": "Set approved=true after explicit human approval."}
            if not approved
            else application.apply_sync("to_moodle", approved=True)
        ),
        name="apply_sync_to_moodle",
        description="Push local files to Moodle. Requires approved=true. Updates the workspace after.",
    )
    add(lambda: application.apply_sync("to_local", approved=True),
        name="apply_sync_to_local",
        description="Pull Moodle content into local Markdown/YAML files.")
    add(lambda path=".": application.workspace.list_dir(path),
        name="list_workspace",
        description="List workspace files.")
    add(lambda path: application.workspace.read_text(path),
        name="read_workspace_file",
        description="Read a workspace file.")
    add(lambda path, content: _write_workspace(application, path, content),
        name="write_workspace_file",
        description="Write a local workspace file. Does not change Moodle.")
    return mcp


def _write_workspace(application: CourseApplication, path: str, content: str) -> str:
    rel = application.workspace.write_text(path, content)
    application.refresh_workspace_snapshot()
    return rel


def _mcp_fn(method, *, write: bool, after):
    sig = inspect.signature(method)
    if write:
        params = list(sig.parameters.values())
        params.append(
            inspect.Parameter(
                "approved",
                inspect.Parameter.KEYWORD_ONLY,
                default=False,
                annotation=bool,
            )
        )
        new_sig = sig.replace(parameters=params)

        def fn(*args, approved: bool = False, **kwargs):
            if not approved:
                return {"ok": False, "error": "Set approved=true after explicit human approval."}
            result = method(*args, **kwargs)
            extra = after() if after else None
            payload = {"ok": True, "result": result}
            if extra:
                payload["workspace_updated"] = extra
            return payload

        fn.__signature__ = new_sig  # type: ignore[attr-defined]
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
