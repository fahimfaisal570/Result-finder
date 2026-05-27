import sqlite3

conn = sqlite3.connect("result_finder.db")

print("Searching database for 'shyamoli' case-insensitive...")
# Get list of all tables
tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]

found = False
for table in tables:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cursor]
    for col in cols:
        # Check if the column type is TEXT
        try:
            q = f"SELECT COUNT(*) FROM {table} WHERE CAST({col} AS TEXT) LIKE '%shyamoli%'"
            cnt = conn.execute(q).fetchone()[0]
            if cnt > 0:
                print(f"  Found in table '{table}', column '{col}': {cnt} row(s)")
                found = True
                # Print sample
                sample = conn.execute(f"SELECT * FROM {table} WHERE CAST({col} AS TEXT) LIKE '%shyamoli%' LIMIT 3").fetchall()
                print(f"    Samples: {sample}")
        except Exception as e:
            pass

if not found:
    print("No references to 'shyamoli' found in the database.")
