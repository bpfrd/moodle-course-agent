---
name: revise-content
description: Revise existing Moodle or local course content in small reviewable steps.
---
# Revise content

1. Fetch the current item (`get_*` or `read_workspace_file`).
2. Propose a concise diff in plain language.
3. Apply locally with `write_workspace_file` **or** on Moodle with the matching `update_*` tool (approval required).
4. Prefer one module at a time. Keep chatting until the teacher is satisfied.
5. After Moodle updates, re-fetch the item. Do not rely on chat history. If a tool errors, read it and fix.
