# Result Finder PRO — Academic Intelligence & Predictive Analytics Platform (`v2`)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30%2B-FF4B4B.svg)](https://streamlit.io/)
[![SQLite WAL](https://img.shields.io/badge/Database-SQLite%20WAL-003B57.svg)](https://www.sqlite.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Result Finder PRO (`v2`)** is an enterprise-grade academic analytics, trend forecasting, retake-aware intelligence, and research benchmarking platform built for Faridpur Engineering College (Constituent College of University of Dhaka). 

While the official university portal ([DUCMC](https://ducmc.du.ac.bd/)) restricts access to single-student, single-exam queries without historical aggregation, **Result Finder PRO `v2`** transforms portal data into a normalized SQLite relational database. It recomputes credit-weighted True CGPA metrics locally, identifies re-admitted students via subject fingerprinting, forecasts future academic performance using hybrid machine learning models, and offers dedicated strategic dashboards for students, faculty advisors, department heads, and academic researchers.

---

## Key Features & Product Capabilities

### 1. Dedicated Pending Retake & Improvement Finder ([`pages/pending_finder.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/pages/pending_finder.py))
A high-performance multi-stage search engine designed for department heads and academic advisors to track uncleared failures and improvement-eligible courses across entire department batches:
* **Stage 1 — Batch Eligibility Filter**: Automatically scans department profiles (CSE, EEE, Civil) to identify all cohorts that completed the specified semester.
* **Stage 2 — Database Candidate Extraction**: Filters students using exact grade point criteria (GP < 2.0 for failing retakes vs 2.0 <= GP <= 2.75 for improvement candidates).
* **Stage 3 — Live Portal Verification (30-Thread Concurrent Engine)**: Connects to the portal to query missing exam schedules and retake publications in real time, caching fresh records into the database.
* **Stage 4 — Deep Projection & Special Retake Classification**: Differentiates between regular retakes and Special Retakes (governed by institutional year-gap rules), producing downloadable CSV reports and metric breakdowns.

### 2. Hybrid Machine Learning Predictor ([`ml_predictor.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/ml_predictor.py))
Forecasts a student's remaining semester GPAs and predicted graduation CGPA using historical performance:
* **Dual-Model Blending**: Combines 1st-degree polynomial linear regression (`np.polyfit`) for directional trend with Exponential Moving Average (EMA, α = 0.6) for recency bias:

```text
Forecast GPA = 0.5 * LinearTrend(t) + 0.5 * EMA(t)
```

* **Credit-Weighted Graduation CGPA**: Computes projected final graduation CGPA based on exact course credit weights across all 8 semesters.
* **Trend Velocity & Uncertainty Scoring**: Measures grade point trajectory slopes and computes 95% confidence intervals (`prediction_confidence`, `confidence_margin`).

### 3. Interactive 8-Tab Analytics Dashboard ([`pages/analytics.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/pages/analytics.py))
* **Baseline Insight**: Current semester GPA distribution, batch mean/median, active student counts, honours roster, subject difficulty ranking, first-chance pass ratio, and subject grade breakdown (A+ to F).
* **Longitudinal Trends**: Multi-semester GPA trajectories, median overlays, individual student spotlights, peak/valley/consistency classifications, and retake clearing success rates.
* **Advanced Patterns**: Subject variance analysis, strategic quadrant mapping (High Performers, Improvers, Declining, Specialists), performance personas, and Pearson correlation heatmaps for subject dependency.
* **Cube Pivot**: Interactive student-by-subject and subject-by-student transposed grade matrices for instant classroom inspection.
* **Clearing List**: Departmental clearing summary displaying GPA, CGPA, result status, retake count, and improvement count with one-click CSV export.
* **GPA Projection & Graduation Planner**: Deep record audit comparing official vs locally recomputed True CGPA, target CGPA calculator, per-course projection with elective selection, and credit-cap enforcement.
* **Student Personal Success Plan**: Student-friendly performance summary, risk classification, plain-language action items, priority subjects, and an integrated longitudinal advisor follow-up timeline.
* **Strategic Insights Mode**: Executive summary highlighting batch momentum, honours pipeline, re-admission alerts, and bottleneck subject detection.

### 4. Research Infrastructure & Benchmark Suite ([`pages/research_dashboard.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/pages/research_dashboard.py) & [`research/`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/research/))
A comprehensive 20-item research and evaluation framework turning operational analytics into measurable, reproducible scientific evidence:
* **Structured Dataset & Taxonomy Layer ([`dataset.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/research/dataset.py))**: Generates ground-truth labeled datasets with SHA-256 salted student anonymization and formal academic state taxonomy (`Regular`, `Retake Candidate`, `Improvement Candidate`, `Re-Admitted`, `At-Risk`, `Stable`, `High Performer`, `Declining`).
* **Baseline Comparison Framework ([`baselines.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/research/baselines.py))**: Implements 10+ baseline models across forecasting (Naive, Moving Average, EMA, Linear), re-admission detection (Simple Overlap), and CGPA reconstruction.
* **Reproducible Experiment Runner ([`run_experiments.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/research/run_experiments.py))**: Evaluates models across time-based folds, generating standard performance metrics (MAE, RMSE, Precision, Recall, F1) and publication figures using Matplotlib.
* **Ablation Testing Suite ([`ablation.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/research/ablation.py))**: Quantifies system performance degradation when removing individual modules (EMA, Fingerprinting, Credit-weighting, Sync queue, File locking).
* **Explainability & Uncertainty Scoring ([`explainer.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/research/explainer.py))**: Outputs plain-language decision rationale and confidence scores for every non-trivial algorithm inference.
* **Temporal Dynamics & Difficulty Drift ([`temporal.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/research/temporal.py))**: Tracks semester-over-semester GPA deltas, course difficulty indices, and cohort-level shifts over time.
* **Diagnostic Error Analysis & Robustness ([`error_analysis.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/research/error_analysis.py), [`robustness.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/research/robustness.py))**: Evaluates 5 failure categories and tests fault tolerance under malformed HTML inputs and DB concurrency.
* **Manual Workflow Benchmarking ([`benchmark_manual.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/research/benchmark_manual.py))**: Measures automated system speedup factors (24x to 4500x time savings) against conventional manual university processes.
* **Formal Documentation ([`METHODS.md`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/research/METHODS.md), [`ETHICS.md`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/research/ETHICS.md))**: Provides complete mathematical specifications, algorithm pseudocode, salt protocols, and IRB privacy standards.

### 5. Retake-Aware Academic Calculations & Credit Engine ([`database.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/database.py))
* **Granular Subject Schema**: Stores individual course grades, credit hours, and attempt timestamps rather than relying on summary portal headers.
* **True CGPA Math**: Uses syllabus credit mappings from [`credit_mapping.json`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/credit_mapping.json). Best recorded grades are used for effective CGPA calculations, while failed subjects remain tracked as pending until cleared.
* **Re-Admitted Student Detection**: Compares candidate subject patterns against regular batch fingerprints (≥ 50% subject overlap and ≥ 70% credit load ratio) to detect re-admitted students and ignore retake guests.

### 6. Automated Background Synchronization ([`v2_auto_sync.py`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/v2_auto_sync.py))
* **Cross-Branch Interoperability**: Ingests automated scan tasks queued from `main`'s 24/7 exam watcher.
* **Readd Roster Auto-Population**: Automatically inserts re-admitted students into target profiles and logs notifications in [`readd_notifications.json`](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/readd_notifications.json).
* **Provisional Profile Auto-Promotion**: Converts provisional student rosters into active profiles upon receiving first published exam results.

---

## Architecture & System Design

```text
                                +-----------------------------+
                                | DUCMC Portal (ducmc.du.ac.bd)|
                                +--------------+--------------+
                                               |
                                               v
                                +--------------+--------------+
                                | cli_scraper.py (Requests)   |
                                +--------------+--------------+
                                               |
                                               v
                                +--------------+--------------+
                                | SQLite database.py (v6 WAL) |
                                | Storage: result_finder.db   |
                                +--------------+--------------+
                                               |
       +--------------------+------------------+--------------------+--------------------+--------------------+
       |                    |                  |                    |                    |                    |
       v                    v                  v                    v                    v                    v
 app.py (Dashboard)   pages/results.py   pages/transcript.py  pages/analytics.py   pages/pending_finder.py pages/research_dashboard.py
 (Batch Profiles)     (Batch Scraper)    (Student History)    (8 Analytics Tabs)   (Retake/Impr Engine)   (Research & Benchmarks)
                                                                    |                                             |
                                                                    v                                             v
                                                              ml_predictor.py                               research/
                                                              (EMA + Polyfit)                               (Dataset, Baselines,
                                                                                                            Ablation & Metrics)
```

---

## Database Model & Schema

The application uses SQLite in **Write-Ahead Logging (WAL)** mode with thread-local connections, busy timeouts, and idempotent v6 auto-migrations.

| Table | Primary Keys / Constraints | Description |
|---|---|---|
| `profiles` | `profile_name` | Stores batch metadata (department, session, registration range, provisional flags). |
| `students` | `(profile_name, reg_no, sess_id)` | Roster of students belonging to each batch profile. |
| `exam_results` | `(profile_name, reg_no, exam_id, sess_id)` | Exam summary metrics (GPA, CGPA, pass status, total points, credits). |
| `subject_grades` | `(profile_name, reg_no, exam_id, subject_code, sess_id)` | Granular course grade records (Grade Point, Letter Grade, Credit Hours). |
| `research_records` | `record_id` (Auto-increment) | Anonymized research dataset with ground-truth labels and academic taxonomy. |
| `record_lineage` | `id` (Auto-increment) | Provenance tracking for data lineage and cross-branch sync execution. |
| `meta_cache` | `key` | Expiring key-value cache for portal exam catalogs and session data. |

---

## Directory Structure & Core Modules

```
├── app.py                          # Streamlit main entry point & profile manager
├── cli_scraper.py                  # Multi-threaded portal scraping & parsing engine
├── database.py                     # SQLite schema (v6), WAL manager, credit math & lineage
├── ml_predictor.py                 # Hybrid EMA + Polyfit grade forecasting model with 95% CI
├── ui_components.py                # Design tokens, CSS injection & reusable cards
├── v2_auto_sync.py                 # Auto-sync worker for external monitor tasks
├── credit_mapping.json             # Department & semester course credit mappings
├── readd_notifications.json        # Persistent store for detected re-admitted students
├── requirements.txt                # Python dependencies (including matplotlib)
├── Launch_Dashboard.bat            # One-click Windows launch script
│
├── pages/
│   ├── analytics.py                # 8-tab interactive analytics & success plans
│   ├── pending_finder.py           # Multi-stage retake & improvement search engine
│   ├── research_dashboard.py       # Research benchmarks, ablation charts & error viewer
│   ├── results.py                  # Live batch scanning & HTML report viewer
│   └── transcript.py               # Single-student multi-session academic transcript
│
├── research/                       # Research Infrastructure & Benchmark Framework
│   ├── config.py                   # Centralized sensitivity thresholds
│   ├── dataset.py                  # SHA-256 salted dataset builder & taxonomy enum
│   ├── baselines.py                # 10+ baseline algorithms for comparative research
│   ├── metrics.py                  # Thread-safe JSONL metric logger & decorators
│   ├── retroactive.py              # Main-branch artifact metric parser
│   ├── run_experiments.py          # Benchmark experiment pipeline & figure generator
│   ├── ablation.py                 # Component ablation study runner
│   ├── explainer.py                # Decision explainability & confidence score calculator
│   ├── temporal.py                 # Time-series, difficulty drift & cohort trend engine
│   ├── error_analysis.py           # Diagnostic failure analyzer
│   ├── case_studies.py             # 5 anonymized student archetype case study generator
│   ├── benchmark_manual.py         # Time savings & speedup comparison vs manual workflow
│   ├── robustness.py               # Fault tolerance & stress testing suite
│   ├── validation_survey.py        # Likert-scale user validation survey template generator
│   ├── METHODS.md                  # Formal algorithm mathematical specifications
│   ├── ETHICS.md                   # Privacy, salt security & IRB compliance standards
│   └── results/                    # Benchmark JSON logs, CSV tables & Matplotlib plots
│
└── tests/                          # Automated unit and integration test suite
    ├── test_database.py            # Database schema, queries & credit math tests
    ├── test_full_system.py         # End-to-end analytics & scraper integration tests
    ├── test_ml_predictor.py        # ML forecasting mathematical validation tests
    └── test_exam_monitor_workflow.py # Monitor workflow & readd detection tests
```

---

## Installation & Setup

### Prerequisites
* Python 3.10 or higher
* Git

### Step-by-Step Installation

```bash
# 1. Clone the repository and switch to v2 branch
git clone https://github.com/fahimfaisal570/Result-finder.git
cd Result-finder
git checkout v2

# 2. Create and activate a virtual environment
python -m venv .venv

# On Windows PowerShell:
.\\.venv\\Scripts\\Activate.ps1

# On Linux/macOS:
source .venv/bin/activate

# 3. Install required dependencies
pip install -r requirements.txt
```

### Launching the Dashboard

```bash
streamlit run app.py
```
Alternatively, on Windows systems, double-click `Launch_Dashboard.bat`.

---

## Running Research Benchmarks & Tests

```bash
# Run reproducible research experiment pipeline
python -m research.run_experiments

# Run ablation study suite
python -m research.ablation

# Run robustness & stress test suite
python -m research.robustness

# Run failure analysis
python -m research.error_analysis

# Run full automated unit & integration test suite
python -m unittest tests/test_database.py -v
python -m unittest tests/test_full_system.py -v
python -m unittest tests/test_ml_predictor.py -v
```

---

## How `main` and `v2` Work Together

Both branches run in tandem:

| Feature / Aspect | `main` Branch | `v2` Branch |
|---|---|---|
| **Storage Backend** | Flat-file JSON (`saved_profiles.json`) | Relational Database (`result_finder.db` SQLite WAL) |
| **Primary Focus** | Live batch viewing, PDF reports, 24/7 Portal Watcher | Advanced Analytics, ML Forecasting, Research Framework |
| **Deployed App** | `fec-result-finder.streamlit.app` | `fec-result-analytics.streamlit.app` |

---

## License & Credits

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

Developed for academic excellence by **[Fahim Faisal](https://www.linkedin.com/in/fahimfaisal09)**.
