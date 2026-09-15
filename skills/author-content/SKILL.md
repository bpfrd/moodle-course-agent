---
name: author-content
description: Create new Moodle course content from scratch or from local Markdown/YAML files.
---
# Author course content

Decide whether the teacher wants Moodle-first or local-first work.

## Local-first (preferred for larger edits)
1. Write Markdown/YAML under `sections/<index>-<slug>/`.
2. Use YAML frontmatter with `type`, `name`, and optional dates.
3. Call `preview_sync` with `direction=to_moodle` and show the plan.
4. Only then call `apply_sync_to_moodle` so the teacher can approve.

## Moodle-first
1. Prefer a template (`list_templates`, `create_aufgabe_*`, `copy_template_module`).
2. If no template fits, use `create_page` / `create_label` / `create_assign` / `create_forum` / `create_url`.
3. Describe the change before the write tool so approval is meaningful.
