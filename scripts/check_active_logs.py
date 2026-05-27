import os

tasks_dir = r"C:\Users\Ucc\.gemini\antigravity\brain\0a4b941b-a029-47d3-bce3-729459e1cc0c\.system_generated\tasks"
if os.path.exists(tasks_dir):
    print("Files in tasks dir:")
    for f in sorted(os.listdir(tasks_dir)):
        p = os.path.join(tasks_dir, f)
        print(f"  {f} | Size: {os.path.getsize(p)} bytes")
else:
    print("Tasks dir does not exist!")
