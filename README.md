Result Finder PRO

Batch-oriented academic result extraction & analytics engine

"Python" (https://img.shields.io/badge/Python-3.10%2B-blue)
"UI" (https://img.shields.io/badge/UI-Streamlit-red)
"Storage" (https://img.shields.io/badge/Storage-JSON-lightgrey)
"Concurrency" (https://img.shields.io/badge/Concurrency-Threading-green)
"Status" (https://img.shields.io/badge/Status-Stable-success)



🚀 Overview

Result Finder PRO turns fragmented result pages into structured, batch-level datasets for analysis.

What it does

- Scrapes results across ranges (multi-batch)
- Normalizes and aggregates data
- Computes rankings, pass/fail stats, and batch insights
- Tracks students across exams



🧭 Architecture (v1)

Input (ranges/profiles)
        ↓
Scraper (threaded, keep-alive, retry)
        ↓
Parser (regex extraction)
        ↓
Storage (JSON profiles)
        ↓
Analytics (ranking, stats)
        ↓
CLI / Streamlit UI



⚡ Performance

- Threaded batch execution
- Connection reuse (Keep-Alive)
- Efficient range scanning

«Throughput depends on network + portal behavior.»



✨ Features

- Program/session discovery
- Main vs retake exam filtering
- Multi-range scanning
- Saved profiles (batch persistence)
- Student history tracking
- Merit lists & pass/fail analytics
- CLI + dashboard workflow



🧱 Key Modules

- Scraper: request engine, retries, pooling
- Parser: regex-based extraction
- Profiles: JSON persistence
- Reports: analytics computations



🛠️ Tech Stack

Python • Streamlit • "re" • Threading/Queue • JSON • "urllib"



⚠️ Limitations

- Fragile to HTML changes (regex)
- Loose data model (dict-heavy)
- Coupling between core logic and UI



🔭 Next (direction)

- Structured DB layer
- Parser abstraction
- Clear service boundaries
- Automation workflows



▶️ Quick Start

pip install -r requirements.txt
streamlit run app.py



📌 Positioning

Not just a scraper — a batch data extraction + analytics engine.