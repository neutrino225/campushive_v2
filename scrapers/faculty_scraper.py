import os
import json
import requests
import time
import random
from tqdm import tqdm
import argparse

# Output directory in project root
DATA_PATH = os.path.join("data", "faculty")
os.makedirs(DATA_PATH, exist_ok=True)

# Constants
DEPARTMENTS = {
    "CS": 301,
    "EE": 302,
    "MS": 303,
    "SH": 313
}

BASE_URL = "http://isb.nu.edu.pk/Faculty"
FACULTY_DETAIL_URL = "https://isb.nu.edu.pk/Faculty/Details1"

HEADERS_JSON = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
}

HEADERS_FORM = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded",
}


def fetch_faculty(department_id):
    """Fetch faculty list for a given department."""
    url = f"{BASE_URL}/GetAllEmp?id={department_id}"
    response = requests.post(url, headers=HEADERS_JSON)
    return response.json() if response.status_code == 200 else None

def fetch_faculty_profile(employee_id):
    """Fetch detailed faculty profile using Employee ID."""
    data = {"id": employee_id}
    response = requests.post(FACULTY_DETAIL_URL, headers=HEADERS_FORM, data=data)
    return response.json() if response.status_code == 200 else None


def scrape_faculty_data():
    """Main function to scrape and save faculty data."""
    for dept, dept_id in DEPARTMENTS.items():
        print(f"\nFetching faculty data for {dept}...")

        faculty_data = fetch_faculty(dept_id)
        if not faculty_data:
            print(f"Failed to fetch {dept} faculty data")
            continue

        for idx, faculty in enumerate(tqdm(faculty_data, desc=f"Fetching {dept} profiles")):
            emp_id = faculty.get("Emp_ID")
            if not emp_id:
                print(f"Skipping faculty with missing Emp_ID in {dept}")
                continue

            profile_data = fetch_faculty_profile(emp_id)
            if profile_data:
                faculty_data[idx]["listEExpr"] = profile_data.get("listEExpr", [])
                faculty_data[idx]["listEEdu"] = profile_data.get("listEEdu", [])
                faculty_data[idx]["listPublication"] = profile_data.get("listPublication", [])
                faculty_data[idx]["Department"] = dept
            else:
                print(f"Failed to fetch profile for {emp_id}")
            time.sleep(random.uniform(0.5, 1.5))  # Avoid hitting rate limits

        # Save data
        file_path = os.path.join(DATA_PATH, f"{dept}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(faculty_data, f, indent=4)

        print(f"Saved {dept} faculty data to {file_path}")

    print(f"\nFaculty data fetched successfully! Saved under {DATA_PATH}")
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape faculty data from ISB NU website.")
    args = parser.parse_args()
    scrape_faculty_data()