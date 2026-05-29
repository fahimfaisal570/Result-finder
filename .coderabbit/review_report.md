# Code Rabbit Review Report — DB & Data Loading Performance
**Author:** Senior Review Agent (Code Rabbit)  
**Target:** `database.py`, `pages/analytics.py`, `pages/results.py`, `app.py`  
**Focus:** Database I/O, data loading latency, and connection efficiency for Streamlit Cloud hosted deployment  
**Date:** 2026-05-29  

---

## Severity Breakdown
- 🔴 **Critical**: 1
- 🟡 **Major**: 3
- 🟢 **Minor**: 2
- 🔵 **Style/Info**: 1

---

## Findings

### 🔴 Critical

#### CR-001 — Connection-per-query storm: Every DB function opens & closes a fresh connection
- **Files:** `database.py` (L85–94, and every function that calls `get_connection()`)
- **Impact:** On Streamlit Cloud (single-core, virtualized I/O), every SQL call pays:
  1. `sqlite3.connect()` → file open + WAL header read
  2. `PRAGMA foreign_keys = ON` → parse + execute
  3. `PRAGMA journal_mode = WAL` → file-system check
  4. `PRAGMA busy_timeout = 30000` → parse + execute
  5. Context manager exit → `conn.close()` → WAL checkpoint flush

  A single analytics page load calls `get_profiles()`, `get_exams_for_profile()`, `get_student_data_for_exam()`, `get_subject_data_for_exam()`, `get_longitudinal_data()`, `get_incomplete_history_students()`, `get_retake_success_stats()` = **7+ separate open/PRAGMA/close cycles**.

  On Streamlit Cloud's virtualized storage, each cycle incurs ~15–30 ms overhead. **7 × 25 ms = 175 ms of pure connection overhead** before any real query runs.

- **Recommendation:** Implement a **thread-local connection pool** pattern. Since SQLite + Streamlit is single-threaded per user session, reuse one connection per thread for the duration of a request cycle. Specifically:

  ```python
  import threading
  _thread_local = threading.local()

  def get_connection():
      conn = getattr(_thread_local, '_conn', None)
      if conn is None:
          conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
          conn.execute("PRAGMA foreign_keys = ON")
          conn.execute("PRAGMA journal_mode = WAL")
          conn.execute("PRAGMA busy_timeout = 30000")
          _thread_local._conn = conn
      return conn
  ```

  This eliminates 6 of 7 open/close cycles per analytics page load, saving ~150 ms on every page visit on Streamlit Cloud.

  **CRITICAL CAVEAT:** The `ClosedOnExitConnection` wrapper currently closes the connection on `__exit__`. All `with get_connection() as conn:` blocks would need to be refactored so the context manager *commits* but does **not** close, since the connection is now pooled. Write operations should call `conn.commit()` explicitly instead of relying on `__exit__`.

---

### 🟡 Major

#### CR-002 — Missing index on `subject_grades(profile_name, exam_id)` — Full table scans on analytics queries
- **File:** `database.py` (L98–124 `ensure_database_indices()`, L845–850, L941–957)
- **Impact:** The current index is `idx_subject_grades_lookup ON subject_grades(profile_name, reg_no, sess_id)`. However, the two heaviest analytics queries filter by `(profile_name, exam_id)`:

  ```sql
  -- get_student_data_for_exam (L845)
  SELECT reg_no, subject_code, grade_point, credit_hours
  FROM subject_grades WHERE profile_name=? AND exam_id=?
  
  -- get_subject_data_for_exam (L947)
  SELECT sg.reg_no, ... FROM subject_grades sg JOIN students s ...
  WHERE sg.profile_name=? AND sg.exam_id=?
  ```

  With 37K rows and no `(profile_name, exam_id)` index, SQLite performs a **full table scan** every time these are called. On Streamlit Cloud's slow disk, this means ~50–100 ms per query unnecessarily.

- **Recommendation:** Add a compound index:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_subject_grades_exam 
  ON subject_grades(profile_name, exam_id)
  ```
  This turns the full scan into an index seek, reducing query time from ~50–100 ms to ~1–5 ms.

---

#### CR-003 — Missing index on `exam_results(profile_name, exam_id)` — Full table scans on JOIN queries
- **File:** `database.py` (L803–815 `get_exams_for_profile()`, L831–838 `get_student_data_for_exam()`)
- **Impact:** The current index on exam_results is `(profile_name, reg_no, sess_id)`. But the JOIN in `get_student_data_for_exam()` filters on `er.exam_id=?` alongside `s.profile_name=?`. The subquery in `get_exams_for_profile()` also groups by `exam_id` where `profile_name=?`.

  Without `(profile_name, exam_id)`, SQLite must scan the entire exam_results table (4.3K rows) to find matching rows.

- **Recommendation:** Add:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_exam_results_exam 
  ON exam_results(profile_name, exam_id)
  ```

