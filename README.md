# Result Finder PRO — University Batch Scraping & Automated Monitoring Infrastructure (`main`)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30%2B-FF4B4B.svg)](https://streamlit.io/)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-24%2F7%20Monitoring-2088FF.svg)](https://github.com/features/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Result Finder PRO (`main`)** is an automated web scraping, exam publication monitoring, and instant email distribution engine built for Faridpur Engineering College (Constituent College of University of Dhaka).

The official university portal ([DUCMC](https://ducmc.du.ac.bd/)) restricts result queries to a single student and exam at a time. **Result Finder PRO `main`** automates batch-level data acquisition using a multi-threaded scraping pipeline, provides an intuitive Streamlit dashboard, runs 24/7 background monitors via GitHub Actions to detect newly published results, generates print-ready PDF reports, and dispatches high-priority email alerts to department heads and administration.

---

## Key Features & Core Capabilities

### 1. Modular High-Concurrency Scraping Engine ([`scraper_core/`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/scraper_core/))
The scraping pipeline is decoupled into specialized modules for resilience and performance:
* **Network & Connection Resilience ([`scraper_core/network.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/scraper_core/network.py))**: Thread-safe HTTP connection pooling (`requests.Session`), connection pre-warming, exponential backoff, jittered retries, and rotating browser User-Agents to prevent connection drops.
* **HTML Parsing ([`scraper_core/parser.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/scraper_core/parser.py))**: Extracts student names, registration numbers, session IDs, GPAs, CGPAs, and subject grade tables across diverse DUCMC HTML templates.
* **Flat-File Storage & Process Safety ([`scraper_core/profiles.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/scraper_core/profiles.py))**: Manages batch rosters in [`saved_profiles.json`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/saved_profiles.json). Utilizes directory-based spinlocks (`file_process_lock`) to guarantee process safety during concurrent multi-job executions.
* **Dynamic HTML Reporting ([`scraper_core/reports.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/scraper_core/reports.py))**: Renders responsive batch HTML reports complete with college branding, grade summary cards, and student result tables.

### 2. Streamlit Web Application ([`app.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/app.py))
An interactive dashboard for managing batch profiles and running live result scans:
* **Batch Profile Management**: Create, rename, edit, and delete academic rosters by specifying Department (CSE, EEE, Civil), Session, and Registration Ranges (e.g. `210101-210150` or discrete IDs `935,936,937`).
* **Provisional Roster Support**: Pre-configure student rosters before results are published. The system monitors for result releases and auto-promotes profiles to active state.
* **Backup & Migration**: One-click JSON backup and restore (`ducmc_export_*.json`) for roster persistence.
* **Single Student & Full Transcript Scans ([`pages/transcript.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/pages/transcript.py))**: Deep-scans a student's full academic record across all sessions, filtering out unrelated cohort exams.
* **Results Viewer ([`pages/results.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/pages/results.py))**: Direct URL parameter-driven scraping engine providing live browser preview and inline HTML saving.

### 3. Interactive Command-Line Scraper ([`cli_scraper.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/cli_scraper.py))
A standalone terminal interface for executing batch scans without launching a web server:
* Interactive prompts for department, session, and exam selection.
* Configurable worker thread count (default 10 threads).
* Automatic post-scan HTML report generation and default browser launch (including Android `am start` fallbacks).

### 4. 24/7 Automated Exam Publication Watcher ([`exam_monitor/`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/exam_monitor/))
A background automation suite running via GitHub Actions ([`.github/workflows/exam_monitor.yml`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/.github/workflows/exam_monitor.yml)):
* **Catalog Polling ([`monitor.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/exam_monitor/monitor.py))**: Polls the university portal every 15 minutes, tracking known exam IDs in [`known_exams.json`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/exam_monitor/known_exams.json).
* **Keyword Exclusion Filtering**: Automatically ignores non-main publication events (e.g. `retake`, `improvement`, `special`, `clearance`, `backlog`, `junior`, `short`, `carry`).
* **Empirical Batch Probing & Readd Detection ([`auto_pdf_mailer.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/exam_monitor/auto_pdf_mailer.py))**: Probes 5 candidate students to identify target profiles, detects re-admitted (readd) students from senior batches via subject-overlap fingerprinting, and auto-promotes provisional profiles.
* **Continuous PDF Generation**: Uses `pdfkit` and `wkhtmltopdf` to generate continuous single-page PDF reports (5000mm height) for seamless mobile viewing.
* **Department-Targeted Email Routing**: Sends instant alerts with PDF attachments to respective department heads using high-priority email headers (`X-Priority: 1`, `Importance: High`).
* **Admin State Utilities**: Includes [`find_latest.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/exam_monitor/find_latest.py) for catalog inspection and [`sync_state.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/exam_monitor/sync_state.py) for manual state resets.

### 5. Portal Uptime & Security Monitor ([`portal_monitor/`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/portal_monitor/))
An isolated monitor ([`.github/workflows/portal_health.yml`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/.github/workflows/portal_health.yml)):
* **Positive Signature Verification ([`health_check.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/portal_monitor/health_check.py))**: Verifies that responses contain expected DUCMC signatures (`DUCMC` + `University of Dhaka`) and flags WAF/CrowdSec security blocks.
* **Transition-Only Alerts**: Dispatches email notifications strictly when status changes (`online` $\leftrightarrow$ `offline`), preventing alert fatigue.
* **CLI Testing Flags**: Supports `--force-online`, `--force-offline`, and `--test-email` for manual verification.

---

## System Architecture

```text
               +----------------------------------+
               |   University Portal (DUCMC)       |
               +----------------+-----------------+
                                |
       +------------------------+------------------------+
       |                                                 |
       v                                                 v
+------+-----------------------+               +---------+-----------------------+
|  Streamlit Application (app.py) |               | GitHub Actions 24/7 Watcher   |
+------+-----------------------+               +---------+-----------------------+
       |                                                 |
       |-- app.py (Roster Manager)                       |-- monitor.py (Catalog Poll)
       |-- pages/results.py (Batch View)                 |-- auto_pdf_mailer.py
       |-- pages/transcript.py (Student History)         |   (Probing, Readd Detection,
       |                                                 |    PDFkit Engine, High-Pri Mail)
       v                                                 v
+------+-------------------------------------------------+-----------------------+
|                       scraper_core/ Engine Package                             |
| (network.py pool | parser.py regex | profiles.py lock | reports.py render)    |
+--------------------------------+-----------------------------------------------+
                                 |
                                 v
                +----------------+----------------+
                | saved_profiles.json Roster Store|
                +----------------+----------------+
                                 |
                                 v (Cross-Branch Task Queue)
                +----------------+----------------+
                |  v2 Branch SQLite Sync Engine   |
                |  (v2_auto_sync.py -> DB)        |
                +---------------------------------+
```

---

## Department Email Routing Matrix

When a new main exam is published, `auto_pdf_mailer.py` inspects the program ID and routes PDF result packages:

| Department | Program ID | Primary Recipients | Headers |
|---|---|---|---|
| **Civil Engineering** | `12` | System Admin + Civil Dept Head | `X-Priority: 1`, `Importance: High` |
| **Electrical & Electronic Engineering (EEE)** | `13` | System Admin + EEE Dept Head | `X-Priority: 1`, `Importance: High` |
| **Computer Science & Engineering (CSE)** | `14` | System Admin + CSE Dept Head | `X-Priority: 1`, `Importance: High` |

---

## How `main` and `v2` Work Together

Both branches operate concurrently in a unified ecosystem:

| Aspect | `main` Branch | `v2` Branch |
|---|---|---|
| **Storage Architecture** | Flat-file JSON (`saved_profiles.json`) | Relational SQLite (`result_finder.db`) |
| **Deployment Role** | Live result scraping, PDF reports, 24/7 publication watcher | Deep analytics, True CGPA math, ML forecasting, retake finder |
| **Live App URL** | `fec-result-finder.streamlit.app` | `fec-result-analytics.streamlit.app` |

**Automated Synchronization Workflow**:
1. When `main`'s exam monitor detects a published exam, `auto_pdf_mailer.py` completes scraping, generates PDF reports, and queues a payload in `v2_sync_tasks.json`.
2. A GitHub Actions workflow switches to `v2` and executes `v2_auto_sync.py`.
3. `v2_auto_sync.py` populates `result_finder.db`, updates student profiles, triggers readd detection, and auto-promotes provisional profiles.

---

## Repository Structure & Core Modules

```
├── app.py                          # Streamlit dashboard entry point
├── cli_scraper.py                  # Core scraping engine & interactive CLI
├── ui_components.py                # UI design system, CSS injection & cards
├── saved_profiles.json             # Flat-file roster storage
├── requirements.txt                # Python dependencies
├── college_logo.png & favicon.ico  # Branding assets
│
├── pages/
│   ├── results.py                  # URL-driven batch scan execution page
│   └── transcript.py               # Deep student academic transcript view
│
├── scraper_core/                   # Decoupled scraper package
│   ├── network.py                  # Connection pooling, retries & UA rotation
│   ├── parser.py                   # HTML regex extraction engine
│   ├── profiles.py                 # Roster management & process spinlocks
│   └── reports.py                  # Dynamic HTML report generator
│
├── exam_monitor/                   # 24/7 Automated publication watcher
│   ├── monitor.py                  # Exam publication detector & catalog scanner
│   ├── auto_pdf_mailer.py          # PDF generator, readd filter & mailer
│   ├── find_latest.py              # Latest exam discovery utility
│   ├── sync_state.py               # Monitor state reset tool
│   └── known_exams.json            # Tracked exam catalog per department
│
├── portal_monitor/                 # Portal health & security monitor
│   ├── health_check.py             # Uptime & WAF verification script
│   └── state.json                  # Last known portal health state
│
└── tests/
    └── test_exam_monitor_workflow.py # Automated workflow test suite
```

---

## Installation & Environment Setup

### Prerequisites
* Python 3.10 or higher
* `wkhtmltopdf` (required for PDF report generation in `exam_monitor`)

### Installation Commands

```bash
# 1. Clone the repository (main branch)
git clone https://github.com/fahimfaisal570/Result-finder.git -b main
cd Result-finder

# 2. Setup virtual environment
python -m venv .venv

# Activate on Windows PowerShell:
.\\.venv\\Scripts\\Activate.ps1

# Activate on Linux/macOS:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Launch Options

* **Streamlit Web Interface**:
  ```bash
  streamlit run app.py
  ```
* **Interactive Terminal CLI**:
  ```bash
  python cli_scraper.py
  ```

### Environment Variables (for Automation & Emailing)

Set these environment variables in your deployment environment or GitHub Repository Secrets:

| Secret Name | Description |
|---|---|
| `EMAIL_USER` | Gmail address for dispatching PDF alerts via SMTP_SSL. |
| `EMAIL_PASS` | Gmail App Password. |
| `RECEIVER_EMAIL` | Default administrator notification email. |
| `CSE_HEAD_EMAIL` | Email recipient for CSE department result packages. |
| `EEE_HEAD_EMAIL` | Email recipient for EEE department result packages. |
| `CIVIL_HEAD_EMAIL` | Email recipient for Civil department result packages. |

---

## Automated Test Suite

Run automated unit and integration tests for the monitoring workflow:

```bash
python -m unittest tests/test_exam_monitor_workflow.py -v
```

---

## License & Credits

Released under the **MIT License** — see [LICENSE](LICENSE).

Developed for academic excellence by **[Fahim Faisal](https://www.linkedin.com/in/fahimfaisal09)**.
