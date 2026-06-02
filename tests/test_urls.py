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
print("STEP 2 - CREATE TEST SECTION FOR URLS")
print("=================================================\n")

test_section = client.create_section(
    name="TEST - URLs",
    summary="<p>Section for integration testing of URL resources.</p>",
    position=len(structure) + 1
)

print(f"Test section created: {test_section}")
TARGET_SECTIONNUM = test_section["sectionnum"]
print(f"Target sectionnum: {TARGET_SECTIONNUM}")


# =========================================================
# STEP 3
# CREATE URL #1
# =========================================================

print("\n=================================================")
print("STEP 3 - CREATE URL #1")
print("=================================================\n")

url1 = client.create_url(
    sectionnum=TARGET_SECTIONNUM,
    name="TEST - URL 1 (FFHS website)",
    intro="<p>Link to the FFHS website.</p>",
    externalurl="https://www.ffhs.ch",
    display=0,  # 0 = automatic, 1 = embed, 5 = open, 6 = popup
    showdescription=1
)

print("URL #1 created:")
print(url1)

url1_cmid = url1["cmid"]
print(f"URL #1 cmid: {url1_cmid}")


# =========================================================
# STEP 4
# GET URL #1
# =========================================================

print("\n=================================================")
print("STEP 4 - GET URL #1")
print("=================================================\n")

fetched = client.get_url(cmid=url1_cmid)
print("Fetched URL #1:")
print(json.dumps(fetched, indent=2, ensure_ascii=False))


# =========================================================
# STEP 5
# UPDATE URL #1
# =========================================================

print("\n=================================================")
print("STEP 5 - UPDATE URL #1")
print("=================================================\n")

updated = client.update_url(
    cmid=url1_cmid,
    name="TEST - URL 1 (updated to Moodle docs)",
    intro="<p>Updated intro: link to Moodle documentation.</p>",
    externalurl="https://docs.moodle.org",
    display=5,  # open in new window
    showdescription=0
)

print("URL #1 updated:")
print(updated)


# =========================================================
# STEP 6
# GET URL #1 AGAIN
# =========================================================

print("\n=================================================")
print("STEP 6 - GET URL #1 (after update)")
print("=================================================\n")

fetched_again = client.get_url(cmid=url1_cmid)
print("Fetched URL #1 after update:")
print(json.dumps(fetched_again, indent=2, ensure_ascii=False))


# =========================================================
# STEP 7
# CREATE URL #2
# =========================================================

print("\n=================================================")
print("STEP 7 - CREATE URL #2")
print("=================================================\n")

url2 = client.create_url(
    sectionnum=TARGET_SECTIONNUM,
    name="TEST - URL 2 (example.org)",
    intro="<p>Second URL for move/copy testing.</p>",
    externalurl="https://example.org",
    display=0
)

print("URL #2 created:")
print(url2)

url2_cmid = url2["cmid"]
print(f"URL #2 cmid: {url2_cmid}")


# =========================================================
# STEP 8
# MOVE URL #1 TO END OF SECTION
# =========================================================

print("\n=================================================")
print("STEP 8 - MOVE URL #1 TO END")
print("=================================================\n")

moved = client.move_module(
    cmid=url1_cmid,
    beforemod=0  # 0 = append at end of section
)

print("URL #1 moved:")
print(moved)


# =========================================================
# STEP 9
# COPY URL #1 BEFORE URL #2
# =========================================================

print("\n=================================================")
print("STEP 9 - COPY URL #1 BEFORE URL #2")
print("=================================================\n")

copied = client.copy_module(
    cmid=url1_cmid,
    beforemod=url2_cmid
)

print("URL #1 copied:")
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
