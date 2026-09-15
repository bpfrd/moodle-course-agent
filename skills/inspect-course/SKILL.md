---
name: inspect-course
description: Inspect Moodle course structure, template sections, and module details without making changes.
---
# Inspect a course

Use read-only tools only.

1. Call `get_course_status` for a compact overview.
2. Use `find_sections` / `find_modules` to locate items. Never guess `cmid` or `sectionnum`.
3. Fetch bodies with `get_label`, `get_page`, `get_url`, `get_forum`, or `get_assign`.
4. Call `list_templates` when the teacher mentions Vorlagen, templates, or hidden/reference sections.
5. Summarize in a short numbered list: sections, hidden items, and anything that looks like a template.
