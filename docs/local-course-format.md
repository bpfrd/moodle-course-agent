# Local course format

Teachers edit a Moodle course as a directory of Markdown and YAML files. Moodle
remains the remote system of record after an **approved** sync; these files are
the local working copy.

## Layout

```
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
```

Numeric prefixes control order. Directory and file names are slugs; the display
name lives in YAML.

## `course.yaml`

```yaml
title: Introduction to Data Analysis
moodle_course_id: 12345
template_section_name: "Modulentwicklung [RK only]"
format: moodle-course-v1
```

## `section.yaml`

```yaml
name: Week 1
summary: "<p>Getting started</p>"
visible: 1
moodle_sectionnum: 1
is_template_section: false
```

`moodle_sectionnum` is written back after a successful create on Moodle.

## Module files

Markdown with YAML frontmatter. `type` is one of `label`, `page`, `url`, `forum`, `assign`.

```markdown
---
type: page
name: Syllabus
visible: 1
visibleoncoursepage: 1
showdescription: 0
moodle_cmid: 101
---

Short intro shown on the course page when showdescription is enabled.

<!-- moodle:content -->

# Syllabus

Full page body. Markdown is converted to HTML when pushing to Moodle.
```

Assignments split intro and activity with `<!-- moodle:activity -->`. A new
assignment is created by copying a template: `template: ohne_abgabe` (default),
`template: mit_abgabe`, or `template: none` to create it from scratch. Without
template assignments in the course, or when the target section is still empty,
it is created from scratch. `template` only matters when the assignment is first
created. URL modules
use `externalurl`. Forums use `forum_type` (default `general`).

`moodle_cmid` is the stable link to the remote module. After creating content on
Moodle, the application writes this field back so later syncs update rather than
duplicate.

## Sync rules

- Comparison and conflict detection are deterministic (content hashes). The LLM
  does not decide what changed.
- The last-synced hashes record which side changed. A change made only on Moodle
  is pulled, a change made only locally is pushed; neither direction reverts the
  other side's one-sided change.
- `to_moodle` creates/updates Moodle from local files. It never deletes Moodle
  modules (the webservice does not implement deletion).
- `to_local` writes or updates local files from Moodle. Unpushed local edits are kept.
- After every approved Moodle write, Moodle-side changes are pulled automatically.
  Local edits that are not pushed yet, and conflicts, are left untouched.
- A **conflict** means both sides changed since the last successful sync. Those
  actions are shown and skipped unless the teacher resolves them.
- Every Moodle mutation still requires explicit human approval.
