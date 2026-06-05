"""In-memory fakes for MoodleClient and the OpenAI SDK.

``FakeMoodleClient`` mirrors the public surface and validation behavior of
``MoodleClient`` so that handler / agent-loop tests exercise the same
code paths the real client would. It is intentionally close to the real
implementation - including the v1 quirks (``if beforemod:`` treating 0 as
"omit", for example) - so the tests reflect production reality.

``FakeOpenAI`` accepts a scripted list of responses and returns them one by
one when ``chat.completions.create`` is called. Each scripted response is
built with the ``assistant_text`` / ``assistant_tool_call`` helpers.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from moodle_client import MoodleAPIError


# ---------------------------------------------------------------------------
# FakeMoodleClient
# ---------------------------------------------------------------------------


class FakeMoodleClient:
    """In-memory stand-in for ``MoodleClient``.

    State is held in ``self._sections`` (the canonical list of sections, each
    with a ``modules`` list) and ``self._module_bodies`` (cmid -> the
    type-specific payload returned by ``get_label`` / ``get_page`` / etc.).
    """

    def __init__(
        self,
        courseid: int = 1,
        initial_course: list[dict[str, Any]] | None = None,
    ) -> None:
        self.courseid = courseid
        self._sections: list[dict[str, Any]] = []
        self._module_bodies: dict[int, dict[str, Any]] = {}
        self._next_section_id = 1
        self._next_cmid = 100
        self.closed = False
        self.calls: list[dict[str, Any]] = []  # audit trail for assertions

        if initial_course is not None:
            self._sections = [dict(s) for s in initial_course]
            for section in self._sections:
                section.setdefault("modules", [])
                for module in section["modules"]:
                    self._next_cmid = max(self._next_cmid, module["id"] + 1)
                self._next_section_id = max(
                    self._next_section_id, section.get("id", 0) + 1
                )
        else:
            self._sections = [self._make_section(name="General", sectionnum=0)]

    # --- context manager ---------------------------------------------------

    def __enter__(self) -> "FakeMoodleClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.closed = True

    # --- public API mirroring MoodleClient ---------------------------------

    @property
    def course(self) -> list[dict[str, Any]]:
        return self._sections

    def dump(self, filename: str = "course-dump.json") -> None:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self._sections, f, indent=2, ensure_ascii=False)

    def call(self, wsfunction: str, **params: Any) -> Any:
        # Tests should not invoke arbitrary wsfunctions through the fake.
        raise NotImplementedError(
            f"FakeMoodleClient.call({wsfunction!r}) is not implemented; "
            "use the typed methods instead."
        )

    # --- read ---------------------------------------------------------------

    def get_module(self, cmid: int) -> dict[str, Any]:
        self._record("get_module", cmid=cmid)
        module = self._find_module(cmid)
        if module is None:
            raise MoodleAPIError(f"moodle_exception: module {cmid} not found")
        return dict(module)

    def get_label(self, cmid: int) -> dict[str, Any]:
        return self._typed_get(cmid, "label")

    def get_page(self, cmid: int) -> dict[str, Any]:
        return self._typed_get(cmid, "page")

    def get_url(self, cmid: int) -> dict[str, Any]:
        return self._typed_get(cmid, "url")

    def get_assign(self, cmid: int) -> dict[str, Any]:
        return self._typed_get(cmid, "assign")

    def get_forum(self, cmid: int) -> dict[str, Any]:
        return self._typed_get(cmid, "forum")

    # --- section writes -----------------------------------------------------

    def create_section(
        self,
        name: str,
        summary: str,
        position: int,
        visible: int = 1,
    ) -> dict[str, Any]:
        self._record("create_section", name=name, position=position)
        total = len(self._sections)
        if position < 1 or position > total + 1:
            raise ValueError(
                f"Invalid position {position}. Must be between 1 and {total + 1}"
            )
        # In Moodle "position" is 1-indexed insertion slot; sectionnum is 0-indexed.
        new_sectionnum = position - 1 if position - 1 <= total else total
        section = self._make_section(
            name=name, summary=summary, visible=visible, sectionnum=None
        )
        self._sections.insert(position - 1, section)
        self._renumber_sections()
        section["section"] = new_sectionnum  # canonical sectionnum after renumber
        return {"sectionnum": section["section"], "sectionid": section["id"]}

    def move_section(self, sectionnum: int, position: int) -> dict[str, Any]:
        self._record("move_section", sectionnum=sectionnum, position=position)
        total = len(self._sections)
        if position < 1 or position > total:
            raise ValueError(
                f"Invalid position {position}. Must be between 1 and {total}"
            )
        idx = self._section_index(sectionnum)
        section = self._sections.pop(idx)
        self._sections.insert(position - 1, section)
        self._renumber_sections()
        return {"sectionnum": position - 1}

    def update_section(
        self,
        sectionnum: int,
        name: str,
        summary: str,
        visible: int = 1,
    ) -> dict[str, Any]:
        self._record("update_section", sectionnum=sectionnum, name=name)
        if sectionnum not in self._section_numbers():
            raise ValueError(f"Invalid section {sectionnum}")
        section = self._sections[self._section_index(sectionnum)]
        section["name"] = name
        section["summary"] = summary
        section["visible"] = visible
        return {"sectionnum": sectionnum}

    # --- label writes -------------------------------------------------------

    def create_label(
        self,
        sectionnum: int,
        labelcontent: str,
        name: str = "",
        visible: int = 1,
        visibleoncoursepage: int = 1,
        beforemod: int | None = None,
    ) -> dict[str, Any]:
        self._record("create_label", sectionnum=sectionnum, name=name)
        if sectionnum not in self._section_numbers():
            raise ValueError(f"Invalid section {sectionnum}")
        return self._insert_module(
            sectionnum=sectionnum,
            beforemod=beforemod,
            modname="label",
            name=name,
            visible=visible,
            visibleoncoursepage=visibleoncoursepage,
            body={"labelcontent": labelcontent},
        )

    def update_label(
        self,
        cmid: int,
        name: str,
        labelcontent: str,
        visible: int = 1,
        visibleoncoursepage: int = 1,
    ) -> dict[str, Any]:
        self._record("update_label", cmid=cmid)
        self._require_cmid(cmid)
        module = self._find_module(cmid)
        assert module is not None
        module["name"] = name
        module["visible"] = visible
        module["visibleoncoursepage"] = visibleoncoursepage
        self._module_bodies[cmid] = {"labelcontent": labelcontent}
        return {"cmid": cmid}

    # --- page writes --------------------------------------------------------

    def create_page(
        self,
        sectionnum: int,
        name: str,
        intro: str,
        pagecontent: str,
        visible: int = 1,
        visibleoncoursepage: int = 1,
        showdescription: int = 0,
        beforemod: int | None = None,
    ) -> dict[str, Any]:
        self._record("create_page", sectionnum=sectionnum, name=name)
        if sectionnum not in self._section_numbers():
            raise ValueError(f"Invalid section number {sectionnum}")
        return self._insert_module(
            sectionnum=sectionnum,
            beforemod=beforemod,
            modname="page",
            name=name,
            visible=visible,
            visibleoncoursepage=visibleoncoursepage,
            body={
                "intro": intro,
                "pagecontent": pagecontent,
                "showdescription": showdescription,
            },
        )

    def update_page(
        self,
        cmid: int,
        name: str,
        intro: str,
        pagecontent: str,
        visible: int = 1,
        visibleoncoursepage: int = 1,
        showdescription: int = 0,
    ) -> dict[str, Any]:
        self._record("update_page", cmid=cmid)
        self._require_cmid(cmid)
        module = self._find_module(cmid)
        assert module is not None
        module["name"] = name
        module["visible"] = visible
        module["visibleoncoursepage"] = visibleoncoursepage
        self._module_bodies[cmid] = {
            "intro": intro,
            "pagecontent": pagecontent,
            "showdescription": showdescription,
        }
        return {"cmid": cmid}

    # --- url writes ---------------------------------------------------------

    def create_url(
        self,
        sectionnum: int,
        name: str,
        intro: str,
        externalurl: str,
        display: int = 0,
        visible: int = 1,
        visibleoncoursepage: int = 1,
        showdescription: int = 0,
        beforemod: int | None = None,
    ) -> dict[str, Any]:
        self._record("create_url", sectionnum=sectionnum, name=name)
        if sectionnum not in self._section_numbers():
            raise ValueError(f"Invalid section number {sectionnum}")
        return self._insert_module(
            sectionnum=sectionnum,
            beforemod=beforemod,
            modname="url",
            name=name,
            visible=visible,
            visibleoncoursepage=visibleoncoursepage,
            body={
                "intro": intro,
                "externalurl": externalurl,
                "display": display,
                "showdescription": showdescription,
            },
        )

    def update_url(
        self,
        cmid: int,
        name: str,
        intro: str,
        externalurl: str,
        display: int = 0,
        visible: int = 1,
        visibleoncoursepage: int = 1,
        showdescription: int = 0,
    ) -> dict[str, Any]:
        self._record("update_url", cmid=cmid)
        self._require_cmid(cmid)
        module = self._find_module(cmid)
        assert module is not None
        module["name"] = name
        module["visible"] = visible
        module["visibleoncoursepage"] = visibleoncoursepage
        self._module_bodies[cmid] = {
            "intro": intro,
            "externalurl": externalurl,
            "display": display,
            "showdescription": showdescription,
        }
        return {"cmid": cmid}

    # --- forum writes -------------------------------------------------------

    def create_forum(
        self,
        sectionnum: int,
        name: str,
        intro: str,
        visible: int = 1,
        visibleoncoursepage: int = 1,
        showdescription: int = 0,
        beforemod: int | None = None,
        type: str = "general",
        showimmediately: int = 0,
        duedate: int = 0,
        cutoffdate: int = 0,
        maxbytes: int = 0,
        maxattachments: int = 1,
        displaywordcount: int = 0,
        forcesubscribe: int = 0,
        trackingtype: int = 1,
        lockdiscussionafter: int = 0,
        blockperiod: int = 0,
        blockafter: int = 0,
        warnafter: int = 0,
    ) -> dict[str, Any]:
        self._record("create_forum", sectionnum=sectionnum, name=name)
        if sectionnum not in self._section_numbers():
            raise ValueError(f"Invalid section number {sectionnum}")
        allowed = {"single", "eachuser", "qanda", "blog", "general"}
        if type not in allowed:
            raise ValueError(f"Invalid forum type {type!r}")
        return self._insert_module(
            sectionnum=sectionnum,
            beforemod=beforemod,
            modname="forum",
            name=name,
            visible=visible,
            visibleoncoursepage=visibleoncoursepage,
            body={
                "intro": intro,
                "type": type,
                "showdescription": showdescription,
                "duedate": duedate,
                "cutoffdate": cutoffdate,
            },
        )

    def update_forum(
        self,
        cmid: int,
        name: str,
        intro: str,
        visible: int = 1,
        visibleoncoursepage: int = 1,
        showdescription: int = 0,
        type: str = "general",
        showimmediately: int = 0,
        duedate: int = 0,
        cutoffdate: int = 0,
        maxbytes: int = 0,
        maxattachments: int = 1,
        displaywordcount: int = 0,
        forcesubscribe: int = 0,
        trackingtype: int = 1,
        lockdiscussionafter: int = 0,
        blockperiod: int = 0,
        blockafter: int = 0,
        warnafter: int = 0,
    ) -> dict[str, Any]:
        self._record("update_forum", cmid=cmid)
        self._require_cmid(cmid)
        module = self._find_module(cmid)
        assert module is not None
        if module.get("modname") != "forum":
            raise MoodleAPIError(f"moodle_exception: cmid {cmid} is not a forum")
        allowed = {"single", "eachuser", "qanda", "blog", "general"}
        if type not in allowed:
            raise ValueError(f"Invalid forum type {type!r}")
        module["name"] = name
        module["visible"] = visible
        module["visibleoncoursepage"] = visibleoncoursepage
        self._module_bodies[cmid] = {
            "intro": intro,
            "type": type,
            "showdescription": showdescription,
            "duedate": duedate,
            "cutoffdate": cutoffdate,
            "forcesubscribe": forcesubscribe,
            "trackingtype": trackingtype,
        }
        return {"cmid": cmid, "message": "ok"}

    # --- assign writes ------------------------------------------------------

    def create_assign(
        self,
        sectionnum: int,
        name: str,
        intro: str,
        activity: str,
        allowsubmissionsfromdate: int = 0,
        duedate: int = 0,
        cutoffdate: int = 0,
        gradingduedate: int = 0,
        timelimit: int = 0,
        submissionattachments: int = 0,
        maxattempts: int = 1,
        grade: int = 100,
        visible: int = 1,
        visibleoncoursepage: int = 1,
        showdescription: int = 0,
        zeitaufwand: str | None = None,
        beforemod: int | None = None,
    ) -> dict[str, Any]:
        self._record("create_assign", sectionnum=sectionnum, name=name)
        if sectionnum not in self._section_numbers():
            raise ValueError(f"Invalid section number {sectionnum}")
        body = {
            "intro": intro,
            "activity": activity,
            "allowsubmissionsfromdate": allowsubmissionsfromdate,
            "duedate": duedate,
            "cutoffdate": cutoffdate,
            "gradingduedate": gradingduedate,
            "timelimit": timelimit,
            "submissionattachments": submissionattachments,
            "maxattempts": maxattempts,
            "grade": grade,
            "showdescription": showdescription,
        }
        result = self._insert_module(
            sectionnum=sectionnum,
            beforemod=beforemod,
            modname="assign",
            name=name,
            visible=visible,
            visibleoncoursepage=visibleoncoursepage,
            body=body,
        )
        if zeitaufwand:
            self._module_bodies[result["cmid"]]["timerequired"] = zeitaufwand
        return result

    def update_assign(
        self,
        cmid: int,
        name: str,
        intro: str,
        activity: str,
        allowsubmissionsfromdate: int = 0,
        duedate: int = 0,
        cutoffdate: int = 0,
        gradingduedate: int = 0,
        timelimit: int = 0,
        submissionattachments: int = 0,
        maxattempts: int = 1,
        grade: int = 100,
        visible: int = 1,
        visibleoncoursepage: int = 1,
        showdescription: int = 0,
        zeitaufwand: str | None = None,
    ) -> dict[str, Any]:
        self._record("update_assign", cmid=cmid)
        self._require_cmid(cmid)
        module = self._find_module(cmid)
        assert module is not None
        module["name"] = name
        module["visible"] = visible
        module["visibleoncoursepage"] = visibleoncoursepage
        self._module_bodies[cmid].update(
            {
                "intro": intro,
                "activity": activity,
                "allowsubmissionsfromdate": allowsubmissionsfromdate,
                "duedate": duedate,
                "cutoffdate": cutoffdate,
                "gradingduedate": gradingduedate,
                "timelimit": timelimit,
                "submissionattachments": submissionattachments,
                "maxattempts": maxattempts,
                "grade": grade,
                "showdescription": showdescription,
            }
        )
        if zeitaufwand:
            self._module_bodies[cmid]["timerequired"] = zeitaufwand
        return {"cmid": cmid}

    # --- module move/copy ---------------------------------------------------

    def move_module(self, cmid: int, beforemod: int) -> dict[str, Any]:
        self._record("move_module", cmid=cmid, beforemod=beforemod)
        cmids = self._all_cmids()
        if cmid not in cmids:
            raise ValueError(f"Module {cmid} not found")
        if beforemod != 0 and beforemod not in cmids:
            raise ValueError(f"beforemod {beforemod} not found")

        # remove from current location
        src_section, src_idx = self._find_module_location(cmid)
        module = src_section["modules"].pop(src_idx)

        if beforemod == 0:
            # append to last section
            self._sections[-1]["modules"].append(module)
        else:
            dst_section, dst_idx = self._find_module_location(beforemod)
            dst_section["modules"].insert(dst_idx, module)
        return {"cmid": cmid}

    def copy_module(self, cmid: int, beforemod: int) -> dict[str, Any]:
        self._record("copy_module", cmid=cmid, beforemod=beforemod)
        cmids = self._all_cmids()
        if cmid not in cmids:
            raise ValueError(f"Module {cmid} not found")
        if beforemod != 0 and beforemod not in cmids:
            raise ValueError(f"Module {beforemod} not found")

        original = self._find_module(cmid)
        assert original is not None
        new_cmid = self._next_cmid
        self._next_cmid += 1
        clone = dict(original)
        clone["id"] = new_cmid
        if cmid in self._module_bodies:
            self._module_bodies[new_cmid] = dict(self._module_bodies[cmid])

        if beforemod == 0:
            self._sections[-1]["modules"].append(clone)
        else:
            dst_section, dst_idx = self._find_module_location(beforemod)
            dst_section["modules"].insert(dst_idx, clone)
        return {"cmid": new_cmid}

    def delete_module(self, cmid: int) -> None:  # pragma: no cover - parity with real
        raise NotImplementedError("Module deletion is not implemented yet")

    # --- internal helpers ---------------------------------------------------

    def _record(self, method: str, **fields: Any) -> None:
        self.calls.append({"method": method, **fields})

    def _make_section(
        self,
        name: str,
        summary: str = "",
        visible: int = 1,
        sectionnum: int | None = None,
    ) -> dict[str, Any]:
        section = {
            "id": self._next_section_id,
            "section": sectionnum if sectionnum is not None else 0,
            "name": name,
            "summary": summary,
            "visible": visible,
            "modules": [],
        }
        self._next_section_id += 1
        return section

    def _renumber_sections(self) -> None:
        for i, section in enumerate(self._sections):
            section["section"] = i

    def _section_numbers(self) -> set[int]:
        return {s["section"] for s in self._sections}

    def _section_index(self, sectionnum: int) -> int:
        for i, section in enumerate(self._sections):
            if section["section"] == sectionnum:
                return i
        raise ValueError(f"Invalid section {sectionnum}")

    def _all_cmids(self) -> set[int]:
        return {m["id"] for s in self._sections for m in s.get("modules", [])}

    def _require_cmid(self, cmid: int) -> None:
        if cmid not in self._all_cmids():
            raise ValueError(f"Invalid cmid {cmid}")

    def _find_module(self, cmid: int) -> dict[str, Any] | None:
        for section in self._sections:
            for module in section.get("modules", []):
                if module["id"] == cmid:
                    return module
        return None

    def _find_module_location(self, cmid: int) -> tuple[dict[str, Any], int]:
        for section in self._sections:
            for idx, module in enumerate(section.get("modules", [])):
                if module["id"] == cmid:
                    return section, idx
        raise ValueError(f"cmid {cmid} not found")

    def _typed_get(self, cmid: int, expected_modname: str) -> dict[str, Any]:
        self._record(f"get_{expected_modname}", cmid=cmid)
        module = self._find_module(cmid)
        if module is None:
            raise MoodleAPIError(f"moodle_exception: cmid {cmid} not found")
        if module.get("modname") != expected_modname:
            raise MoodleAPIError(
                f"moodle_exception: cmid {cmid} is a {module.get('modname')}, "
                f"not a {expected_modname}"
            )
        return {
            "cmid": cmid,
            "name": module.get("name"),
            "visible": module.get("visible"),
            **self._module_bodies.get(cmid, {}),
        }

    def _insert_module(
        self,
        sectionnum: int,
        beforemod: int | None,
        modname: str,
        name: str,
        visible: int,
        visibleoncoursepage: int,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        section = self._sections[self._section_index(sectionnum)]
        cmid = self._next_cmid
        self._next_cmid += 1
        module = {
            "id": cmid,
            "modname": modname,
            "name": name,
            "visible": visible,
            "visibleoncoursepage": visibleoncoursepage,
        }
        # Mirror the v1 quirk: falsy beforemod (None or 0) -> append.
        if beforemod:
            try:
                _, idx = self._find_module_location(beforemod)
                # Only honor beforemod if it lives in the same section.
                if any(m["id"] == beforemod for m in section["modules"]):
                    section["modules"].insert(idx, module)
                else:
                    section["modules"].append(module)
            except ValueError:
                section["modules"].append(module)
        else:
            section["modules"].append(module)
        self._module_bodies[cmid] = body
        return {"cmid": cmid, "sectionnum": sectionnum}


# ---------------------------------------------------------------------------
# FakeOpenAI
# ---------------------------------------------------------------------------


def _tool_call(call_id: str, name: str, arguments: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def assistant_text(text: str) -> SimpleNamespace:
    """Build a scripted response where the model returns a final text reply."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text, tool_calls=None),
                finish_reason="stop",
            )
        ]
    )


def assistant_tool_call(
    name: str, arguments: dict[str, Any], call_id: str = "call_1"
) -> SimpleNamespace:
    """Build a scripted response where the model requests a single tool call."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[_tool_call(call_id, name, arguments)],
                ),
                finish_reason="tool_calls",
            )
        ]
    )


def assistant_tool_calls(
    calls: list[tuple[str, dict[str, Any]]],
) -> SimpleNamespace:
    """Build a scripted response with multiple tool calls in one turn."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        _tool_call(f"call_{i}", name, args)
                        for i, (name, args) in enumerate(calls, start=1)
                    ],
                ),
                finish_reason="tool_calls",
            )
        ]
    )


class FakeOpenAI:
    """Returns scripted responses; records every ``create`` invocation."""

    def __init__(self, scripted_responses: list[SimpleNamespace]) -> None:
        self._scripted = list(scripted_responses)
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        **_: Any,
    ) -> SimpleNamespace:
        self.calls.append(
            {
                "model": model,
                "messages": list(messages),
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        if not self._scripted:
            raise AssertionError(
                "FakeOpenAI ran out of scripted responses; the agent loop "
                "made more turns than expected."
            )
        return self._scripted.pop(0)
