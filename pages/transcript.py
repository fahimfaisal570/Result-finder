"""
pages/transcript.py — Individual Student Transcript Page
Invoked when user clicks a student name on the main dashboard.
Runs CLI Exhaustive Scan and renders the transcript HTML (Student Record).
"""
import streamlit as st
import sys, os, json, queue, threading, time, re
import ui_components as ui

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cli_scraper as cs
import database as db

st.set_page_config(page_title="Student Record", layout="wide")
ui.inject_essential_ui()

# --- Read URL params ---
params       = st.query_params
reg_str      = params.get("reg", "")
pro_id       = params.get("pro_id", "")
profile_name = params.get("profile", "")
sess_id      = params.get("sess_id", "AUTO")

if not reg_str or not pro_id:
    st.error("Missing parameters. Please navigate from the main dashboard.")
    st.stop()

try:
    st_reg = int(reg_str)
except:
    st.error("Invalid registration number.")
    st.stop()

# Smart Scope Fix: Resolve per-student sess_id (readd students differ from batch sess_id)
# This prevents reg_no collision with same-numbered students in other batches.
if (sess_id == "AUTO" or not sess_id) and profile_name:
    try:
        profiles = db.get_profiles()
        if profile_name in profiles:
            p_data = profiles[profile_name]
            # Search for this specific student's individual sess_id in the regs list
            # regs format: [[reg_no, sess_id, name], ...]
            for reg_entry in p_data.get("regs", []):
                if isinstance(reg_entry, list) and len(reg_entry) >= 2:
                    try:
                        if int(reg_entry[0]) == st_reg:
                            candidate = str(reg_entry[1])
                            if candidate and candidate != "AUTO":
                                sess_id = candidate
                            break
                    except (ValueError, TypeError):
                        pass
            # Fallback to batch-level session if per-student not found
            if sess_id == "AUTO" or not sess_id:
                sess_id = p_data.get("sess_id", "AUTO")
    except Exception as e:
        st.error(f"Error loading profile database for transcript: {e}")

st.title("Student Record")
st.caption(f"**Name:** {profile_name} &nbsp;|&nbsp; **Registration:** {st_reg}")

# Pinpoint Fix: Ensure a valid session handshake before starting history scan
with st.spinner("Initializing session with university portal..."):
    programs, sessions = cs.fetch_programs_and_sessions()

# Display scan mode
st.info("**Deep CLI-Native Scan Active**: Probing every session across every exam for 100% parity. This takes 1-3 mins but finds every retake found by the CLI.", icon=":material/info:")
st.divider()

# --- Load all exams for this program ---
with st.spinner("Fetching examination list from portal…"):
    all_exams = cs.fetch_exams(pro_id)

if not all_exams:
    st.error("Could not load examination list. Portal may be down.")
    st.stop()

# --- Exhaustive CLI Scan Logic (Native Engine) ---
progress_bar = st.progress(0, text="Firing up CLI engine for student record scan…")
status_msg = st.empty()

def update_progress(current, total, status_text=None):
    val = current / total if total > 0 else 0
    if status_text:
        progress_bar.progress(val, text=f"Scanning… {status_text}")
        status_msg.caption(f"{status_text}")
    else:
        progress_bar.progress(val, text=f"Processed {current}/{total} exams.")
        status_msg.caption(f"Processed {current}/{total} exams.")

# --- Smart Scope Hardening ---
# 1. Resolve the student's start year from their pinned session name
#    e.g. "Session 2022-2023" -> start_search_year = 2022
start_search_year = 0
if sess_id and sess_id != "AUTO":
    sess_name = sessions.get(sess_id, "")
    y_match = re.search(r"20(\d{2})", sess_name)
    if y_match:
        start_search_year = int("20" + y_match.group(1))

# 2. Filter the exam list: only probe exams from the student's cohort year onward
#    A 1-year buffer is applied to catch any edge cases (readd students may appear
#    in an exam published slightly before their own session year).
EXAM_YEAR_PATTERN = re.compile(r'\b(20\d{2})\b')

def _extract_exam_year(exam_name: str) -> int:
    """Extracts the publication year from an exam name string."""
    matches = EXAM_YEAR_PATTERN.findall(exam_name)
    # The last 4-digit year in the name is typically the publication year
    return int(matches[-1]) if matches else 0

filtered_exam_ids = []
for eid, ename in all_exams.items():
    if start_search_year:
        ey = _extract_exam_year(ename)
        if ey and ey < (start_search_year - 1):  # 1-year buffer for overlaps
            continue
    filtered_exam_ids.append(eid)

# 3. Build tasks with PINNED sess_id for 100% accuracy
#    This prevents pulling results for a different student with the same reg_no in another batch.
exam_tasks = [(st_reg, sess_id, eid) for eid in filtered_exam_ids]

# --- Absolute CLI-Native Exhaustive Scan ---
status_msg.info(f"Deep Probing {len(filtered_exam_ids)} relevant examinations from {start_search_year or 'all years'}...")
history = cs.run_batch_scan_engine(
    tasks=exam_tasks,
    pro_id=pro_id,
    exam_id="0",
    all_sessions=sessions,
    progress_callback=update_progress,
    num_threads=15
)
progress_bar.empty()
status_msg.empty()

if not history:
    st.warning("No records found for this student across any examination. The portal might be busy or the session expired.")
    st.stop()

# Map exam names from IDs and sort chronologically (Ascending, 1st year at top)
for res in history:
    eid = res.get('_exam_id')
    if eid and eid in all_exams:
        res['_exam_name'] = all_exams[eid]

history.sort(key=lambda x: str(x.get('_exam_name', '')), reverse=False)
student_name = history[0].get("Name") or history[0].get("Student Name") or f"Student {st_reg}"

# --- Generate Native CLI HTML Transcript ---
try:
    html_out = cs.generate_transcript_report(history, "Academic History", student_name, return_html=True)
except Exception as e:
    st.error(f"CLI HTML generation failed: {e}")
    st.stop()

# --- Render inline report ---
st.html(html_out)

# --- Download Button ---
st.download_button(
    label="Download Student Record HTML",
    data=html_out.encode("utf-8"),
    file_name=f"Student_Record_{student_name.replace(' ', '_')}_{st_reg}.html",
    mime="text/html"
)

ui.add_contact_section()
