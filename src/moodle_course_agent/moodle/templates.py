"""Helpers for creating assignments from pre-existing template assignments.

These functions intentionally do not modify ``MoodleClient``. They compose the
existing client operations:
1) locate template assignment cmids in a known section,
2) copy the selected template assignment,
3) update the copied assignment content/metadata.
"""

from __future__ import annotations

from typing import Any

from moodle_course_agent.moodle.client import MoodleClient

DEFAULT_TEMPLATE_SECTION_NAME = "Modulentwicklung [RK only]"
TEMPLATE_NAME_OHNE_ABGABE = "Vorlage: Aufgabe ohne Abgabe"
TEMPLATE_NAME_MIT_ABGABE = "Vorlage: Aufgabe mit Abgabe"


def _build_allowed_zeitaufwand_values() -> set[str]:
    """Build the exact allowed value set for field 'timerequired'."""
    allowed = {"0", "individual", "0h", "5min", "10min", "15min", "0.25h", "0.5h", "0.75h"}

    # 1h..9.75h in 0.25h increments
    for whole in range(1, 10):
        allowed.add(f"{whole}h")
        allowed.add(f"{whole}.25h")
        allowed.add(f"{whole}.5h")
        allowed.add(f"{whole}.75h")

    # 10h..29.5h in 0.5h increments
    for whole in range(10, 30):
        allowed.add(f"{whole}h")
        allowed.add(f"{whole}.5h")

    # 30h..100h in full-hour increments
    for whole in range(30, 101):
        allowed.add(f"{whole}h")

    # 110h..200h in 10h increments + larger fixed values
    for whole in range(110, 201, 10):
        allowed.add(f"{whole}h")
    allowed.update({"250h", "300h"})

    return allowed


ALLOWED_ZEITAUFWAND_VALUES = frozenset(_build_allowed_zeitaufwand_values())


def validate_zeitaufwand(value: str | None) -> str | None:
    """Validate timerequired custom field value."""
    if value is None:
        return value
    if value not in ALLOWED_ZEITAUFWAND_VALUES:
        raise ValueError(
            "Invalid zeitaufwand value. Use one of the allowed timerequired values "
            f"(got: {value!r})."
        )
    return value


def get_assign_templates(
    client: MoodleClient,
    section_name: str = DEFAULT_TEMPLATE_SECTION_NAME,
) -> dict[str, int]:
    """Return template cmids for both assignment variants.

    Returns:
        {"ohne_abgabe": <cmid>, "mit_abgabe": <cmid>}
    """
    target_section = next(
        (s for s in client.course if s.get("name") == section_name),
        None,
    )
    if target_section is None:
        raise ValueError(f"Section not found: {section_name}")

    mapping = {
        TEMPLATE_NAME_OHNE_ABGABE: "ohne_abgabe",
        TEMPLATE_NAME_MIT_ABGABE: "mit_abgabe",
    }
    out: dict[str, int] = {}
    for module in target_section.get("modules", []):
        if module.get("modname") != "assign":
            continue
        key = mapping.get(module.get("name"))
        if key:
            out[key] = module["id"]

    missing = [k for k in ("ohne_abgabe", "mit_abgabe") if k not in out]
    if missing:
        raise ValueError(f"Missing template assignments: {missing}")
    return out


def _resolve_beforemod_for_section(
    client: MoodleClient,
    sectionnum: int | None,
    beforemod: int | None,
) -> int:
    """Resolve placement for ``copy_module``.

    If ``beforemod`` is provided, that wins.
    If only ``sectionnum`` is provided, place before the first module in that
    section (or return 0 if the section is empty).
    If neither is provided, return 0.
    """
    if beforemod is not None:
        return beforemod
    if sectionnum is None:
        return 0

    section = next((s for s in client.course if s.get("section") == sectionnum), None)
    if section is None:
        raise ValueError(f"Section not found: {sectionnum}")

    modules = section.get("modules", [])
    if not modules:
        return 0
    return modules[0]["id"] # return the cmid of the first module in the section
    # return modules[-1]["id"] # return the cmid of the last module in the section


def _create_assign_from_template(
    client: MoodleClient,
    template_key: str,
    *,
    name: str,
    intro: str,
    activity: str,
    sectionnum: int | None = None,
    beforemod: int | None = None,
    allowsubmissionsfromdate: int = 0,
    duedate: int = 0,
    cutoffdate: int = 0,
    gradingduedate: int = 0,
    timelimit: int = 0,
    submissionattachments: int = 0,
    maxattempts: int = 1,
    grade: int = 100,
    visible: int = 1,
    visibleoncoursepage: int = 1,
    showdescription: int = 0,
    zeitaufwand: str | None = None,
    template_section_name: str = DEFAULT_TEMPLATE_SECTION_NAME,
) -> dict[str, Any]:
    validate_zeitaufwand(zeitaufwand)

    templates = get_assign_templates(client, section_name=template_section_name)
    template_cmid = templates[template_key]
    insert_before = _resolve_beforemod_for_section(client, sectionnum, beforemod)

    copied = client.copy_module(cmid=template_cmid, beforemod=insert_before)
    new_cmid = copied["cmid"]
    try:
        updated = client.update_assign(
            cmid=new_cmid,
            name=name,
            intro=intro,
            activity=activity,
            allowsubmissionsfromdate=allowsubmissionsfromdate,
            duedate=duedate,
            cutoffdate=cutoffdate,
            gradingduedate=gradingduedate,
            timelimit=timelimit,
            submissionattachments=submissionattachments,
            maxattempts=maxattempts,
            grade=grade,
            visible=visible,
            visibleoncoursepage=visibleoncoursepage,
            showdescription=showdescription,
            zeitaufwand=zeitaufwand,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Copied template {template_key} to new cmid {new_cmid}, but updating the copy failed: "
            f"{exc}. The copy is still on Moodle; update it with update_assign instead of creating another."
        ) from exc
    return {
        "template": template_key,
        "template_cmid": template_cmid,
        "new_cmid": new_cmid,
        "copied": copied,
        "updated": updated,
    }


def create_aufgabe_ohne_abgabe(client: MoodleClient, **kwargs: Any) -> dict[str, Any]:
    """Create assignment by copying template 'Vorlage: Aufgabe ohne Abgabe'."""
    return _create_assign_from_template(client, "ohne_abgabe", **kwargs)


def create_aufgabe_mit_abgabe(client: MoodleClient, **kwargs: Any) -> dict[str, Any]:
    """Create assignment by copying template 'Vorlage: Aufgabe mit Abgabe'."""
    return _create_assign_from_template(client, "mit_abgabe", **kwargs)

