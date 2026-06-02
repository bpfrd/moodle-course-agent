"""Unit tests for every tool handler in ``agent.tools``.

These tests run the handler directly against a ``FakeMoodleClient`` so we
verify both:
  * argument routing into the underlying client method, and
  * the ok/error envelope returned to the LLM.
"""

from __future__ import annotations

from agent.tools import TOOLS, openai_schemas


# ---------------------------------------------------------------------------
# Registry sanity
# ---------------------------------------------------------------------------


def test_openai_schemas_match_registry():
    schemas = openai_schemas()
    names_in_schema = {s["function"]["name"] for s in schemas}
    assert names_in_schema == set(TOOLS.keys())
    for schema in schemas:
        params = schema["function"]["parameters"]
        assert params["type"] == "object"
        assert "properties" in params


def test_each_tool_has_description():
    for name, tool in TOOLS.items():
        assert tool.description, f"{name} has no description"


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------


def test_get_course_structure(fake_client):
    out = TOOLS["get_course_structure"].handler(fake_client, {})
    assert out["ok"] is True
    assert [s["sectionnum"] for s in out["result"]] == [0, 1]


def test_get_label_returns_body(fake_client):
    out = TOOLS["get_label"].handler(fake_client, {"cmid": 100})
    assert out["ok"] is True
    assert out["result"]["labelcontent"] == "<p>welcome</p>"


def test_get_label_wrong_type_returns_error(fake_client):
    out = TOOLS["get_label"].handler(fake_client, {"cmid": 101})  # 101 is a page
    assert out["ok"] is False
    assert "label" in out["error"]


def test_get_label_unknown_cmid_returns_error(fake_client):
    out = TOOLS["get_label"].handler(fake_client, {"cmid": 99999})
    assert out["ok"] is False
    assert out["error_type"] == "MoodleAPIError"


# ---------------------------------------------------------------------------
# Section writes
# ---------------------------------------------------------------------------


def test_create_section_appends(fake_client):
    out = TOOLS["create_section"].handler(
        fake_client,
        {"name": "Week 2", "summary": "<p>w2</p>", "position": 3, "visible": 1},
    )
    assert out["ok"] is True
    assert len(fake_client.course) == 3
    assert fake_client.course[-1]["name"] == "Week 2"


def test_create_section_invalid_position(fake_client):
    out = TOOLS["create_section"].handler(
        fake_client,
        {"name": "x", "summary": "", "position": 99, "visible": 1},
    )
    assert out["ok"] is False
    assert out["error_type"] == "ValueError"


def test_move_section_reorders(fake_client):
    out = TOOLS["move_section"].handler(
        fake_client, {"sectionnum": 1, "position": 1}
    )
    assert out["ok"] is True
    assert fake_client.course[0]["name"] == "Week 1"


def test_update_section_invalid_sectionnum(fake_client):
    out = TOOLS["update_section"].handler(
        fake_client,
        {"sectionnum": 99, "name": "x", "summary": "y", "visible": 1},
    )
    assert out["ok"] is False
    assert "Invalid section" in out["error"]


# ---------------------------------------------------------------------------
# Label writes
# ---------------------------------------------------------------------------


def test_create_label(fake_client):
    out = TOOLS["create_label"].handler(
        fake_client,
        {
            "sectionnum": 1,
            "labelcontent": "<p>hello</p>",
            "name": "My label",
        },
    )
    assert out["ok"] is True
    new_cmid = out["result"]["cmid"]
    assert any(m["id"] == new_cmid for m in fake_client.course[1]["modules"])
    assert fake_client._module_bodies[new_cmid]["labelcontent"] == "<p>hello</p>"


def test_update_label(fake_client):
    out = TOOLS["update_label"].handler(
        fake_client,
        {
            "cmid": 100,
            "name": "Renamed",
            "labelcontent": "<p>new</p>",
        },
    )
    assert out["ok"] is True
    label = fake_client._find_module(100)
    assert label["name"] == "Renamed"
    assert fake_client._module_bodies[100]["labelcontent"] == "<p>new</p>"


# ---------------------------------------------------------------------------
# Page / URL / Assign writes
# ---------------------------------------------------------------------------


def test_create_page(fake_client):
    out = TOOLS["create_page"].handler(
        fake_client,
        {
            "sectionnum": 0,
            "name": "Notes",
            "intro": "<p>i</p>",
            "pagecontent": "<p>body</p>",
        },
    )
    assert out["ok"] is True
    assert fake_client.course[0]["modules"][-1]["modname"] == "page"


def test_create_url(fake_client):
    out = TOOLS["create_url"].handler(
        fake_client,
        {
            "sectionnum": 1,
            "name": "Slides",
            "intro": "",
            "externalurl": "https://example.org/slides.pdf",
        },
    )
    assert out["ok"] is True
    new_cmid = out["result"]["cmid"]
    assert fake_client._module_bodies[new_cmid]["externalurl"] == "https://example.org/slides.pdf"


def test_create_assign_with_zeitaufwand(fake_client):
    out = TOOLS["create_assign"].handler(
        fake_client,
        {
            "sectionnum": 1,
            "name": "HW 2",
            "intro": "<p>i</p>",
            "activity": "<p>q</p>",
            "duedate": 1735689600,
            "zeitaufwand": "2h",
        },
    )
    assert out["ok"] is True
    cmid = out["result"]["cmid"]
    assert fake_client._module_bodies[cmid]["timerequired"] == "2h"
    assert fake_client._module_bodies[cmid]["duedate"] == 1735689600


