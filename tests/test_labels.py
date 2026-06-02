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
print("STEP 2 - CREATE TEST SECTION FOR LABELS")
print("=================================================\n")

test_section = client.create_section(
    name="TEST - Labels",
    summary="<p>Section for integration testing of labels.</p>",
    position=len(structure) + 1
)

print(f"Test section created: {test_section}")
TARGET_SECTIONNUM = test_section["sectionnum"]
print(f"Target sectionnum: {TARGET_SECTIONNUM}")


# =========================================================
# STEP 3
# CREATE LABEL #1
# =========================================================

print("\n=================================================")
print("STEP 3 - CREATE LABEL #1")
print("=================================================\n")

label1 = client.create_label(
    sectionnum=TARGET_SECTIONNUM,
    labelcontent="<p><strong>TEST</strong> label #1 content.</p>",
    name="TEST - Label 1"
)

print("Label #1 created:")
print(label1)

label1_cmid = label1["cmid"]
print(f"Label #1 cmid: {label1_cmid}")


# =========================================================
# STEP 4
# GET LABEL #1
# =========================================================

print("\n=================================================")
print("STEP 4 - GET LABEL #1")
print("=================================================\n")

fetched = client.get_label(cmid=label1_cmid)
print("Fetched label #1:")
print(json.dumps(fetched, indent=2, ensure_ascii=False))


# =========================================================
# STEP 5
# UPDATE LABEL #1
# =========================================================

print("\n=================================================")
print("STEP 5 - UPDATE LABEL #1")
print("=================================================\n")

updated = client.update_label(
    cmid=label1_cmid,
    name="TEST - Label 1 (updated)",
    labelcontent="<p>Updated content via API.</p>"
)

print("Label #1 updated:")
print(updated)


# =========================================================
# STEP 6
# GET LABEL #1 AGAIN
# =========================================================

print("\n=================================================")
print("STEP 6 - GET LABEL #1 (after update)")
print("=================================================\n")

fetched_again = client.get_label(cmid=label1_cmid)
print("Fetched label #1 after update:")
print(json.dumps(fetched_again, indent=2, ensure_ascii=False))


# =========================================================
# STEP 7
# CREATE LABEL #2
# =========================================================

print("\n=================================================")
print("STEP 7 - CREATE LABEL #2")
print("=================================================\n")

label2 = client.create_label(
    sectionnum=TARGET_SECTIONNUM,
    labelcontent="<p>TEST label #2 content.</p>",
    name="TEST - Label 2"
)

print("Label #2 created:")
print(label2)

label2_cmid = label2["cmid"]
print(f"Label #2 cmid: {label2_cmid}")


# =========================================================
# STEP 8
# MOVE LABEL #1 TO END OF SECTION
# =========================================================

print("\n=================================================")
print("STEP 8 - MOVE LABEL #1 TO END")
print("=================================================\n")

moved = client.move_module(
    cmid=label1_cmid,
    beforemod=0  # 0 = append at end of section
)

print("Label #1 moved:")
print(moved)


# =========================================================
# STEP 9
# COPY LABEL #1 BEFORE LABEL #2
# =========================================================

print("\n=================================================")
print("STEP 9 - COPY LABEL #1 BEFORE LABEL #2")
print("=================================================\n")

copied = client.copy_module(
    cmid=label1_cmid,
    beforemod=label2_cmid
)

print("Label #1 copied:")
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
