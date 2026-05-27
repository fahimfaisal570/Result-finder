import sqlite3
import os

dbs = ["result_finder.db", "database.db", "result_data.db"]

for db_name in dbs:
    if not os.path.exists(db_name):
        print(f"\n{db_name} does not exist.")
        continue
        
    print(f"\n=== Searching {db_name} for 'shyamoli' ===")
    conn = sqlite3.connect(db_name)
    try:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    except Exception as e:
        print(f"  Error getting tables: {e}")
        continue
        
    found = False
    for table in tables:
        try:
            cursor = conn.execute(f"PRAGMA table_info({table})")
            cols = [row[1] for row in cursor]
        except Exception as e:
            continue
            
        for col in cols:
            try:
                q = f"SELECT COUNT(*) FROM {table} WHERE CAST({col} AS TEXT) LIKE '%shyamoli%'"
                cnt = conn.execute(q).fetchone()[0]
                if cnt > 0:
                    print(f"  Found in table '{table}', column '{col}': {cnt} row(s)")
                    found = True
                    sample = conn.execute(f"SELECT * FROM {table} WHERE CAST({col} AS TEXT) LIKE '%shyamoli%' LIMIT 2").fetchall()
                    print(f"    Sample: {sample}")
            except Exception as e:
                pass
    if not found:
        print("  No references found.")
