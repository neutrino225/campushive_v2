import json
import os

def count_bahria():
    data_dir = 'data/faculty'
    count = 0
    files = [f for f in os.listdir(data_dir) if f.endswith('.json')]
    print(f"Scanning files: {files}")
    for filename in files:
        filepath = os.path.join(data_dir, filename)
        with open(filepath, 'r') as f:
            try:
                data = json.load(f)
                for faculty in data:
                    # Convert whole object to string to search everywhere
                    faculty_str = json.dumps(faculty).lower()
                    if "bahria university" in faculty_str:
                        count += 1
                        print(f"Found in {filename}: {faculty.get('Name')}")
            except Exception as e:
                print(f"Error reading {filename}: {e}")
    print(f"Total count: {count}")

if __name__ == "__main__":
    count_bahria()
