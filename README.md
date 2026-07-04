# Result Finder PRO (v2)

> **Full-Stack Academic Intelligence Platform**  
> *Transforms a one-student-at-a-time university portal into a batch-powered analytics engine with graduation planning, automated monitoring, and real-time strategic intelligence.*

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit_1.58-FF4B4B?logo=streamlit&logoColor=white)
![SQLite](https://img.shields.io/badge/Database-SQLite_WAL-003B57?logo=sqlite&logoColor=white)
![Altair](https://img.shields.io/badge/Charts-Altair_6-1F77B4)
![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub_Actions-2088FF?logo=githubactions&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## The Problem

The DUCMC portal (`ducmc.du.ac.bd`) — the only official source of academic results for Faridpur Engineering College — has critical limitations:

- **One-student-at-a-time lookups** — viewing a batch of 60+ students takes hours of manual data entry
- **No batch analytics** — no GPA distributions, trends, risk detection, or cross-batch comparisons
- **Incorrect CGPA calculations** — the portal doesn't always handle retakes/improvements correctly
- **No automated alerts** — faculty must manually check whether new results have been published
- **No graduation planning** — students can't project their graduation CGPA or plan retake strategies

## The Solution

This `v2` branch is the **database-backed analytics rewrite** of Result Finder. It scrapes the university portal with concurrent threads, stores everything in a relational SQLite database with ACID guarantees, independently verifies portal-claimed GPAs, and provides a 6-tab OLAP analytics dashboard with graduation projection tools.

> *Looking for the production CLI scraper & email automation pipeline? See the [`main` branch](https://github.com/fahimfaisal570/Result-finder/tree/main). Both branches are deployed simultaneously and [work together](#how-main-and-v2-work-together).*

---

## Features

### Scraping Engine (`cli_scraper.py` — 1,953 lines)

| Feature | Description |
|---------|-------------|
| **Concurrent Batch Scanning** | 10–15 worker threads with queue-based task distribution scan an entire batch in minutes |
| **SSL Connection Pre-Warming** | 6 parallel TLS handshakes pre-established on startup — cold start reduced from ~20s to ~3s |
| **Auto Session Discovery** | Tries all sessions when `sess_id="AUTO"` to locate readmitted students from different batches |
| **Smart Exam Classification** | Scoring system auto-classifies exams into Main Semesters / Retake / Improvement with probe verification |
| **User-Agent Rotation** | 5 browser UA strings with exponential backoff (4 retries + jitter) |
| **HTML Report Generation** | Print-optimized reports with registration tables, scholarship eligibility, and CGPA rankings |
| **Academic Transcripts** | Dark-themed chronological per-student record across all exam appearances |

### Database Layer (`database.py` — 2,605 lines)

| Feature | Description |
|---------|-------------|
| **ACID-Safe Storage** | SQLite with WAL journal mode, 30s busy timeout, foreign key enforcement |
| **Thread-Local Connection Pool** | Connections keyed by `DB_PATH`, wrapped for transaction management |
| **Idempotent Upserts** | `INSERT OR REPLACE` / `ON CONFLICT DO UPDATE` — safe to re-run any operation |
| **5 Schema Migrations** | v1→v5, all idempotent, auto-run on startup |
| **Shadow GPA Auditing** | Independently computes GPA from official syllabus credit mappings, stores alongside portal-claimed values, logs drift |
| **Retake-Aware CGPA** | Best grade across ALL attempts per subject. Credit-weighted. Improvement vs retake classification |
| **Compound Indices** | `idx_subject_grades_lookup`, `idx_exam_results_lookup`, `idx_students_lookup`, `idx_subject_grades_exam`, `idx_exam_results_exam` |

### Database Schema

```
profiles ─┬─→ students         (profile_name, reg_no, sess_id) UNIQUE
           ├─→ exam_results     (profile_name, reg_no, exam_id, sess_id) UNIQUE
           └─→ subject_grades   (profile_name, reg_no, subject_code, exam_id, sess_id) UNIQUE

scan_log    (profile_name, exam_id) PK — tracks last scan timestamp
meta_cache  (key) PK — JSON key-value cache with TTL
```

### Web Dashboard (4 pages)

**Home (`app.py`)** — Two modes:
- **Interactive Scan** — Select program/session/exam, enter registration ranges, add senior re-add batches, launch scraper
- **Saved Profiles** — Select batch, view student list with transcript links, see classified exams, one-click "Batch Scan All Main Exams", add individual students from other sessions

**Results (`pages/results.py`)** — Two modes:
- **Single Exam** — Runs scraper, renders inline HTML report, save to analytics DB
- **Batch Mode** — Sequentially scans all main semester exams, saves all results, redirects to dashboard

**Transcript (`pages/transcript.py`)** — Deep CLI-native scan:
- Fetches student's full academic history across every exam
- Smart scope: filters exams to cohort year onward (with 1-year buffer)
- Per-student session resolution for readd students

**Analytics (`pages/analytics.py` — 2,183 lines)** — See below.

### Analytics Dashboard — 6 Tabs

#### Tab 1: Baseline Insight
- **GPA Distribution** — 40-bin histogram with adaptive axis (removes 0–2 void)
- **First-Chance Pass Ratio** — Donut chart showing % passing all subjects on first attempt
- **Subject Difficulty Ranking** — Horizontal bar chart sorted by mean GP (passing grades ≥2.0 only)
- **Achievement Gradient** — Rank vs CGPA line chart with adaptive Y-axis
- **Grade Distribution** — 100% stacked bar per subject (A+ through F, curated 10-color scale)

#### Tab 2: Trends
- **Batch GPA Trajectory** — Multi-line chart across semesters with dashed median overlay and student spotlight selector
- **Student Trajectory Metrics** — Peak, valley, consistency (1−σ), trajectory classification via linear regression (Rising / Declining / V-shape Recovery / Stable)
- **Retake & Improvement Success Tracker** — Total retakes, success rate, avg GP gain, per-subject breakdown
- **Cross-Batch Benchmarking** — Compare multiple profiles on same semester with density curve overlay

#### Tab 3: Advanced Patterns
- **Subject Variance Boxplots** — Min-max per subject, clipped [2.0, 4.0]
- **Performance Personas Scatter** — Strategic quadrant with 24-color archetype coding (Top/Steady/Average + Improving/Declining + Promotion-based overrides). Spotlight ring, ⚠️ danger overlay, interactive zoom
- **Subject Dependency Heatmap** — Pearson correlation matrix (red-blue scheme)

#### Tab 4: Cube Pivot
- Student × Subject GP matrix or transposed Subject × Student view

#### Tab 5: Clearing List
- Sortable table (reg, name, GPA, CGPA, status, improvement/retake counts) with CSV export

#### Tab 6: GPA Projection & Graduation Planner
- **Deep Analysis** per student — fetches full portal history, computes True CGPA, precise target GPA, pending retakes
- **Semester-wise Breakdown** — Official vs Adjusted GPA/CGPA per semester with colored deltas
- **Retake/Improvement Simulation** — Toggle checkboxes and set target GPs to see adjusted CGPA in real-time
- **Graduation Target Calculator** — Slider for target CGPA → shows required avg GPA per remaining semester
- **Graduation CGPA Simulator** — Summary mode (GPA number per semester) or Detailed mode (per-course GP slider with elective checkboxes and credit cap enforcement for CSE 7–8 / Civil 8)
- Paginated student cards (10/page) with `@st.fragment` isolation

### Strategic Analysis Brief
When enabled, shows an executive summary above the tabs:
- **Batch Momentum** — Mean GPA vs historical CGPA trend
- **Honours Pipeline** — Count and % of students with CGPA ≥ 3.50
- **Risk Detection** — Readd alerts (mathematically impossible to recover), failed promotion, critical at-risk, at-risk students — each with named student lists and individual "Deep Analysis" buttons
- **Bottleneck Subject** — Lowest cohort average GP
- **Synergy Detection** — Strongest Pearson correlation between subject pairs

### Provisional Batch System
- Create student rosters **before** exam results are published
- System auto-promotes to full profile on first result import
- Provisional batches get a standalone Graduation CGPA Simulator with all 8 semesters as inputs

### Readd (Re-admitted Student) Detection
Detects senior batch students repeating a year using **subject-overlap fingerprinting**:
1. Builds reference fingerprint from regular batch (subject codes taken by ≥30% of students)
2. Scans senior batch students against the exam
3. Genuine readd: ≥50% subject overlap AND ≥70% load ratio
4. Ghosts (improvement/retake-only): filtered out
5. Readd students automatically added to profile roster

### Automation & Monitoring
- **Exam Publication Watcher** (`exam_monitor/monitor.py`) — GitHub Actions cron polls portal for new exams across CSE, EEE, Civil
- **Auto PDF Reports** (`exam_monitor/auto_pdf_mailer.py`) — Identifies batch via empirical probing, scrapes, detects readds, generates PDF, emails to admin + dept heads
- **Cross-Branch Sync** (`v2_auto_sync.py`) — Receives sync tasks from `main` branch, re-scrapes, saves to SQLite, runs readd detection
- **Portal Uptime Monitor** (`portal_monitor/health_check.py`) — Alerts only on state transitions (online↔offline), uses positive verification (whitelist approach)

---

## How `main` and `v2` Work Together

Both branches are deployed simultaneously. When `main`'s exam monitor detects a new exam:

```
main: monitor.py detects new exam
  → auto_pdf_mailer.py scrapes, generates PDF, emails it
  → Queues sync task to v2_sync_tasks.json
  
v2: v2_auto_sync.py receives task
  → Re-scrapes same students into SQLite database
  → Runs readd detection
  → Auto-promotes provisional profiles
```

| Branch | Storage | Deployment | Primary Role |
|--------|---------|------------|-------------|
| `main` | `saved_profiles.json` | `fec-result-finder.streamlit.app` | Exam monitoring, PDF reports, result viewing |
| `v2` | `result_finder.db` (SQLite) | `fec-result-analytics.streamlit.app` | Analytics, projections, deep analysis |

---

## Repository Structure

```
├── app.py                          # Streamlit entry point (445 lines)
├── cli_scraper.py                  # Scraping engine (1,953 lines)
├── database.py                     # SQLite persistence layer (2,605 lines)
├── ui_components.py                # Design system — CSS/JS/fonts (311 lines)
├── pdf_extractor.py                # Syllabus PDF → credit_mapping.json (153 lines)
├── v2_auto_sync.py                 # Cross-branch sync worker (260 lines)
├── credit_mapping.json             # Department-isolated credit weights
├── requirements.txt                # 7 dependencies
├── Launch_Dashboard.bat            # Windows one-click launcher
│
├── pages/
│   ├── analytics.py                # OLAP analytics dashboard (2,183 lines)
│   ├── results.py                  # Exam scan execution page (256 lines)
│   └── transcript.py               # Individual student record (170 lines)
│
├── exam_monitor/
│   ├── monitor.py                  # Exam publication detector (208 lines)
│   ├── auto_pdf_mailer.py          # PDF report generator + emailer (488 lines)
│   ├── find_latest.py              # Latest exam finder utility (35 lines)
│   ├── sync_state.py               # State reset utility (29 lines)
│   └── known_exams.json            # Known exam IDs per department
│
├── portal_monitor/
│   ├── health_check.py             # Portal uptime monitor (194 lines)
│   └── state.json                  # Last known portal status
│
├── tests/
│   ├── test_database.py            # 18+ unit tests (653 lines)
│   └── test_full_system.py         # 5 integration tests (180 lines)
│
└── .github/workflows/
    └── portal_health.yml           # GitHub Actions uptime workflow
```

**Total:** ~9,400+ lines of application code across 15 Python modules.

---

## Quick Start

### 1. Install
```bash
git clone https://github.com/fahimfaisal570/Result-finder.git -b v2
cd Result-finder
pip install -r requirements.txt
```

### 2. Launch
```bash
streamlit run app.py
```
The database (`result_finder.db`) auto-initializes with all schema migrations on first run.

**Windows shortcut:** Double-click `Launch_Dashboard.bat`.

### 3. First Steps
1. Switch to **Saved Profiles** mode in the sidebar
2. Create a provisional batch (e.g., `cse 12`) with registration ranges
3. When results are published, click **Check Portal & Import** to scan
4. Navigate to **Analytics** for full batch analysis

---

## Testing

```bash
# Database ACID, migrations, CGPA math, projections
python -m unittest tests/test_database.py -v

# CLI ↔ Database integration, retake logic, connection pooling
python -m unittest tests/test_full_system.py -v
```

23+ tests covering: idempotency, FK cascading, retake-aware CGPA, longitudinal parsing, graduation projection math, connection pre-warming, semester code parsing, and more.

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| streamlit | 1.58.0 | Multi-page web dashboard |
| pandas | 3.0.3 | DataFrames, pivots, aggregations |
| numpy | 2.5.0 | Linear regression, statistics |
| altair | 6.2.2 | All interactive visualizations (20+ chart types) |
| requests | 2.34.2 | HTTP with connection pooling |
| pypdf | 6.14.2 | Syllabus PDF parsing |
| pdfkit | 1.0.0 | HTML → PDF batch report generation |

---

## License & Credits

Released under the **MIT License**.

Developed for academic excellence — bridging legacy university portals and modern data needs.

**Author:** [Fahim Faisal](https://www.linkedin.com/in/fahimfaisal09)