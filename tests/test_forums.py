import json
from dotenv import load_dotenv
import os

from moodle_client import MoodleClient


load_dotenv()

BASE_URL = os.getenv("BASE_URL")
WSTOKEN = os.getenv("WSTOKEN")
COURSE_ID = int(os.getenv("COURSE_ID"))

client = MoodleClient(
    courseid=COURSE_ID,
    base_url=BASE_URL,
    token=WSTOKEN,
)

print("\n=================================================")
print("STEP 1 - GET COURSE STRUCTURE")
print("=================================================\n")

structure = client.dump(filename="course-structure.json")
print(f"Total sections: {len(structure)}")

print("\n=================================================")
print("STEP 2 - CREATE TEST SECTION FOR FORUMS")
print("=================================================\n")

test_section = client.create_section(
    name="TEST - Forums",
    summary="<p>Section for integration testing of forums.</p>",
    position=len(structure) + 1,
)

print(f"Test section created: {test_section}")
TARGET_SECTIONNUM = test_section["sectionnum"]
print(f"Target sectionnum: {TARGET_SECTIONNUM}")

print("\n=================================================")
print("STEP 3 - CREATE FORUM #1")
print("=================================================\n")

forum1 = client.create_forum(
    sectionnum=TARGET_SECTIONNUM,
    name="TEST - Forum 1 (general)",
    intro="<p>Peer discussion forum for integration testing.</p>",
    type="general",
    showdescription=1,
)

print("Forum #1 created:")
print(forum1)

forum1_cmid = forum1["cmid"]
print(f"Forum #1 cmid: {forum1_cmid}")

print("\n=================================================")
print("STEP 4 - CREATE FORUM #2 (eachuser)")
print("=================================================\n")

forum2 = client.create_forum(
    sectionnum=TARGET_SECTIONNUM,
    name="TEST - Forum 2 (eachuser)",
    intro="<p>Each person posts one discussion.</p>",
    type="eachuser",
)

print("Forum #2 created:")
print(forum2)

forum2_cmid = forum2["cmid"]
print(f"Forum #2 cmid: {forum2_cmid}")

print("\n=================================================")
print("STEP 5 - GET FORUM #1")
print("=================================================\n")

fetched = client.get_forum(cmid=forum1_cmid)
print("Forum #1 fetched:")
print(json.dumps(fetched, indent=2, ensure_ascii=False))

print("\n=================================================")
print("STEP 6 - UPDATE FORUM #1")
print("=================================================\n")

updated = client.update_forum(
    cmid=forum1_cmid,
    name="TEST - Forum 1 (updated)",
    intro="<p>Updated peer discussion forum.</p>",
    type="general",
    showdescription=0,
)

print("Forum #1 updated:")
print(updated)

print("\n=================================================")
print("STEP 7 - GET FORUM #1 (after update)")
print("=================================================\n")

fetched_again = client.get_forum(cmid=forum1_cmid)
print("Forum #1 fetched after update:")
print(json.dumps(fetched_again, indent=2, ensure_ascii=False))

print("\n=================================================")
print("STEP 8 - VERIFY IN COURSE STRUCTURE")
print("=================================================\n")

for section in client.course:
    if section["section"] == TARGET_SECTIONNUM:
        forums = [m for m in section.get("modules", []) if m.get("modname") == "forum"]
        print(json.dumps(forums, indent=2, ensure_ascii=False))
        break

print("\nDone. Remove TEST - Forums section manually in Moodle when finished.")
