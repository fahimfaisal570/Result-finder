import streamlit as st
import sys, os, json, queue, threading, time, base64

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cli_scraper as cs
import database as db

st.set_page_config(page_title="Exam Results", page_icon="🏆", layout="wide")
st.markdown("""
<style>
    [data-testid="stSidebarNav"] { display: none !important; }
    [data-testid="stAppViewBlockContainer"] { padding: 1rem 1rem !important; max-width: 100% !important; }
    iframe { border: none !important; }
</style>
""", unsafe_allow_html=True)

# --- Read URL params ---
params       = st.query_params
profile_name = params.get("profile", "")
exam_id      = params.get("exam_id", "")
exam_name    = params.get("exam_name", "Examination")
payload_b64  = params.get("payload", "") # Multi-batch payload

# Manual Scan Params (Legacy single-batch)
pro_id_manual  = params.get("pro_id", "")
range_manual   = params.get("range", "")
sess_id_manual = params.get("sess_id", "")

if not exam_id:
    st.error("❌ Missing Exam ID. Please navigate from the main dashboard.")
    st.stop()

# --- Load data source ---
regs = []
pro_id = ""
sess_id = "" # Master session for report tagging

# 1. Source: Multi-Batch Payload (High Priority)
if payload_b64:
    try:
        import json
        batch_data = json.loads(base64.b64decode(payload_b64).decode())
        pro_id = pro_id_manual # Always provided with payload
        # batch_data structure: [[range_str, sess_id], ...]
        for r_str, s_id in batch_data:
            if not sess_id: sess_id = s_id # Use first batch as primary
            parsed = cs.parse_range(r_str)
            regs.extend([[r, s_id] for r in parsed])
    except Exception as e:
        st.error(f"❌ Failed to parse scan payload: {e}")
        st.stop()

# 2. Source: Saved Profile
elif profile_name:
    # Source: Saved Profile
    try:
        profiles = db.get_profiles()
        if profile_name in profiles:
            p_data = profiles[profile_name]
            pro_id = p_data.get("pro_id")
            sess_id = p_data.get("sess_id") # Pinpoint Fix: Capture session from profile
            regs_raw = p_data.get("regs", [])
            for r in regs_raw:
                if isinstance(r, list): regs.append((int(r[0]), str(r[1])))
                else: regs.append((int(r), "AUTO"))
        else:
            st.error(f"❌ Profile '{profile_name}' not found.")
            st.stop()
    except Exception as e:
        st.error(f"❌ Could not load profiles: {e}")
        st.stop()
else:
    # Source: Manual Range (Interactive Scan)
    if not pro_id_manual or not range_manual:
        st.error("❌ Incomplete scan parameters.")
        st.stop()
    pro_id = pro_id_manual
    manual_regs = cs.parse_range(range_manual)
    if not manual_regs:
        st.error("❌ Invalid registration range.")
        st.stop()
    sess_id = sess_id_manual or "AUTO" # Ensure sess_id is defined for report links
    regs = [(r, sess_id) for r in manual_regs]
    profile_name = "Manual Scan"

if not regs:
    st.error("❌ No student registrations to scan.")
    st.stop()

st.title(f"🏆 {exam_name}")
st.caption(f"**Source:** {profile_name} &nbsp;|&nbsp; **Students:** {len(regs)}")

# Pinpoint Fix: Ensure a valid session handshake before starting threads
with st.spinner("Initializing session with university portal..."):
    programs, sessions = cs.fetch_programs_and_sessions()

# Debug trace for the user
if len(regs) > 0:
    st.info(f"🚀 Loaded {len(regs)} students for scanning. Starting CLI engine...", icon="ℹ️")
st.divider()

# --- Fetch results using NATIVE CLI engine ---
progress_bar = st.progress(0, text="Firing up CLI engine for background scan…")
status_msg = st.empty()

def update_progress(current, total, status_text=None):
    val = current / total if total > 0 else 0
    if status_text:
        progress_bar.progress(val, text=f"Scanning… {status_text}")
        status_msg.caption(f"🔍 {status_text}")
    else:
        progress_bar.progress(val, text=f"🏁 Processed {current}/{total} students.")
        status_msg.caption(f"🏁 Processed {current}/{total} students.")

results = cs.run_batch_scan_engine(
    tasks=regs,
    pro_id=pro_id,
    exam_id=exam_id,
    all_sessions=sessions,
    progress_callback=update_progress,
    num_threads=10
)

progress_bar.empty()
status_msg.empty()

if not results:
    st.warning("⚠️ No results found. The portal might be busy or the session expired. Try again or check the CLI.")
    st.stop()

# --- Generate CLI-Native HTML ---
html_out = cs.generate_html_report(results, exam_name, pro_id=pro_id, sess_id=sess_id)

# --- Render inline (Iframe with dynamic height to prevent cut-off) ---
calc_height = 800 + (len(results) * 60)
st.components.v1.html(html_out, height=calc_height, scrolling=True)

# --- Save as Profile Feature ---
if results:
    st.write("---")
    if profile_name and profile_name != "Manual Scan":
        st.markdown(f"### 💾 Save Analytics to database")
        st.caption(f"Save these exam grades to **'{profile_name}'** to visualize them on the Analytics Dashboard.")
        if st.button("📊 Save Exam Analytics", use_container_width=True):
            try:
                db.save_exam_analytics_only(profile_name, exam_id, exam_name, results)
                st.cache_data.clear()
                st.success(f"✅ Exam Analytics saved to '{profile_name}'! Head to the Analytics tab to view trends.")
            except Exception as e:
                st.error(f"❌ Failed to save analytics: {e}")
    else:
        st.markdown("### 💾 Save results as a Profile")
        st.caption("Name this scan to access it later from the main dashboard.")
        
        with st.form("save_profile_form"):
            batch_name = st.text_input("Profile Name", placeholder="e.g., EEE-2022-Batch10")
            submitted = st.form_submit_button("📁 Save Profile Permanently", use_container_width=True)
            
            if submitted:
                if not batch_name:
                    st.error("❌ Please provide a name for the profile.")
                else:
                    try:
                        db.save_profile_and_results(batch_name, pro_id, sess_id, results, exam_id, exam_name)
                        st.cache_data.clear()
                        st.success(f"✅ Profile '{batch_name}' saved! You can now access it from the Sidebar.")
                    except Exception as e:
                        st.error(f"❌ Failed to save profile: {e}")

# --- Download Button ---
st.download_button(
    label="⬇️ Download CLI Results HTML",
    data=html_out.encode("utf-8"),
    file_name=f"Results_{profile_name.replace(' ','_')}_{exam_id}.html",
    mime="text/html",
    use_container_width=True
)
