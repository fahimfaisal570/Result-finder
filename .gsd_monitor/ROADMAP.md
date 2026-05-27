# Roadmap — Result Finder & Publication Monitor

- [x] **Milestone 1: Fast-Boot Architecture (Zero-Dependency)**
  - [x] Task 1.1: Defer heavy module imports in `monitor.py` to allow high-frequency cron checks to complete under 2 seconds.
  - [x] Task 1.2: Establish clean exit code separation (e.g. exit code 0 for no changes, exit code for new publications) to coordinate GITHUB_OUTPUT chains.

- [x] **Milestone 2: Multi-Recipient Department Routing & Security**
  - [x] Task 2.1: Establish secure environment-mapped head emails (`CSE_HEAD_EMAIL`, `EEE_HEAD_EMAIL`, `CIVIL_HEAD_EMAIL`).
  - [x] Task 2.2: Implement secure SMTP app passwords bypassing default plain-text logs.

- [x] **Milestone 3: Performance, Stealth scans & Concurrency Controls**
  - [x] Task 3.1: Pre-compile all options extraction and option values regex patterns at module level to eliminate parse bottlenecks.
  - [x] Task 3.2: Implement dynamic, context-specific monkeypatching of `random.uniform` inside `auto_pdf_mailer.py` to scale down timing safety jitters in CI pipelines.
  - [x] Task 3.3: Implement the KeepAlive HTTPS connection manager to recycle TCP connections safely.

- [x] **Milestone 4: Premium Dashboard UI & User Experience (Current)**
  - [x] Task 4.1: Integrate custom Outfit Google Fonts, premium elevations, cards, and smooth micro-animations into Streamlit dashboard.
  - [x] Task 4.2: Program dynamic mouse event triggers in JS to open selectboxes instantly on hover.
  - [x] Task 4.3: Implement secure frontend admin settings block to handle profiles creation, deletions, and smart purges.

- [ ] **Milestone 5: Advanced Security Hardening (Planned)**
  - [ ] Task 5.1: Replace the hardcoded `admin123` credential in `app.py` with environment variable loading.
  - [ ] Task 5.2: Set up automated sanitization of parsed student names inside Streamlit to block any potential XSS from malformed HTML.
