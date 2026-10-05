---
name: synchronize
description: Compare Moodle and local course files and apply an approved sync plan.
---
# Synchronize Moodle and local content

Do **not** invent differences. Always call `preview_sync`.

1. `preview_sync` with `preview`, `to_moodle`, or `to_local`.
2. Present counts and each action. Ask whether to update local from Moodle or Moodle from local.
3. Conflicts mean both sides changed since last sync. Ask which side wins; do not apply them automatically.
4. `apply_sync_to_moodle` requires human approval and skips conflicts.
5. `apply_sync_to_local` writes Markdown/YAML only; it does not mutate Moodle and keeps unpushed local edits.
6. After apply, call `preview_sync` / `get_course_status` and confirm the plan is clean. If a result has `ok: false`, read the error and fix.
7. Moodle extras are never deleted automatically (API limitation + safety).
