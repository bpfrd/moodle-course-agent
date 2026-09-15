"""Strands tools: Moodle API (from the client), workspace, templates, sync."""

from __future__ import annotations

import inspect
from typing import Any, Optional

from strands import tool

from moodle_course_agent.app import CourseApplication
from moodle_course_agent.moodle import iter_moodle_methods
from moodle_course_agent.moodle.templates import (
    create_aufgabe_mit_abgabe,
    create_aufgabe_ohne_abgabe,
    get_assign_templates,
)
from moodle_course_agent.workspace.sandbox import WorkspaceError

READ_EXTRAS = [
    "get_course_status",
    "get_course_structure",
    "find_sections",
    "find_modules",
    "list_templates",
    "list_workspace",
    "workspace_tree",
    "read_workspace_file",
    "preview_sync",
    "recall_memory",
]
WORKSPACE_WRITES = [
    "write_workspace_file",
    "create_workspace_dir",
    "rename_workspace_path",
    "delete_workspace_path",
]


def hitl_allowlist(client: Any | None = None) -> list[str]:
    """Tools that may run without human approval (reads, local files, pull-to-local)."""
    names = list(READ_EXTRAS + WORKSPACE_WRITES + ["remember_fact", "apply_sync_to_local"])
    if client is not None:
        names.extend(name for name, _, write, _ in iter_moodle_methods(client) if not write)
    return names


ALLOWED_WITHOUT_APPROVAL = hitl_allowlist()


def _safe(fn):
    try:
        return {"ok": True, "result": fn()}
    except (WorkspaceError, ValueError, Exception) as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "error_type": type(exc).__name__}


def _bind_moodle_tool(method, *, name: str, doc: str, write: bool, after_write):
    def body(*args, **kwargs):
        try:
            result = method(*args, **kwargs)
            extra = after_write() if write else None
            payload: dict[str, Any] = {"ok": True, "result": result}
            if extra:
                payload["workspace_updated"] = extra
            return payload
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "error_type": type(exc).__name__}

    body.__name__ = name
    body.__doc__ = doc + (" Requires human approval." if write else "")
    body.__signature__ = inspect.signature(method)
    return tool(body)


