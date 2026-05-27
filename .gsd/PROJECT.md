# Result Finder — Project Specifications

*Streamlit-based academic result analytics dashboard that scrapes and analyzes university exam results (DUCMC portal) from Bangladesh. Modernized as a web application on the `v2` branch, discarding mobile-only limitations.*

## Core Tech Stack
- **Frontend:** Streamlit (Python web framework)
- **Backend:** Python 3 (CLI scraper, database layer)
- **Database:** SQLite with WAL mode, robust 30s connection timeout and busy retries
- **Networking:** Standard `requests.Session` thread-safe connection pooling
- **Pages:** `app.py` (main), `pages/results.py`, `pages/analytics.py`, `pages/transcript.py`

## Development Conventions
- All SQL queries use parameterized statements (no string interpolation)
- Database access exclusively through `database.py` helper functions
- `get_connection()` returns auto-closing `ClosedOnExitConnection` wrapper
- Streamlit UI components isolated in `ui_components.py`
- Unit tests in `tests/test_database.py` and `tests/test_full_system.py`

## Key Files
- `database.py` — SQLite layer with compound query indices
- `cli_scraper.py` — Scraper engine with pre-compiled regex, exponential backoff, and modern requests pooling
- `app.py` — Main Streamlit dashboard
- `pages/analytics.py` — Analytics dashboard
- `pages/results.py` — Results page
- `pages/transcript.py` — Transcript page
- `ui_components.py` — Shared CSS/JS injection
