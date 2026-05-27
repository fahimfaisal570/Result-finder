# Code Rabbit Senior Review Report
**Author:** Senior Review Agent (Code Rabbit Superpower)  
**Target Branch / Commit:** `v2` / `13f68a8`

## Severity Breakdown
- 🔴 **Critical**: 1
- 🟡 **Major**: 2
- 🟢 **Minor**: 1
- 🔵 **Style/Info**: 2

---

## Findings

### 🔴 Critical

#### 1. Circular Environment Dependency: top-level `streamlit` import in non-dashboard modules
- **File:** `database.py` (L12)
- **Issue:** The backend analytics module `database.py` imports `streamlit as st` at the top level. Since `v2_auto_sync.py` and potentially other command-line utilities / automated tasks run in headless CI/CD workflow environments where Streamlit is NOT installed (only `requirements.txt` dependencies might be present, and Streamlit might not be in the execution path or the runner is minimal), importing `database.py` will throw an immediate `ImportError`. This breaks the automated sync workflow (`v2_auto_sync.py`) when executed from GitHub Actions or CRON schedulers.
- **Remediation:** 
  Refactor the Streamlit dependency in `database.py` to be dynamically imported only inside functions that actually require it (e.g. if Streamlit utility calls or caches are used). Looking closely at `database.py`, it does not actually use the `st` object at all! The import can be completely removed from `database.py`.
  ```diff
  -import streamlit as st
  ```

---

### 🟡 Major

#### 1. Hardcoded Linux-only Filepath `/tmp/...` for Sync Operations
- **File:** `v2_auto_sync.py` (L5)
- **Issue:** The `SYNC_FILE` is hardcoded as `"/tmp/v2_sync_tasks.json"`. While this works perfectly in GitHub Actions ubuntu-runners, it causes failures when running or testing locally on a Windows development system (where `/tmp/` is not a valid absolute path, leading to `FileNotFoundError` or permission issues when trying to write to `C:\tmp`).
- **Remediation:**
  Use Python's standard `tempfile` module to resolve the system's temporary directory dynamically, guaranteeing cross-platform compatibility across Windows and Linux runner environments.
  ```python
  import tempfile
  SYNC_FILE = os.path.join(tempfile.gettempdir(), "v2_sync_tasks.json")
  ```

#### 2. Synchronous Resource Cleanup Vulnerability on Process Crash
- **File:** `v2_auto_sync.py` (L241)
- **Issue:** The sync file cleanup `os.remove(SYNC_FILE)` is called at the very end of the `main()` function. If an unhandled exception occurs during the database sync or readd detection loop, the script terminates immediately, leaving the temporary `v2_sync_tasks.json` on disk. In subsequent runs or local test environments, this stale file might be processed again or cause state pollution.
- **Remediation:**
  Wrap the main loop execution inside a `try...finally` block to guarantee that cleanup of temporary session resources occurs even in the event of an unhandled exception or runtime crash.
  ```python
  try:
      # execution logic...
  finally:
      if os.path.exists(SYNC_FILE):
          try:
              os.remove(SYNC_FILE)
              print("Removed temporary sync tasks file.")
          except Exception as e:
              print(f"Failed to clean up sync file: {e}")
  ```

---

### 🟢 Minor

#### 1. Dynamic Local CGPA Calculation Fallback to None (Multi-Exam Omissions)
- **File:** `database.py` (L875-L892)
- **Issue:** When the portal ommits a student's CGPA in a specific exam, the dashboard attempts to dynamically calculate a retake-aware CGPA up to that exam by running a grouped query. However, if the `exam_id` happens to be non-integer (e.g., custom semester tag or special exam codes containing letters), a `ValueError` is caught, and the calculation silently skips, returning `cgpa = 0.0`.
- **Remediation:**
  Handle string-based or non-integer `exam_id` by performing a secondary lookup on the `scan_log` or ordering by `scanned_at` timestamps instead of casting to an integer, or falling back to the standard `true_cgpa` computed across all known records if chronology cannot be established.

---

### 🔵 Style/Info

#### 1. Hardcoded Standard Credit Maps
- **File:** `database.py` (L983-L996)
- **Issue:** The standard required credits are hardcoded for CSE, Civil, and EEE semesters (1-8) inside `get_semester_total_credits()`. While this prevents the elective over-counting bug, any future changes to standard department curriculums will require manual code modification.
- **Remediation:**
  Move these standard credits to a `standard_credits` block inside `credit_mapping.json` so they can be managed outside of code logic.

#### 2. Duplicate Redundant Code in Auto-PDF Mailer
- **File:** `auto_pdf_main.py` vs `v2_auto_sync.py`
- **Issue:** `_get_senior_profiles_json` in `auto_pdf_main.py` (L130) contains the same profile batch parsing logic that has been modernized in `v2_auto_sync.py` via `db.get_senior_batch_profiles`.
- **Remediation:**
  Clean up and import the modernized database lookup helper rather than maintaining duplicate parsing blocks.
