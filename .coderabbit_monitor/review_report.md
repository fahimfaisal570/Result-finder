# Code Rabbit Review Report — Result Finder & Publication Monitor
**Author:** Senior Review Agent (Code Rabbit Superpower)  
**Project:** FEC Result Finder & Publication Monitor Suite  
**Target Branch / Commit:** `main` / `6e4ba23`  
**Status:** 🔬 **Deep Architectural Review — 1 Major Risk Identified (Action Required)**

---

## Severity Breakdown
- 🔴 **Critical**: 0
- 🟡 **Major**: 1
- 🟢 **Minor**: 3
- 🔵 **Style/Info**: 2

---

## Findings

### 🔴 Critical (0 Open)
*None.*

---

### 🟡 Major (1 Open)

#### 1. Hardcoded Administrator Global Password in Dashboard Frontend
*   **File:** [app.py](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/app.py) (L574)
*   **Issue:** The Streamlit dashboard hardcodes the administrative credential in plain text:
    ```python
    st.session_state.is_admin = (admin_pw == "admin123")
    ```
    This allows anyone who reads the source code or accesses the public repository to obtain administrative privilege to modify, rename, delete, or purge profiles and databases.
*   **Recommendation:** Retrieve the admin password from environment variables:
    ```python
    import os
    st.session_state.is_admin = (admin_pw == os.getenv("ADMIN_PASSWORD", "admin123"))
    ```

---

### 🟢 Minor (3 Open)

#### 1. Potential Client-Side XSS via Unsafe HTML Rendering
*   **File:** [app.py](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/app.py) (L496, L537)
*   **Issue:** The student list links and exam navigation lists are rendered using `unsafe_allow_html=True`. While the names are parsed from the university's database or local files, a malformed name containing html tags could lead to local script injection:
    ```python
    student_links_html += f"<li><a href='{tx_url}' target='_blank'>📄 {name} ...</a></li>"
    ```
*   **Recommendation:** Apply HTML escaping using standard library `html.escape` to student names and profile names before formatting them into HTML blocks:
    ```python
    import html
    escaped_name = html.escape(name)
    ```

#### 2. Synchronous File Writes in Multi-Threaded Scrapers
*   **File:** [auto_pdf_mailer.py](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/exam_monitor/auto_pdf_mailer.py) (L279, L387)
*   **Issue:** Inside `detect_readds_main_branch` and `process_and_mail`, `saved_profiles.json` and `v2_sync_tasks.json` are written synchronously using standard file operations (`open` + `json.dump`) without explicit locking. Since these run inside or downstream of multi-threaded worker flows, parallel writes could cause file corruption.
*   **Recommendation:** Wrap file write operations with a global thread lock:
    ```python
    import threading
    _file_write_lock = threading.Lock()
    
    with _file_write_lock:
        with open(profiles_path, "w") as f:
            json.dump(profiles, f, indent=2)
    ```

#### 3. Fallback Parse Inaccuracies in Unnamed Decimal Result Divs
*   **File:** [parser.py](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/scraper_core/parser.py) (L186-191)
*   **Issue:** The fallback logic for capturing GPAs searches the overall result box for any decimal:
    ```python
    m = re.search(r'([\d\.]+)', res_box.group(1))
    ```
    If the text says `Promoted to Year 3`, the parser will grab `3` as the GPA, which leads to incorrect record metrics.
*   **Recommendation:** Restrict the decimal search to match a valid GPA decimal format (e.g. `\b\d\.\d{2}\b` matching `3.50` but not `3`).

---

### 🔵 Style/Info (2 Open)

#### 1. Redundant Hover-Open Javascript Injected Multiple Times
*   **File:** [app.py](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/app.py) (L284, L317)
*   **Issue:** The `HOVER_OPEN_JS` block is defined once and injected into the main view, then injected again in the sidebar block. This attaches duplicate event listeners to the parent window's `mouseover` event, causing minor event handling overhead.
*   **Recommendation:** Inject the script only once globally in the main layout block.

#### 2. Defer heavy standard libraries in network and parser
*   **File:** [network.py](file:///c:/Users/Ucc/Downloads/result%20finder%20separate/scraper_core/network.py)
*   **Issue:** The fast-boot monitor still loads multiple standard library modules like `ssl`, `json`, and `subprocess`.
*   **Recommendation:** Defer importing heavier standard modules until they are explicitly needed in active helper functions.
