"""
migrate_to_turso.py

Advanced, deployer-grade utility to seed your Turso Cloud database with your local SQLite data.
Usage: 
  python misc/migrate_to_turso.py <TURSO_URL> <TURSO_TOKEN>
"""
import sqlite3
import sys
import os

try:
    import libsql
except ImportError:
    print("Error: 'libsql' package not found. Run 'pip install libsql' first.")
    sys.exit(1)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_DB = os.path.join(BASE_DIR, "result_finder.db")

def migrate(url, token):
    if not os.path.exists(LOCAL_DB):
        print(f"Error: Local database not found at {LOCAL_DB}")
        return

    print(f"Connecting to local database: {LOCAL_DB}")
    local_conn = sqlite3.connect(LOCAL_DB)
    
    print(f"Connecting to Turso: {url}")
    try:
        remote_conn = libsql.connect(url, auth_token=token)
    except Exception as e:
        print(f"Failed to connect to Turso: {e}")
        return

    # Increase recursion depth for large schemas if needed
    sys.setrecursionlimit(2000)
    
    # Tables to clean up for a fresh start (Order matters for Foreign Keys)
    TABLES_TO_DROP = ["subject_grades", "exam_results", "scan_log", "students", "profiles"]
    
    try:
        print("Gathering and cleaning local schema/data...")
        
        # 1. Start with a clean slate
        sql_batch = []
        for table in TABLES_TO_DROP:
            sql_batch.append(f"DROP TABLE IF EXISTS {table};")
            
        # 2. Collect and clean all iterdump lines
        for line in local_conn.iterdump():
            # Skip transaction markers
            if line.startswith(("BEGIN TRANSACTION", "COMMIT")):
                continue
            
            # Clean the line: Remove "main." prefix
            cleaned_line = line.replace('"main".', '').replace('main.', '')
            
            # Make CREATE statements idempotent
            if cleaned_line.strip().startswith("CREATE TABLE "):
                cleaned_line = cleaned_line.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1)
            elif cleaned_line.strip().startswith("CREATE INDEX "):
                cleaned_line = cleaned_line.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ", 1)
            elif cleaned_line.strip().startswith("CREATE UNIQUE INDEX "):
                cleaned_line = cleaned_line.replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX IF NOT EXISTS ", 1)
            
            # Skip empty lines or comments
            if not cleaned_line.strip() or cleaned_line.startswith('--'):
                continue
            
            sql_batch.append(cleaned_line)
        
        # 3. Join and execute as a SINGLE script
        print(f"Executing batch migration ({len(sql_batch)} statements)...")
        full_sql = "\n".join(sql_batch)
        
        # Using executescript for high performance and atomicity
        remote_conn.executescript(full_sql)
        
        print("✅ Migration Successful!")
        print("Your cloud database is now in sync with your local data.")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
    finally:
        local_conn.close()
        remote_conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python misc/migrate_to_turso.py <URL> <TOKEN>")
    else:
        migrate(sys.argv[1], sys.argv[2])
