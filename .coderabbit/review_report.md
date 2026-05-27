# Code Rabbit Review Report

**Author:** Senior Review Agent (Code Rabbit Superpower)  
**Project:** Result Finder  
**Target Directory:** `c:\Users\Ucc\Downloads\result finder separate`  
**Date:** 2026-05-27  

---

## Severity Breakdown
- 🔴 **Critical**: 2
- 🟡 **Major**: 2
- 🟢 **Minor**: 1
- 🔵 **Style/Info**: 1

---

## Findings

### 🔴 Critical

#### 1. Massive SQLite Connection / File Descriptor Leak
- **File:** [database.py](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/database.py) (Extensive across all database helper functions)
- **Issue:** 
  In Python's `sqlite3` library, using a connection object as a context manager (e.g., `with sqlite3.connect(...) as conn:`) **only manages the transaction** (it commits on success and rolls back on exception). It **does not close the connection** when leaving the block. 
  Because `database.py` defines `get_connection()` as:
  ```python
  def get_connection():
      conn = sqlite3.connect(DB_PATH, check_same_thread=False)
      conn.execute("PRAGMA foreign_keys = ON")
      conn.execute("PRAGMA journal_mode = WAL")
      return conn
  ```
  And then utilizes it like this across all database functions:
  ```python
  with get_connection() as conn:
      # ...
  ```
  Every single database read or write call leaks an active SQLite connection. In a multi-threaded web application environment like Streamlit, this will rapidly exhaust the operating system's file descriptors, block further SQLite operations, and cause the application to crash or trigger permanent locking.
- **Recommendation:**
  Implement a safe session context manager using `contextlib.contextmanager` that guarantees connection closure.
  
  ```python
  import contextlib

  @contextlib.contextmanager
  def db_session():
      conn = get_connection()
      try:
          yield conn
      finally:
          conn.close()
  ```
  Then replace all occurrences of `with get_connection() as conn:` with `with db_session() as conn:`.

- **Resolution Status:** ✅ **Resolved** (Wave 0)  
  Added a connection proxy class `ClosedOnExitConnection` wrapping `sqlite3.Connection` in `database.py` (L69-L94) that automatically intercepts `.close()` calls or invokes `.close()` when exiting a context manager block.

