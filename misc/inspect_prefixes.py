import sqlite3
import re

LOCAL_DB = "result_finder.db"

def inspect_schema():
    conn = sqlite3.connect(LOCAL_DB)
    print("--- FULL SCHEMA DUMP ---")
    for line in conn.iterdump():
        if "main." in line:
            print(f"FOUND PREFIX: {line}")
        
        # Check for Foreign Keys explicitly
        if "REFERENCES" in line.upper():
            print(f"FK LINE: {line}")
            
    conn.close()

if __name__ == "__main__":
    inspect_schema()
