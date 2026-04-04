import sqlite3
import json

def get_schema():
    conn = sqlite3.connect('result_finder.db')
    schema = conn.execute("SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL").fetchall()
    for name, sql in schema:
        print(f"--- TABLE/INDEX/TRIGGER: {name} ---")
        print(sql)
        print("-" * 30)
    conn.close()

if __name__ == "__main__":
    get_schema()
