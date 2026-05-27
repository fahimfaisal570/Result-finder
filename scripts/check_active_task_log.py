import os
import glob

# Search in the exact tasks directory
tasks_dir = r"C:\Users\Ucc\.gemini\antigravity\brain\0a4b941b-a029-47d3-bce3-729459e1cc0c\.system_generated\tasks"
print(f"Searching in: {tasks_dir}")

matches = glob.glob(os.path.join(tasks_dir, "task-*.log"))
if not matches:
    print("No log files found!")
else:
    # Sort matches by modification time descending
    matches.sort(key=os.path.getmtime, reverse=True)
    latest_match = matches[0]
    print(f"Latest Log File Match: {latest_match}")
    print("  File size:", os.path.getsize(latest_match))
    try:
        with open(latest_match, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        print("  Total lines:", len(lines))
        print("  First 10 lines:")
        for line in lines[:10]:
            print("   ", line.strip())
        print("  Last 20 lines:")
        for line in lines[-20:]:
            print("   ", line.strip())
    except Exception as e:
        print(f"  Error reading file: {e}")

