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

structure = client.dump(
    filename="course-structure.json"
)

print("Course structure saved to:")
print("course-structure.json")


# =========================================================
# STEP 2
# VALIDATE POSITION
# =========================================================

print("\n=================================================")
print("STEP 2 - VALIDATE POSITION")
print("=================================================\n")

sections = structure

total_sections = len(sections)

print(f"Total sections found: {total_sections}")

create_position = 4

# =========================================================
# STEP 3
# CREATE SECTION
# =========================================================

print("\n=================================================")
print("STEP 3 - CREATE SECTION")
print("=================================================\n")

created_section = client.create_section(
    name="created from code",
    summary="<p>Created via API</p>",
    position=create_position
)

print("Section created successfully")
print(created_section)

new_sectionnum = created_section["sectionnum"]

print(f"New section number: {new_sectionnum}")


# =========================================================
# STEP 4
# MOVE SECTION
# =========================================================

print("\n=================================================")
print("STEP 4 - MOVE SECTION")
print("=================================================\n")

move_position = 6

moved = client.move_section(
    sectionnum=new_sectionnum,
    position=move_position
)

new_sectionnum = moved["sectionnum"]
print("Section moved successfully")
print(moved)


# =========================================================
# STEP 5
# UPDATE SECTION
# =========================================================

print("\n=================================================")
print("STEP 5 - UPDATE SECTION")
print("=================================================\n")

try:

    updated = client.update_section(
        sectionnum=new_sectionnum,
        name="created from code updated",
        summary="<p>Updated via API</p>"
    )

    print("Section updated successfully")
    print(updated)

except Exception as e:

    print("\nWARNING:")
    print("Update section endpoint may not exist.")
    print(str(e))


# =========================================================
# STEP 6
# SAVE UPDATED STRUCTURE
# =========================================================

print("\n=================================================")
print("STEP 6 - SAVE UPDATED STRUCTURE")
print("=================================================\n")

updated_structure = client.dump(
    filename="course-structure.json"
)

print("Updated structure saved")


# =========================================================
# DONE
# =========================================================

print("\n=================================================")
print("DONE")
print("=================================================\n")