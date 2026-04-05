import streamlit as st
import sys, os, json, queue, threading, time, base64
import ui_components as ui

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cli_scraper as cs
import database as db

st.set_page_config(page_title="Exam Results", page_icon="🏆", layout="wide")
ui.inject_essential_ui()

# --- Read URL params ---
params          = st.query_params
profile_name    = params.get("profile", "")
exam_id         = params.get("exam_id", "")
exam_name       = params.get("exam_name", "Examination")
payload_b64     = params.get("payload", "") # Multi-batch payload
batch_exams_b64 = params.get("batch_exams", "")

if not exam_id and not batch_exams_b64:
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
        pro_id = params.get("pro_id", "") # Always provided with payload
        # batch_data structure: [[range_str, sess_id], ...]
        for r_str, s_id in batch_data:
            if not sess_id: sess_id = s_id # Use first batch as primary
            parsed = cs.parse_range(r_str)
            regs.extend([[r, s_id] for r in parsed])
    except Exception as e:
        st.error(f"❌ Failed to parse scan payload: {e}")
        st.stop()

# 2. Source: Saved Profile (Batch or Single)
elif profile_name:
    try:
        profiles = db.get_profiles()
        if profile_name in profiles:
            p_data = profiles[profile_name]
            pro_id = p_data.get("pro_id")
            sess_id = p_data.get("sess_id") 
            regs_raw = p_data.get("regs", [])
            for r in regs_raw:
                if isinstance(r, (list, tuple)): regs.append((int(r[0]), str(r[1])))
                else: regs.append((int(r), "AUTO"))
        else:
            st.error(f"❌ Profile '{profile_name}' not found.")
            st.stop()
    except Exception as e:
        st.error(f"❌ Could not load profiles: {e}")
        st.stop()
else:
    # Source: Manual Range (Interactive Scan)
    pro_id_manual  = params.get("pro_id", "")
    range_manual   = params.get("range", "")
    sess_id_manual = params.get("sess_id", "")
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

# --- Initialization ---
with st.spinner("Initializing session with university portal..."):
    programs, sessions = cs.fetch_programs_and_sessions()

def update_progress(current, total, status_text=None):
    # This will be used inside the loop
    val = current / total if total > 0 else 0
    if status_text:
        progress_bar.progress(val, text=f"Scanning… {status_text}")
        status_msg.caption(f"🔍 {status_text}")
    else:
        progress_bar.progress(val, text=f"🏁 Processed {current}/{total} students.")
        status_msg.caption(f"🏁 Processed {current}/{total} students.")

# --- Mode 1: Batch Exam Mode ---
if batch_exams_b64:
    try:
        batch_exams = json.loads(base64.b64decode(batch_exams_b64).decode())
    except:
        st.error("❌ Failed to decode batch exams payload.")
        st.stop()
    
    st.title("🚀 Automated Batch Scan")
    st.caption(f"**Profile:** {profile_name} &nbsp;|&nbsp; **Exams to Scan:** {len(batch_exams)} &nbsp;|&nbsp; **Students:** {len(regs)}")
    st.info("The engine will now sequentially scan all main semester exams for this profile and prepare them for your analytics dashboard.", icon="ℹ️")
    st.divider()

    if "batch_results" not in st.session_state:
        st.session_state.batch_results = {} # exam_id -> results_list

    # Overall Batch Progress
    overall_progress = st.progress(0, text="Starting overall batch process...")
    
    # Per-Exam Progress
    progress_bar = st.progress(0, text="Waiting to start scan...")
    status_msg = st.empty()

    for i, (eid, ename) in enumerate(batch_exams):
        pct = (i) / len(batch_exams)
        overall_progress.progress(pct, text=f"Overall Progress: {i}/{len(batch_exams)} Exams Finished")
        
        if eid in st.session_state.batch_results:
            st.success(f"✅ Already scanned: {ename}")
            continue
            
        st.write(f"### 🔍 Scanning: {ename}")
        results = cs.run_batch_scan_engine(
            tasks=regs,
            pro_id=pro_id,
            exam_id=eid,
            all_sessions=sessions,
            progress_callback=update_progress,
            num_threads=15
        )
        if results:
            st.session_state.batch_results[eid] = {"name": ename, "data": results}
            st.success(f"✅ Finished {ename} ({len(results)} records found)")
        else:
            st.warning(f"⚠️ No records found for {ename}")
        
        st.divider()

    overall_progress.progress(1.0, text="🏁 Batch Scan Complete!")
    progress_bar.empty()
    status_msg.empty()

    # Summary and Save
    if st.session_state.batch_results:
        st.markdown("### 📊 Batch Summary")
        summary_data = []
        for eid, info in st.session_state.batch_results.items():
            summary_data.append({"Exam": info["name"], "Students Found": len(info["data"]), "Status": "Ready for Analytics"})
        st.table(summary_data)

        st.write("---")
        if st.button("💾 Save All to Analytics Dashboard", use_container_width=True, type="primary"):
            success_count = 0
            with st.spinner("Persisting results to database..."):
                for eid, info in st.session_state.batch_results.items():
                    try:
                        db.save_exam_analytics_only(profile_name, eid, info["name"], info["data"])
                        success_count += 1
                    except Exception as e:
                        st.error(f"❌ Failed to save {info['name']}: {e}")
            
            if success_count > 0:
                st.cache_data.clear()
                st.balloons()
                msg_placeholder = st.empty()
                for seconds in range(3, 0, -1):
                    msg_placeholder.success(f"✅ Successfully saved {success_count} exams to '{profile_name}'! Redirecting to dashboard in {seconds} seconds...")
                    time.sleep(1)
                
                # Clear session state and redirect
                del st.session_state.batch_results
                st.query_params.clear()
                st.switch_page("app.py")
    else:
        st.error("❌ No results were captured during the batch scan.")

# --- Mode 2: Single Exam Mode ---
else:
    st.title(f"🏆 {exam_name}")
    st.caption(f"**Source:** {profile_name} &nbsp;|&nbsp; **Students:** {len(regs)}")

    if len(regs) > 0:
        st.info(f"🚀 Loaded {len(regs)} students for scanning. Starting CLI engine...", icon="ℹ️")
    st.divider()

    progress_bar = st.progress(0, text="Firing up CLI engine for background scan…")
    status_msg = st.empty()

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

    html_out = cs.generate_html_report(results, exam_name, pro_id=pro_id, sess_id=sess_id)
    calc_height = 800 + (len(results) * 60)
    st.components.v1.html(html_out, height=calc_height, scrolling=True)

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
                    
                    # Add redirect here too if wanted, but user only asked for batch
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

    st.download_button(
        label="⬇️ Download CLI Results HTML",
        data=html_out.encode("utf-8"),
        file_name=f"Results_{profile_name.replace(' ','_')}_{exam_id}.html",
        mime="text/html",
        use_container_width=True
    )

ui.add_contact_section()

ui.add_contact_section()
