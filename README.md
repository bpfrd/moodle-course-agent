# Moodle Course Agent

[![CI](https://github.com/bpfrd/moodle-course-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/bpfrd/moodle-course-agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/github/license/bpfrd/moodle-course-agent)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)

A Moodle course-editing API and tool layer for AI agents. The REST client and `agent/tools.py` definitions let an agent inspect a course, plan changes, and apply them through Moodle webservices.

## What the repo provides

| Component | Role |
|-----------|------|
| `moodle_client.py` | Moodle REST client (sections, labels, pages, URLs, forums, assignments) |
| `template_assignments.py` | Copy assignment templates, then update content |
| `agent/tools.py` | Tool definitions for agent-driven API calls |
| `agent/main.py` | Optional CLI agent for terminal chat over the same tools |

### Supported operations (v1)

| Type | Create | Read | Update |
|------|--------|------|--------|
| Section | ✓ | ✓ | ✓ |
| Label | ✓ | ✓ | ✓ |
| Page | ✓ | ✓ | ✓ |
| URL | ✓ | ✓ | ✓ |
| Forum | ✓ | ✓ | ✓ |
| Assignment | ✓ | ✓ | ✓ |

Not supported: delete modules/sections, file uploads, quizzes, user enrolment.

## Prerequisites

- Python 3.11 or 3.12
- Moodle with the course-editing webservices used by this client (see `moodle_client.py`)
- Webservice token with edit access to the target course
- Assignment templates in your Moodle course (if you use template-based assignment tools)

## Installation

```bash
python -m venv .venv
source .venv/bin/activate   # Linux / macOS
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env`:

| Variable | Description |
|----------|-------------|
| `BASE_URL` | Moodle REST endpoint |
| `WSTOKEN` | Webservice token |
| `COURSE_ID` | Target course id |

The course id is set once on the client. Individual API calls do not pass `courseid` again.

## Using the tools

Read `agent/tools.py` for every available operation, its description, and argument schema. Agents should call read tools first (`get_course_structure`, `get_assign`, etc.), present a plan, and only run write tools after explicit confirmation.

```python
from dotenv import load_dotenv
import os
from moodle_client import MoodleClient
from agent.tools import TOOLS

load_dotenv()
client = MoodleClient(
    base_url=os.environ["BASE_URL"],
    token=os.environ["WSTOKEN"],
    courseid=int(os.environ["COURSE_ID"]),
)
result = TOOLS["get_course_structure"].handler(client, {})
```

## Development

### Tests

```bash
pytest -v
```

Unit tests use fakes — no live Moodle required.

Integration scripts (live Moodle, run with `python` not `pytest`):

```bash
python tests/test_sections.py
python tests/test_labels.py
python tests/test_pages.py
python tests/test_urls.py
python tests/test_forums.py
python tests/test_assigns.py
```

Optional CLI agent:

```bash
python -m agent.main
```

## Project structure

```
moodle_client.py          Moodle REST client
template_assignments.py   Assignment template helpers
agent/
  tools.py                API tool definitions
  main.py                 Optional CLI agent
prompts/system.md         CLI agent system prompt
tests/
```

## License

This project is licensed under the [MIT License](LICENSE).
