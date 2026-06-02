import json
from dotenv import load_dotenv
import os

from moodle_client import MoodleClient


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
print("STEP 2 - CREATE TEST SECTION FOR PAGES")
print("=================================================\n")

test_section = client.create_section(
    name="TEST - Pages",
    summary="<p>Section for integration testing of pages.</p>",
    position=len(structure) + 1
)

print(f"Test section created: {test_section}")
TARGET_SECTIONNUM = test_section["sectionnum"]
print(f"Target sectionnum: {TARGET_SECTIONNUM}")


# =========================================================
# STEP 3
# CREATE PAGE #1
# =========================================================

print("\n=================================================")
print("STEP 3 - CREATE PAGE #1")
print("=================================================\n")

page1 = client.create_page(
    sectionnum=TARGET_SECTIONNUM,
    name="TEST - Page 1",
    intro="<p>Intro shown on course page.</p>",
    pagecontent=(
        "<h3>Welcome</h3>"
        "<p>This is <strong>TEST page #1</strong> body.</p>"
        "<ul><li>item one</li><li>item two</li></ul>"
    ),
    showdescription=1
)

print("Page #1 created:")
print(page1)

page1_cmid = page1["cmid"]
print(f"Page #1 cmid: {page1_cmid}")


# =========================================================
# STEP 4
# GET PAGE #1
# =========================================================

print("\n=================================================")
print("STEP 4 - GET PAGE #1")
print("=================================================\n")

fetched = client.get_page(cmid=page1_cmid)
print("Fetched page #1:")
print(json.dumps(fetched, indent=2, ensure_ascii=False))


# =========================================================
# STEP 5
# UPDATE PAGE #1
# =========================================================

print("\n=================================================")
print("STEP 5 - UPDATE PAGE #1")
print("=================================================\n")

updated = client.update_page(
    cmid=page1_cmid,
    name="TEST - Page 1 (updated)",
    intro="<p>Updated intro.</p>",
    pagecontent="<h3>Updated</h3><p>New body content.</p>",
    showdescription=0
)

print("Page #1 updated:")
print(updated)


# =========================================================
# STEP 6
# GET PAGE #1 AGAIN
# =========================================================

print("\n=================================================")
print("STEP 6 - GET PAGE #1 (after update)")
print("=================================================\n")

fetched_again = client.get_page(cmid=page1_cmid)
print("Fetched page #1 after update:")
print(json.dumps(fetched_again, indent=2, ensure_ascii=False))


# =========================================================
# STEP 7
# CREATE PAGE #2
# =========================================================

print("\n=================================================")
print("STEP 7 - CREATE PAGE #2")
print("=================================================\n")

page2 = client.create_page(
    sectionnum=TARGET_SECTIONNUM,
    name="TEST - Page 2",
    intro="<p>Intro for page 2.</p>",
    pagecontent="<p>Body for page 2.</p>"
)

print("Page #2 created:")
print(page2)

page2_cmid = page2["cmid"]
print(f"Page #2 cmid: {page2_cmid}")


# =========================================================
# STEP 8
# MOVE PAGE #1 TO END OF SECTION
# =========================================================

print("\n=================================================")
print("STEP 8 - MOVE PAGE #1 TO END")
print("=================================================\n")

moved = client.move_module(
    cmid=page1_cmid,
    beforemod=0  # 0 = append at end of section
)

print("Page #1 moved:")
print(moved)


# =========================================================
# STEP 9
# COPY PAGE #1 BEFORE PAGE #2
# =========================================================

print("\n=================================================")
print("STEP 9 - COPY PAGE #1 BEFORE PAGE #2")
print("=================================================\n")

copied = client.copy_module(
    cmid=page1_cmid,
    beforemod=page2_cmid
)

print("Page #1 copied:")
print(copied)


# =========================================================
# STEP 10
# SAVE FINAL STRUCTURE
# =========================================================

print("\n=================================================")
print("STEP 10 - SAVE FINAL STRUCTURE")
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
