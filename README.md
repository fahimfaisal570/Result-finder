# Result Finder PRO (main)

> **Automated Academic Scraping & Reporting Pipeline**  
> *Production-grade exam result extraction, automated PDF reports to department heads, and readd detection — all running autonomously via GitHub Actions.*

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Storage](https://img.shields.io/badge/Storage-JSON-lightgrey)
![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub_Actions-2088FF?logo=githubactions&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## The Problem

The DUCMC portal (`ducmc.du.ac.bd`) — the only official source of academic results for Faridpur Engineering College — shows results one student at a time. Faculty must manually check each student's registration number, one by one, to compile batch results. For 60+ students across 3 departments, this takes hours. Worse, there's no notification system — faculty have no idea when new results are published.

## The Solution

The `main` branch is the **production automation pipeline** of Result Finder. It continuously monitors the portal for new exam publications, automatically scrapes entire batches, generates PDF reports, and emails them directly to department heads — all running autonomously via GitHub Actions.

> *Looking for the database-backed analytics platform with OLAP dashboards, graduation projections, and 20+ interactive visualizations? See the [`v2` branch](https://github.com/fahimfaisal570/Result-finder/tree/v2). Both branches are deployed simultaneously and [work together](#how-main-and-v2-work-together).*

---

## Features

### Concurrent Scraping Engine (`cli_scraper.py`)

| Feature | Description |
|---------|-------------|
| **Multi-threaded Batch Scanning** | Queue-based worker pool (10–15 threads) scrapes an entire batch in minutes |
| **HTTP Connection Pooling** | `requests.Session` with 20 pool connections and 100 max size — bypasses TLS handshake overhead |
| **Exponential Backoff + Jitter** | 4 retries with randomized delays to handle portal rate limits |
| **User-Agent Rotation** | 5 browser UA strings to avoid WAF detection |
| **Regex-Only HTML Parsing** | 40+ compiled regex patterns — zero dependency on BeautifulSoup |
| **Cookie & Session Management** | PHPSESSID tracking, automatic session warming before AJAX calls |
| **HTML Report Generation** | Print-optimized reports with registration tables, scholarship eligibility (top half by SGPA), and CGPA rankings |
| **Academic Transcript Generation** | Dark-themed chronological per-student record with per-exam subject tables |

### Full CLI Interface (`cli_scraper.py`)

Complete state machine (States 0→7) for terminal-based operation:
1. **Source Selection** — Manual scan, Load saved profile, Manage profiles, Create manual batch
2. **Program Selection** — CSE, EEE, Civil Engineering
3. **Session & Registration Range** — Flexible range parsing (e.g., `210101-210150`, `935,936,937`)
4. **Senior Re-add Loop** — Add registration ranges from senior batches
5. **Exam Selection** — Smart classification with probe verification
6. **Execute Scan** — Multi-threaded scraping with live progress
7. **Post-Scan** — Save HTML report, open in browser (Android `am start` fallback), offer profile save

### Profile Management
- **CRUD Operations** — Create, rename, delete batch profiles
- **Add/Remove Students** — Scan portal to verify before adding; Smart Purge removes students not found in an exam
- **Provisional Batches** — Create rosters before results are published; auto-promotes on first result import
- **Export/Import** — JSON backup/restore (`ducmc_export_*.json`)
- **Storage** — `saved_profiles.json` flat file with process-safe directory locking

### Lightweight Streamlit Dashboard (`app.py`)

| Page | Description |
|------|-------------|
| **Home** | Program/session configuration, interactive scans, saved profile management, student list with transcript links, classified exam links, batch scan all exams |
| **Results** (`pages/results.py`) | Runs scraper from URL params, renders inline HTML report, save to profile |
| **Transcript** (`pages/transcript.py`) | Deep-scans every exam for a single student with smart cohort-year filtering |

### Exam Publication Watcher (`exam_monitor/`)

The core automation pipeline — runs on GitHub Actions and monitors the portal 24/7:

```
GitHub Actions (cron) → monitor.py → Detects new exam
  → Filters out retake/improvement/special/backlog exams
  → Sends high-priority text alert (admin + dept head)
  → auto_pdf_mailer.py:
      → Identifies target batch via empirical probing (tests 5 students)
      → Scrapes all batch students (10 threads)
      → Detects readd students from senior batches (subject-overlap fingerprinting)
      → Auto-promotes provisional batches
      → Generates HTML → PDF report (pdfkit, 5000mm continuous page)
      → Emails PDF attachment (Gmail SMTP_SSL, high-priority headers)
      → Queues sync task for v2 branch
```

**Email Routing:**

| Department | Program ID | Recipients |
|-----------|-----------|------------|
| Civil Engineering | 12 | Admin + Civil Dept Head |
| EEE | 13 | Admin + EEE Dept Head |
| CSE | 14 | Admin + CSE Dept Head |

All emails include `X-Priority: 1` and `Importance: High` headers for phone push notifications.

**State Tracking:** `known_exams.json` tracks all known exam IDs per department. New exam = current IDs minus known IDs.

**Exclusion Filter:** Exams matching any of these keywords are ignored: `retake`, `improvement`, `special`, `clearance`, `backlog`, `junior`, `short`, `carry`.

### Readd Detection (Subject-Overlap Fingerprinting)

When a new exam is detected, the system identifies re-admitted ("readd") students from senior batches:

1. **Build reference fingerprint** — subject codes taken by ≥30% of regular batch students (≥4 subjects)
2. **Scan senior batch students** against the exam
3. **Ghost filter** — genuine readd requires ≥50% subject overlap AND ≥70% load ratio
4. Improvement/retake-only students are filtered out
5. Confirmed readds are added to `saved_profiles.json` under the target profile

### Portal Uptime Monitor (`portal_monitor/`)

Separate, isolated health monitoring:
- **Positive verification** — portal is "online" only if HTML contains "DUCMC" AND "University of Dhaka" AND no CrowdSec/WAF blocks
- **Alert on transitions only** — emails sent only when status changes (online→offline or offline→online), preventing alert fatigue
- **State persistence** — uses GitHub Actions Cache (not git commits) to persist `state.json` across runs
- **CLI flags** — `--force-online`, `--force-offline`, `--test-email` for manual testing

### Process Safety

JSON file writes (across concurrent GitHub Actions jobs) are protected by **directory-based atomic locks**:

```python
@contextlib.contextmanager
def file_process_lock(lock_path, timeout=30):
    # os.mkdir() is atomic on all OS — used as a spinlock
    # 200ms poll interval, 30s timeout with fallback
```

This prevents `saved_profiles.json` and `state.json` corruption when multiple CI jobs run simultaneously.

---

## How `main` and `v2` Work Together

Both branches are deployed simultaneously as separate Streamlit apps:

| Branch | Storage | Deployment | Primary Role |
|--------|---------|------------|-------------|
| `main` | `saved_profiles.json` | `fec-result-finder.streamlit.app` | Exam monitoring, PDF reports, result viewing |
| `v2` | `result_finder.db` (SQLite) | `fec-result-analytics.streamlit.app` | Analytics, projections, deep analysis |

When `main`'s exam monitor detects a new exam and processes it:

1. `auto_pdf_mailer.py` writes a sync task to `v2_sync_tasks.json` (temp file, locked write)
2. The GitHub Actions workflow checks out the `v2` branch and runs `v2_auto_sync.py`
3. `v2_auto_sync.py` re-scrapes the same students and saves to the SQLite database
4. Both branches now have the same data in their respective storage formats

---

## Repository Structure

```
├── app.py                          # Streamlit dashboard entry point
├── cli_scraper.py                  # Core scraping engine & CLI
├── ui_components.py                # Design system — CSS/JS/fonts
├── saved_profiles.json             # Flat-file profile storage
├── requirements.txt                # Project dependencies
├── college_logo.png & favicon.ico  # UI branding assets
│
├── pages/
│   ├── results.py                  # Exam scan execution page
│   └── transcript.py               # Individual student record
│
├── scraper_core/                   # Modularized scraper components
│   ├── network.py                  # Connection pooling, retries
│   ├── parser.py                   # HTML regex extraction
│   ├── profiles.py                 # Profile loading/saving
│   └── reports.py                  # HTML report generation
│
├── exam_monitor/
│   ├── monitor.py                  # Exam publication detector
│   ├── auto_pdf_mailer.py          # PDF generator + emailer
│   ├── find_latest.py              # Latest exam utility
│   ├── sync_state.py               # State reset utility
│   └── known_exams.json            # Known exam IDs per dept
│
├── portal_monitor/
│   ├── health_check.py             # Portal uptime monitor
│   └── state.json                  # Last known portal status
│
├── tests/
│   └── test_exam_monitor_workflow.py
│
└── .github/workflows/
    ├── portal_health.yml           # Uptime monitoring workflow
    └── exam_monitor.yml            # Exam detection cron workflow
```

---

## Quick Start

### 1. Install
```bash
git clone https://github.com/fahimfaisal570/Result-finder.git -b main
cd Result-finder
pip install -r requirements.txt
```

### 2. Launch Dashboard
```bash
streamlit run app.py
```

### 3. Run CLI Scraper
```bash
python cli_scraper.py
```
Interactive terminal interface — select program, session, registration range, and exam.

### 4. Environment Variables (for automation)
```bash
EMAIL_USER=your_gmail@gmail.com
EMAIL_PASS=your_app_password
RECEIVER_EMAIL=admin@example.com
CSE_HEAD_EMAIL=cse_head@example.com
EEE_HEAD_EMAIL=eee_head@example.com
CIVIL_HEAD_EMAIL=civil_head@example.com
```

---

## Testing

```bash
python -m unittest tests/test_exam_monitor_workflow.py -v
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| streamlit | Web dashboard |
| pandas | Data manipulation |
| requests | HTTP with connection pooling |
| pdfkit | HTML → PDF conversion |

---

## License & Credits

Released under the **MIT License**.

Developed for academic excellence — automating result distribution for Faridpur Engineering College.

**Author:** [Fahim Faisal](https://www.linkedin.com/in/fahimfaisal09)
