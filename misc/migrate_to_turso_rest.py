"""
migrate_to_turso_rest.py

The ULTIMATE migration script. 
Bypasses the 'libsql-client' library bugs by using Turso's REST API directly.
This version fixes the "ok" response type and logs errors to a file.
"""
import sqlite3
import sys
import os
import time
import requests
import json

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_DB = os.path.join(BASE_DIR, "result_finder.db")
ERROR_LOG = os.path.join(BASE_DIR, "misc", "migration_errors.log")

def migrate(url, token):
    if not os.path.exists(LOCAL_DB):
        print(f"Error: Local database not found at {LOCAL_DB}")
        return

    if url.startswith("libsql://"):
        url = url.replace("libsql://", "https://")
    
    print(f"Connecting to local database: {LOCAL_DB}")
    local_conn = sqlite3.connect(LOCAL_DB)
    
    print(f"Targeting Turso via REST Session: {url}")
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    })

    def remote_execute_batch(stmts):
        payload = {
            "requests": [{"type": "execute", "stmt": {"sql": s}} for s in stmts]
        }
        try:
            res = session.post(f"{url}/v2/pipeline", json=payload, timeout=60)
            if res.status_code != 200:
                return [(s, f"HTTP {res.status_code}: {res.text[:100]}") for s in stmts]
            
            results = res.json().get("results", [])
            errors = []
            for i, r in enumerate(results):
                if r.get("type") == "error":
                    errors.append((stmts[i], r.get("error", {}).get("message")))
            return errors
        except Exception as e:
            return [(s, str(e)) for s in stmts]

    TABLES_TO_DROP = ["subject_grades", "exam_results", "scan_log", "students", "profiles"]
    
    try:
        with open(ERROR_LOG, "w") as log_f:
            print("--- PHASE 1: CLEANING REMOTE DB & DISABLING FKs ---")
            remote_execute_batch(["PRAGMA foreign_keys = OFF;"])
            
            drop_stmts = [f"DROP TABLE IF EXISTS {t}" for t in TABLES_TO_DROP]
            remote_execute_batch(drop_stmts)
            print("Existing tables dropped and FKs disabled.")

            print("\n--- PHASE 2: GATHERING & CLEANING LOCAL DATA ---")
            sql_statements = []
            for line in local_conn.iterdump():
                if line.startswith(("BEGIN TRANSACTION", "COMMIT")): continue
                cleaned = line.replace('"main".', '').replace('main.', '')
                if not cleaned.strip() or cleaned.startswith('--'): continue
                
                if "CREATE TABLE " in cleaned: 
                    cleaned = cleaned.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ")
                
                sql_statements.append(cleaned)
            
            print(f"Collected {len(sql_statements)} SQL statements.")

            print("\n--- PHASE 3: UPLOADING TO TURSO (REST API) ---")
            success_count = 0
            error_count = 0
            start_time = time.time()
            
            batch_size = 50 
            for i in range(0, len(sql_statements), batch_size):
                batch_slice = sql_statements[i:i+batch_size]
                errors = remote_execute_batch(batch_slice)
                
                if errors:
                    for stmt, err in errors:
                        if "already exists" in err:
                            success_count += 1
                            continue
                        log_f.write(f"ERROR: {err}\nSQL: {stmt}\n\n")
                        error_count += 1
                    success_count += (len(batch_slice) - len(errors))
                else:
                    success_count += len(batch_slice)
                
                if (i + len(batch_slice)) % 500 == 0 or i + len(batch_slice) >= len(sql_statements):
                    progress = min(100, (i + len(batch_slice)) / len(sql_statements) * 100)
                    print(f"Progress: {progress:.1f}% ({success_count} success, {error_count} errors)")

            print("Re-enabling foreign key checks...")
            remote_execute_batch(["PRAGMA foreign_keys = ON;"])

            print(f"\nMigration completed in {time.time() - start_time:.1f} seconds.")
            print(f"Total: {success_count} success, {error_count} errors.")
            if error_count > 0:
                print(f"⚠️ Errors logged to {ERROR_LOG}")
            
            print("\n--- PHASE 4: VERIFYING TABLE COUNTS ---")
            v_list = session.post(f"{url}/v2/pipeline", json={
                "requests": [{"type": "execute", "stmt": {"sql": "SELECT name FROM sqlite_master WHERE type='table'"}}]
            }).json()
            # New check: results[0]["type"] == "ok"
            found_tables = []
            if v_list["results"][0]["type"] == "ok":
                found_tables = [r[0]["value"] for r in v_list["results"][0]["response"]["result"]["rows"]]
            print(f"Remote tables: {found_tables}")

            count_queries = [f"SELECT COUNT(*) FROM {t}" for t in TABLES_TO_DROP if t in found_tables]
            if count_queries:
                v_res = session.post(f"{url}/v2/pipeline", json={
                    "requests": [{"type": "execute", "stmt": {"sql": q}} for q in count_queries]
                }).json()
                
                for i, r in enumerate(v_res.get("results", [])):
                    t_name = [t for t in TABLES_TO_DROP if t in found_tables][i]
                    if r.get("type") == "ok": # FIXED: "ok" instead of "success"
                        count = r["response"]["result"]["rows"][0][0]["value"]
                        print(f"✅ Table '{t_name}': {count} rows migrated.")
                    else:
                        print(f"❌ Table '{t_name}': ERROR READING COUNT")

    except Exception as e:
        print(f"❌ Critical failure: {e}")
    finally:
        local_conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python misc/migrate_to_turso_rest.py <URL> <TOKEN>")
    else:
        migrate(sys.argv[1], sys.argv[2])
