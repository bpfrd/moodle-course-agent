"""Build a normalized Moodle course snapshot from the live (or fake) client."""

from __future__ import annotations

from typing import Any

from moodle_course_agent.hashing import content_hash
from moodle_course_agent.models import (
    CourseSnapshot,
    ModuleSnapshot,
    ModuleType,
    SectionSnapshot,
    utcnow,
)
from moodle_course_agent.moodle.client import MoodleClient

_GETTERS = {
    "label": "get_label",
    "page": "get_page",
    "url": "get_url",
    "forum": "get_forum",
    "assign": "get_assign",
}

_HASH_FIELDS = {
    "label": ("name", "visible", "visibleoncoursepage", "labelcontent"),
    "page": ("name", "visible", "visibleoncoursepage", "showdescription", "intro", "pagecontent"),
    "url": ("name", "visible", "visibleoncoursepage", "showdescription", "intro", "externalurl", "display"),
    "forum": ("name", "visible", "visibleoncoursepage", "showdescription", "intro", "type"),
    "assign": (
        "name",
        "visible",
        "visibleoncoursepage",
        "showdescription",
        "intro",
        "activity",
        "duedate",
        "cutoffdate",
        "allowsubmissionsfromdate",
        "grade",
        "maxattempts",
        "zeitaufwand",
    ),
}


def slugify(value: str) -> str:
    raw = (value or "untitled").strip().lower()
    out = []
    for ch in raw:
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    slug = "".join(out).strip("-") or "untitled"
    return slug[:60]


def _section_local_id(sectionnum: int, name: str) -> str:
    return f"sec-{sectionnum:02d}-{slugify(name)}"


def _module_local_id(section_id: str, position: int, name: str, modname: str) -> str:
    return f"{section_id}/{position:02d}-{slugify(name)}.{modname}"


def _extract_fields(modname: str, body: dict[str, Any], module: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    wanted = _HASH_FIELDS.get(modname, ())
    merged = {**module, **body}
    for key in wanted:
        if key == "zeitaufwand":
            value = merged.get("zeitaufwand") or merged.get("timerequired")
            if value:
                fields[key] = value
        elif key in merged and merged[key] is not None:
            fields[key] = merged[key]
    if "name" not in fields:
        fields["name"] = module.get("name", "")
    return fields


def _module_hash(modname: str, name: str, visible: int, fields: dict[str, Any]) -> str:
    keys = _HASH_FIELDS.get(modname, ("name", "visible"))
    payload = {"modname": modname, "name": name, "visible": visible}
    for key in keys:
        if key in fields:
            payload[key] = fields[key]
    return content_hash(payload)


def fetch_module_body(client: MoodleClient, modname: str, cmid: int) -> dict[str, Any]:
    getter = _GETTERS.get(modname)
    if not getter:
        return {}
    try:
        return getattr(client, getter)(cmid) or {}
    except Exception:
        return {}


def build_moodle_snapshot(
    client: MoodleClient,
    *,
    template_section_name: str | None = None,
    fetch_bodies: bool = True,
) -> CourseSnapshot:
    """Normalize `core_course_get_contents` (+ optional per-module bodies)."""
    raw_sections = client.course or []
    sections: list[SectionSnapshot] = []

    for index, raw in enumerate(raw_sections):
        sectionnum = int(raw.get("section", index))
        name = raw.get("name") or f"Section {sectionnum}"
        summary = raw.get("summary") or ""
        visible = int(raw.get("visible", 1))
        is_template = bool(
            template_section_name and name == template_section_name
        ) or bool(raw.get("visible", 1) == 0 and "vorlage" in name.lower())
        section_id = _section_local_id(sectionnum, name)
        modules: list[ModuleSnapshot] = []
        for pos, raw_mod in enumerate(raw.get("modules") or []):
            cmid = int(raw_mod.get("id"))
            modname = raw_mod.get("modname") or ModuleType.UNKNOWN.value
            mname = raw_mod.get("name") or f"{modname}-{cmid}"
            body = fetch_module_body(client, modname, cmid) if fetch_bodies else {}
            fields = _extract_fields(modname, body, raw_mod)
            snapshot = ModuleSnapshot(
                local_id=_module_local_id(section_id, pos + 1, mname, modname),
                modname=modname,
                name=mname,
                visible=int(raw_mod.get("visible", 1)),
                visibleoncoursepage=int(raw_mod.get("visibleoncoursepage", 1)),
                cmid=cmid,
                sectionnum=sectionnum,
                section_name=name,
                position=pos + 1,
                fields=fields,
                source="moodle",
            )
            snapshot.content_hash = _module_hash(
                modname, snapshot.name, snapshot.visible, fields
            )
            modules.append(snapshot)

        section = SectionSnapshot(
            local_id=section_id,
            name=name,
            summary=summary,
            visible=visible,
            sectionnum=sectionnum,
            position=index,
            is_template_section=is_template,
            modules=modules,
            source="moodle",
        )
        section.content_hash = content_hash(
            {"name": name, "summary": summary, "visible": visible}
        )
        sections.append(section)

    title = ""
    if sections:
        title = sections[0].name if sections[0].sectionnum == 0 else f"Course {client.courseid}"

    return CourseSnapshot(
        course_id=int(client.courseid),
        title=title,
        source="moodle",
        fetched_at=utcnow(),
        sections=sections,
        template_section_name=template_section_name,
    )


def compact_summary(snapshot: CourseSnapshot) -> list[dict[str, Any]]:
    """LLM-safe projection: ids/names/types only, no HTML bodies."""
    return snapshot.summary()["sections"]
