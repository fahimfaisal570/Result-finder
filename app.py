import streamlit as st
import pandas as pd
import os
import sys
import time
import re
import ssl
import collections
import random
import threading
import queue
import urllib.request as urllib_req
import json
import cli_scraper as cs
import database as db
import ui_components as ui

# --- Session State Initialization ---
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# --- Helper: Logo Base64 ---
def get_base64_logo(file_path):
    import base64
    if not os.path.exists(file_path): return ""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# --- Logic Delegation ---
classify_exams = cs.classify_exams
fetch_exams = cs.fetch_exams
fetch_student_result = cs.fetch_student_result
format_session = cs.format_session
parse_range_string = cs.parse_range 
make_request = cs.make_request
extract_options_from_html = cs.extract_options_from_html
BASE_URL = cs.BASE_URL
AJAX_URL = cs.AJAX_URL
SESSIONS_CACHE = cs.SESSIONS_CACHE
PROGRAMS_CACHE = cs.PROGRAMS_CACHE

# --- Essential Design System ---
st.set_page_config(page_title="Result Finder", page_icon="🎓", layout="wide")
ui.inject_essential_ui()

# --- Logic Blocks ---
def fetch_programs_and_sessions():
    html = make_request(BASE_URL)
    if not html: return {}, {}
    programs = collections.OrderedDict()
    sessions = collections.OrderedDict()
    select_blocks = re.findall(r'<select.*?</select>', html, re.DOTALL | re.IGNORECASE)
    for block in select_blocks:
        options = extract_options_from_html(block)
        if not options: continue
        first_opt_text = options[0][1].lower() if options else ""
        if 'session' in first_opt_text:
            for val, text in options: sessions[val] = text
        elif 'course name' in first_opt_text:
            categories = [o[0] for o in options if o[0] != "0"]
            for cat_id in categories:
                cat_url = f"{BASE_URL}ajax/get_program_by_course.php?course_id={cat_id}"
                cat_html = make_request(cat_url)
                if cat_html:
                    p_opts = extract_options_from_html(cat_html)
                    for p_val, p_text in p_opts:
                        if p_val != "0": programs[p_val] = p_text
    
    if programs:
        whitelist = ["computer science", "civil engineering", "electrical and electronic"]
        filtered = {k: v for k, v in programs.items() if "b.sc." in v.lower() and any(w in v.lower() for w in whitelist)}
        programs = collections.OrderedDict(sorted(filtered.items(), key=lambda x: x[1]))
    
    if sessions:
        formatted = []
        for sid, sname in sessions.items():
            year_match = re.search(r"(20\d{2})", sname)
            if year_match:
                start_year = int(year_match.group(1))
                if start_year >= 2016:
                    formatted.append((sid, sname)) 
        
        formatted.sort(key=lambda x: x[1], reverse=True)
        sessions = collections.OrderedDict(formatted)
        SESSIONS_CACHE.update(sessions) 

    return programs, sessions

class BatchManager:
    def load_profiles(self):
        return db.get_profiles()

batch_manager = BatchManager()

# --- Header ---
st.title("🎓 Result Finder")
st.write("A premium, high-performance web dashboard for academic result analytics.")

if 'programs' not in st.session_state:
    with st.spinner("Connecting..."):
        st.session_state.programs, st.session_state.sessions = fetch_programs_and_sessions()

# --- Sidebar ---
with st.sidebar:
    logo_file = "college_logo.png"
    if os.path.exists(logo_file):
        b64 = get_base64_logo(logo_file)
        st.markdown(f'<div style="text-align: center; margin-top:-70px;"><img src="data:image/png;base64,{b64}" width="160"></div>', unsafe_allow_html=True)
    else:
        st.title("🎓 Result Finder")
    
    st.write("---")
    
    # Sidebar navigation and information
    st.write("---")
    mode = st.radio("Mode", ["Interactive Scan", "Saved Profiles"], index=1)

