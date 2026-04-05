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
        
    print(f"Connecting to Turso (HTTPS Mode): {url}")
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
        create_statements = []
        insert_statements = []
        index_statements = []
        
        for line in local_conn.iterdump():
            if line.startswith(("BEGIN TRANSACTION", "COMMIT")): continue
            
            # Clean: Remove "main." prefix and double-quoted "main". prefix
            cleaned = line.replace('"main".', '').replace('main.', '')
            if not cleaned.strip() or cleaned.startswith('--'): continue
            
            # Make CREATE idempotent
            if "CREATE TABLE " in cleaned: 
                cleaned = cleaned.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ")
                create_statements.append(cleaned)
            elif "INSERT INTO " in cleaned:
                insert_statements.append(cleaned)
            elif "CREATE INDEX " in cleaned or "CREATE UNIQUE INDEX " in cleaned:
                cleaned = cleaned.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ")
                cleaned = cleaned.replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX IF NOT EXISTS ")
                index_statements.append(cleaned)
            else:
                # Other statements (like triggers etc if any)
                create_statements.append(cleaned)
        
        print(f"Collected: {len(create_statements)} Schema, {len(insert_statements)} Data, {len(index_statements)} Index statements.")

        print("\n--- PHASE 3: UPLOADING SCHEMA ---")
        # Run schema statements one by one or in small batches
        client.batch(create_statements)
        print("Schema created successfully.")

        print("\n--- PHASE 4: UPLOADING DATA (Batch Mode) ---")
        success_count = 0
        error_count = 0
        start_time = time.time()
        
        # Log errors to a file
        log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migration_errors.log")
        with open(log_file, "w") as log:
            log.write(f"Migration started at {time.ctime()}\n")

        batch_size = 10 
        for i in range(0, len(insert_statements), batch_size):
            batch_slice = insert_statements[i:i+batch_size]
            try:
                client.batch(batch_slice)
                success_count += len(batch_slice)
            except Exception as e:
                # If a batch fails, retry one by one for detailed logging
                for line in batch_slice:
                    try:
                        client.execute(line)
                        success_count += 1
                    except Exception as le:
                        error_count += 1
                        with open(log_file, "a") as log:
                            # Log the full exception type and message
                            log.write(f"\n[{type(le).__name__}] ERROR: {str(le)}\n")
                            log.write(f"SQL: {line[:1000]}\n")
            
            if (i + len(batch_slice)) % 500 == 0 or i + len(batch_slice) >= len(insert_statements):
                progress = min(100, (i + len(batch_slice)) / len(insert_statements) * 100)
                print(f"Progress: {progress:.1f}% ({success_count} success, {error_count} errors)")

        print("\n--- PHASE 5: UPLOADING INDEXES ---")
        if index_statements:
            client.batch(index_statements)
            print("Indexes created successfully.")

        duration = time.time() - start_time
        print(f"\n--- PHASE 6: FINAL INTEGRITY CHECK ---")
        remote_tables_res = client.execute("SELECT name FROM sqlite_master WHERE type='table'")
        remote_tables = [r[0] for r in remote_tables_res.rows]
        
        for table in TABLES_TO_DROP:
            if table in remote_tables:
                count_res = client.execute(f"SELECT COUNT(*) FROM {table}")
                count = count_res.rows[0][0]
                print(f"✅ Table '{table}': {count} rows migrated.")
            else:
                print(f"❌ Table '{table}': MISSING!")

        print(f"\nMigration completed in {duration:.1f} seconds.")
        print(f"Total: {success_count} success, {error_count} errors.")
        if error_count > 0:
            print(f"See {log_file} for details.")
        
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
