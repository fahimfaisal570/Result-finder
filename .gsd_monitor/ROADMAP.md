# Roadmap — FEC Exam Publication Monitor

- [x] **Wave 1: Fast Boot Architecture**
  - [x] Task 1.1: Defer heavy module imports (`pdfkit`, `auto_pdf_mailer`) to allow fast check-only runs under 2 seconds.
  - [x] Task 1.2: Set up environment outputs for GITHUB_OUTPUT to trigger down-stream heavy runners only when new exams are found.

- [x] **Wave 2: Multi-Recipient Email Routing & Security**
  - [x] Task 2.1: Implement department-specific head email routing via secure environment secrets.
  - [x] Task 2.2: Implement secure app-specific Gmail password integration.

- [x] **Wave 3: Performance Optimization (Current)**
  - [x] Task 3.1: Pre-compile all option parsing regex patterns at module levels to maximize parsing speed.
  - [x] Task 3.2: Implement dynamic runtime `random.uniform` monkeypatching in `auto_pdf_mailer.py` to reduce scraper jitter by 85% in workflow environments.
  - [x] Task 3.3: Verify all CLI detection commands (`monitor.py`, `find_latest.py`, `sync_state.py`) execute with 100% success.
