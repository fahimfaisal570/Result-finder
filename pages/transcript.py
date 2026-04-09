"""
pages/transcript.py — Individual Student Transcript Page
Invoked when user clicks a student name on the main dashboard.
Runs CLI Exhaustive Scan and renders the transcript HTML (Student Record).
"""
import streamlit as st
import sys, os, json, queue, threading, time

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cli_scraper as cs

st.set_page_config(page_title="Student Record", page_icon="favicon.ico", layout="wide")
st.markdown("""
<style>
    [data-testid="stSidebarNav"] { display: none !important; }
    [data-testid="stAppViewBlockContainer"] { padding: 1rem 1rem !important; max-width: 100% !important; }
    iframe { border: none !important; }
</style>
""", unsafe_allow_html=True)

# --- Read URL params ---
params       = st.query_params
reg_str      = params.get("reg", "")
pro_id       = params.get("pro_id", "")
profile_name = params.get("profile", "")
sess_id      = params.get("sess_id", "AUTO")

# Pinpoint Fallback: If sess_id is missing/AUTO but we have a profile name, resolve it from the profile
if (sess_id == "AUTO" or not sess_id) and profile_name:
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "saved_profiles.json"), "r") as f:
            profiles = json.load(f)
        if profile_name in profiles:
            p_data = profiles[profile_name]
            sess_id = p_data.get("sess_id", "AUTO")
    except: pass

if not reg_str or not pro_id:
    st.error("❌ Missing parameters. Please navigate from the main dashboard.")
    st.stop()

try:
    st_reg = int(reg_str) # Renamed reg to st_reg
except:
    st.error("❌ Invalid registration number.")
    st.stop()

st.title("📄 Student Record")
st.caption(f"**Name:** {profile_name} &nbsp;|&nbsp; **Registration:** {st_reg}")

# Pinpoint Fix: Ensure a valid session handshake before starting history scan
with st.spinner("Initializing session with university portal..."):
    programs, sessions = cs.fetch_programs_and_sessions()

# Display scan mode
# Full transparency: Tell the user this is the Pure CLI Option [2] logic
st.info("⌛ **Deep CLI-Native Scan Active**: Probing every session across every exam for 100% parity. This takes 1-3 mins but finds every retake found by the CLI.", icon="⏳")
st.divider()

# --- Load all exams for this program ---
with st.spinner("Fetching examination list from portal…"):
    all_exams = cs.fetch_exams(pro_id)

if not all_exams:
    st.error("❌ Could not load examination list. Portal may be down.")
    st.stop()

# --- Exhaustive CLI Scan Logic (Native Engine) ---
progress_bar = st.progress(0, text="Firing up CLI engine for student record scan…")
status_msg = st.empty()

def update_progress(current, total, status_text=None):
    val = current / total if total > 0 else 0
    if status_text:
        progress_bar.progress(val, text=f"Scanning… {status_text}")
        status_msg.caption(f"🔍 {status_text}")
    else:
        progress_bar.progress(val, text=f"🏁 Processed {current}/{total} exams.")
        status_msg.caption(f"🏁 Processed {current}/{total} exams.")

# --- Smart Scope Hardening (Aligned with Result finder.py heuristics) ---
# 1. Determine student start year from session (e.g. Session 22 -> 2022)
start_search_year = 0
if sess_id and sess_id != "AUTO":
    # Try to extract year from session name (e.g. "Session 2022-2023")
    sess_name = sessions.get(sess_id, "")
    y_match = re.search(r"20(\d{2})", sess_name)
    if y_match: start_search_year = int("20" + y_match.group(1))

# 2. Filter exams: Only scan exams from the student's cohort year onwards
filtered_exam_ids = []
for eid, ename in all_exams.items():
    _, _, ey = cs.parse_exam_info(ename)
    if ey and start_search_year:
        if ey < (start_search_year - 1): # 1-year buffer for overlaps
            continue
    filtered_exam_ids.append(eid)

# 3. Build tasks: Use PINNED session for 100% accuracy, fall back to AUTO only if unknown
# This prevents reg-number collisions across different batches (the result 890 issue)
exam_tasks = [(st_reg, sess_id, eid) for eid in filtered_exam_ids]

# --- Absolute CLI-Native Exhaustive Scan ---
status_msg.info(f"🔍 Deep Probing {len(filtered_exam_ids)} relevant examinations from {start_search_year or 'all years'}...")
history = cs.run_batch_scan_engine(
    tasks=exam_tasks,
    pro_id=pro_id,
    exam_id="0",
    all_sessions=sessions, 
    progress_callback=update_progress,
    num_threads=12 # Balanced for stability
)
progress_bar.empty()
status_msg.empty()

if not history:
    st.warning("⚠️ No records found for this student across any examination. The portal might be busy or the session expired.")
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
    # Use "Academic History" as the fallback title to match CLI exactly
    html_out = cs.generate_transcript_report(history, "Academic History", student_name, return_html=True)
except Exception as e:
    st.error(f"❌ CLI HTML generation failed: {e}")
    st.stop()

# --- Render inline (Iframe with dynamic height to prevent cut-off) ---
calc_height = 600 + (len(history) * 300)
st.components.v1.html(html_out, height=calc_height, scrolling=True)

# --- Download Button ---
st.download_button(
    label="⬇️ Download Student Record HTML",
    data=html_out.encode("utf-8"),
    file_name=f"Student_Record_{student_name.replace(' ', '_')}_{st_reg}.html",
    mime="text/html"
)
