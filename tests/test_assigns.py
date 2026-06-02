import json
import time
from dotenv import load_dotenv
import os

from moodle_client import MoodleClient
from template_assignments import (
    create_aufgabe_mit_abgabe,
    create_aufgabe_ohne_abgabe,
    get_assign_templates,
)


# =========================================================
# LOAD ENV
# =========================================================

load_dotenv()

BASE_URL = os.getenv("BASE_URL")
WSTOKEN = os.getenv("WSTOKEN")
COURSE_ID = int(os.getenv("COURSE_ID"))


# =========================================================
# INIT CLIENT
# =========================================================

client = MoodleClient(
    courseid=COURSE_ID,
    base_url=BASE_URL,
    token=WSTOKEN
)


# =========================================================
# DATE HELPERS
# =========================================================

# Moodle expects Unix timestamps (seconds since epoch) for due dates.
NOW = int(time.time())
DUEDATE_30_DAYS = NOW + 30 * 24 * 3600
DUEDATE_45_DAYS = NOW + 45 * 24 * 3600


# =========================================================
# STEP 1
# GET COURSE STRUCTURE
# =========================================================

print("\n=================================================")
print("STEP 1 - GET COURSE STRUCTURE")
print("=================================================\n")

structure = client.dump(filename="course-structure.json")
print(f"Total sections: {len(structure)}")


# =========================================================
# STEP 2
# CREATE TEST SECTION
# =========================================================

print("\n=================================================")
print("STEP 2 - CREATE TEST SECTION FOR ASSIGNMENTS")
print("=================================================\n")

test_section = client.create_section(
    name="TEST - Assignments",
    summary="<p>Section for integration testing of assignments.</p>",
    position=len(structure) + 1
)

print(f"Test section created: {test_section}")
TARGET_SECTIONNUM = test_section["sectionnum"]
print(f"Target sectionnum: {TARGET_SECTIONNUM}")


# =========================================================
# STEP 3
# CREATE ASSIGNMENT #1
# =========================================================

print("\n=================================================")
print("STEP 3 - CREATE ASSIGNMENT #1")
print("=================================================\n")

assign1 = client.create_assign(
    sectionnum=TARGET_SECTIONNUM,
    name="TEST - Assignment 1",
    intro="<p>Intro shown above the assignment.</p>",
    activity=(
        "<h3>Task</h3>"
        "<p>Answer the following questions:</p>"
        "<ol>"
        "<li>What is the capital of Switzerland?</li>"
        "<li>Explain the API in two sentences.</li>"
        "</ol>"
    ),
    duedate=DUEDATE_30_DAYS,
    grade=100,
    maxattempts=2,
    zeitaufwand="1h"  # FFHS custom field "timerequired"
)

print("Assignment #1 created:")
print(assign1)

assign1_cmid = assign1["cmid"]
print(f"Assignment #1 cmid: {assign1_cmid}")
print(f"Due date set: {time.strftime('%Y-%m-%d %H:%M', time.localtime(DUEDATE_30_DAYS))}")


# =========================================================
# STEP 4
# GET ASSIGNMENT #1
# =========================================================

print("\n=================================================")
print("STEP 4 - GET ASSIGNMENT #1")
print("=================================================\n")

fetched = client.get_assign(cmid=assign1_cmid)
print("Fetched assignment #1:")
print(json.dumps(fetched, indent=2, ensure_ascii=False))


# =========================================================
# STEP 5
# UPDATE ASSIGNMENT #1
# =========================================================

print("\n=================================================")
print("STEP 5 - UPDATE ASSIGNMENT #1")
print("=================================================\n")

updated = client.update_assign(
    cmid=assign1_cmid,
    name="TEST - Assignment 1 (updated)",
    intro="<p>Updated intro.</p>",
    activity=(
        "<h3>Updated task</h3>"
        "<p>Different questions now:</p>"
        "<ul><li>One short answer.</li></ul>"
    ),
    duedate=DUEDATE_45_DAYS,
    grade=50,
    maxattempts=1,
    zeitaufwand="0.75h"
)

print("Assignment #1 updated:")
print(updated)
print(f"New due date: {time.strftime('%Y-%m-%d %H:%M', time.localtime(DUEDATE_45_DAYS))}")


# =========================================================
# STEP 6
# GET ASSIGNMENT #1 AGAIN
# =========================================================