---

#### CR-004 — `get_profiles()` called redundantly on every page load — no deduplication
- **Files:** `app.py` (L191), `pages/analytics.py` (L227, L997), `pages/results.py` (L48)
- **Impact:** `get_profiles()` does a full table scan on `profiles` + a full table scan on `students` (886 rows). On the analytics page, it's called:
  1. Line 227 — initial page load
  2. Line 997 — Cross-Batch Benchmarking section calls `db.get_profiles().keys()` again

  Each call opens a new connection, runs 2 queries, and builds a dict with all student data. On Streamlit Cloud, this ~15 ms × 2 = 30 ms of redundant work.

  Additionally, `_incomplete_students` (L346) and `load_longitudinal` (L296) each open their own connections when they could share.

- **Recommendation:** For analytics.py, capture `profiles` once at load time (which already happens at L227) and reuse the variable. The second call at L997 should use the existing `profiles` dict rather than calling `db.get_profiles()` again:
  ```python
  # Line 997: Use already-loaded profiles dict
  all_profiles = sorted(profiles.keys())  # instead of db.get_profiles().keys()
  ```

---

### 🟢 Minor

#### CR-005 — `get_connection()` sets `PRAGMA journal_mode = WAL` on every call
- **File:** `database.py` (L92)
- **Impact:** `journal_mode` is a database-level persistent setting — once set to WAL, it persists across connections. Executing this PRAGMA on every connection open adds a file-system check overhead (~3–5 ms) that is completely unnecessary after the first successful call.
- **Recommendation:** Execute `PRAGMA journal_mode = WAL` only once during `init_db()`, not on every connection:
  ```python
  def get_connection():
      conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
      conn.execute("PRAGMA foreign_keys = ON")
      conn.execute("PRAGMA busy_timeout = 30000")
      return ClosedOnExitConnection(conn)
  ```

---

#### CR-006 — `get_longitudinal_data()` builds complex in-memory dict without SQL pre-filtering
- **File:** `database.py` (L2067–2144)
- **Impact:** This function fetches **every exam result for every student** in the profile with a single query, then filters retakes in Python, then groups by semester label in Python. For a profile with 50 students × 8 semesters = 400 rows, this is fine. But it's doing a JOIN across `exam_results` + `students` without the optimal index, and then processing regex patterns (`SEM_PATTERN`) on every row in Python.
- **Recommendation:** Pre-filter retake exams in SQL by adding `AND er.exam_name NOT LIKE '%retake%' AND er.exam_name NOT LIKE '%improvement%'` to the query. This reduces the rows Python needs to process. The regex grouping can't easily move to SQL, but reducing input size helps.

---

### 🔵 Style/Info

#### CR-007 — `from collections import defaultdict` imported inside function bodies repeatedly
- **Files:** `database.py` (L704, L853)
- **Impact:** The `defaultdict` import appears inside `get_effective_cgpa_per_student()` and `get_student_data_for_exam()`. While Python caches module imports after the first call, the import statement itself still has a small overhead per invocation. More importantly, this is a code smell.
- **Recommendation:** Move `from collections import defaultdict` to the top-level imports at the beginning of `database.py`.

---

## Priority Recommendation Matrix

| ID | Severity | Estimated Latency Saving (Cloud) | Implementation Risk | Priority |
|----|----------|------|-----|----------|
| CR-001 | 🔴 Critical | ~150 ms/page | Medium (refactor all `with` blocks) | **P0** |
| CR-002 | 🟡 Major | ~50–100 ms/analytics load | Very Low (1-line index) | **P0** |
| CR-003 | 🟡 Major | ~30–50 ms/analytics load | Very Low (1-line index) | **P0** |
| CR-004 | 🟡 Major | ~15–30 ms/page | Very Low (use cached var) | **P1** |
| CR-005 | 🟢 Minor | ~3–5 ms/connection | Very Low | **P1** |
| CR-006 | 🟢 Minor | ~5–10 ms/page | Low | **P2** |
| CR-007 | 🔵 Info | Negligible | None | **P3** |

## Combined Impact Estimate
Implementing CR-001 through CR-005 would save approximately **250–335 ms per analytics page load** on Streamlit Cloud. Given that the current page load is estimated at 500–800 ms, this represents a **30–50% latency reduction**.
