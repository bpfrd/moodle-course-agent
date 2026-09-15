from functools import wraps
import json
from typing import Dict, Any, Optional
import requests


class MoodleAPIError(Exception):
    pass


def mutate(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        result = method(self, *args, **kwargs)
        self._sync()
        return result
    return wrapper

class MoodleClient:

    def __init__(self, base_url: str, token: str, courseid: int, timeout: int = 60):
        self.base_url = base_url
        self.token = token
        self.courseid = courseid
        self.timeout = timeout
        self._course = None
        self.session = requests.Session()
        self._sync()
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self.session.close()

    @property
    def course(self):
        return self._course

    def _sync(self):
        self._course = self.call(
            "core_course_get_contents",
            courseid=self.courseid
        )
    
    def dump(self, filename: str = "course-dump.json"):

        if not self.course:
            self._sync()

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.course, f, indent=2, ensure_ascii=False)
        return self.course

    def call(self, wsfunction: str, **params):

        payload = {
            "wstoken": self.token,
            "moodlewsrestformat": "json",
            "wsfunction": wsfunction,
        }

        payload.update(params)

        response = self.session.post(
            self.base_url,
            data=payload,
            timeout=self.timeout
        )

        response.raise_for_status()

        data = response.json()

        if isinstance(data, dict) and data.get("exception"):
            raise MoodleAPIError(
                f"{data.get('exception')}: {data.get('message')}"
            )

        return data

    @mutate
    def create_section(
        self,
        name: str,
        summary: str,
        position: int,
        visible: int = 1
    ):
        
        total_sections = len(self.course)
        if position < 1 or position > total_sections + 1:
            raise ValueError(
                f"Invalid position {position}. "
                f"Must be between 1 and {total_sections + 1}"
            )

        return self.call(
            "local_ffhs_course_editing_create_section",
            courseid=self.courseid,
            position=position,
            name=name,
            summary=summary,
            visible=visible
        )

    @mutate
    def move_section(
        self,
        sectionnum: int,
        position: int
    ):
        total_sections = len(self.course)
        if position < 1 or position > total_sections:
            raise ValueError(
                f"Invalid position {position}. "
                f"Must be between 1 and {total_sections}"
            )
        
        return self.call(
            "local_ffhs_course_editing_move_section",
            courseid=self.courseid,
            sectionnum=sectionnum,
            position=position
        )
    
    @mutate
    def update_section(
        self,
        sectionnum: int,
        name: str,
        summary: str,
        visible: int = 1
    ):
        # check if sectionnum is valid
        section_numbers = {s["section"] for s in self.course}
        if sectionnum not in section_numbers:
            raise ValueError(f"Invalid section {sectionnum}")

        return self.call(
            "local_ffhs_course_editing_update_section",
            courseid=self.courseid,
            sectionnum=sectionnum,
            name=name,
            summary=summary,
            visible=visible
        )
    
    def get_module(
        self,
        cmid: int
    ):

        return self.call(
            "core_course_get_course_module",
            cmid=cmid
        )
    
    def get_label(
        self,
        cmid: int
    ):

        return self.call(
            "local_ffhs_course_editing_get_label",
            courseid=self.courseid,
            cmid=cmid
        )

    def get_page(
        self,
        cmid: int
    ):

        return self.call(
            "local_ffhs_course_editing_get_page",
            courseid=self.courseid,
            cmid=cmid
        )

    def get_url(
        self,
        cmid: int
    ):

        return self.call(
            "local_ffhs_course_editing_get_url",
            courseid=self.courseid,
            cmid=cmid
        )

    def get_assign(
        self,
        cmid: int
    ):

        return self.call(
            "local_ffhs_course_editing_get_assign",
            courseid=self.courseid,
            cmid=cmid
        )

    def get_forum(
        self,
        cmid: int,
    ):
        return self.call(
            "local_ffhs_course_editing_get_forum",
            courseid=self.courseid,
            cmid=cmid,
        )

    @mutate
    def create_label(
        self,
        sectionnum: int,
        labelcontent: str, # html content of the label
        name: str = "",
        visible: int = 1,
        visibleoncoursepage: int = 1,
        beforemod: Optional[int] = None
    ):

        # check if sectionnum is valid
        section_numbers = {s["section"] for s in self.course}
        if sectionnum not in section_numbers:
            raise ValueError(f"Invalid section {sectionnum}")

        payload = {
            "courseid": self.courseid,
            "sectionnum": sectionnum,
            "labelcontent": labelcontent,
            "name": name,
            "visible": visible,
            "visibleoncoursepage": visibleoncoursepage
        }

        if beforemod:
            payload["beforemod"] = beforemod

        return self.call(
            "local_ffhs_course_editing_create_label",
            **payload
        )
    
    @mutate
    def create_page(
        self,
        sectionnum: int,
        name: str,
        intro: str, # html content describing the page, shown on course page if showdescription is enabled
        pagecontent: str, # html content of the page
        visible: int = 1,
        visibleoncoursepage: int = 1,
        showdescription: int = 0,
        beforemod: Optional[int] = None
    ):

        section_numbers = {s["section"] for s in self.course}
        if sectionnum not in section_numbers:
            raise ValueError(
                f"Invalid section number {sectionnum}"
            )

        payload = {
            "courseid": self.courseid,
            "sectionnum": sectionnum,
            "name": name,
            "intro": intro,
            "pagecontent": pagecontent,
            "visible": visible,
            "visibleoncoursepage": visibleoncoursepage,
            "showdescription": showdescription,
        }

        if beforemod:
            payload["beforemod"] = beforemod

        created_page = self.call(
            "local_ffhs_course_editing_create_page",
            **payload
        )
        
        return created_page

    @mutate
    def create_forum(
        self,
        sectionnum: int,
        name: str,
        intro: str,
        visible: int = 1,
        visibleoncoursepage: int = 1,
        showdescription: int = 0,
        beforemod: Optional[int] = None,
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
    ):
        section_numbers = {s["section"] for s in self.course}
        if sectionnum not in section_numbers:
            raise ValueError(f"Invalid section number {sectionnum}")

        allowed_types = {"single", "eachuser", "qanda", "blog", "general"}
        if type not in allowed_types:
            raise ValueError(
                f"Invalid forum type {type!r}. "
                f"Allowed: {', '.join(sorted(allowed_types))}"
            )

        payload = {
            "courseid": self.courseid,
            "sectionnum": sectionnum,
            "name": name,
            "intro": intro,
            "visible": visible,
            "visibleoncoursepage": visibleoncoursepage,
            "showdescription": showdescription,
            "type": type,
            "showimmediately": showimmediately,
            "duedate": duedate,
            "cutoffdate": cutoffdate,
            "maxbytes": maxbytes,
            "maxattachments": maxattachments,
            "displaywordcount": displaywordcount,
            "forcesubscribe": forcesubscribe,
            "trackingtype": trackingtype,
            "lockdiscussionafter": lockdiscussionafter,
            "blockperiod": blockperiod,
            "blockafter": blockafter,
            "warnafter": warnafter,
        }

        if beforemod:
            payload["beforemod"] = beforemod

        return self.call(
            "local_ffhs_course_editing_create_forum",
            **payload,
        )

    @mutate
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
    ):
        cmids = {m["id"] for s in self.course for m in s.get("modules", [])}
        if cmid not in cmids:
            raise ValueError(f"Invalid cmid {cmid}")

        allowed_types = {"single", "eachuser", "qanda", "blog", "general"}
        if type not in allowed_types:
            raise ValueError(
                f"Invalid forum type {type!r}. "
                f"Allowed: {', '.join(sorted(allowed_types))}"
            )

        return self.call(
            "local_ffhs_course_editing_update_forum",
            courseid=self.courseid,
            cmid=cmid,
            name=name,
            intro=intro,
            visible=visible,
            visibleoncoursepage=visibleoncoursepage,
            showdescription=showdescription,
            type=type,
            showimmediately=showimmediately,
            duedate=duedate,
            cutoffdate=cutoffdate,
            maxbytes=maxbytes,
            maxattachments=maxattachments,
            displaywordcount=displaywordcount,
            forcesubscribe=forcesubscribe,
            trackingtype=trackingtype,
            lockdiscussionafter=lockdiscussionafter,
            blockperiod=blockperiod,
            blockafter=blockafter,
            warnafter=warnafter,
        )

    @mutate
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
        beforemod: Optional[int] = None
    ):

        section_numbers = {s["section"] for s in self.course}
        if sectionnum not in section_numbers:
            raise ValueError(
                f"Invalid section number {sectionnum}"
            )

        payload = {
            "courseid": self.courseid,
            "sectionnum": sectionnum,
            "name": name,
            "intro": intro,
            "externalurl": externalurl,
            "display": display,
            "visible": visible,
            "visibleoncoursepage": visibleoncoursepage,
            "showdescription": showdescription,
        }

        if beforemod:
            payload["beforemod"] = beforemod

        created_url = self.call(
            "local_ffhs_course_editing_create_url",
            **payload
        )

        return created_url

    @mutate
    def create_assign(
        self,
        sectionnum: int,
        name: str,
        intro: str, # html content describing the assignment
        activity: str, # html content describing the assignment activity (e.g. instructions, questions, etc.)
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
        zeitaufwand: Optional[str] = None,
        beforemod: Optional[int] = None
    ):

        section_numbers = {s["section"] for s in self.course}
        if sectionnum not in section_numbers:
            raise ValueError(
                f"Invalid section number {sectionnum}"
            )

        payload = {
            "courseid": self.courseid,
            "sectionnum": sectionnum,
            "name": name,
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
            "visible": visible,
            "visibleoncoursepage": visibleoncoursepage,
            "showdescription": showdescription,
        }

        if beforemod:
            payload["beforemod"] = beforemod

        created_assign = self.call(
            "local_ffhs_course_editing_create_assign",
            **payload
        )

        if zeitaufwand:
            self.call(
                "local_ffhs_course_editing_update_module_customfield",
                courseid=self.courseid,
                cmid=created_assign["cmid"],
                field="timerequired",
                value=zeitaufwand
            )

        return created_assign

    @mutate
    def update_label(
        self,
        cmid: int,
        name: str,
        labelcontent: str,
        visible: int = 1,
        visibleoncoursepage: int = 1
    ):
        # check if cmid is valid
        cmids = {m["id"] for s in self.course for m in s.get("modules", [])}
        if cmid not in cmids:
            raise ValueError(f"Invalid cmid {cmid}")

        updated_label = self.call(
            "local_ffhs_course_editing_update_label",
            courseid=self.courseid,
            cmid=cmid,
            name=name,
            labelcontent=labelcontent,
            visible=visible,
            visibleoncoursepage=visibleoncoursepage
        )

        return updated_label

    @mutate
    def update_page(
        self,
        cmid: int,
        name: str,
        intro: str,
        pagecontent: str,
        visible: int = 1,
        visibleoncoursepage: int = 1,
        showdescription: int = 0
    ):

        # check if cmid is valid
        cmids = {m["id"] for s in self.course for m in s.get("modules", [])}
        if cmid not in cmids:
            raise ValueError(f"Invalid cmid {cmid}")

        updated_page = self.call(
            "local_ffhs_course_editing_update_page",
            courseid=self.courseid,
            cmid=cmid,
            name=name,
            intro=intro,
            pagecontent=pagecontent,
            visible=visible,
            visibleoncoursepage=visibleoncoursepage,
            showdescription=showdescription
        )

        return updated_page

    @mutate
    def update_url(
        self,
        cmid: int,
        name: str,
        intro: str,
        externalurl: str,
        display: int = 0,
        visible: int = 1,
        visibleoncoursepage: int = 1,
        showdescription: int = 0
    ):

        # check if cmid is valid
        cmids = {m["id"] for s in self.course for m in s.get("modules", [])}
        if cmid not in cmids:
            raise ValueError(f"Invalid cmid {cmid}")

        updated_url = self.call(
            "local_ffhs_course_editing_update_url",
            courseid=self.courseid,
            cmid=cmid,
            name=name,
            intro=intro,
            externalurl=externalurl,
            display=display,
            visible=visible,
            visibleoncoursepage=visibleoncoursepage,
            showdescription=showdescription
        )
        return updated_url

    @mutate
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
        zeitaufwand: Optional[str] = None
    ):

        # check if cmid is valid
        cmids = {m["id"] for s in self.course for m in s.get("modules", [])}
        if cmid not in cmids:
            raise ValueError(f"Invalid cmid {cmid}")

        updated_assign = self.call(
            "local_ffhs_course_editing_update_assign",
            courseid=self.courseid,
            cmid=cmid,
            name=name,
            intro=intro,
            activity=activity,
            allowsubmissionsfromdate=allowsubmissionsfromdate,
            duedate=duedate,
            cutoffdate=cutoffdate,
            gradingduedate=gradingduedate,
            timelimit=timelimit,
            submissionattachments=submissionattachments,
            maxattempts=maxattempts,
            grade=grade,
            visible=visible,
            visibleoncoursepage=visibleoncoursepage,
            showdescription=showdescription
        )
        
        if zeitaufwand:
            self.call(
                "local_ffhs_course_editing_update_module_customfield",
                courseid=self.courseid,
                cmid=cmid,
                field="timerequired",
                value=zeitaufwand
            )
        return updated_assign

    @mutate
    def move_module(
        self,
        cmid: int,
        beforemod: int
    ):

        cmids = {m["id"] for s in self.course for m in s.get("modules", [])}
        if cmid not in cmids:
            raise ValueError(f"Module {cmid} not found")

        if beforemod != 0 and beforemod not in cmids:
            raise ValueError(
                f"beforemod {beforemod} not found"
            )

        moved_module = self.call(
            "local_ffhs_course_editing_move_module",
            courseid=self.courseid,
            cmid=cmid,
            beforemod=beforemod
        )
        return moved_module

    @mutate
    def delete_module(
        self,
        cmid: int
    ):

        raise NotImplementedError(
            "Module deletion is not implemented yet"
        )

    @mutate
    def copy_module(
        self,
        cmid: int,
        beforemod: int
    ):

        # check if cmid and beforemod are valid
        cmids = {m["id"] for s in self.course for m in s.get("modules", [])}
        if cmid not in cmids:
            raise ValueError(f"Module {cmid} not found")
        if beforemod != 0 and beforemod not in cmids:
            raise ValueError(f"Module {beforemod} not found")
        
        new_module = self.call(
            "local_ffhs_course_editing_copy_module",
            courseid=self.courseid,
            cmid=cmid,
            beforemod=beforemod
        )
        return new_module
    