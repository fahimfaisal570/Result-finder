import sqlite3

conn = sqlite3.connect("result_finder.db")
cursor = conn.execute("SELECT key, substr(value, 1, 100) FROM meta_cache")
for row in cursor:
    print(f"Key: {row[0]} | Value: {row[1]}")
