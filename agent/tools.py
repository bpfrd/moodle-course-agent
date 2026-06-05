"""Tool registry: wraps each public MoodleClient method as an LLM-callable tool.

Each tool has:
  * A Pydantic model that validates arguments and produces a JSON schema.
  * A handler that calls the underlying MoodleClient method and returns a
    JSON-serializable dict ``{"ok": True, "result": ...}`` or
    ``{"ok": False, "error": "..."}``.
  * A ``write`` flag indicating whether the operation mutates the course
    (used by the agent loop to require confirmation).

The registry is exposed through ``TOOLS`` (name -> Tool) and ``openai_schemas()``
(list of tool definitions ready to pass to ``openai.chat.completions.create``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

FORUM_TYPES = Literal["single", "eachuser", "qanda", "blog", "general"]

from moodle_client import MoodleAPIError, MoodleClient
from template_assignments import (
    create_aufgabe_mit_abgabe,
    create_aufgabe_ohne_abgabe,
    validate_zeitaufwand,
)

from .summaries import course_summary


# ---------------------------------------------------------------------------
# Argument schemas
# ---------------------------------------------------------------------------


class _NoArgs(BaseModel):
    pass


class GetModuleArgs(BaseModel):
    cmid: int = Field(..., description="Course module id from get_course_structure")


class FindSectionArgs(BaseModel):
    section_name: str = Field(..., description="Exact name of the section as shown in the course summary")
    exact: bool = Field(True, description="If true, match section_name exactly; otherwise use substring match")


class FindModulesArgs(BaseModel):
    section_name: Optional[str] = Field(
        None,
        description="Optional section name to limit the search (as shown in the course summary).",
    )
    modname: Optional[str] = Field(
        None,
        description="Optional Moodle module name, e.g. 'assign', 'page', 'label', 'url', 'forum'.",
    )
    name_contains: Optional[str] = Field(
        None,
        description="Optional substring match against the module display name.",
    )
    cmid: Optional[int] = Field(
        None,
        description="Optional cmid to find a single module. If provided, other filters are ignored.",
    )


class GetModuleFromCacheArgs(BaseModel):
    cmid: int = Field(..., description="Course module id to locate in the cached course structure")


class CreateSectionArgs(BaseModel):
    name: str = Field(..., description="Section title")
    summary: str = Field(..., description="HTML summary shown under the section title")
    position: int = Field(
        ...,
        description=(
            "1-indexed position where the new section will be inserted. "
            "Must be between 1 and (current number of sections + 1)."
        ),
    )
    visible: int = Field(1, description="1 for visible, 0 for hidden")


class MoveSectionArgs(BaseModel):
    sectionnum: int = Field(..., description="Section number to move")
    position: int = Field(
        ...,
        description="1-indexed target position; must be within existing sections",
    )


class UpdateSectionArgs(BaseModel):
    sectionnum: int = Field(..., description="Section number to update")
    name: str
    summary: str = Field(..., description="HTML summary shown under the section title")
    visible: int = 1


class CreateLabelArgs(BaseModel):
    sectionnum: int
    labelcontent: str = Field(..., description="HTML content of the label")
    name: str = ""
    visible: int = 1
    visibleoncoursepage: int = 1
    beforemod: Optional[int] = Field(
        None,
        description="cmid of an existing module to insert before; omit to append at end",
    )


class UpdateLabelArgs(BaseModel):
    cmid: int
    name: str
    labelcontent: str
    visible: int = 1
    visibleoncoursepage: int = 1


class CreatePageArgs(BaseModel):
    sectionnum: int
    name: str
    intro: str = Field(
        ...,
        description="HTML shown on the course page if showdescription is enabled",
    )
    pagecontent: str = Field(..., description="HTML body of the page")
    visible: int = 1
    visibleoncoursepage: int = 1
    showdescription: int = 0
    beforemod: Optional[int] = None


class UpdatePageArgs(BaseModel):
    cmid: int
    name: str
    intro: str
    pagecontent: str
    visible: int = 1
    visibleoncoursepage: int = 1
    showdescription: int = 0


class CreateUrlArgs(BaseModel):
    sectionnum: int
    name: str
    intro: str
    externalurl: str = Field(..., description="Full URL the link points to")
    display: int = Field(
        0,
        description="Moodle URL display mode (0=automatic, 1=embed, 5=open, 6=in popup)",
    )
    visible: int = 1
    visibleoncoursepage: int = 1
    showdescription: int = 0
    beforemod: Optional[int] = None


class UpdateUrlArgs(BaseModel):
    cmid: int
    name: str
    intro: str
    externalurl: str
    display: int = 0
    visible: int = 1
    visibleoncoursepage: int = 1
    showdescription: int = 0


class CreateForumArgs(BaseModel):
    sectionnum: int
    name: str
    intro: str = Field(..., description="HTML intro/description for the forum")
    visible: int = 1
    visibleoncoursepage: int = 1
    showdescription: int = 0
    beforemod: Optional[int] = None
    type: FORUM_TYPES = Field(
        "general",
        description=(
            "Forum type: single, eachuser, qanda, blog, or general "
            "(open discussion — default for peer forums)"
        ),
    )
    showimmediately: int = 0
    duedate: int = Field(0, description="Unix timestamp; 0 means no due date")
    cutoffdate: int = Field(0, description="Unix timestamp; 0 means no cutoff")
    maxbytes: int = 0
    maxattachments: int = 1
    displaywordcount: int = 0
    forcesubscribe: int = Field(
        0,
        description="0=optional, 1=forced, 2=auto, 3=disabled subscription",
    )
    trackingtype: int = Field(1, description="0=off, 1=optional read tracking")
    lockdiscussionafter: int = 0
    blockperiod: int = 0
    blockafter: int = 0
    warnafter: int = 0


class UpdateForumArgs(BaseModel):
    cmid: int
    name: str
    intro: str = Field(..., description="HTML intro/description for the forum")
    visible: int = 1
    visibleoncoursepage: int = 1
    showdescription: int = 0
    type: FORUM_TYPES = Field(
        "general",
        description=(
            "Forum type: single, eachuser, qanda, blog, or general "
            "(open discussion — default for peer forums)"
        ),
    )
    showimmediately: int = 0
    duedate: int = Field(0, description="Unix timestamp; 0 means no due date")
    cutoffdate: int = Field(0, description="Unix timestamp; 0 means no cutoff")
    maxbytes: int = 0
    maxattachments: int = 1
    displaywordcount: int = 0
    forcesubscribe: int = Field(
        0,
        description="0=optional, 1=forced, 2=auto, 3=disabled subscription",
    )
    trackingtype: int = Field(1, description="0=off, 1=optional read tracking")
    lockdiscussionafter: int = 0
    blockperiod: int = 0
    blockafter: int = 0
    warnafter: int = 0


class CreateAssignArgs(BaseModel):
    sectionnum: int
    name: str
    intro: str = Field(..., description="HTML description shown above the assignment")
    activity: str = Field(
        ...,
        description="HTML body with the actual assignment instructions/questions",
    )
    allowsubmissionsfromdate: int = Field(
        0, description="Unix timestamp; 0 means no restriction"
    )
    duedate: int = Field(0, description="Unix timestamp; 0 means no due date")
    cutoffdate: int = Field(0, description="Unix timestamp; 0 means no cutoff")
    gradingduedate: int = 0
    timelimit: int = Field(0, description="Time limit in seconds; 0 means none")
    submissionattachments: int = 0
    maxattempts: int = 1
    grade: int = 100
    visible: int = 1
    visibleoncoursepage: int = 1
    showdescription: int = 0
    zeitaufwand: Optional[str] = Field(
        None,
        description=(
            "Optional value for the FFHS 'timerequired' custom field "
            "(e.g. '30 min', '2h'). Leave empty if not applicable."
        ),
    )
    beforemod: Optional[int] = None

    @field_validator("zeitaufwand")
    @classmethod
    def _validate_zeitaufwand(cls, value: Optional[str]) -> Optional[str]:
        return validate_zeitaufwand(value)


class UpdateAssignArgs(BaseModel):
    cmid: int
    name: str
    intro: str
    activity: str
    allowsubmissionsfromdate: int = 0
    duedate: int = 0
    cutoffdate: int = 0
    gradingduedate: int = 0
    timelimit: int = 0
    submissionattachments: int = 0
    maxattempts: int = 1
    grade: int = 100
    visible: int = 1
    visibleoncoursepage: int = 1
    showdescription: int = 0
    zeitaufwand: Optional[str] = None

    @field_validator("zeitaufwand")
    @classmethod
    def _validate_zeitaufwand(cls, value: Optional[str]) -> Optional[str]:
        return validate_zeitaufwand(value)


class CreateAufgabeFromTemplateArgs(BaseModel):
    name: str
    intro: str
    activity: str
    sectionnum: Optional[int] = Field(
        None,
        description="Target section number for the copied assignment",
    )
    beforemod: Optional[int] = Field(
        None,
        description="Insert before this cmid; overrides sectionnum placement",
    )
    allowsubmissionsfromdate: int = 0
    duedate: int = 0
    cutoffdate: int = 0
    gradingduedate: int = 0
    timelimit: int = 0
    submissionattachments: int = 0
    maxattempts: int = 1
    grade: int = 100
    visible: int = 1
    visibleoncoursepage: int = 1
    showdescription: int = 0
    zeitaufwand: Optional[str] = None
    template_section_name: str = Field(
        "Modulentwicklung [RK only]",
        description="Section where the assignment templates live",
    )

    @field_validator("zeitaufwand")
    @classmethod
    def _validate_zeitaufwand(cls, value: Optional[str]) -> Optional[str]:
        return validate_zeitaufwand(value)


class MoveModuleArgs(BaseModel):
    cmid: int = Field(..., description="cmid of the module to move")
    beforemod: int = Field(
        ...,
        description="cmid of the module to insert before; 0 to append at end of section",
    )


class CopyModuleArgs(BaseModel):
    cmid: int
    beforemod: int = Field(
        ..., description="cmid of the module to insert before; 0 to append at end"
    )


# ---------------------------------------------------------------------------
# Tool descriptor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[MoodleClient, dict[str, Any]], dict[str, Any]]
    write: bool


def _safe_call(fn: Callable[[], Any]) -> dict[str, Any]:
    """Run ``fn`` and return a uniform ok/error envelope for the LLM."""
    try:
        return {"ok": True, "result": fn()}
    except ValidationError as exc:
        return {
            "ok": False,
            "error": f"Invalid arguments: {exc}",
            "error_type": "ValidationError",
        }
    except (MoodleAPIError, ValueError) as exc:
        return {"ok": False, "error": str(exc), "error_type": type(exc).__name__}


def _run(args_model: type[BaseModel], args: dict[str, Any], fn: Callable[[Any], Any]) -> dict[str, Any]:
    """Parse ``args`` with ``args_model`` and call ``fn(parsed)`` inside _safe_call.

    Parsing happens inside the safe-call closure so Pydantic ValidationError
    becomes an ok/error envelope the LLM can recover from, rather than an
    uncaught exception that crashes the agent loop.
    """
    return _safe_call(lambda: fn(args_model(**args)))


# ---------------------------------------------------------------------------
# Handlers (one per tool)
# ---------------------------------------------------------------------------


def _h_get_course_structure(client: MoodleClient, _args: dict[str, Any]) -> dict[str, Any]:
    return _safe_call(lambda: course_summary(client.course))


def _h_get_module(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(GetModuleArgs, args, lambda a: client.get_module(a.cmid))


def _h_get_label(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(GetModuleArgs, args, lambda a: client.get_label(a.cmid))


def _h_get_page(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(GetModuleArgs, args, lambda a: client.get_page(a.cmid))


def _h_get_url(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(GetModuleArgs, args, lambda a: client.get_url(a.cmid))


def _h_get_assign(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(GetModuleArgs, args, lambda a: client.get_assign(a.cmid))


def _h_get_forum(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(GetModuleArgs, args, lambda a: client.get_forum(a.cmid))


def _h_find_sections(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    def fn() -> Any:
        a = FindSectionArgs(**args)
        matches = []
        for s in client.course:
            s_name = s.get("name")
            ok = (
                s_name == a.section_name
                if a.exact
                else (a.section_name.lower() in (s_name or "").lower())
            )
            if not ok:
                continue
            matches.append(
                {
                    "sectionnum": s.get("section"),
                    "name": s.get("name"),
                    "visible": s.get("visible", 1),
                    "modules_count": len(s.get("modules", [])),
                }
            )
        return matches

    return _safe_call(fn)


def _h_find_modules(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    def fn() -> Any:
        a = FindModulesArgs(**args)
        modules = []
        for s in client.course:
            s_name = s.get("name")
            if (
                a.section_name is not None
                and (s_name or "").lower() != a.section_name.lower()
            ):
                continue
            sectionnum = s.get("section")
            for m in s.get("modules", []):
                if a.cmid is not None:
                    if m.get("id") != a.cmid:
                        continue
                else:
                    if a.modname is not None and m.get("modname") != a.modname:
                        continue
                    if a.name_contains is not None:
                        if a.name_contains.lower() not in (m.get("name") or "").lower():
                            continue

                modules.append(
                    {
                        "cmid": m.get("id"),
                        "modname": m.get("modname"),
                        "name": m.get("name"),
                        "visible": m.get("visible", 1),
                        "visibleoncoursepage": m.get("visibleoncoursepage", 1),
                        "sectionnum": sectionnum,
                    }
                )
        return modules

    return _safe_call(fn)


def _h_get_module_from_cache(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    def fn() -> Any:
        a = GetModuleFromCacheArgs(**args)
        for s in client.course:
            for m in s.get("modules", []):
                if m.get("id") == a.cmid:
                    return {
                        "cmid": m.get("id"),
                        "modname": m.get("modname"),
                        "name": m.get("name"),
                        "visible": m.get("visible", 1),
                        "visibleoncoursepage": m.get("visibleoncoursepage", 1),
                        "sectionnum": s.get("section"),
                    }
        raise ValueError(f"Module cmid not found in cached course structure: {a.cmid}")

    return _safe_call(fn)


def _h_create_section(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        CreateSectionArgs,
        args,
        lambda a: client.create_section(
            name=a.name, summary=a.summary, position=a.position, visible=a.visible
        ),
    )


def _h_move_section(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        MoveSectionArgs,
        args,
        lambda a: client.move_section(sectionnum=a.sectionnum, position=a.position),
    )


def _h_update_section(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        UpdateSectionArgs,
        args,
        lambda a: client.update_section(
            sectionnum=a.sectionnum,
            name=a.name,
            summary=a.summary,
            visible=a.visible,
        ),
    )


def _h_create_label(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        CreateLabelArgs,
        args,
        lambda a: client.create_label(
            sectionnum=a.sectionnum,
            labelcontent=a.labelcontent,
            name=a.name,
            visible=a.visible,
            visibleoncoursepage=a.visibleoncoursepage,
            beforemod=a.beforemod,
        ),
    )


def _h_update_label(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        UpdateLabelArgs,
        args,
        lambda a: client.update_label(
            cmid=a.cmid,
            name=a.name,
            labelcontent=a.labelcontent,
            visible=a.visible,
            visibleoncoursepage=a.visibleoncoursepage,
        ),
    )


def _h_create_page(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        CreatePageArgs,
        args,
        lambda a: client.create_page(
            sectionnum=a.sectionnum,
            name=a.name,
            intro=a.intro,
            pagecontent=a.pagecontent,
            visible=a.visible,
            visibleoncoursepage=a.visibleoncoursepage,
            showdescription=a.showdescription,
            beforemod=a.beforemod,
        ),
    )


def _h_update_page(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        UpdatePageArgs,
        args,
        lambda a: client.update_page(
            cmid=a.cmid,
            name=a.name,
            intro=a.intro,
            pagecontent=a.pagecontent,
            visible=a.visible,
            visibleoncoursepage=a.visibleoncoursepage,
            showdescription=a.showdescription,
        ),
    )


def _h_create_url(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        CreateUrlArgs,
        args,
        lambda a: client.create_url(
            sectionnum=a.sectionnum,
            name=a.name,
            intro=a.intro,
            externalurl=a.externalurl,
            display=a.display,
            visible=a.visible,
            visibleoncoursepage=a.visibleoncoursepage,
            showdescription=a.showdescription,
            beforemod=a.beforemod,
        ),
    )


def _h_update_forum(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        UpdateForumArgs,
        args,
        lambda a: client.update_forum(
            cmid=a.cmid,
            name=a.name,
            intro=a.intro,
            visible=a.visible,
            visibleoncoursepage=a.visibleoncoursepage,
            showdescription=a.showdescription,
            type=a.type,
            showimmediately=a.showimmediately,
            duedate=a.duedate,
            cutoffdate=a.cutoffdate,
            maxbytes=a.maxbytes,
            maxattachments=a.maxattachments,
            displaywordcount=a.displaywordcount,
            forcesubscribe=a.forcesubscribe,
            trackingtype=a.trackingtype,
            lockdiscussionafter=a.lockdiscussionafter,
            blockperiod=a.blockperiod,
            blockafter=a.blockafter,
            warnafter=a.warnafter,
        ),
    )


def _h_create_forum(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        CreateForumArgs,
        args,
        lambda a: client.create_forum(
            sectionnum=a.sectionnum,
            name=a.name,
            intro=a.intro,
            visible=a.visible,
            visibleoncoursepage=a.visibleoncoursepage,
            showdescription=a.showdescription,
            beforemod=a.beforemod,
            type=a.type,
            showimmediately=a.showimmediately,
            duedate=a.duedate,
            cutoffdate=a.cutoffdate,
            maxbytes=a.maxbytes,
            maxattachments=a.maxattachments,
            displaywordcount=a.displaywordcount,
            forcesubscribe=a.forcesubscribe,
            trackingtype=a.trackingtype,
            lockdiscussionafter=a.lockdiscussionafter,
            blockperiod=a.blockperiod,
            blockafter=a.blockafter,
            warnafter=a.warnafter,
        ),
    )


def _h_update_url(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        UpdateUrlArgs,
        args,
        lambda a: client.update_url(
            cmid=a.cmid,
            name=a.name,
            intro=a.intro,
            externalurl=a.externalurl,
            display=a.display,
            visible=a.visible,
            visibleoncoursepage=a.visibleoncoursepage,
            showdescription=a.showdescription,
        ),
    )


def _h_create_assign(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        CreateAssignArgs,
        args,
        lambda a: client.create_assign(
            sectionnum=a.sectionnum,
            name=a.name,
            intro=a.intro,
            activity=a.activity,
            allowsubmissionsfromdate=a.allowsubmissionsfromdate,
            duedate=a.duedate,
            cutoffdate=a.cutoffdate,
            gradingduedate=a.gradingduedate,
            timelimit=a.timelimit,
            submissionattachments=a.submissionattachments,
            maxattempts=a.maxattempts,
            grade=a.grade,
            visible=a.visible,
            visibleoncoursepage=a.visibleoncoursepage,
            showdescription=a.showdescription,
            zeitaufwand=a.zeitaufwand,
            beforemod=a.beforemod,
        ),
    )


def _h_update_assign(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        UpdateAssignArgs,
        args,
        lambda a: client.update_assign(
            cmid=a.cmid,
            name=a.name,
            intro=a.intro,
            activity=a.activity,
            allowsubmissionsfromdate=a.allowsubmissionsfromdate,
            duedate=a.duedate,
            cutoffdate=a.cutoffdate,
            gradingduedate=a.gradingduedate,
            timelimit=a.timelimit,
            submissionattachments=a.submissionattachments,
            maxattempts=a.maxattempts,
            grade=a.grade,
            visible=a.visible,
            visibleoncoursepage=a.visibleoncoursepage,
            showdescription=a.showdescription,
            zeitaufwand=a.zeitaufwand,
        ),
    )


def _h_create_aufgabe_ohne_abgabe(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        CreateAufgabeFromTemplateArgs,
        args,
        lambda a: create_aufgabe_ohne_abgabe(
            client,
            name=a.name,
            intro=a.intro,
            activity=a.activity,
            sectionnum=a.sectionnum,
            beforemod=a.beforemod,
            allowsubmissionsfromdate=a.allowsubmissionsfromdate,
            duedate=a.duedate,
            cutoffdate=a.cutoffdate,
            gradingduedate=a.gradingduedate,
            timelimit=a.timelimit,
            submissionattachments=a.submissionattachments,
            maxattempts=a.maxattempts,
            grade=a.grade,
            visible=a.visible,
            visibleoncoursepage=a.visibleoncoursepage,
            showdescription=a.showdescription,
            zeitaufwand=a.zeitaufwand,
            template_section_name=a.template_section_name,
        ),
    )


def _h_create_aufgabe_mit_abgabe(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        CreateAufgabeFromTemplateArgs,
        args,
        lambda a: create_aufgabe_mit_abgabe(
            client,
            name=a.name,
            intro=a.intro,
            activity=a.activity,
            sectionnum=a.sectionnum,
            beforemod=a.beforemod,
            allowsubmissionsfromdate=a.allowsubmissionsfromdate,
            duedate=a.duedate,
            cutoffdate=a.cutoffdate,
            gradingduedate=a.gradingduedate,
            timelimit=a.timelimit,
            submissionattachments=a.submissionattachments,
            maxattempts=a.maxattempts,
            grade=a.grade,
            visible=a.visible,
            visibleoncoursepage=a.visibleoncoursepage,
            showdescription=a.showdescription,
            zeitaufwand=a.zeitaufwand,
            template_section_name=a.template_section_name,
        ),
    )


def _h_move_module(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        MoveModuleArgs,
        args,
        lambda a: client.move_module(cmid=a.cmid, beforemod=a.beforemod),
    )


def _h_copy_module(client: MoodleClient, args: dict[str, Any]) -> dict[str, Any]:
    return _run(
        CopyModuleArgs,
        args,
        lambda a: client.copy_module(cmid=a.cmid, beforemod=a.beforemod),
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        # Read tools -------------------------------------------------------
        Tool(
            name="get_course_structure",
            description=(
                "Return a compact summary of the course: sections with "
                "sectionnum, name, visibility, and the modules inside each "
                "section (cmid, modname, name, visibility). Call this before "
                "any other tool if you do not already have a recent summary."
            ),
            args_model=_NoArgs,
            handler=_h_get_course_structure,
            write=False,
        ),
        Tool(
            name="get_module",
            description=(
                "Return raw Moodle data for a single course module by cmid. "
                "Use this for diagnostic info; prefer get_label/get_page/"
                "get_url/get_forum/get_assign when you know the module type."
            ),
            args_model=GetModuleArgs,
            handler=_h_get_module,
            write=False,
        ),
        Tool(
            name="get_label",
            description="Return the full content of a label by cmid.",
            args_model=GetModuleArgs,
            handler=_h_get_label,
            write=False,
        ),
        Tool(
            name="get_page",
            description="Return the full content of a page by cmid.",
            args_model=GetModuleArgs,
            handler=_h_get_page,
            write=False,
        ),
        Tool(
            name="get_url",
            description="Return the full content of a URL resource by cmid.",
            args_model=GetModuleArgs,
            handler=_h_get_url,
            write=False,
        ),
        Tool(
            name="get_assign",
            description="Return the full content of an assignment by cmid.",
            args_model=GetModuleArgs,
            handler=_h_get_assign,
            write=False,
        ),
        Tool(
            name="get_forum",
            description="Return the full content of a forum by cmid.",
            args_model=GetModuleArgs,
            handler=_h_get_forum,
            write=False,
        ),
        Tool(
            name="find_sections",
            description=(
                "Find sections in the cached course structure by name. "
                "Returns matching section summaries (sectionnum, name, visibility, modules_count)."
            ),
            args_model=FindSectionArgs,
            handler=_h_find_sections,
            write=False,
        ),
        Tool(
            name="find_modules",
            description=(
                "Find modules in the cached course structure by filters such as section_name, modname, "
                "name_contains, or cmid. Returns matching modules with their cmid, modname, name, visibility, "
                "and sectionnum."
            ),
            args_model=FindModulesArgs,
            handler=_h_find_modules,
            write=False,
        ),
        Tool(
            name="get_module_from_cache",
            description=(
                "Get a single module's summary (cmid/modname/name/visibility/sectionnum) from the cached course "
                "structure without calling Moodle WS."
            ),
            args_model=GetModuleFromCacheArgs,
            handler=_h_get_module_from_cache,
            write=False,
        ),
        # Section writes ---------------------------------------------------
        Tool(
            name="create_section",
            description=(
                "Create a new section at the given 1-indexed position. "
                "position must be between 1 and current_section_count + 1."
            ),
            args_model=CreateSectionArgs,
            handler=_h_create_section,
            write=True,
        ),
        Tool(
            name="move_section",
            description="Move an existing section to a new 1-indexed position.",
            args_model=MoveSectionArgs,
            handler=_h_move_section,
            write=True,
        ),
        Tool(
            name="update_section",
            description=(
                "Update a section's name, summary, and visibility. All three "
                "fields are sent to Moodle, so include current values for "
                "fields you do not want to change."
            ),
            args_model=UpdateSectionArgs,
            handler=_h_update_section,
            write=True,
        ),
        # Label writes -----------------------------------------------------
        Tool(
            name="create_label",
            description="Create a label (rich-text snippet) inside a section.",
            args_model=CreateLabelArgs,
            handler=_h_create_label,
            write=True,
        ),
        Tool(
            name="update_label",
            description="Update an existing label by cmid.",
            args_model=UpdateLabelArgs,
            handler=_h_update_label,
            write=True,
        ),
        # Page writes ------------------------------------------------------
        Tool(
            name="create_page",
            description="Create a page (full HTML document) inside a section.",
            args_model=CreatePageArgs,
            handler=_h_create_page,
            write=True,
        ),
        Tool(
            name="update_page",
            description="Update an existing page by cmid.",
            args_model=UpdatePageArgs,
            handler=_h_update_page,
            write=True,
        ),
        # URL writes -------------------------------------------------------
        Tool(
            name="create_url",
            description="Create a URL resource (external link) inside a section.",
            args_model=CreateUrlArgs,
            handler=_h_create_url,
            write=True,
        ),
        Tool(
            name="update_url",
            description="Update an existing URL resource by cmid.",
            args_model=UpdateUrlArgs,
            handler=_h_update_url,
            write=True,
        ),
        # Forum writes -----------------------------------------------------
        Tool(
            name="create_forum",
            description=(
                "Create a forum inside a section. Use type 'general' for open "
                "peer discussions. Dates are Unix timestamps (0 = no restriction)."
            ),
            args_model=CreateForumArgs,
            handler=_h_create_forum,
            write=True,
        ),
        Tool(
            name="update_forum",
            description="Update an existing forum by cmid.",
            args_model=UpdateForumArgs,
            handler=_h_update_forum,
            write=True,
        ),
        # Assign writes ----------------------------------------------------
        Tool(
            name="create_assign",
            description=(
                "Create an assignment inside a section. Dates are Unix "
                "timestamps (0 means no restriction)."
            ),
            args_model=CreateAssignArgs,
            handler=_h_create_assign,
            write=True,
        ),
        Tool(
            name="update_assign",
            description="Update an existing assignment by cmid.",
            args_model=UpdateAssignArgs,
            handler=_h_update_assign,
            write=True,
        ),
        Tool(
            name="create_aufgabe_ohne_abgabe",
            description=(
                "Create assignment by copying template 'Vorlage: Aufgabe ohne "
                "Abgabe' from the template section and then updating content."
            ),
            args_model=CreateAufgabeFromTemplateArgs,
            handler=_h_create_aufgabe_ohne_abgabe,
            write=True,
        ),
        Tool(
            name="create_aufgabe_mit_abgabe",
            description=(
                "Create assignment by copying template 'Vorlage: Aufgabe mit "
                "Abgabe' from the template section and then updating content."
            ),
            args_model=CreateAufgabeFromTemplateArgs,
            handler=_h_create_aufgabe_mit_abgabe,
            write=True,
        ),
        # Module move/copy -------------------------------------------------
        Tool(
            name="move_module",
            description=(
                "Move a module to a new position. beforemod is the cmid of "
                "an existing module to insert before, or 0 to append at the "
                "end of its section."
            ),
            args_model=MoveModuleArgs,
            handler=_h_move_module,
            write=True,
        ),
        Tool(
            name="copy_module",
            description=(
                "Duplicate a module. beforemod is the cmid of an existing "
                "module to insert the copy before, or 0 to append at the end."
            ),
            args_model=CopyModuleArgs,
            handler=_h_copy_module,
            write=True,
        ),
    ]
}


def _pydantic_to_openai_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic JSON schema to one OpenAI's tool API accepts.

    Pydantic emits ``"title"`` everywhere and may include ``"$defs"``; OpenAI
    is happy with both but we strip ``title`` for cleanliness.
    """
    schema = model.model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    return schema


def openai_schemas() -> list[dict[str, Any]]:
    """Return the tool list in the shape ``openai.chat.completions.create`` expects."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": _pydantic_to_openai_schema(tool.args_model),
            },
        }
        for tool in TOOLS.values()
    ]