def build_tools(app: CourseApplication) -> list:
    client = app.moodle

    def after_write():
        return app.after_moodle_write()

    moodle_tools = [
        _bind_moodle_tool(method, name=name, doc=doc, write=write, after_write=after_write)
        for name, method, write, doc in iter_moodle_methods(client)
    ]

    @tool
    def get_course_status() -> dict[str, Any]:
        """Compact live status: Moodle summary, workspace tree, sync counts."""
        return _safe(lambda: {
            "moodle": (app.moodle_snapshot or app.refresh_moodle_snapshot()).summary(),
            "workspace_tree": app.workspace.tree(),
            "sync_counts": app.preview_sync("preview").counts,
            "memory": [f.model_dump(mode="json") for f in app.store.load_memory().facts],
        })

    @tool
    def get_course_structure() -> dict[str, Any]:
        """Section/module ids, names, and types from the current Moodle snapshot."""
        return _safe(lambda: (app.moodle_snapshot or app.refresh_moodle_snapshot()).summary()["sections"])

    @tool
    def find_sections(section_name: str, exact: bool = True) -> dict[str, Any]:
        """Find sections in the Moodle snapshot by name. Never guess sectionnum."""
        def fn():
            snapshot = app.moodle_snapshot or app.refresh_moodle_snapshot()
            matches = []
            for section in snapshot.sections:
                ok = section.name == section_name if exact else section_name.lower() in section.name.lower()
                if ok:
                    matches.append({
                        "sectionnum": section.sectionnum,
                        "name": section.name,
                        "visible": section.visible,
                        "modules_count": len(section.modules),
                        "is_template_section": section.is_template_section,
                    })
            return matches
        return _safe(fn)

    @tool
    def find_modules(
        section_name: Optional[str] = None,
        modname: Optional[str] = None,
        name_contains: Optional[str] = None,
        cmid: Optional[int] = None,
    ) -> dict[str, Any]:
        """Find modules in the Moodle snapshot. Never guess cmid."""
        def fn():
            snapshot = app.moodle_snapshot or app.refresh_moodle_snapshot()
            found = []
            for section in snapshot.sections:
                if section_name and section.name.lower() != section_name.lower():
                    continue
                for module in section.modules:
                    if cmid is not None and module.cmid != cmid:
                        continue
                    if cmid is None:
                        if modname and module.modname != modname:
                            continue
                        if name_contains and name_contains.lower() not in module.name.lower():
                            continue
                    found.append({
                        "cmid": module.cmid,
                        "modname": module.modname,
                        "name": module.name,
                        "visible": module.visible,
                        "sectionnum": section.sectionnum,
                        "section_name": section.name,
                    })
            return found
        return _safe(fn)

    @tool
    def list_templates() -> dict[str, Any]:
        """List modules in hidden/reference/template sections."""
        def fn():
            snapshot = app.moodle_snapshot or app.refresh_moodle_snapshot()
            templates = []
            for section in snapshot.sections:
                if not section.is_template_section and section.visible:
                    continue
                for module in section.modules:
                    templates.append({
                        "cmid": module.cmid,
                        "modname": module.modname,
                        "name": module.name,
                        "sectionnum": section.sectionnum,
                        "section_name": section.name,
                    })
            try:
                mapping = get_assign_templates(client, app.settings.template_section_name)
            except Exception:
                mapping = {}
            return {"modules": templates, "named_assign_templates": mapping}
        return _safe(fn)

    @tool
    def create_aufgabe_ohne_abgabe(
        name: str,
        intro: str,
        activity: str,
        sectionnum: Optional[int] = None,
        beforemod: Optional[int] = None,
        duedate: int = 0,
        zeitaufwand: Optional[str] = None,
        template_section_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Copy the 'Aufgabe ohne Abgabe' template, then update it (requires approval)."""
        def fn():
            result = create_aufgabe_ohne_abgabe(
                client,
                name=name,
                intro=intro,
                activity=activity,
                sectionnum=sectionnum,
                beforemod=beforemod,
                duedate=duedate,
                zeitaufwand=zeitaufwand,
                template_section_name=template_section_name or app.settings.template_section_name,
            )
            after_write()
            return result
        return _safe(fn)

    @tool
    def create_aufgabe_mit_abgabe(
        name: str,
        intro: str,
        activity: str,
        sectionnum: Optional[int] = None,
        beforemod: Optional[int] = None,
        duedate: int = 0,
        zeitaufwand: Optional[str] = None,
        template_section_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Copy the 'Aufgabe mit Abgabe' template, then update it (requires approval)."""
        def fn():
            result = create_aufgabe_mit_abgabe(
                client,
                name=name,
                intro=intro,
                activity=activity,
                sectionnum=sectionnum,
                beforemod=beforemod,
                duedate=duedate,
                zeitaufwand=zeitaufwand,
                template_section_name=template_section_name or app.settings.template_section_name,
            )
            after_write()
            return result
        return _safe(fn)

    @tool
    def copy_template_module(cmid: int, beforemod: int = 0, new_name: Optional[str] = None) -> dict[str, Any]:
        """Copy a template module into the course (requires approval). Optionally rename."""
        def fn():
            copied = client.copy_module(cmid=cmid, beforemod=beforemod)
            new_cmid = copied.get("cmid")
            if new_name and new_cmid:
                snapshot = app.refresh_moodle_snapshot()
                module = snapshot.module_by_cmid(int(new_cmid))
                if module and module.modname == "label":
                    body = client.get_label(int(new_cmid))
                    client.update_label(int(new_cmid), new_name, body.get("labelcontent") or "", visible=1)
            after_write()
            return copied
        return _safe(fn)

    @tool
    def list_workspace(path: str = ".") -> dict[str, Any]:
        """List files and directories in the local course workspace."""
        return _safe(lambda: app.workspace.list_dir(path))

    @tool
    def workspace_tree() -> dict[str, Any]:
        """Show the local workspace as a tree."""
        return _safe(lambda: app.workspace.tree())

    @tool
    def read_workspace_file(path: str) -> dict[str, Any]:
        """Read a Markdown/YAML/text file from the workspace."""
        return _safe(lambda: {"path": path, "content": app.workspace.read_text(path)})

    @tool
    def write_workspace_file(path: str, content: str, overwrite: bool = True) -> dict[str, Any]:
        """Create or update a local workspace file. Does not change Moodle."""
        def fn():
            rel = app.workspace.write_text(path, content, overwrite=overwrite)
            app.refresh_workspace_snapshot()
            return {"path": rel}
        return _safe(fn)

    @tool
    def create_workspace_dir(path: str) -> dict[str, Any]:
        """Create a directory in the workspace."""
        return _safe(lambda: {"path": app.workspace.create_dir(path)})

    @tool
    def rename_workspace_path(source: str, dest: str) -> dict[str, Any]:
        """Rename a file or directory in the workspace."""
        def fn():
            rel = app.workspace.rename(source, dest)
            app.refresh_workspace_snapshot()
            return {"path": rel}
        return _safe(fn)

    @tool
    def delete_workspace_path(path: str) -> dict[str, Any]:
        """Delete a workspace file or empty directory. Does not change Moodle."""
        def fn():
            rel = app.workspace.delete(path)
            app.refresh_workspace_snapshot()
            return {"deleted": rel}
        return _safe(fn)

    @tool
    def preview_sync(direction: str = "preview") -> dict[str, Any]:
        """Deterministic Moodle ↔ local diff. direction: preview | to_moodle | to_local."""
        return _safe(lambda: app.preview_sync(direction).model_dump(mode="json"))

    @tool
    def apply_sync_to_moodle() -> dict[str, Any]:
        """Push local course files to Moodle (requires approval). Skips conflicts. Updates workspace after."""
        return _safe(lambda: app.apply_sync("to_moodle", approved=True, skip_conflicts=True))

    @tool
    def apply_sync_to_local() -> dict[str, Any]:
        """Pull Moodle content into local Markdown/YAML files. Does not change Moodle."""
        return _safe(lambda: app.apply_sync("to_local", approved=True))

    @tool
    def remember_fact(key: str, value: str) -> dict[str, Any]:
        """Store a small durable preference. Snapshots remain the source of truth for course state."""
        return _safe(lambda: app.store.remember(key, value).model_dump(mode="json"))

    @tool
    def recall_memory() -> dict[str, Any]:
        """Return stored conversational facts."""
        return _safe(lambda: app.store.load_memory().model_dump(mode="json"))

    extras = [
        get_course_status,
        get_course_structure,
        find_sections,
        find_modules,
        list_templates,
        create_aufgabe_ohne_abgabe,
        create_aufgabe_mit_abgabe,
        copy_template_module,
        list_workspace,
        workspace_tree,
        read_workspace_file,
        write_workspace_file,
        create_workspace_dir,
        rename_workspace_path,
        delete_workspace_path,
        preview_sync,
        apply_sync_to_moodle,
        apply_sync_to_local,
        remember_fact,
        recall_memory,
    ]
    return moodle_tools + extras
