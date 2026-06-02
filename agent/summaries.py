"""Compact projections of MoodleClient.course for LLM context.

The raw output of ``core_course_get_contents`` is large and noisy. The LLM only
needs the minimum information required to choose the next tool call: section
numbers, module ids, names, and module types. Full bodies are fetched on demand
via the ``get_label``/``get_page``/``get_url``/``get_assign`` tools.
"""

from __future__ import annotations

from typing import Any


def course_summary(course: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return a compact tree of sections and modules suitable for LLM context.

    The output looks like::

        [
            {
                "sectionnum": 0,
                "name": "General",
                "visible": 1,
                "modules": [
                    {"cmid": 123, "modname": "label", "name": "Welcome", "visible": 1},
                    ...
                ],
            },
            ...
        ]
    """
    if not course:
        return []

    summary: list[dict[str, Any]] = []
    for section in course:
        modules = [
            {
                "cmid": m.get("id"),
                "modname": m.get("modname"),
                "name": m.get("name"),
                "visible": m.get("visible", 1),
            }
            for m in section.get("modules", [])
        ]
        summary.append(
            {
                "sectionnum": section.get("section"),
                "name": section.get("name"),
                "visible": section.get("visible", 1),
                "modules": modules,
            }
        )
    return summary
