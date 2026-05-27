# Roadmap — Code Quality Remediation

## Source
All tasks derived from [Code Rabbit Review Report](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/.coderabbit/review_report.md)

---

- [x] Wave 0: Critical Hotfixes (Already Applied)
  - [x] Task 0.1: Fix SQLite connection leak — `ClosedOnExitConnection` wrapper in `database.py`
  - [x] Task 0.2: Fix `migrate_schema_v2` crash — remove `sess_id` from GROUP BY
  - [x] Task 0.3: Fix HTTP pool broken connection accumulation — `broken` flag in `KeepAlivePool`

- [x] Wave 1: Database Performance (N+1 Elimination)
  - [x] Task 1.1: Refactor `get_effective_cgpa_per_student()` to use batch SQL
  - [x] Task 1.2: Run existing tests to verify no regression

- [x] Wave 2: Security Hardening
  - [x] Task 2.1: Externalize admin password from `app.py` to env var with hash comparison

- [x] Wave 3: Code Hygiene & Deduplication
  - [x] Task 3.1: Remove duplicate `_run_deep_analysis` + `_render_deep_result` in `analytics.py`
  - [x] Task 3.2: Remove duplicate `ui.add_contact_section()` call in `pages/results.py`
  - [x] Task 3.3: Organize utility/inspection scripts into `scripts/` folder

- [ ] Wave 4: Final Verification Gate
  - [ ] Task 4.1: Run full test suite and confirm 13/13 pass
  - [ ] Task 4.2: Update review report with resolution status
