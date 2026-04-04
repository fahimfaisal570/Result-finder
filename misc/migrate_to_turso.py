"""
migrate_to_turso.py

Utility to seed your Turso Cloud database with your local SQLite data.
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

    # Use the 'iterdump' approach for standard SQLite -> SQLite migration
    print("Fetching local data (iterdump)...")
    
    # Increase recursion depth for large schemas if needed
    sys.setrecursionlimit(2000)
    
    # We'll execute the dump script on the remote connection
    # Note: Turso/libSQL handles standard SQL dumps perfectly.
    try:
        print("Migrating schema and data to Turso. This may take a few moments...")
        for line in local_conn.iterdump():
            # Skip transaction markers as libSQL handles its own batching
            if line.startswith(("BEGIN TRANSACTION", "COMMIT")):
                continue
            remote_conn.execute(line)
        
        print("✅ Migration Successful!")
        print("You can now add your TURSO_DATABASE_URL and TURSO_AUTH_TOKEN to Streamlit Secrets.")
        
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
