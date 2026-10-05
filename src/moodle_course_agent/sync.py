"""Deterministic Moodle ↔ workspace comparison and apply.

The LLM never computes diffs. This module is the source of truth for:
snapshots comparison, conflict detection, and sync plans.
"""

from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

import yaml

from moodle_course_agent.models import (
    ChangeKind,
    CourseSnapshot,
    ModuleSnapshot,
    SectionSnapshot,
    SyncAction,
    SyncPlan,
    SyncRecord,
    utcnow,
)
from moodle_course_agent.moodle.client import MoodleClient
from moodle_course_agent.moodle.templates import (
    create_aufgabe_mit_abgabe,
    create_aufgabe_ohne_abgabe,
    get_assign_templates,
)
from moodle_course_agent.workspace import (
    build_workspace_snapshot,
    export_snapshot_to_workspace,
    module_file_name,
    section_dir_name,
    update_frontmatter_cmid,
    update_section_yaml_num,
    write_module_file,
)
from moodle_course_agent.workspace.sandbox import WorkspaceSandbox

SUPPORTED = {"label", "page", "url", "forum", "assign"}
ASSIGN_TEMPLATES = {"ohne_abgabe", "mit_abgabe"}
_CONFLICT_REASON = "Both Moodle and local changed since last sync"


def _int(value: Any, default: int) -> int:
    """``int(value)``, using ``default`` only when the value is missing (0 stays 0)."""
    return default if value is None or value == "" else int(value)


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _action(**kwargs: Any) -> SyncAction:
    kwargs.setdefault("id", uuid4().hex[:12])
    return SyncAction(**kwargs)


def _module_key(module: ModuleSnapshot) -> str:
    if module.cmid is not None:
        return f"cmid:{module.cmid}"
    return f"local:{module.local_id}"


def _match_sections(
    moodle: CourseSnapshot, workspace: CourseSnapshot
) -> list[tuple[SectionSnapshot | None, SectionSnapshot | None]]:
    used_local: set[str] = set()
    pairs: list[tuple[SectionSnapshot | None, SectionSnapshot | None]] = []

    local_by_num = {
        s.sectionnum: s for s in workspace.sections if s.sectionnum is not None
    }
    local_by_name: dict[str, list[SectionSnapshot]] = {}
    for section in workspace.sections:
        local_by_name.setdefault(_norm(section.name), []).append(section)

    for remote in moodle.sections:
        local = None
        if remote.sectionnum in local_by_num:
            local = local_by_num[remote.sectionnum]
        elif _norm(remote.name) in local_by_name:
            for candidate in local_by_name[_norm(remote.name)]:
                if candidate.local_id not in used_local:
                    local = candidate
                    break
        if local:
            used_local.add(local.local_id)
        pairs.append((remote, local))

    for local in workspace.sections:
        if local.local_id not in used_local:
            pairs.append((None, local))
    return pairs


def _match_modules(
    remote_section: SectionSnapshot | None,
    local_section: SectionSnapshot | None,
) -> list[tuple[ModuleSnapshot | None, ModuleSnapshot | None]]:
    remotes = list(remote_section.modules) if remote_section else []
    locals_ = list(local_section.modules) if local_section else []
    used_local: set[str] = set()
    pairs: list[tuple[ModuleSnapshot | None, ModuleSnapshot | None]] = []

    local_by_cmid = {m.cmid: m for m in locals_ if m.cmid is not None}
    local_by_name: dict[tuple[str, str], list[ModuleSnapshot]] = {}
    for module in locals_:
        local_by_name.setdefault((_norm(module.modname), _norm(module.name)), []).append(module)

    for remote in remotes:
        local = None
        if remote.cmid in local_by_cmid:
            local = local_by_cmid[remote.cmid]
        else:
            key = (_norm(remote.modname), _norm(remote.name))
            for candidate in local_by_name.get(key, []):
                if candidate.local_id not in used_local:
                    local = candidate
                    break
        if local:
            used_local.add(local.local_id)
        pairs.append((remote, local))

    for local in locals_:
        if local.local_id not in used_local:
            pairs.append((None, local))
    return pairs


