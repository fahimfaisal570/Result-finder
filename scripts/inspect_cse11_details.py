import sqlite3

conn = sqlite3.connect("result_finder.db")
cursor = conn.execute("PRAGMA table_info(students)")
print("Columns in 'students' table:")
for col in cursor:
    print(f"  {col[1]} ({col[2]})")

print("\nColumns in 'results' table (if exists):")
try:
    cursor_res = conn.execute("PRAGMA table_info(results)")
    for col in cursor_res:
        print(f"  {col[1]} ({col[2]})")
except Exception as e:
    print(f"Error checking results table: {e}")
    
print("\nColumns in other tables:")
cursor_tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
for table in cursor_tables:
    table_name = table[0]
    print(f"\nTable: {table_name}")
    try:
        col_cursor = conn.execute(f"PRAGMA table_info({table_name})")
        for col in col_cursor:
            print(f"  {col[1]} ({col[2]})")
    except Exception as e:
        print(f"Error checking table {table_name}: {e}")
