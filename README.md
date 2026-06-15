# Result Finder PRO (v2)

> **Academic Data Platform & Analytics Platform**  
> *From manual result-checking to automated intelligence — built for real university operations.*

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 🎯 The Vision

University portals typically show results one student at a time, lacking batch queries, analytics, or longitudinal exports. 
**Result Finder PRO** automates result scraping and structures the data into a relational database to enable interactive analysis.

This `v2` branch is a complete data platform rewrite, introducing persistent database storage, OLAP-style analytics, and academic planning features.

*(Looking for the production CLI scraper & email automation? Switch to the [`main` branch](https://github.com/fahimfaisal570/Result-finder/tree/main).)*

---

## ⚡ Core Features (v2)

### 📊 Advanced Multi-Page Streamlit Dashboard
A multi-page interface replacing command-line output with rich, interactive visualizations.
- **Home Dashboard (`app.py` & `ui_components.py`):** Program and session configuration, interactive scraper runs, and batch roster previews.
- **Roster & Exam Results (`pages/results.py`):** Dynamic result cards showing GPAs, CGPA standings, and fail/promotion status.
- **Academic Transcripts (`pages/transcript.py`):** Full chronological student grade history with interactive visualizations.
- **Analytics & Projections (`pages/analytics.py`):** Merit list rankings, cross-batch comparisons, GPA projections with a simulator supporting elective check-boxes, and retake simulations.

### 🗄️ Normalized Database Storage (`database.py`)
Relational SQLite database running in WAL mode with compound indices (`idx_subject_grades_exam`, `idx_exam_results_exam`) for page load optimization.
- **Idempotent Upserts:** Safe double-saves with unique constraint rules.
- **Schema Migrations:** Integrated, versioned migrations (v2 through v5) run automatically on startup.
- **Connection Pooling:** A thread-local SQLite connection pool keyed by database path.

### 🧠 Intelligent Analytics & Scraper (`cli_scraper.py`)
- **SSL Connection Pre-Warming:** Pre-establishes TCP/TLS handshakes concurrently using thread pools, reducing dashboard scan start latency from 20s to under 3s.
- **Shadow GPA Audit:** Validates portal-calculated GPAs against a local database of official course credits (`credit_mapping.json`) to detect rounding drift.
- **Retake-Aware CGPA Engine:** Chronologically resolves repeated courses to compute true cumulative standings using window functions.

### 🤖 Monitoring & Automation Suites
- **Exam Publication Watcher (`exam_monitor/`):** Regularly checks the DUCMC portal for newly published results, maps them to saved batches, and delivers PDF reports to faculty via SMTP.
- **Portal Health Monitoring (`portal_monitor/`):** Decooupled whitelist-based uptime check verifying server signatures and notifying administrators of portal transitions.

---

## 📁 Repository Structure

- `app.py`: Streamlit entry point.
- `database.py`: Database operations, connection pool, and migrations.
- `cli_scraper.py`: Concurrent scraper engine, TLS pre-warming, and cohort classification.
- `ui_components.py`: Injected HTML/CSS styling and common UI headers.
- `credit_mapping.json`: Official department curriculum course codes and credit weights.
- `v2_auto_sync.py` & `auto_pdf_main.py`: Automated scanning and sync drivers.
- `pdf_extractor.py`: PDF parser utility.
- `config.py`: Local configuration settings.
- `pages/`: Multi-page streamlit dashboards (`analytics.py`, `results.py`, `transcript.py`).
- `exam_monitor/`: Auto scan, PDF generation, and SMTP notifier scripts.
- `portal_monitor/`: DUCMC uptime health check suite.
- `scripts/`: Development and database investigation utilities (e.g., college boundary detection, database inspectors).
- `tests/`: Unit and integration testing suite.

---

## 🚀 Quick Start

### 1. Installation
Ensure you have Python 3.10+ installed.

```bash
git clone https://github.com/fahimfaisal570/Result-finder.git -b v2
cd Result-finder
pip install -r requirements.txt
```

### 2. Launch Streamlit UI
```bash
streamlit run app.py
```
*The database schema (`result_finder.db`) will initialize automatically on first run.*

### 3. Run Automated Syncing (Optional)
Ensure SMTP variables are configured, then execute:
```bash
python v2_auto_sync.py
```

---

## 🧪 Testing

Run the test suite covering database ACID logic, migrations, and calculations:

```bash
python -m unittest tests/test_database.py -v
python -m unittest tests/test_full_system.py -v
```

---

## 📄 License & Credits

Released under the **MIT License**.

Developed for academic excellence to bridge the gap between legacy university portals and modern data needs.

**Author:** [Fahim Faisal](https://www.linkedin.com/in/fahimfaisal09)