def build_sync_plan(
    moodle: CourseSnapshot,
    workspace: CourseSnapshot,
    record: SyncRecord,
    *,
    direction: str = "preview",
) -> SyncPlan:
    """Compare snapshots. Direction filters which actions are included."""
    actions: list[SyncAction] = []

    for remote_section, local_section in _match_sections(moodle, workspace):
        if remote_section and not local_section:
            actions.append(
                _action(
                    kind=ChangeKind.MOODLE_ONLY,
                    entity="section",
                    summary=f"Moodle section {remote_section.name!r} has no local counterpart",
                    moodle_id=remote_section.sectionnum,
                    sectionnum=remote_section.sectionnum,
                    name=remote_section.name,
                    mutates_moodle=False,
                    details={"moodle_hash": remote_section.content_hash},
                )
            )
            for module in remote_section.modules:
                if module.modname not in SUPPORTED:
                    continue
                actions.append(
                    _action(
                        kind=ChangeKind.MOODLE_ONLY,
                        entity="module",
                        summary=f"Moodle {module.modname} {module.name!r} has no local file",
                        moodle_id=module.cmid,
                        sectionnum=module.sectionnum,
                        modname=module.modname,
                        name=module.name,
                        mutates_moodle=False,
                        details={"moodle_hash": module.content_hash, "module": module.model_dump(mode="json")},
                    )
                )
            continue

        if local_section and not remote_section:
            actions.append(
                _action(
                    kind=ChangeKind.LOCAL_ONLY,
                    entity="section",
                    summary=f"Local section {local_section.name!r} is not on Moodle",
                    local_path=local_section.local_id,
                    name=local_section.name,
                    mutates_moodle=True,
                    details={"local_hash": local_section.content_hash, "summary": local_section.summary, "visible": local_section.visible},
                )
            )
            for module in local_section.modules:
                if module.modname not in SUPPORTED:
                    continue
                actions.append(
                    _action(
                        kind=ChangeKind.LOCAL_ONLY,
                        entity="module",
                        summary=f"Local {module.modname} {module.name!r} is not on Moodle",
                        local_path=module.local_id,
                        modname=module.modname,
                        name=module.name,
                        mutates_moodle=True,
                        details={"local_hash": module.content_hash, "module": module.model_dump(mode="json")},
                    )
                )
            continue

        assert remote_section and local_section
        if remote_section.content_hash != local_section.content_hash:
            rec = record.items.get(f"section:{remote_section.sectionnum}")
            side = _changed_side(rec, remote_section.content_hash, local_section.content_hash)
            kind = _diff_kind(side, direction)
            actions.append(
                _action(
                    kind=kind,
                    entity="section",
                    summary=(
                        f"Section {local_section.name!r} differs between Moodle and local"
                        + (" (conflict)" if kind == ChangeKind.CONFLICT else "")
                    ),
                    local_path=local_section.local_id,
                    moodle_id=remote_section.sectionnum,
                    sectionnum=remote_section.sectionnum,
                    name=local_section.name,
                    mutates_moodle=kind == ChangeKind.UPDATE_ON_MOODLE,
                    conflict_reason=_CONFLICT_REASON if kind == ChangeKind.CONFLICT else None,
                    details={
                        "changed_side": side,
                        "moodle_hash": remote_section.content_hash,
                        "local_hash": local_section.content_hash,
                        "moodle_name": remote_section.name,
                        "local_name": local_section.name,
                        "local_summary": local_section.summary,
                        "local_visible": local_section.visible,
                    },
                )
            )

        for remote_mod, local_mod in _match_modules(remote_section, local_section):
            if remote_mod and not local_mod:
                if remote_mod.modname not in SUPPORTED:
                    continue
                actions.append(
                    _action(
                        kind=ChangeKind.MOODLE_ONLY,
                        entity="module",
                        summary=f"Moodle {remote_mod.modname} {remote_mod.name!r} has no local file",
                        moodle_id=remote_mod.cmid,
                        sectionnum=remote_mod.sectionnum,
                        modname=remote_mod.modname,
                        name=remote_mod.name,
                        mutates_moodle=False,
                        details={"moodle_hash": remote_mod.content_hash, "module": remote_mod.model_dump(mode="json")},
                    )
                )
            elif local_mod and not remote_mod:
                if local_mod.modname not in SUPPORTED:
                    continue
                actions.append(
                    _action(
                        kind=ChangeKind.LOCAL_ONLY,
                        entity="module",
                        summary=f"Local {local_mod.modname} {local_mod.name!r} is not on Moodle",
                        local_path=local_mod.local_id,
                        sectionnum=local_section.sectionnum,
                        modname=local_mod.modname,
                        name=local_mod.name,
                        mutates_moodle=True,
                        details={"local_hash": local_mod.content_hash, "module": local_mod.model_dump(mode="json")},
                    )
                )
            elif remote_mod and local_mod:
                if remote_mod.modname not in SUPPORTED and local_mod.modname not in SUPPORTED:
                    continue
                if remote_mod.content_hash == local_mod.content_hash:
                    continue
                rec = record.items.get(_module_key(remote_mod)) or record.items.get(
                    f"local:{local_mod.local_id}"
                )
                side = _changed_side(rec, remote_mod.content_hash, local_mod.content_hash)
                kind = _diff_kind(side, direction)
                actions.append(
                    _action(
                        kind=kind,
                        entity="module",
                        summary=(
                            f"{local_mod.modname} {local_mod.name!r} differs"
                            + (" (conflict)" if kind == ChangeKind.CONFLICT else "")
                        ),
                        local_path=local_mod.local_id,
                        moodle_id=remote_mod.cmid,
                        sectionnum=remote_mod.sectionnum,
                        modname=local_mod.modname,
                        name=local_mod.name,
                        mutates_moodle=kind == ChangeKind.UPDATE_ON_MOODLE,
                        conflict_reason=_CONFLICT_REASON if kind == ChangeKind.CONFLICT else None,
                        details={
                            "changed_side": side,
                            "moodle_hash": remote_mod.content_hash,
                            "local_hash": local_mod.content_hash,
                            "local_module": local_mod.model_dump(mode="json"),
                            "moodle_module": remote_mod.model_dump(mode="json"),
                        },
                    )
                )

    filtered = _filter_direction(actions, direction)
    counts: dict[str, int] = {}
    for action in filtered:
        counts[action.kind.value] = counts.get(action.kind.value, 0) + 1
    counts["total"] = len(filtered)
    counts["moodle_mutations"] = sum(1 for a in filtered if a.mutates_moodle)
    return SyncPlan(
        direction=direction if direction in {"to_moodle", "to_local", "preview"} else "preview",  # type: ignore[arg-type]
        generated_at=utcnow(),
        actions=filtered,
        counts=counts,
    )


