# Moodle Course Agent

Shell assistant for one teacher and one Moodle course. Inspect the course, edit a local Markdown/YAML workspace, revise materials in chat, and sync to Moodle — with explicit approval for every remote change.

## What it does

- Empty workspace → fetch the Moodle course into local files
- Existing workspace → hash compare; the agent asks whether to update local from Moodle or Moodle from local
- Edit files directly, or work in the Rich chat until you are satisfied, then push to Moodle
- Every Moodle write pauses for `y` / `n`
- After a remote change, the workspace is updated to match
- MCP server exposes the Moodle API for other clients

## Layout

```
moodle-agent (Rich shell) ─┐
moodle-agent mcp           ─┤
                            └─ CourseApplication
                                  Moodle client · workspace · sync plan (hashes)
                                  Strands agent (tools, skills, session, HITL)
                                  LLM guardrail · lifecycle hooks
                                  OpenTelemetry → local Langfuse
```

## Requirements

- Python 3.11+
- Moodle with `local_ffhs_course_editing_*` webservices, or `MOODLE_MOCK=1`
- OpenAI API key, or AWS Bedrock credentials

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Shell

```bash
moodle-agent                 # Rich chat (default)
moodle-agent status          # Moodle + workspace + sync preview
moodle-agent mcp             # Moodle API MCP server (stdio)
```

Same as `python -m moodle_course_agent`.

Chat commands: `/status` `/reset` `/help` `/exit`

Local file edits do not need approval. Moodle writes do.

## MCP

`moodle-agent mcp` registers every public Moodle client method (get/create/update/move/copy) plus workspace and sync. Before any Moodle write, the server asks the teacher directly through MCP elicitation, so the calling model cannot approve its own change. Clients without elicitation support must pass `approved=true`; write tools are annotated `destructiveHint` so hosts can show their own permission prompt. After a Moodle write, Moodle-side changes are pulled into local files.

## Guardrail

Each user turn is classified by a small LLM call (not keyword filters, so course material about history or conflict is not blocked). Off-topic requests, sexual content, hate speech, and real-world violence are refused with: `Sorry, I can not help with this.`

| Variable | Default | Effect |
|----------|---------|--------|
| `GUARDRAIL_ENABLED` | `1` | Turn the classifier off with `0` |
| `GUARDRAIL_MODEL` | chat model | Cheaper classifier model on the same provider, e.g. `gpt-4o-mini` |
| `GUARDRAIL_FAIL_OPEN` | `0` | If the classifier errors, the turn is refused; `1` allows it instead |

## Observability

Strands traces via OpenTelemetry. Point them at a local Langfuse instance:

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=http://localhost:3000
```

See the [Langfuse self-hosting docs](https://langfuse.com/docs/deployment/self-host). Evaluation datasets can be added later in that UI. `OTEL_CONSOLE=1` prints spans in the terminal.

## Local course files

See [docs/local-course-format.md](docs/local-course-format.md). Short version: `course.yaml` plus `sections/<index>-<slug>/` with `section.yaml` and Markdown modules (`type`, `name`, optional `moodle_cmid`).

## Skills

`skills/`: inspect-course, author-content, revise-content, adapt-templates, manage-workspace, synchronize.

## Tests

```bash
pytest -v
```

No live Moodle required. Live smoke: `RUN_LIVE_SMOKE=1 pytest tests/e2e/test_live_smoke.py`.

## Moodle API limits

The wrapped plugin does not support deleting modules/sections, file uploads, quizzes, or enrolment. Sync never auto-deletes Moodle content.

## License

This project is licensed under the [MIT License](LICENSE).
