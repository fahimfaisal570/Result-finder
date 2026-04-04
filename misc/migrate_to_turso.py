"""
migrate_to_turso.py

Hardened, professional-grade utility to seed your Turso Cloud database.
Uses the official 'libsql-client' for reliable remote data transfer.
"""
import sqlite3
import sys
import os
import time

try:
    import libsql_client
except ImportError:
    print("Error: 'libsql-client' package not found. Run 'pip install libsql-client' first.")
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
    
    # Force HTTPS for stability
    if url.startswith("libsql://"):
        url = url.replace("libsql://", "https://")
        
    print(f"Connecting to Turso: {url}")
    try:
        client = libsql_client.create_client_sync(url, auth_token=token)
    except Exception as e:
        print(f"Failed to connect to Turso: {e}")
        return

    # Tables to clean up
    TABLES_TO_DROP = ["subject_grades", "exam_results", "scan_log", "students", "profiles"]
    
    try:
        print("--- PHASE 1: PREPARING REMOTE DB ---")
        # In libsql-client, we just run the DROP commands
        drop_stmts = [f"DROP TABLE IF EXISTS {t}" for t in TABLES_TO_DROP]
        client.batch(drop_stmts)
        print("Existing tables dropped successfully.")
        
        print("\n--- PHASE 2: GATHERING & CLEANING LOCAL DATA ---")
        sql_statements = []
        for line in local_conn.iterdump():
            if line.startswith(("BEGIN TRANSACTION", "COMMIT")): continue
            
            # Clean: Remove "main." prefix
            cleaned = line.replace('"main".', '').replace('main.', '')
            if not cleaned.strip() or cleaned.startswith('--'): continue
            
            # Make CREATE idempotent
            if "CREATE TABLE " in cleaned: cleaned = cleaned.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ")
            if "CREATE INDEX " in cleaned: cleaned = cleaned.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ")
            if "CREATE UNIQUE INDEX " in cleaned: cleaned = cleaned.replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX IF NOT EXISTS ")
            
            sql_statements.append(cleaned)
        
        print(f"Collected {len(sql_statements)} SQL statements.")

        print("\n--- PHASE 3: UPLOADING TO TURSO (Batch Mode) ---")
        success_count = 0
        error_count = 0
        start_time = time.time()
        
        # libsql-client .batch() is highly performant
        batch_size = 50 
        for i in range(0, len(sql_statements), batch_size):
            batch_slice = sql_statements[i:i+batch_size]
            try:
                client.batch(batch_slice)
                success_count += len(batch_slice)
            except Exception as e:
                # If a batch fails, retry one by one for detailed logging
                print(f"⚠️ Batch around line {i} failed. Retrying one by one...")
                for line in batch_slice:
                    try:
                        client.execute(line)
                        success_count += 1
                    except Exception as le:
                        # Log error but continue unless it's critical
                        print(f"❌ SQL Execution Error: {le}")
                        print(f"   Statement: {line[:100]}...")
                        error_count += 1
            
            if (i + batch_slice.__len__()) % 500 == 0 or i + batch_slice.__len__() >= len(sql_statements):
                progress = min(100, (i + len(batch_slice)) / len(sql_statements) * 100)
                print(f"Progress: {progress:.1f}% ({success_count} success, {error_count} errors)")

        duration = time.time() - start_time
        print(f"\n--- PHASE 4: FINAL INTEGRITY CHECK ---")
        remote_tables_res = client.execute("SELECT name FROM sqlite_master WHERE type='table'")
        remote_tables = [r[0] for r in remote_tables_res.rows]
        print(f"Remote tables found: {remote_tables}")
        
        for table in TABLES_TO_DROP:
            if table in remote_tables:
                count_res = client.execute(f"SELECT COUNT(*) FROM {table}")
                count = count_res.rows[0][0]
                print(f"✅ Table '{table}': {count} rows migrated.")
            else:
                print(f"❌ Table '{table}': MISSING!")

        print(f"\nMigration completed in {duration:.1f} seconds.")
        print(f"Total: {success_count} success, {error_count} errors.")
        
    except Exception as e:
        print(f"❌ Critical failure: {e}")
    finally:
        local_conn.close()
        client.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python misc/migrate_to_turso.py <URL> <TOKEN>")
    else:
        migrate(sys.argv[1], sys.argv[2])