def _changed_side(rec: dict[str, str] | None, moodle_hash: str, local_hash: str) -> str:
    """Which side moved since the last sync: ``moodle``, ``local``, ``both``, or ``unknown``.

    Only called for pairs whose hashes differ. ``unknown`` means there is no
    usable baseline, so only an explicit sync direction can resolve it.
    """
    if not rec or not rec.get("moodle_hash") or not rec.get("local_hash"):
        return "unknown"
    moodle_changed = moodle_hash != rec["moodle_hash"]
    local_changed = local_hash != rec["local_hash"]
    if moodle_changed and local_changed:
        return "both"
    if moodle_changed:
        return "moodle"
    if local_changed:
        return "local"
    return "unknown"


def _diff_kind(side: str, direction: str) -> ChangeKind:
    """Carry each one-sided change toward the side that did not change."""
    if side == "both":
        return ChangeKind.CONFLICT
    if side == "moodle":
        return ChangeKind.UPDATE_LOCAL
    if side == "local":
        return ChangeKind.UPDATE_ON_MOODLE
    return ChangeKind.UPDATE_LOCAL if direction == "to_local" else ChangeKind.UPDATE_ON_MOODLE


def _filter_direction(actions: list[SyncAction], direction: str) -> list[SyncAction]:
    if direction == "to_moodle":
        keep = {
            ChangeKind.CREATE_ON_MOODLE,
            ChangeKind.UPDATE_ON_MOODLE,
            ChangeKind.LOCAL_ONLY,
            ChangeKind.CONFLICT,
        }
        out = []
        for action in actions:
            if action.kind not in keep:
                continue
            if action.kind == ChangeKind.LOCAL_ONLY:
                action = action.model_copy(
                    update={"kind": ChangeKind.CREATE_ON_MOODLE, "mutates_moodle": True}
                )
            out.append(action)
        return out
    if direction == "to_local":
        keep = {
            ChangeKind.CREATE_LOCAL,
            ChangeKind.UPDATE_LOCAL,
            ChangeKind.MOODLE_ONLY,
            ChangeKind.CONFLICT,
        }
        out = []
        for action in actions:
            if action.kind not in keep:
                continue
            if action.kind == ChangeKind.MOODLE_ONLY:
                action = action.model_copy(
                    update={"kind": ChangeKind.CREATE_LOCAL, "mutates_moodle": False}
                )
            out.append(action)
        return out
    return actions


