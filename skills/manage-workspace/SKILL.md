---
name: manage-workspace
description: Organize the local Markdown/YAML course workspace without touching Moodle.
---
# Manage the local workspace

All paths are relative to the configured workspace. `..` is rejected.

Typical layout:

```
course.yaml
sections/00-general/section.yaml
sections/00-general/01-welcome.md
```

1. `workspace_tree` / `list_workspace` before changing files.
2. Create directories with `create_workspace_dir`.
3. Write Markdown with YAML frontmatter (`type`, `name`, optional `moodle_cmid`).
4. Rename/delete carefully; deleting local files does **not** delete Moodle content.
5. After structural changes, `preview_sync` so the teacher sees the effect.
