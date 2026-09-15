---
name: adapt-templates
description: Find reusable Moodle templates, copy them, and adapt names and bodies.
---
# Adapt templates

Teachers keep reusable assignments/activities in hidden or named reference sections.

1. `list_templates` first.
2. For FFHS-style assignments, prefer:
   - `create_aufgabe_ohne_abgabe`
   - `create_aufgabe_mit_abgabe`
3. For other module types, `copy_template_module` then `update_*`.
4. Place the copy with `beforemod` / `sectionnum` from the live structure.
5. Never edit the template original unless the teacher explicitly asks.
