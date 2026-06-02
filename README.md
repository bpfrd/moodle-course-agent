# Moodle Course Agent

[![CI](https://github.com/bpfrd/moodle-course-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/bpfrd/moodle-course-agent/actions/workflows/ci.yml)

A Python client for Moodle course-editing webservices, with a local CLI agent that helps teachers build and update course content through conversation.

The client handles sections, labels, pages, URL resources, and assignments. The agent turns those operations into GPT tools, asks for confirmation before any change is applied, and logs every action.

## Features

- **Course client** — create, read, update, move, and copy sections and modules via REST webservices
- **Teaching agent** — natural-language interface over the same API, backed by OpenAI tool calling
- **Confirmation gate** — writes require explicit approval in the terminal
- **Audit log** — each session is recorded as JSONL under `logs/`
- **Offline tests** — unit tests run against in-memory fakes; no Moodle or API keys required

## Prerequisites

- Python 3.11 or 3.12
- A Moodle instance with the course-editing webservice functions enabled
- A webservice token with permission to edit the target course
- An OpenAI API key (agent only)

## Installation

```bash
python -m venv .venv
source .venv/bin/activate   # Linux / macOS
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Description |
|----------|-------------|
| `BASE_URL` | Moodle REST endpoint, e.g. `https://moodle.example.org/webservice/rest/server.php` |
| `WSTOKEN` | Webservice token |
| `COURSE_ID` | Numeric ID of the course to edit |
| `OPENAI_API_KEY` | OpenAI API key (required for the agent) |
| `OPENAI_MODEL` | Optional; defaults to `gpt-4o` |

The course ID is set once on the client. Individual API calls do not take a course parameter.

## Using the agent

Start the CLI:

```bash
python -m agent.main
```

The agent loads the current course structure, then accepts prompts such as:

- *What sections and activities are in this course?*
- *Create a section called "Week 5" at the end of the course.*
- *Add a welcome label and a syllabus page to that section.*
- *Create an assignment due in two weeks, worth 100 points.*

Before any write is sent to Moodle, the agent shows what it intends to do and waits for confirmation (`y` to apply).

| Command | Description |
|---------|-------------|
| `/exit` | End the session |
| `/reset` | Clear conversation history |

Session logs are written to `logs/agent-<timestamp>-<pid>.jsonl`.

## Using the client directly

The agent is built on `MoodleClient` in `moodle_client.py`. You can use it in your own scripts:

```python
from moodle_client import MoodleClient

with MoodleClient(base_url=..., token=..., courseid=...) as client:
    print(client.course)                          # current structure
    client.create_section(name="Week 5", summary="<p>...</p>", position=6)
    client.create_label(sectionnum=5, labelcontent="<p>Welcome</p>", name="Welcome")
    client.dump("course-structure.json")
```

See the integration scripts under `tests/` for full examples of each module type.

## Development

### Unit tests

Run the full suite:

```bash
pytest -v
```

These tests use `FakeMoodleClient` and `FakeOpenAI`. They do not contact Moodle or OpenAI.

| Module | Coverage |
|--------|----------|
| `tests/test_summaries.py` | Course summary projection for LLM context |
| `tests/test_tools.py` | Tool schemas, handlers, and error envelopes |
| `tests/test_loop.py` | Agent loop, confirmation flow, context refresh |

Run a subset:

```bash
pytest tests/test_tools.py -v
pytest tests/test_loop.py -v
```

### Integration scripts

The scripts below call a live Moodle instance. Run them with `python`, not `pytest`:

```bash
python tests/test_sections.py
python tests/test_labels.py
python tests/test_pages.py
python tests/test_urls.py
python tests/test_assigns.py
```

Each script creates a section named `TEST - …` and walks through create, read, update, move, and copy for one module type. Remove test content manually in Moodle when finished.

### Continuous integration

Pushes and pull requests to `main` trigger [`.github/workflows/ci.yml`](.github/workflows/ci.yml), which runs `pytest` on Python 3.11 and 3.12. Integration scripts are excluded from CI.

## Project structure

```
moodle_client.py          Moodle REST client
agent/
  main.py                 CLI entrypoint
  loop.py                 OpenAI tool-calling loop
  tools.py                Tool definitions and handlers
  summaries.py            Compact course summary for the LLM
  confirm.py              Write confirmation prompt
  audit.py                Session audit log
prompts/system.md         Agent system prompt
tests/                    Unit tests and integration scripts
.github/workflows/ci.yml  GitHub Actions workflow
```