def test_create_assign_rejects_invalid_zeitaufwand(fake_client):
    out = TOOLS["create_assign"].handler(
        fake_client,
        {
            "sectionnum": 1,
            "name": "Invalid Zeitaufwand",
            "intro": "<p>i</p>",
            "activity": "<p>a</p>",
            "zeitaufwand": "30 min",  # invalid: must be e.g. 0.5h, 1h, 5min, ...
        },
    )
    assert out["ok"] is False
    assert out["error_type"] == "ValidationError"
    assert "Invalid zeitaufwand value" in out["error"]


def test_update_assign(fake_client):
    out = TOOLS["update_assign"].handler(
        fake_client,
        {
            "cmid": 102,
            "name": "Homework 1 (updated)",
            "intro": "<p>i</p>",
            "activity": "<p>q</p>",
            "duedate": 1735689600,
        },
    )
    assert out["ok"] is True
    assert fake_client._find_module(102)["name"] == "Homework 1 (updated)"


def test_create_aufgabe_ohne_abgabe_from_template(fake_client):
    template_section = {
        "id": 3,
        "section": 2,
        "name": "Modulentwicklung [RK only]",
        "summary": "",
        "visible": 1,
        "modules": [],
    }
    fake_client.course.append(template_section)
    t1 = fake_client.create_assign(
        sectionnum=2,
        name="Vorlage: Aufgabe ohne Abgabe",
        intro="<p>tmpl 1</p>",
        activity="<p>tmpl 1 body</p>",
    )["cmid"]
    fake_client.create_assign(
        sectionnum=2,
        name="Vorlage: Aufgabe mit Abgabe",
        intro="<p>tmpl 2</p>",
        activity="<p>tmpl 2 body</p>",
    )

    out = TOOLS["create_aufgabe_ohne_abgabe"].handler(
        fake_client,
        {
            "name": "Generated ohne",
            "intro": "<p>i</p>",
            "activity": "<p>a</p>",
            "sectionnum": 1,
            "duedate": 1735689600,
            "template_section_name": "Modulentwicklung [RK only]",
        },
    )
    assert out["ok"] is True
    assert out["result"]["template_cmid"] == t1
    new_cmid = out["result"]["new_cmid"]
    assert fake_client._find_module(new_cmid)["name"] == "Generated ohne"


def test_create_aufgabe_mit_abgabe_from_template(fake_client):
    template_section = {
        "id": 3,
        "section": 2,
        "name": "Modulentwicklung [RK only]",
        "summary": "",
        "visible": 1,
        "modules": [],
    }
    fake_client.course.append(template_section)
    fake_client.create_assign(
        sectionnum=2,
        name="Vorlage: Aufgabe ohne Abgabe",
        intro="<p>tmpl 1</p>",
        activity="<p>tmpl 1 body</p>",
    )
    t2 = fake_client.create_assign(
        sectionnum=2,
        name="Vorlage: Aufgabe mit Abgabe",
        intro="<p>tmpl 2</p>",
        activity="<p>tmpl 2 body</p>",
    )["cmid"]

    out = TOOLS["create_aufgabe_mit_abgabe"].handler(
        fake_client,
        {
            "name": "Generated mit",
            "intro": "<p>i</p>",
            "activity": "<p>a</p>",
            "beforemod": 101,
            "template_section_name": "Modulentwicklung [RK only]",
        },
    )
    assert out["ok"] is True
    assert out["result"]["template_cmid"] == t2
    new_cmid = out["result"]["new_cmid"]
    assert fake_client._find_module(new_cmid)["name"] == "Generated mit"


# ---------------------------------------------------------------------------
# Move / copy
# ---------------------------------------------------------------------------


def test_move_module(fake_client):
    out = TOOLS["move_module"].handler(
        fake_client, {"cmid": 100, "beforemod": 102}
    )
    assert out["ok"] is True
    cmids_week1 = [m["id"] for m in fake_client.course[1]["modules"]]
    assert cmids_week1.index(100) < cmids_week1.index(102)


def test_copy_module(fake_client):
    out = TOOLS["copy_module"].handler(
        fake_client, {"cmid": 100, "beforemod": 101}
    )
    assert out["ok"] is True
    new_cmid = out["result"]["cmid"]
    assert new_cmid != 100
    assert fake_client._module_bodies[new_cmid] == fake_client._module_bodies[100]


def test_move_module_unknown_cmid(fake_client):
    out = TOOLS["move_module"].handler(
        fake_client, {"cmid": 99999, "beforemod": 0}
    )
    assert out["ok"] is False


# ---------------------------------------------------------------------------
# Pydantic validation: bad arguments are caught before reaching the client
# ---------------------------------------------------------------------------


def test_pydantic_rejects_missing_required(fake_client):
    """Bad arguments must surface as ok=False, not as an uncaught exception."""
    out = TOOLS["create_section"].handler(fake_client, {"name": "x"})
    assert out["ok"] is False
    assert out["error_type"] == "ValidationError"
    assert "summary" in out["error"] or "position" in out["error"]


def test_pydantic_rejects_wrong_type(fake_client):
    out = TOOLS["get_label"].handler(fake_client, {"cmid": "not-a-number"})
    assert out["ok"] is False
    assert out["error_type"] == "ValidationError"