def action_record_keys(action: SyncAction) -> set[str]:
    """Sync-record keys that an action refers to."""
    if action.entity == "section":
        return {f"section:{action.moodle_id}"} if action.moodle_id is not None else set()
    keys = set()
    if action.moodle_id is not None:
        keys.add(f"cmid:{action.moodle_id}")
    if action.local_path:
        keys.add(f"local:{action.local_path}")
    return keys


def record_from_snapshots(
    moodle: CourseSnapshot,
    workspace: CourseSnapshot,
    previous: SyncRecord | None = None,
    *,
    synced: set[str] | frozenset[str] = frozenset(),
) -> SyncRecord:
    """Record baseline hashes for matched pairs.

    Without ``previous`` every matched pair becomes the baseline. Otherwise a pair
    gets a fresh baseline only if both sides match or it was just ``synced``;
    pairs that still differ keep their previous entry so pending one-sided
    edits and conflicts are still detected on the next sync.
    """
    old = previous.items if previous else {}
    items: dict[str, dict[str, str]] = {}

    def put(keys: list[str], moodle_hash: str, local_hash: str, local_path: str) -> None:
        if previous is not None and moodle_hash != local_hash and not synced.intersection(keys):
            prior = next((old[k] for k in keys if k in old), None)
            if prior:
                for key in keys:
                    items[key] = prior
            return
        entry = {"moodle_hash": moodle_hash, "local_hash": local_hash, "local_path": local_path}
        for key in keys:
            items[key] = entry

    for remote, local in _match_sections(moodle, workspace):
        if not (remote and local):
            continue
        put([f"section:{remote.sectionnum}"], remote.content_hash, local.content_hash, local.local_id)
        for rm, lm in _match_modules(remote, local):
            if rm and lm:
                put([_module_key(rm), f"local:{lm.local_id}"], rm.content_hash, lm.content_hash, lm.local_id)
    return SyncRecord(updated_at=utcnow(), items=items)