print("\n=================================================")
print("STEP 6 - GET ASSIGNMENT #1 (after update)")
print("=================================================\n")

fetched_again = client.get_assign(cmid=assign1_cmid)
print("Fetched assignment #1 after update:")
print(json.dumps(fetched_again, indent=2, ensure_ascii=False))


# =========================================================
# STEP 7
# CREATE ASSIGNMENT #2
# =========================================================

print("\n=================================================")
print("STEP 7 - CREATE ASSIGNMENT #2")
print("=================================================\n")

assign2 = client.create_assign(
    sectionnum=TARGET_SECTIONNUM,
    name="TEST - Assignment 2",
    intro="<p>Second assignment for move/copy testing.</p>",
    activity="<p>Just a placeholder activity.</p>",
    duedate=0,  # no due date
    grade=10
)

print("Assignment #2 created:")
print(assign2)

assign2_cmid = assign2["cmid"]
print(f"Assignment #2 cmid: {assign2_cmid}")


# =========================================================
# STEP 8
# TEMPLATE LOOKUP
# =========================================================

print("\n=================================================")
print("STEP 8 - LOOKUP ASSIGNMENT TEMPLATES")
print("=================================================\n")

templates = get_assign_templates(client)
print("Template cmids:")
print(templates)


# =========================================================
# STEP 9
# CREATE FROM TEMPLATE: OHNE ABGABE
# =========================================================

print("\n=================================================")
print("STEP 9 - CREATE TEMPLATE ASSIGN (OHNE ABGABE)")
print("=================================================\n")

tmpl_ohne = create_aufgabe_ohne_abgabe(
    client,
    name="TEST - Template Assign ohne Abgabe",
    intro="<p>Generated from template (ohne Abgabe).</p>",
    activity="<p>This assignment was copied from the ohne-Abgabe template.</p>",
    sectionnum=TARGET_SECTIONNUM,
    duedate=DUEDATE_30_DAYS,
    grade=20,
    zeitaufwand="0.5h",
)
print(tmpl_ohne)


# =========================================================
# STEP 10
# CREATE FROM TEMPLATE: MIT ABGABE
# =========================================================

print("\n=================================================")
print("STEP 10 - CREATE TEMPLATE ASSIGN (MIT ABGABE)")
print("=================================================\n")

tmpl_mit = create_aufgabe_mit_abgabe(
    client,
    name="TEST - Template Assign mit Abgabe",
    intro="<p>Generated from template (mit Abgabe).</p>",
    activity="<p>This assignment was copied from the mit-Abgabe template.</p>",
    sectionnum=TARGET_SECTIONNUM,
    duedate=DUEDATE_45_DAYS,
    grade=30,
    submissionattachments=1,
    zeitaufwand="1h",
)
print(tmpl_mit)


# =========================================================
# STEP 11
# MOVE ASSIGNMENT #1 TO END OF SECTION
# =========================================================

print("\n=================================================")
print("STEP 11 - MOVE ASSIGNMENT #1 TO END")
print("=================================================\n")

moved = client.move_module(
    cmid=assign1_cmid,
    beforemod=0  # 0 = append at end of section
)

print("Assignment #1 moved:")
print(moved)


# =========================================================
# STEP 12
# COPY ASSIGNMENT #1 BEFORE ASSIGNMENT #2
# =========================================================

print("\n=================================================")
print("STEP 12 - COPY ASSIGNMENT #1 BEFORE ASSIGNMENT #2")
print("=================================================\n")

copied = client.copy_module(
    cmid=assign1_cmid,
    beforemod=assign2_cmid
)

print("Assignment #1 copied:")
print(copied)


# =========================================================
# STEP 13
# SAVE FINAL STRUCTURE
# =========================================================

print("\n=================================================")
print("STEP 13 - SAVE FINAL STRUCTURE")
print("=================================================\n")

final = client.dump(filename="course-structure.json")

test_section_now = next(
    s for s in final if s["section"] == TARGET_SECTIONNUM
)

print(f"Section {TARGET_SECTIONNUM} ({test_section_now['name']}) now has "
      f"{len(test_section_now['modules'])} module(s):")
for m in test_section_now["modules"]:
    print(f"  - cmid={m['id']:<6} modname={m['modname']:<8} name={m['name']}")


# =========================================================
# DONE
# =========================================================

print("\n=================================================")
print("DONE")
print("=================================================\n")
