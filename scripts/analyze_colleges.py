import sqlite3

conn = sqlite3.connect("result_finder.db")

profiles = ["cse 11", "eee 11", "civil 11"]

for p in profiles:
    print(f"\n=== PROFILE: {p} ===")
    # Join students and exam_results to get the college names
    cursor = conn.execute("""
        SELECT s.reg_no, s.name, r.exam_name, r.raw_json 
        FROM students s
        LEFT JOIN exam_results r ON s.profile_name = r.profile_name AND s.reg_no = r.reg_no
        WHERE s.profile_name = ? AND s.reg_no >= 2023000000
    """, (p,))
    
    colleges = {}
    rows = cursor.fetchall()
    for row in rows:
        reg_no, student_name, exam_name, raw_json = row
        college = "Unknown"
        if raw_json:
            try:
                data = json.loads(raw_json)
                # Let's see what keys are in raw_json
                college = data.get("College", data.get("college_name", "Unknown"))
            except Exception as e:
                pass
        colleges[college] = colleges.get(college, 0) + 1
    
    print("Colleges distribution:")
    for col, count in colleges.items():
        print(f"  {col}: {count}")