def apply_to_local(
    sandbox: WorkspaceSandbox,
    moodle: CourseSnapshot,
    plan: SyncPlan,
) -> list[str]:
    """Apply create/update-local actions. Does not touch Moodle."""
    written: list[str] = []
    if sandbox.is_empty() or not sandbox.exists("course.yaml"):
        return export_snapshot_to_workspace(sandbox, moodle, overwrite=True)

    modules_by_cmid = {
        m.cmid: m
        for s in moodle.sections
        for m in s.modules
        if m.cmid is not None
    }
    sections_by_num = {s.sectionnum: s for s in moodle.sections}

    for action in plan.actions:
        if action.kind == ChangeKind.CONFLICT:
            continue
        if action.kind == ChangeKind.CREATE_LOCAL and action.entity == "section":
            section = sections_by_num.get(action.moodle_id) if action.moodle_id is not None else None
            if not section:
                continue
            dirname = section_dir_name(section.position, section.name)
            rel_dir = f"sections/{dirname}"
            sandbox.create_dir(rel_dir)
            sandbox.write_text(
                f"{rel_dir}/section.yaml",
                yaml.safe_dump(
                    {
                        "name": section.name,
                        "summary": section.summary,
                        "visible": section.visible,
                        "moodle_sectionnum": section.sectionnum,
                        "is_template_section": section.is_template_section,
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
            )
            written.append(f"{rel_dir}/section.yaml")
            for pos, module in enumerate(section.modules, start=1):
                if module.modname not in SUPPORTED:
                    continue
                rel = f"{rel_dir}/{module_file_name(pos, module.name, module.modname)}"
                write_module_file(sandbox, rel, module)
                written.append(rel)
        elif action.kind in {ChangeKind.CREATE_LOCAL, ChangeKind.UPDATE_LOCAL} and action.entity == "module":
            module = modules_by_cmid.get(action.moodle_id) if action.moodle_id is not None else None
            if not module:
                details = action.details.get("module") or action.details.get("moodle_module")
                if details:
                    module = ModuleSnapshot.model_validate(details)
            if not module:
                continue
            rel = action.local_path
            if not rel:
                section = sections_by_num.get(module.sectionnum)
                dirname = section_dir_name(section.position if section else 0, module.section_name or "section")
                rel = f"sections/{dirname}/{module_file_name(module.position or 1, module.name, module.modname)}"
                sandbox.create_dir(f"sections/{dirname}")
            write_module_file(sandbox, rel, module)
            written.append(rel)
        elif action.kind == ChangeKind.UPDATE_LOCAL and action.entity == "section":
            section = sections_by_num.get(action.moodle_id) if action.moodle_id is not None else None
            if section and action.local_path:
                sandbox.write_text(
                    f"{action.local_path}/section.yaml",
                    yaml.safe_dump(
                        {
                            "name": section.name,
                            "summary": section.summary,
                            "visible": section.visible,
                            "moodle_sectionnum": section.sectionnum,
                            "is_template_section": section.is_template_section,
                        },
                        allow_unicode=True,
                        sort_keys=False,
                    ),
                )
                written.append(f"{action.local_path}/section.yaml")
    return written


def apply_to_moodle(
    client: MoodleClient,
    sandbox: WorkspaceSandbox,
    plan: SyncPlan,
    *,
    template_section_name: str | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Execute Moodle-mutating actions. Caller MUST have obtained approval."""
    results: list[dict[str, Any]] = []
    log = progress or (lambda _msg: None)

    for action in plan.actions:
        if action.kind == ChangeKind.CONFLICT:
            results.append({"id": action.id, "skipped": True, "reason": "conflict"})
            continue
        if not action.mutates_moodle and action.kind != ChangeKind.CREATE_ON_MOODLE:
            continue
        if action.kind not in {ChangeKind.CREATE_ON_MOODLE, ChangeKind.UPDATE_ON_MOODLE, ChangeKind.LOCAL_ONLY}:
            continue
        try:
            result = _apply_one_moodle(client, sandbox, action, template_section_name)
            results.append({"id": action.id, "ok": True, **result})
            log(f"applied {action.kind.value}: {action.summary}")
        except Exception as exc:  # noqa: BLE001 - surface to the plan result
            results.append({"id": action.id, "ok": False, "error": str(exc), "summary": action.summary})
            log(f"failed {action.summary}: {exc}")
    return results


def _apply_one_moodle(
    client: MoodleClient,
    sandbox: WorkspaceSandbox,
    action: SyncAction,
    template_section_name: str | None,
) -> dict[str, Any]:
    if action.entity == "section" and action.kind in {ChangeKind.CREATE_ON_MOODLE, ChangeKind.LOCAL_ONLY}:
        details = action.details
        position = len(client.course) + 1
        created = client.create_section(
            name=action.name or "Untitled",
            summary=str(details.get("summary") or ""),
            position=position,
            visible=_int(details.get("visible"), 1),
        )
        sectionnum = created.get("sectionnum")
        if action.local_path and sectionnum is not None:
            update_section_yaml_num(sandbox, action.local_path, int(sectionnum))
        return {"created": created}

    if action.entity == "section" and action.kind == ChangeKind.UPDATE_ON_MOODLE:
        details = action.details
        client.update_section(
            sectionnum=int(action.moodle_id or action.sectionnum or 0),
            name=str(details.get("local_name") or action.name or ""),
            summary=str(details.get("local_summary") or ""),
            visible=_int(details.get("local_visible"), 1),
        )
        return {"updated": "section"}

    module_data = action.details.get("module") or action.details.get("local_module") or {}
    module = ModuleSnapshot.model_validate(module_data) if module_data else None
    if module is None:
        raise ValueError(f"Missing module payload for action {action.id}")

    if action.kind in {ChangeKind.CREATE_ON_MOODLE, ChangeKind.LOCAL_ONLY}:
        sectionnum = action.sectionnum
        if sectionnum is None:
            # try last section
            sectionnum = client.course[-1]["section"] if client.course else 0
        created = _create_module(client, module, int(sectionnum), template_section_name)
        cmid = created.get("cmid") or created.get("new_cmid")
        if action.local_path and cmid is not None:
            update_frontmatter_cmid(sandbox, action.local_path, int(cmid))
        return {"created": created}

    if action.kind == ChangeKind.UPDATE_ON_MOODLE:
        cmid = int(action.moodle_id)
        _update_module(client, module, cmid)
        return {"updated": cmid}

    raise ValueError(f"Unsupported action {action.kind}")


def _create_module(
    client: MoodleClient,
    module: ModuleSnapshot,
    sectionnum: int,
    template_section_name: str | None,
) -> dict[str, Any]:
    fields = module.fields
    common = dict(
        sectionnum=sectionnum,
        visible=module.visible,
        visibleoncoursepage=module.visibleoncoursepage,
    )
    if module.modname == "label":
        return client.create_label(
            labelcontent=str(fields.get("labelcontent") or ""),
            name=module.name,
            **common,
        )
    if module.modname == "page":
        return client.create_page(
            name=module.name,
            intro=str(fields.get("intro") or ""),
            pagecontent=str(fields.get("pagecontent") or ""),
            showdescription=int(fields.get("showdescription") or 0),
            **common,
        )
    if module.modname == "url":
        return client.create_url(
            name=module.name,
            intro=str(fields.get("intro") or ""),
            externalurl=str(fields.get("externalurl") or ""),
            display=int(fields.get("display") or 0),
            showdescription=int(fields.get("showdescription") or 0),
            **common,
        )
    if module.modname == "forum":
        return client.create_forum(
            name=module.name,
            intro=str(fields.get("intro") or ""),
            type=str(fields.get("type") or "general"),
            showdescription=int(fields.get("showdescription") or 0),
            **common,
        )
    if module.modname == "assign":
        template_key = _assign_template_key(module)
        if template_key and _can_copy_template_into(client, sectionnum, template_section_name):
            # Errors after this point propagate: falling back to create_assign
            # would duplicate the assignment if the template copy already exists.
            create = create_aufgabe_mit_abgabe if template_key == "mit_abgabe" else create_aufgabe_ohne_abgabe
            return create(
                client,
                name=module.name,
                intro=str(fields.get("intro") or ""),
                activity=str(fields.get("activity") or ""),
                sectionnum=sectionnum,
                duedate=int(fields.get("duedate") or 0),
                cutoffdate=int(fields.get("cutoffdate") or 0),
                allowsubmissionsfromdate=int(fields.get("allowsubmissionsfromdate") or 0),
                grade=_int(fields.get("grade"), 100),
                maxattempts=_int(fields.get("maxattempts"), 1),
                visible=module.visible,
                visibleoncoursepage=module.visibleoncoursepage,
                showdescription=int(fields.get("showdescription") or 0),
                zeitaufwand=fields.get("zeitaufwand"),
                template_section_name=template_section_name,
            )
        return client.create_assign(
            name=module.name,
            intro=str(fields.get("intro") or ""),
            activity=str(fields.get("activity") or ""),
            duedate=int(fields.get("duedate") or 0),
            cutoffdate=int(fields.get("cutoffdate") or 0),
            allowsubmissionsfromdate=int(fields.get("allowsubmissionsfromdate") or 0),
            grade=_int(fields.get("grade"), 100),
            maxattempts=_int(fields.get("maxattempts"), 1),
            zeitaufwand=fields.get("zeitaufwand"),
            showdescription=int(fields.get("showdescription") or 0),
            **common,
        )
    raise ValueError(f"Unsupported module type {module.modname}")


def _assign_template_key(module: ModuleSnapshot) -> str | None:
    """Template from frontmatter ``template``: ohne_abgabe (default), mit_abgabe, or none."""
    value = (module.template or "ohne_abgabe").strip().lower()
    if value == "none":
        return None
    if value not in ASSIGN_TEMPLATES:
        raise ValueError(
            f"Unknown assignment template {module.template!r} in {module.local_id}; "
            "use ohne_abgabe, mit_abgabe, or none"
        )
    return value


def _can_copy_template_into(client: MoodleClient, sectionnum: int, template_section_name: str | None) -> bool:
    """Template copies are placed before an existing module, so the section must not be empty."""
    if not template_section_name:
        return False
    section = next((s for s in client.course if s.get("section") == sectionnum), None)
    if not section or not section.get("modules"):
        return False
    try:
        get_assign_templates(client, template_section_name)
    except ValueError:
        return False
    return True


def _update_module(client: MoodleClient, module: ModuleSnapshot, cmid: int) -> None:
    fields = module.fields
    if module.modname == "label":
        client.update_label(
            cmid=cmid,
            name=module.name,
            labelcontent=str(fields.get("labelcontent") or ""),
            visible=module.visible,
            visibleoncoursepage=module.visibleoncoursepage,
        )
        return
    if module.modname == "page":
        client.update_page(
            cmid=cmid,
            name=module.name,
            intro=str(fields.get("intro") or ""),
            pagecontent=str(fields.get("pagecontent") or ""),
            visible=module.visible,
            visibleoncoursepage=module.visibleoncoursepage,
            showdescription=int(fields.get("showdescription") or 0),
        )
        return
    if module.modname == "url":
        client.update_url(
            cmid=cmid,
            name=module.name,
            intro=str(fields.get("intro") or ""),
            externalurl=str(fields.get("externalurl") or ""),
            display=int(fields.get("display") or 0),
            visible=module.visible,
            visibleoncoursepage=module.visibleoncoursepage,
            showdescription=int(fields.get("showdescription") or 0),
        )
        return
    if module.modname == "forum":
        client.update_forum(
            cmid=cmid,
            name=module.name,
            intro=str(fields.get("intro") or ""),
            visible=module.visible,
            visibleoncoursepage=module.visibleoncoursepage,
            showdescription=int(fields.get("showdescription") or 0),
            type=str(fields.get("type") or "general"),
        )
        return
    if module.modname == "assign":
        client.update_assign(
            cmid=cmid,
            name=module.name,
            intro=str(fields.get("intro") or ""),
            activity=str(fields.get("activity") or ""),
            allowsubmissionsfromdate=int(fields.get("allowsubmissionsfromdate") or 0),
            duedate=int(fields.get("duedate") or 0),
            cutoffdate=int(fields.get("cutoffdate") or 0),
            grade=_int(fields.get("grade"), 100),
            maxattempts=_int(fields.get("maxattempts"), 1),
            visible=module.visible,
            visibleoncoursepage=module.visibleoncoursepage,
            showdescription=int(fields.get("showdescription") or 0),
            zeitaufwand=fields.get("zeitaufwand"),
        )
        return
    raise ValueError(f"Unsupported module type {module.modname}")
