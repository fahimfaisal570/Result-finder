# Result Finder PRO v2

Academic Data Pipeline & Analytics Platform

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![UI](https://img.shields.io/badge/UI-Streamlit-red)
![Database](https://img.shields.io/badge/Database-SQLite-blue)
![Automation](https://img.shields.io/badge/Automation-Enabled-purple)
![Status](https://img.shields.io/badge/Status-Advanced-orange)

---

## 🚀 Overview

v2 evolves the system from a scraper into a stateful data platform with persistence, analytics, and automation.

## Adds

- SQLite data model
- Transcript-level analytics
- Automated monitoring + reporting
- Modular UI

---

## 🧭 System Flow

Input → Scraper → Parser → Database → Analytics → Dashboard → Reports

---

## 🧠 Architecture (v2)

### Ingestion

- Threaded scraping, keep-alive, retry/backoff

### Parsing

- Regex extraction → structured records

### Data (SQLite)

- profiles • students • results • subjects

### Intelligence

- Profile system (stateful batches)
- Session inference
- Re-add detection (cross-batch discovery)
- Student tracking across exams

### Analytics

- Merit ranking • distributions • batch comparisons • transcripts

### Interface

- Streamlit multi-page UI (modular components)

### Automation

- Detect new exams → match profiles → batch scan → PDF → email

---

## 🗄️ Data Model (simplified)

profiles(id, name, program, session, ranges, created_at)
students(id, roll, name, batch, program_id)
results(id, student_id, exam_id, total_mark, position, grade, status)
subjects(id, result_id, code, name, credit, mark, grade)

---

## ⚡ Performance

- Lower latency via persistent connections
- DB-backed queries scale better than JSON
- Parallel batch execution

---

## ✨ Features

- Persistent storage (SQLite)
- Saved profiles + batch workflows
- Transcript analytics (credit-aware)
- PDF credit extraction
- Automated monitoring & email reports
- Modular UI + pages
- Test suite (DB + system)

---

## 📄 PDF & Credit Mapping

- Extract subject–credit mappings from PDFs
- Enables accurate GPA/transcript analytics

---

## 🔁 Automation Pipeline

Exam Detection → Profile Matching → Batch Scan → PDF → Email

---

## 🧪 Testing

- Database tests
- End-to-end system checks
- Integration stubs

---

## 🛠️ Tech Stack

Python • Streamlit • SQLite • "re" • Threading/Queue • PDF libs • SMTP

---

## ⚠️ Limitations

- Regex parsing still brittle
- Partial separation of concerns
- Heuristic-based matching in automation

---

## 🔭 Roadmap

- Parser abstraction (DOM/API)
- Service layer (clean boundaries)
- API-based ingestion
- Cloud deployment (scalable backend)

---

## ▶️ Quick Start

pip install -r requirements.txt
streamlit run app.py

---

## 📌 Positioning

Not a scraper — an event-driven data pipeline with analytics + automation.

---

## 🔄 Evolution

v1 → extraction + analytics
v2 → platform (data + intelligence + automation)