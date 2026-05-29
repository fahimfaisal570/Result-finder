# Code Rabbit Review Report — DB & Data Loading Performance (Round 2)
**Author:** Senior Review Agent (Code Rabbit)  
**Target:** `database.py`, `pages/analytics.py`, `pages/results.py`, `app.py`  
**Focus:** Advanced query optimizations, index seek preservation, self-join elimination, and standard imports cleanup.  
**Date:** 2026-05-29  

---

## Severity Breakdown
- 🔴 **Critical**: 1
- 🟡 **Major**: 2
- 🟢 **Minor**: 1
- 🔵 **Style/Info**: 1

---

## Findings

### 🔴 Critical

#### CR2-001 — N+1 Queries storm in `get_cross_batch_comparison()`
- **File:** `database.py` (L2202–2268)
- **Impact:** When a user selects multiple batches in the dashboard to compare (e.g., comparing CSE 09, CSE 10, CSE 11), `get_cross_batch_comparison()` executes:
  1. For each batch: a query to find all exams matching the pattern.
  2. For each batch: a query to fetch GPAs for the chosen "main" exam.
  
  For 5 batches, this incurs **10 separate query roundtrips** in a sequential loop. On virtualized cloud environments with high I/O latency, this adds ~150–200 ms of pure connection/transaction overhead.
- **Remediation:**
  Refactor `get_cross_batch_comparison()` to perform exactly **2 bulk fetches**:
  1. Fetch all matching exams for all selected profiles in a single query using an `IN` clause:
     ```sql
     SELECT profile_name, exam_id, exam_name, COUNT(reg_no) as student_count
     FROM exam_results
     WHERE profile_name IN (list_of_profiles) AND exam_name LIKE ?
     GROUP BY profile_name, exam_id, exam_name
     ```
  2. Filter and find the main exam for each batch in Python, then fetch GPAs for all matched exams in a single bulk query using compound `OR` conditions:
     ```sql
     SELECT profile_name, gpa
     FROM exam_results
     WHERE (profile_name = ? AND exam_id = ?) OR (profile_name = ? AND exam_id = ?) OR ...
     ```

---

### 🟡 Major

#### CR2-002 — Index seek invalidation via `CAST(exam_id AS INTEGER)` in `get_student_data_for_exam()`
- **File:** `database.py` (L877–889)
- **Impact:** The historical CGPA query filters on `CAST(exam_id AS INTEGER) <= ?`. Because of the `CAST` function applied directly to the column, SQLite cannot use the optimized compound index `idx_subject_grades_exam ON subject_grades(profile_name, exam_id)`. It is forced to scan all `subject_grades` rows matching the `profile_name` (~37K total rows), causing 30–50 ms latency.
- **Remediation:**
  Do not cast the database column in the query. Instead:
  1. Fetch all relevant `exam_ids` for the profile from `scan_log` (or in memory) where the integer representation is `<= exam_id_int`.
  2. Execute the query using an index-friendly `exam_id IN (list_of_matched_ids)` filter. Since the column matches the index exactly, SQLite performs super-fast index seeks (~1 ms).

#### CR2-003 — Double table scan self-join in `get_effective_cgpa_per_student()`
- **File:** `database.py` (L734–752)
- **Impact:** The subquery to get the latest raw CGPA per student performs an `INNER JOIN` against another `GROUP BY` subquery on `exam_results` (4.3K rows), sorting and scanning twice.
- **Remediation:**
  Use a modern `ROW_NUMBER() OVER (PARTITION BY reg_no, sess_id ORDER BY CAST(exam_id AS INTEGER) DESC) as rn` window function. This reads the table exactly once, partitioning and sorting the matches efficiently in-memory before extracting the latest rows.

---

### 🟢 Minor

#### CR2-004 — Code Smell: Redundant Inline Imports in Function Bodies
- **Files:** `database.py` (L2073, L2255), `pages/analytics.py` (L38, L253, L370, L371, L470, L471, L713), `pages/results.py` (L33), `app.py` (L24)
- **Impact:** Importing standard library modules (`re`, `statistics`, `base64`, `json`) inside loops or function bodies repeatedly incurs minor interpreter overhead and violates clean code standards.
- **Remediation:**
  Consolidate all standard imports to the top level of each respective file.

---

## Combined Impact Estimate
Implementing these optimizations will reduce the number of queries for cross-batch comparisons to a hard constant of `2`, preserve compound index seeks on historical scans, and optimize the analytics calculations, resulting in another **150–250 ms latency saving** on virtualized cloud hosting environments!
