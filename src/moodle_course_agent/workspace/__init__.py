"""Local course format: directories + Markdown/YAML.

Layout::

    workspace/
      course.yaml
      sections/
        00-general/
          section.yaml
          01-welcome.md
        01-week-1/
          section.yaml
          01-syllabus.md
          02-homework.md

Module files are Markdown with YAML frontmatter. See docs/local-course-format.md.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from moodle_course_agent.hashing import content_hash
from moodle_course_agent.models import CourseSnapshot, ModuleSnapshot, SectionSnapshot, utcnow
from moodle_course_agent.moodle.snapshot import slugify
from moodle_course_agent.workspace.sandbox import WorkspaceSandbox

ACTIVITY_MARKER = "<!-- moodle:activity -->"
CONTENT_MARKER = "<!-- moodle:content -->"

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def markdown_to_html(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if text.lstrip().startswith("<") and ">" in text[:80]:
        return text
    import markdown as md

    return md.markdown(text, extensions=["extra", "sane_lists"])


def html_to_markdown(html: str) -> str:
    html = (html or "").strip()
    if not html:
        return ""
    from markdownify import markdownify as to_md

    return to_md(html, heading_style="ATX").strip()


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("Frontmatter must be a YAML mapping")
    return meta, match.group(2)


def dump_frontmatter(meta: dict[str, Any], body: str) -> str:
    dumped = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    body = body or ""
    if body and not body.startswith("\n"):
        return f"---\n{dumped}\n---\n\n{body.rstrip()}\n"
    return f"---\n{dumped}\n---\n{body}"


def load_course_yaml(sandbox: WorkspaceSandbox) -> dict[str, Any]:
    if not sandbox.exists("course.yaml"):
        return {}
    data = yaml.safe_load(sandbox.read_text("course.yaml")) or {}
    if not isinstance(data, dict):
        raise ValueError("course.yaml must be a mapping")
    return data


def write_course_yaml(sandbox: WorkspaceSandbox, data: dict[str, Any]) -> None:
    sandbox.write_text(
        "course.yaml",
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
    )


def _split_assign_body(body: str) -> tuple[str, str]:
    if ACTIVITY_MARKER in body:
        intro, activity = body.split(ACTIVITY_MARKER, 1)
        return intro.strip(), activity.strip()
    return body.strip(), ""


def _split_page_body(body: str) -> tuple[str, str]:
    if CONTENT_MARKER in body:
        intro, content = body.split(CONTENT_MARKER, 1)
        return intro.strip(), content.strip()
    return "", body.strip()


def parse_module_file(relative: str, text: str, sectionnum: int | None, section_name: str) -> ModuleSnapshot:
    meta, body = split_frontmatter(text)
    modname = str(meta.get("type") or meta.get("modname") or "page")
    name = str(meta.get("name") or Path(relative).stem)
    visible = int(meta.get("visible", 1))
    fields: dict[str, Any] = {
        "name": name,
        "visible": visible,
        "visibleoncoursepage": int(meta.get("visibleoncoursepage", 1)),
    }
    if modname == "label":
        fields["labelcontent"] = markdown_to_html(body)
    elif modname == "page":
        intro_md, content_md = _split_page_body(body)
        fields["intro"] = markdown_to_html(intro_md)
        fields["pagecontent"] = markdown_to_html(content_md)
        fields["showdescription"] = int(meta.get("showdescription", 0))
    elif modname == "url":
        fields["intro"] = markdown_to_html(body)
        fields["externalurl"] = meta.get("externalurl") or meta.get("url") or ""
        fields["display"] = int(meta.get("display", 0))
        fields["showdescription"] = int(meta.get("showdescription", 0))
    elif modname == "forum":
        fields["intro"] = markdown_to_html(body)
        fields["type"] = meta.get("forum_type") or meta.get("forumtype") or "general"
        fields["showdescription"] = int(meta.get("showdescription", 0))
    elif modname == "assign":
        intro_md, activity_md = _split_assign_body(body)
        fields["intro"] = markdown_to_html(intro_md)
        fields["activity"] = markdown_to_html(activity_md)
        for key in (
            "duedate",
            "cutoffdate",
            "allowsubmissionsfromdate",
            "gradingduedate",
            "timelimit",
            "grade",
            "maxattempts",
            "showdescription",
            "submissionattachments",
        ):
            if key in meta:
                fields[key] = int(meta[key])
        if meta.get("zeitaufwand") or meta.get("timerequired"):
            fields["zeitaufwand"] = meta.get("zeitaufwand") or meta.get("timerequired")
    else:
        fields["raw"] = body

    cmid = meta.get("moodle_cmid")
    snapshot = ModuleSnapshot(
        local_id=relative,
        modname=modname,
        name=name,
        visible=visible,
        visibleoncoursepage=int(meta.get("visibleoncoursepage", 1)),
        cmid=int(cmid) if cmid is not None else None,
        sectionnum=sectionnum,
        section_name=section_name,
        fields=fields,
        template=str(meta["template"]) if meta.get("template") is not None else None,
        source="workspace",
    )
    snapshot.content_hash = content_hash(
        {"modname": modname, "name": name, "visible": visible, **fields}
    )
    return snapshot


def module_to_markdown(module: ModuleSnapshot) -> str:
    meta: dict[str, Any] = {
        "type": module.modname,
        "name": module.name,
        "visible": module.visible,
        "visibleoncoursepage": module.visibleoncoursepage,
    }
    if module.cmid is not None:
        meta["moodle_cmid"] = module.cmid
    fields = module.fields
    body = ""
    if module.modname == "label":
        body = html_to_markdown(str(fields.get("labelcontent") or ""))
    elif module.modname == "page":
        meta["showdescription"] = int(fields.get("showdescription") or 0)
        intro = html_to_markdown(str(fields.get("intro") or ""))
        content = html_to_markdown(str(fields.get("pagecontent") or ""))
        body = f"{intro}\n\n{CONTENT_MARKER}\n\n{content}".strip() if intro else content
    elif module.modname == "url":
        meta["externalurl"] = fields.get("externalurl") or ""
        meta["display"] = int(fields.get("display") or 0)
        meta["showdescription"] = int(fields.get("showdescription") or 0)
        body = html_to_markdown(str(fields.get("intro") or ""))
    elif module.modname == "forum":
        meta["forum_type"] = fields.get("type") or "general"
        meta["showdescription"] = int(fields.get("showdescription") or 0)
        body = html_to_markdown(str(fields.get("intro") or ""))
    elif module.modname == "assign":
        for key in (
            "duedate",
            "cutoffdate",
            "allowsubmissionsfromdate",
            "grade",
            "maxattempts",
            "showdescription",
        ):
            if key in fields:
                meta[key] = fields[key]
        if fields.get("zeitaufwand") or fields.get("timerequired"):
            meta["zeitaufwand"] = fields.get("zeitaufwand") or fields.get("timerequired")
        intro = html_to_markdown(str(fields.get("intro") or ""))
        activity = html_to_markdown(str(fields.get("activity") or ""))
        body = f"{intro}\n\n{ACTIVITY_MARKER}\n\n{activity}".strip()
    else:
        body = str(fields.get("raw") or "")
    return dump_frontmatter(meta, body)


def section_dir_name(position: int, name: str) -> str:
    return f"{position:02d}-{slugify(name)}"


def module_file_name(position: int, name: str, modname: str) -> str:
    return f"{position:02d}-{slugify(name)}.md"


def build_workspace_snapshot(
    sandbox: WorkspaceSandbox,
    *,
    course_id: int,
    template_section_name: str | None = None,
) -> CourseSnapshot:
    meta = load_course_yaml(sandbox)
    title = str(meta.get("title") or "")
    template_name = meta.get("template_section_name") or template_section_name
    sections: list[SectionSnapshot] = []
    sections_root = sandbox.root / "sections"
    if sections_root.is_dir():
        dirs = sorted(
            [p for p in sections_root.iterdir() if p.is_dir() and not p.name.startswith(".")],
            key=lambda p: p.name,
        )
        for index, directory in enumerate(dirs):
            rel_dir = sandbox.relative_to_root(directory)
            section_yaml: dict[str, Any] = {}
            yaml_path = directory / "section.yaml"
            if yaml_path.exists():
                loaded = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                if isinstance(loaded, dict):
                    section_yaml = loaded
            name = str(section_yaml.get("name") or directory.name)
            summary = str(section_yaml.get("summary") or "")
            visible = int(section_yaml.get("visible", 1))
            sectionnum = section_yaml.get("moodle_sectionnum")
            is_template = bool(section_yaml.get("is_template_section")) or (
                bool(template_name) and name == template_name
            )
            modules: list[ModuleSnapshot] = []
            md_files = sorted(
                [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".md"],
                key=lambda p: p.name,
            )
            for pos, md_file in enumerate(md_files, start=1):
                rel = sandbox.relative_to_root(md_file)
                module = parse_module_file(
                    rel,
                    md_file.read_text(encoding="utf-8"),
                    int(sectionnum) if sectionnum is not None else None,
                    name,
                )
                module.position = pos
                modules.append(module)
            section = SectionSnapshot(
                local_id=rel_dir,
                name=name,
                summary=summary,
                visible=visible,
                sectionnum=int(sectionnum) if sectionnum is not None else None,
                position=index,
                is_template_section=is_template,
                modules=modules,
                source="workspace",
            )
            section.content_hash = content_hash(
                {"name": name, "summary": summary, "visible": visible}
            )
            sections.append(section)

    return CourseSnapshot(
        course_id=int(meta.get("moodle_course_id") or course_id),
        title=title,
        source="workspace",
        fetched_at=utcnow(),
        sections=sections,
        template_section_name=template_name,
    )


def export_snapshot_to_workspace(
    sandbox: WorkspaceSandbox,
    snapshot: CourseSnapshot,
    *,
    overwrite: bool = False,
) -> list[str]:
    """Write a Moodle snapshot as local Markdown/YAML files."""
    written: list[str] = []
    if sandbox.exists("course.yaml") and not overwrite:
        return written
    write_course_yaml(
        sandbox,
        {
            "title": snapshot.title,
            "moodle_course_id": snapshot.course_id,
            "template_section_name": snapshot.template_section_name,
            "format": "moodle-course-v1",
        },
    )
    written.append("course.yaml")
    for index, section in enumerate(snapshot.sections):
        dirname = section_dir_name(index, section.name)
        rel_dir = f"sections/{dirname}"
        sandbox.create_dir(rel_dir)
        section_yaml = {
            "name": section.name,
            "summary": section.summary,
            "visible": section.visible,
            "moodle_sectionnum": section.sectionnum,
            "is_template_section": section.is_template_section,
        }
        sandbox.write_text(
            f"{rel_dir}/section.yaml",
            yaml.safe_dump(section_yaml, allow_unicode=True, sort_keys=False),
        )
        written.append(f"{rel_dir}/section.yaml")
        for pos, module in enumerate(section.modules, start=1):
            if module.modname not in {"label", "page", "url", "forum", "assign"}:
                continue
            filename = module_file_name(pos, module.name, module.modname)
            rel = f"{rel_dir}/{filename}"
            sandbox.write_text(rel, module_to_markdown(module))
            written.append(rel)
    return written


def write_module_file(sandbox: WorkspaceSandbox, relative: str, module: ModuleSnapshot) -> str:
    return sandbox.write_text(relative, module_to_markdown(module))


def update_frontmatter_cmid(sandbox: WorkspaceSandbox, relative: str, cmid: int) -> None:
    text = sandbox.read_text(relative)
    meta, body = split_frontmatter(text)
    meta["moodle_cmid"] = cmid
    sandbox.write_text(relative, dump_frontmatter(meta, body))


def update_section_yaml_num(sandbox: WorkspaceSandbox, section_dir: str, sectionnum: int) -> None:
    path = f"{section_dir}/section.yaml"
    data: dict[str, Any] = {}
    if sandbox.exists(path):
        loaded = yaml.safe_load(sandbox.read_text(path)) or {}
        if isinstance(loaded, dict):
            data = loaded
    data["moodle_sectionnum"] = sectionnum
    sandbox.write_text(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
