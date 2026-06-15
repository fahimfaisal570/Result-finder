# Result Finder PRO (main)

> **Academic Scraper & Automated Reporting Pipeline**  
> *Production-ready academic data extraction, automated email alerts, and lightweight dashboard.*

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Storage](https://img.shields.io/badge/Storage-JSON-lightgrey)
![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub_Actions-2088FF?logo=githubactions&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 🎯 The Vision

University portals typically show results one student at a time, making cohort-wide review slow and manual. 

The `main` branch serves as the **lightweight, production-grade automated scraper and reporting system**. It handles result scraping via high-speed connection pools, parses structured content, generates offline HTML transcripts or PDF reports, and can automatically deliver them to department heads via email alerts. Additionally, it offers a lightweight interactive Streamlit dashboard backed by flat JSON file storage.

*(Looking for the database-backed version with SQLite persistence, advanced OLAP analytics, connection pre-warming, and a full GPA projection simulator? Switch to the [`v2` branch](https://github.com/fahimfaisal570/Result-finder/tree/v2).)*

---

## ⚡ Core Features (main)

### 🕵️‍♂️ Concurrent CLI Scraper (`cli_scraper.py`)
- **HTTP Connection Pool:** Uses persistent connections to bypass TLS handshake overhead, speeding up scraping by 3x.
- **Stealth & Resilience:** Implements dynamic User-Agent rotation, cookie pinning (PHPSESSID tracking), and exponential backoff to handle portal rate limits smoothly.
- **Regex Parsing:** Employs 40+ resilient regex patterns to structure messy HTML tables across 3 different department formats without relying on heavy DOM parsers like BeautifulSoup.

### 📊 Lightweight Streamlit Dashboard (`app.py`)
A fast, lightweight interactive dashboard using simple JSON storage:
- **Interactive Scans (`app.py`):** Define student registration ranges and run batch scans directly from the UI.
- **Saved Profiles:** View, rename, and manage cohort lists stored in `saved_profiles.json`.
- **Roster Views (`pages/results.py`):** Display search lists and student status.
- **Transcripts (`pages/transcript.py`):** View complete academic records with formatted historical tables.

### 🤖 Monitoring & Automation (`exam_monitor/`)
- **Portal Watching (`monitor.py`):** Periodically queries the portal for new exam publications.
- **Automated Delivery (`auto_pdf_mailer.py`):** Once a new exam is found, it crawls the cohort, generates a formatted PDF, and delivers it via SMTP.
- **GitHub Actions Integration:** Pre-configured cron job configuration (`exam_monitor.yml`) to run checking schedules in the cloud automatically.

---

## 📁 Repository Structure

- `app.py`: Streamlit dashboard entry point.
- `cli_scraper.py`: Core scraper script and thread runner.
- `saved_profiles.json`: Lightweight JSON profile storage database.
- `requirements.txt`: Project dependencies.
- `college_logo.png` & `favicon.ico`: UI branding assets.
- `pages/`: Multi-page streamlit dashboards (`results.py` and `transcript.py`).
- `scraper_core/`: Core modules encapsulating the scraper logic:
  - `network.py`: Connection pooling, retries, and request wrappers.
  - `parser.py`: HTML regex search extraction and data structuring.
  - `profiles.py`: Roster saving, profiles loader, and files manager.
  - `reports.py`: Data aggregation and HTML transcript generation.
- `exam_monitor/`: Monitoring scripts and alert components:
  - `monitor.py`: Exam watcher script checking DUCMC.
  - `auto_pdf_mailer.py`: PDF aggregator, scraper wrapper, and SMTP alert mailer.
  - `find_latest.py`: Latest published exam checking utility.
  - `sync_state.py`: Syncs cache states.
  - `known_exams.json`: Tracked exams database.
- `tests/`: Automated test suite (`test_exam_monitor_workflow.py`).

---

## 🚀 Quick Start

### 1. Installation
Ensure you have Python 3.10+ installed.

```bash
git clone https://github.com/fahimfaisal570/Result-finder.git -b main
cd Result-finder
pip install -r requirements.txt
```

### 2. Launch Streamlit Dashboard
```bash
streamlit run app.py
```

### 3. Run Scraper via CLI
You can execute scans directly from the terminal:
```bash
python cli_scraper.py
```

---

## 🧪 Testing

Run the automated monitoring workflow tests:

```bash
python -m unittest tests/test_exam_monitor_workflow.py -v
```

---

## 📄 License & Credits

Released under the **MIT License**.

Developed for academic excellence to automate and streamline result distribution.

**Author:** [Fahim Faisal](https://www.linkedin.com/in/fahimfaisal09)