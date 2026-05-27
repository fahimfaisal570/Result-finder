# Result Finder — Code Quality Remediation

*Streamlit-based academic result analytics dashboard that scrapes and analyzes university exam results (DUCMC portal). The focus of this remediation is fixing all Critical, Major, and Minor issues identified by the Code Rabbit senior code review.*

## Core Tech Stack
- **Frontend:** Streamlit (Python web framework)
- **Backend:** Python 3.12 (CLI scraper, database layer)
- **Database:** SQLite with WAL mode
- **Networking:** Raw `http.client` keep-alive connection pool
- **Pages:** `app.py` (main), `pages/results.py`, `pages/analytics.py`, `pages/transcript.py`

## Development Conventions
- All SQL queries use parameterized statements (no string interpolation)
- Database access exclusively through `database.py` helper functions
- `get_connection()` returns auto-closing `ClosedOnExitConnection` wrapper
- Streamlit UI components isolated in `ui_components.py`
- Unit tests in `tests/test_database.py` and `tests/test_full_system.py`

## Key Files
- `database.py` — SQLite layer (2226 lines)
- `cli_scraper.py` — HTTP scraper engine (1911 lines)
- `app.py` — Main Streamlit dashboard (367 lines)
- `pages/analytics.py` — Analytics dashboard (1934 lines)
- `pages/results.py` — Results page (260 lines)
- `pages/transcript.py` — Transcript page (171 lines)
- `ui_components.py` — Shared CSS/JS injection (311 lines)
