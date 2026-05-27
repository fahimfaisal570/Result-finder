# Roadmap — Code Quality & Scraper Modernization

## Source
All tasks derived from [Code Rabbit Review Report](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/.coderabbit/review_report.md)

---

- [x] Wave 0: Critical Hotfixes
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

- [x] Wave 4: Final Verification Gate
  - [x] Task 4.1: Run full test suite and confirm 13/13 pass
  - [x] Task 4.2: Update review report with resolution status

- [x] Wave 5: Database Query Optimization (Indices & Concurrency)
  - [x] Task 5.1: Configure timeouts and busy retry parameters in `get_connection()`
  - [x] Task 5.2: Create compound database lookup indices dynamically in `init_db()` and all migrations
  - [x] Task 5.3: Run unit tests to verify index creation and connection safety

- [x] Wave 6: Scraper & Regex Robustness
  - [x] Task 6.1: Define robust, compiled, case-insensitive regex patterns for student metadata in `cli_scraper.py`
  - [x] Task 6.2: Implement randomized exponential backoff retry delays inside the scraper request loop
  - [x] Task 6.3: Run automated test suite to confirm zero scraper regressions

- [x] Wave 7: Requests.Session Pool Migration (Modernized Webapp Edition)
  - [x] Task 7.1: Add `import requests` and setup global session with thread-safe `HTTPAdapter` pool
  - [x] Task 7.2: Refactor `make_request()` to use `session.get()` and `session.post()` with explicit timeouts
  - [x] Task 7.3: Replace custom `SESSION_COOKIES` and locking blocks with standard native cookies checks
  - [x] Task 7.4: Add `requests` directly to `requirements.txt`

- [x] Wave 8: PDF Report Formatting & Times New Roman Style Alignment
  - [x] Task 8.1: Migrate HTML/PDF results report styling in `cli_scraper.py` to match Times New Roman format of main branch
  - [x] Task 8.2: Implement clean page-break styling and remove anchors in results tables for official look
  - [x] Task 8.3: Add Bangladesh timezone-aware generation metadata

- [x] Wave 9: Obsolete Code & Backup Cleanups
  - [x] Task 9.1: Clean up redundant Python 2 compatibility shims and conditional checks in `cli_scraper.py`
  - [x] Task 9.2: Delete residual `cli_scraper.py.bak` from the repository root
  - [x] Task 9.3: Remove unused `ssl_context` variables
  - [x] Task 9.4: Run all verification tests and commit