if mode == "Interactive Scan":
    with st.sidebar:
        p_list = list(st.session_state.programs.values())
        program_name = st.selectbox("Program", options=p_list if p_list else ["No Programs"])
        pro_id = [k for k, v in st.session_state.programs.items() if v == program_name][0] if p_list and program_name != "No Programs" else None
        
        s_list = list(st.session_state.sessions.values())
        session_name = st.selectbox("Session", options=s_list)
        sess_id = [k for k, v in st.session_state.sessions.items() if v == session_name][0]
        
        exams_raw = fetch_exams(pro_id) if pro_id else {}
        mains, others = classify_exams(exams_raw, session_name)
        exam_type = st.radio("Exam Category", ["Main Exams", "Retake / All Exams"], horizontal=True)
        
        if exam_type == "Main Exams" and mains:
            exam_name = st.selectbox("Examination", options=list(mains.values()))
            exam_id = [k for k, v in mains.items() if v == exam_name][0]
        else:
            exam_name = st.selectbox("Examination (All)", options=list(exams_raw.values()) if exams_raw else ["No Exams"])
            exam_id = [k for k, v in exams_raw.items() if v == exam_name][0] if exams_raw and exam_name != "No Exams" else None

    st.header("Start New Scan")
    
    if 'ra_items' not in st.session_state:
        st.session_state.ra_items = []

    st.markdown(f"**Main Batch ({session_name})**")
    main_range = st.text_input("Registration Numbers (e.g., 210101-210150)", key="main_range_input")
    
    st.markdown("---")
    st.markdown("**Senior Re-adds**")
    to_delete = []
    for i, ra in enumerate(st.session_state.ra_items):
        r_col1, r_col2, r_col3 = st.columns([3, 2, 0.5])
        with r_col1:
            ra['range'] = st.text_input(f"Range {i+1}", value=ra['range'], key=f"ra_range_{i}")
        with r_col2:
            s_options = list(st.session_state.sessions.values())
            s_idx = s_options.index(ra['sess']) if ra['sess'] in s_options else 0
            ra['sess'] = st.selectbox(f"Session {i+1}", options=s_options, index=s_idx, key=f"ra_sess_{i}")
        with r_col3:
            st.write("") 
            if st.button("🗑️", key=f"ra_del_{i}"):
                to_delete.append(i)
    
    if to_delete:
        for idx in sorted(to_delete, reverse=True):
            st.session_state.ra_items.pop(idx)
        st.rerun()

    if st.button("Add Senior Batch Range"):
        st.session_state.ra_items.append({'range': '', 'sess': session_name})
        st.rerun()

    if exam_id and (main_range or st.session_state.ra_items):
        import json, base64
        from urllib.parse import quote as _quote
        payload = []
        if main_range: payload.append([main_range, sess_id])
        for ra in st.session_state.ra_items:
            if ra['range']:
                ra_sid = [k for k, v in st.session_state.sessions.items() if v == ra['sess']][0]
                payload.append([ra['range'], ra_sid])
        
        if payload:
            payload_str = base64.b64encode(json.dumps(payload).encode()).decode()
            res_url = f"/results?pro_id={pro_id}&exam_id={exam_id}&exam_name={_quote(exam_name)}&payload={payload_str}"
            st.link_button(f"🚀 Run Scraper & View Results ({len(payload)} Batches)", url=res_url, use_container_width=True)

else: # Saved Profiles Mode
    st.sidebar.markdown("---")
    st.sidebar.page_link("pages/analytics.py", label="Open Data Analytics", icon="📊")
    st.sidebar.markdown("---")
    profiles = db.get_profiles()
    if not profiles:
        st.info("No saved profiles found. Run a scan first!")
    else:
        st.sidebar.header("Profiles")
        p_selected = st.sidebar.selectbox("Select Profile", sorted(list(profiles.keys())))
        profile_data = profiles[p_selected]

        st.header(f"📋 Profile: {p_selected}")
        st.write(f"Students: {len(profile_data.get('regs', []))}")
        
        with st.expander("👥 View Student List"):
            p_regs = profile_data.get('regs', [])
            pro_id_p = profile_data.get('pro_id', '')
            import urllib.parse as _urlparse
            links = []
            for r in p_regs:
                reg_no = r[0] if isinstance(r, list) else r
                name   = r[2] if isinstance(r, list) and len(r) > 2 else f"Reg {reg_no}"
                url = f"/transcript?reg={reg_no}&pro_id={_urlparse.quote(str(pro_id_p))}&profile={_urlparse.quote(p_selected)}"
                links.append(f"• [{name} ({reg_no})]({url})")
            st.markdown("\n".join(links))

        exams_raw = fetch_exams(profile_data.get('pro_id')) if profile_data.get('pro_id') else {}
        if exams_raw:
            p_regs = profile_data.get('regs', [])
            active_sess_id = profile_data.get('sess_id') or (p_regs[0][1] if p_regs else "Any")
            active_sess_name = SESSIONS_CACHE.get(str(active_sess_id), str(active_sess_id))
            probe_regs = [r[0] for r in p_regs if str(r[1]) == str(active_sess_id)][:5]
            mains_dict, others_dict = classify_exams(exams_raw, active_sess_name, probe_regs=probe_regs, pro_id=profile_data.get('pro_id'))
            
            st.markdown(f"<div style='text-align: center; color: #8b949e; font-size: 0.8rem; letter-spacing: 0.1em; margin-bottom: 20px;'>⭐ MAIN BATCH EXAMS</div>", unsafe_allow_html=True)
            for eid, ename in mains_dict.items():
                from urllib.parse import quote as _quote
                url = f"/results?profile={_quote(p_selected)}&exam_id={eid}&exam_name={_quote(ename)}"
                st.markdown(f"• **[{ename}]({url})**")
            
            if others_dict:
                with st.expander("🔄 Other / Retake Exams"):
                    for eid, ename in others_dict.items():
                        url = f"/results?profile={_quote(p_selected)}&exam_id={eid}&exam_name={_quote(ename)}"
                        st.markdown(f"• **[{ename}]({url})**")

    st.markdown("---")
    st.markdown("<div style='text-align: center; color: #858585; font-size: 0.8rem;'>Developed with ❤️ for Academic Excellence | Showcase Version</div>", unsafe_allow_html=True)
with st.sidebar:
    with st.expander("🔒 Admin Access"):
        admin_pw = st.text_input("Admin Password", type="password")
        st.session_state.is_admin = (admin_pw == "admin123")

ui.add_contact_section()