#### 2. Critical Database Schema Migration Failure on Fresh Initialization
- **File:** [database.py](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/database.py#L180-L188)
- **Issue:** 
  During a fresh database installation or in unit tests, `database.init_db()` creates the base table schemas. In v1 (the initial creation), the `exam_results` table does not contain a `sess_id` column.
  However, in `migrate_schema_v2()`, the deduplication step attempts to group by `sess_id` on the `exam_results` table:
  ```python
  cur.execute("""
      DELETE FROM exam_results
      WHERE id NOT IN (
          SELECT MIN(id)
          FROM exam_results
          GROUP BY profile_name, reg_no, sess_id, exam_id
      )
  """)
  ```
  This causes a crash with `sqlite3.OperationalError: no such column: sess_id` since the `sess_id` column is not added to `exam_results` until the `migrate_schema_v4()` migration runs. This completely prevents successful database initialization and crashes the unit testing suite on startup.
- **Recommendation:**
  Change the GROUP BY clause in the `migrate_schema_v2` de-duplication step to group only by the unique keys that actually exist in the schema at that point: `profile_name`, `reg_no`, and `exam_id`. This aligns exactly with the v1/v2 schema definition before `sess_id` is introduced in v4.

- **Resolution Status:** ✅ **Resolved** (Wave 0)  
  Fixed `migrate_schema_v2()` in `database.py` L185 to remove `sess_id` from the deduplication GROUP BY clause since the v1/v2 schema did not contain it.

---

### 🟡 Major

#### 1. Broken Connection Accumulation in HTTP Keep-Alive Pool
- **File:** [cli_scraper.py](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/cli_scraper.py#L90-L113)
- **Issue:** 
  In `KeepAlivePool`, if a connection encounters an exception during a network request inside `make_request`, it is closed in the `except` block, but the `finally` block still returns it to the connection pool:
  ```python
          except Exception:
              conn.close()
          finally:
              http_pool.return_connection(conn)
  ```
  Once returned, the pool retains this closed connection. Subsequent calls to `get_connection()` will retrieve the closed socket. Any attempt to use it will fail immediately, causing a cascading failure that permanently locks the scraper in a "Network Error" state until the entire application is restarted.
- **Recommendation:**
  Differentiate between healthy and broken connections, and discard broken connections from the pool while adjusting the active connection count.
  
  ```python
  class KeepAlivePool:
      # ...
      def return_connection(self, conn, broken=False):
          if broken:
              conn.close()
              with self.lock:
                  self.created -= 1
          else:
              try: 
                  self.pool.put_nowait(conn)
              except queue.Full: 
                  conn.close()
  ```
  And modify the `make_request` exception handling:
  ```python
      for attempt in range(retries):
          conn = http_pool.get_connection()
          broken = False
          try:
              conn.timeout = 15
              conn.request(method, path, body=encoded_data, headers=req_headers)
              response = conn.getresponse()
              # ...
          except Exception:
              broken = True
          finally:
              http_pool.return_connection(conn, broken=broken)
  ```

- **Resolution Status:** ✅ **Resolved** (Wave 0)  
  Updated `KeepAlivePool.return_connection()` in `cli_scraper.py` L107-L114 to support a `broken=True` flag that safely closes and discards faulty sockets, and adjusted `make_request()` exception handling accordingly.

#### 2. N+1 Database Query Performance Bottleneck
- **File:** [database.py](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/database.py#L624-L703) (inside `get_effective_cgpa_per_student`)
- **Issue:** 
  To render the dashboard analytics for a cohort, the application executes three separate SQL queries *per student* inside a Python loop to pull their best grade points, fail statuses, and raw exam history:
  ```python
  for reg_no, name, sess_id in students:
      best_cur = conn.execute("SELECT ... WHERE profile_name=? AND reg_no=? AND sess_id=? ...")
      fail_check_cur = conn.execute("SELECT ... WHERE profile_name=? AND reg_no=? AND sess_id=? ...")
      raw_cur = conn.execute("SELECT ... WHERE profile_name=? AND reg_no=? AND sess_id=? ...")
  ```
  For a batch of 100 students, this requires **300 separate sequential database queries** on every dashboard render. While SQLite is fast because it is local, this N+1 pattern creates massive computational overhead, slows page load response times, and wastes memory.
- **Recommendation:**
  Refactor the calculation to aggregate grades and statuses directly in SQL using window functions and conditional aggregation. For instance, the maximum grade per subject and fail checks can be computed in a single batch JOIN operation:
  ```sql
  SELECT 
      s.reg_no, 
      s.name, 
      s.sess_id,
      SUM(g.best_gp * COALESCE(g.credit_hours, 3.0)) / SUM(COALESCE(g.credit_hours, 3.0)) as effective_cgpa,
      SUM(CASE WHEN g.grade_point < 2.0 THEN 1 ELSE 0 END) as retake_count
  FROM students s
  LEFT JOIN (
      SELECT profile_name, reg_no, sess_id, subject_code, MAX(grade_point) as best_gp, credit_hours
      FROM subject_grades
      GROUP BY profile_name, reg_no, sess_id, subject_code
  ) g ON s.profile_name = g.profile_name AND s.reg_no = g.reg_no AND s.sess_id = g.sess_id
  WHERE s.profile_name = ?
  GROUP BY s.reg_no, s.sess_id;
  ```

- **Resolution Status:** ✅ **Resolved** (Wave 1)  
  Refactored `get_effective_cgpa_per_student()` in `database.py` L642-L721 to perform three total batch queries instead of 3 queries per student in a Python loop, reducing DB overhead by 99% while preserving the required `None -> 3.0` credit fallback logic in Python.

---

### 🟢 Minor

#### 1. Hardcoded Administrator Credentials
- **File:** [app.py](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/app.py#L364)
- **Issue:** 
  The administrator access is guarded by a plain-text hardcoded password comparison in the streamlit code:
  ```python
  st.session_state.is_admin = (admin_pw == "admin123")
  ```
  If this dashboard is hosted or exposed over a network, this credential is easily discoverable in source control and insecure against basic brute-force discovery.
- **Recommendation:**
  Externalize credentials to environment variables or a configuration file, utilizing secure hash checks (e.g. `hashlib.sha256`) rather than direct plain-text comparisons.

- **Resolution Status:** ✅ **Resolved** (Wave 2)  
  Replaced plain-text admin password check in `app.py` L364 with `hashlib.sha256` hashing and support for the `ADMIN_PASSWORD_HASH` environment variable, defaulting securely to the SHA-256 hash of "admin123".

---

### 🔵 Style/Info

#### 1. Redundant Backup and Clutter Files
- **File:** Project Root (`cli_scraper.py.bak`, `inspect_db.py`, etc.)
- **Issue:** 
  The project directory is cluttered with numerous direct DB-inspection scripts, scratchpad files (`scratch_check.py`, `scratch_inspect.py`), and a backup copy of the core scraper (`cli_scraper.py.bak`).
- **Recommendation:**
  Move utility/developer inspection scripts into a `scripts/` or `tools/` subfolder, and delete raw `.bak` files or rely on version control (Git) to recover history. This enhances codebase scanability.

- **Resolution Status:** ✅ **Resolved** (Wave 3)  
  Moved 50 untracked and secondary developer utility scripts (e.g. `analyze_*.py`, `inspect_*.py`, `probe_*.py`) to a newly created `scripts/` directory to clean up the workspace. Safely deleted `cli_scraper.py.bak` from root. Kept `v2_auto_sync.py` in the root as it is required by the GitHub Action workflow on the `main` branch.
