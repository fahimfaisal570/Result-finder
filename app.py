import streamlit as st
import os
import base64
import time
import re
import json
from urllib.parse import quote as _quote
import cli_scraper as cs
import database as db
import ui_components as ui


# --- Session State Initialization ---
if "is_admin" not in st.session_state:
    st.session_state.is_admin = True

# --- Essential Design System ---
st.set_page_config(page_title="Result Finder", page_icon="favicon.ico", layout="wide")
ui.inject_essential_ui()

# --- Logic Blocks ---

# --- Branded Header ---
logo_col, text_col = st.columns([1, 6], vertical_alignment="center")
with logo_col:
    if os.path.exists("college_logo.png"):
        st.image("college_logo.png", width=85)
with text_col:
    st.markdown(
        '<div style="font-family: Outfit, sans-serif; font-size: 2.2rem; font-weight: 700; line-height: 1.1; color: var(--text-color);">'
        'Result Finder <span style="font-size: 0.9rem; font-weight: 600; color: #16A34A; vertical-align: middle; margin-left: 4px;">PRO</span>'
        '</div>',
        unsafe_allow_html=True
    )
    st.caption("A premium web dashboard for academic result analytics and cohort intelligence.")

if 'programs' not in st.session_state:
    with st.spinner("Connecting..."):
        st.session_state.programs, st.session_state.sessions = cs.fetch_programs_and_sessions()

# --- Sidebar ---
with st.sidebar:
    st.markdown(
        '<div style="font-family: Outfit, sans-serif; font-size: 1.1rem; font-weight: 600; '
        'letter-spacing: -0.01em; padding: 0.5rem 0 0.75rem 0; opacity: 0.95;">'
        'Result Finder PRO</div>',
        unsafe_allow_html=True
    )
    mode = st.radio("Mode", ["Interactive Scan", "Saved Profiles"], index=1)

if mode == "Interactive Scan":
    with st.sidebar:
        p_list = list(st.session_state.programs.values())
        program_name = st.selectbox("Program", options=p_list if p_list else ["No Programs"])
        pro_id = [k for k, v in st.session_state.programs.items() if v == program_name][0] if p_list and program_name != "No Programs" else None
        
        s_list = list(st.session_state.sessions.values())
        session_name = st.selectbox("Session", options=s_list)
        sess_id = [k for k, v in st.session_state.sessions.items() if v == session_name][0]
        
        exams_raw = cs.fetch_exams(pro_id) if pro_id else {}
        mains, others = cs.classify_exams(exams_raw, session_name)
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
    
    st.divider()
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
            if st.button("", key=f"ra_del_{i}", icon=":material/delete:"):
                to_delete.append(i)
    
    if to_delete:
        for idx in sorted(to_delete, reverse=True):
            st.session_state.ra_items.pop(idx)
        st.rerun()

    if st.button("Add Senior Batch Range"):
        st.session_state.ra_items.append({'range': '', 'sess': session_name})
        st.rerun()

    if exam_id and (main_range or st.session_state.ra_items):
        payload = []
        if main_range: payload.append([main_range, sess_id])
        for ra in st.session_state.ra_items:
            if ra['range']:
                ra_sid = [k for k, v in st.session_state.sessions.items() if v == ra['sess']][0]
                payload.append([ra['range'], ra_sid])
        
        if payload:
            payload_str = base64.b64encode(json.dumps(payload).encode()).decode()
            res_url = f"/results?pro_id={pro_id}&exam_id={exam_id}&exam_name={_quote(exam_name)}&payload={payload_str}"
            st.link_button(f"Run Scraper & View Results ({len(payload)} Batches)", url=res_url, width='stretch')

else: # Saved Profiles Mode
    st.sidebar.divider()
    st.sidebar.page_link("pages/analytics.py", label="Open Data Analytics", icon=":material/analytics:")
    st.sidebar.page_link("pages/pending_finder.py", label="Pending Finder", icon=":material/search:")
    st.sidebar.divider()
    
    # --- Create Manual Batch in Sidebar ---
    with st.sidebar.expander("Create Manual Batch", expanded=False, icon=":material/construction:"):
        st.write("Create a provisional batch without portal results.")
        PROFILE_NAME_PATTERN = re.compile(r'^(cse|eee|civil)\s+\d+$', re.IGNORECASE)
        
        prov_name = st.text_input("Profile Name (e.g. cse 12)", placeholder="cse 12", key="prov_name_input")
        
        # Programs & Sessions
        p_list_prov = list(st.session_state.programs.values())
        p_keys_prov = list(st.session_state.programs.keys())
        p_sel_prov = st.selectbox("Program", options=p_list_prov, key="prov_pro_sel")
        pro_id_prov = p_keys_prov[p_list_prov.index(p_sel_prov)] if p_sel_prov in p_list_prov else ""
        
        s_list_prov = list(st.session_state.sessions.values())
        s_keys_prov = list(st.session_state.sessions.keys())
        s_sel_prov = st.selectbox("Session", options=s_list_prov, key="prov_sess_sel")
        sess_id_prov = s_keys_prov[s_list_prov.index(s_sel_prov)] if s_sel_prov in s_list_prov else ""
        
        regs_input = st.text_input("Registration Numbers", placeholder="e.g. 220101-220160", key="prov_regs_input")
        
        if st.button("Create Batch", type="primary", width="stretch", key="btn_create_prov"):
            if not prov_name or not regs_input or not pro_id_prov or not sess_id_prov:
                st.error("Please fill in all fields.")
            elif not PROFILE_NAME_PATTERN.match(prov_name):
                st.error("Must follow format: 'cse 12', 'eee 12', 'civil 12'")
            elif db.profile_exists(prov_name.lower().strip()):
                st.error("Profile already exists")
            else:
                parsed_regs = cs.parse_range(regs_input)
                if not parsed_regs:
                    st.error("Invalid registration range.")
                else:
                    # Remove duplicate registration numbers (ensure uniqueness)
                    parsed_regs = list(dict.fromkeys(parsed_regs))
                    db.save_provisional_profile(prov_name.lower().strip(), pro_id_prov, sess_id_prov, [(r,) for r in parsed_regs])
                    cs.batch_manager.save_provisional_to_json(prov_name.lower().strip(), pro_id_prov, sess_id_prov, parsed_regs)
                    st.session_state.prov_name_input = ""
                    st.session_state.prov_regs_input = ""
                    st.success(f"Provisional batch '{prov_name}' created!")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()

    profiles = db.get_profiles()
    if not profiles:
        st.info("No saved profiles found. Run a scan or create a manual batch in the sidebar first!")
    else:
        st.sidebar.header("Profiles")
        p_selected = st.sidebar.selectbox("Select Profile", sorted(list(profiles.keys())))
        profile_data = profiles[p_selected]
        is_prov = profile_data.get('is_provisional', False)

        st.header(f"Profile: {p_selected}")
        if is_prov:
            st.warning("**Provisional Batch** — Waiting for portal results to publish.", icon=":material/schedule:")
            
            # --- Check Portal CTA ---
            st.markdown("### Check Portal for Results")
            st.info("Check if DUCMC portal has published the first exam results for this batch.")
            
            exams_raw = cs.fetch_exams(profile_data.get('pro_id')) if profile_data.get('pro_id') else {}
            if exams_raw:
                chk_exam_name = st.selectbox("Select Exam to Check Against", options=list(exams_raw.values()), key="chk_portal_exam")
                chk_exam_id = [k for k, v in exams_raw.items() if v == chk_exam_name][0]
                
                if st.button("Check Portal & Import", type="primary", width="stretch", key="btn_chk_prov"):
                    p_regs = profile_data.get('regs', [])
                    active_sess_id = profile_data.get('sess_id')
                    probe_regs = [r[0] for r in p_regs if str(r[1]) == str(active_sess_id)][:5]
                    
                    with st.spinner("Probing portal with sample students..."):
                        matched = False
                        for reg in probe_regs:
                            res_data, success = cs.fetch_student_result(reg, profile_data.get('pro_id'), active_sess_id, chk_exam_id)
                            if success and isinstance(res_data, dict) and 'GPA' in res_data:
                                matched = True
                                break
                        
                        if not matched:
                            st.warning("No results found on portal yet for this exam.", icon=":material/search_off:")
                        else:
                            st.success("Results found on portal! Redirecting to scraper...", icon=":material/check_circle:")
                            payload = [[f"{p_regs[0][0]}-{p_regs[-1][0]}", active_sess_id]]
                            payload_str = base64.b64encode(json.dumps(payload).encode()).decode()
                            st.markdown(f'<meta http-equiv="refresh" content="0; url=/results?profile={_quote(p_selected)}&exam_id={chk_exam_id}&exam_name={_quote(chk_exam_name)}">', unsafe_allow_html=True)
                            st.link_button("Launch Full Import & Promotion", url=f"/results?profile={_quote(p_selected)}&exam_id={chk_exam_id}&exam_name={_quote(chk_exam_name)}")
            st.divider()
 
        st.write(f"Students: {len(profile_data.get('regs', []))}")
        
        with st.expander("View Student List", icon=":material/list:"):
            p_regs = profile_data.get('regs', [])
            pro_id_p = profile_data.get('pro_id', '')
            links = []
            for r in p_regs:
                reg_no = r[0] if isinstance(r, list) else r
                name   = r[2] if isinstance(r, list) and len(r) > 2 else f"Reg {reg_no}"
                url = f"/transcript?reg={reg_no}&pro_id={_quote(str(pro_id_p))}&profile={_quote(p_selected)}"
                links.append(f"• [{name} ({reg_no})]({url})")
            st.markdown("\n".join(links))
 
        exams_raw = cs.fetch_exams(profile_data.get('pro_id')) if profile_data.get('pro_id') else {}
        if exams_raw:
            p_regs = profile_data.get('regs', [])
            active_sess_id = profile_data.get('sess_id') or (p_regs[0][1] if p_regs else "Any")
            active_sess_name = cs.SESSIONS_CACHE.get(str(active_sess_id), str(active_sess_id))
            probe_regs = [r[0] for r in p_regs if str(r[1]) == str(active_sess_id)][:5]
            _classify_key = f"classify_{p_selected}_{profile_data.get('pro_id')}_{active_sess_id}"
            if _classify_key not in st.session_state:
                st.session_state[_classify_key] = cs.classify_exams(
                    exams_raw,
                    active_sess_name,
                    probe_regs=probe_regs,
                    pro_id=profile_data.get('pro_id'),
                    profile_name=p_selected
                )
            mains_dict, others_dict = st.session_state[_classify_key]
            
            st.markdown("<div style='text-align: center; color: var(--text-color); opacity: 0.6; font-size: 0.8rem; letter-spacing: 0.1em; margin-bottom: 20px; text-transform: uppercase;'>Main Batch Exams</div>", unsafe_allow_html=True)
            for eid, ename in mains_dict.items():
                url = f"/results?profile={_quote(p_selected)}&exam_id={eid}&exam_name={_quote(ename)}"
                st.markdown(f"• **[{ename}]({url})**")
            
            # --- NEW: Batch Scan Feature ---
            if mains_dict:
                st.write("")
                # Prepare batch payload: list of [id, name]
                batch_payload = [[eid, ename] for eid, ename in mains_dict.items()]
                batch_b64 = base64.b64encode(json.dumps(batch_payload).encode()).decode()
                batch_url = f"/results?profile={_quote(p_selected)}&batch_exams={batch_b64}"
                
                st.link_button("Batch Scan All Main Exams", url=batch_url, width='stretch', type="primary")
                st.caption("Automatic one-click scan of all detected main semester exams for this profile.")

            if others_dict:
                with st.expander("Other / Retake Exams"):
                    for eid, ename in others_dict.items():
                        url = f"/results?profile={_quote(p_selected)}&exam_id={eid}&exam_name={_quote(ename)}"
                        st.markdown(f"• **[{ename}]({url})**")

            # --- Add Student Feature ---
            with st.expander("Add Student to Profile"):
                st.caption("Manually add students from other sessions/batches to this profile by scanning the portal.")
                
                add_reg_input = st.text_input(
                    "Registration Number(s)",
                    placeholder="e.g., 937 or 935,936,937",
                    key="add_student_regs"
                )
                
                # Session selection
                s_list_add = list(st.session_state.sessions.values())
                s_keys_add = list(st.session_state.sessions.keys())
                add_sess_name = st.selectbox("Session of Student(s)", options=s_list_add, key="add_student_sess")
                add_sess_id = s_keys_add[s_list_add.index(add_sess_name)] if add_sess_name in s_list_add else ""
                
                # Exam selection (all exams for this department)
                all_exam_names = list(exams_raw.values()) if exams_raw else []
                add_exam_name = st.selectbox("Scan Against Exam", options=all_exam_names, key="add_student_exam")
                add_exam_id = [k for k, v in exams_raw.items() if v == add_exam_name][0] if exams_raw and add_exam_name else ""
                
                if st.button("Scan Students", key="add_student_scan_btn", width='stretch'):
                    if not add_reg_input or not add_exam_id:
                        st.error("Please provide registration number(s) and select an exam.")
                    else:
                        parsed_regs = cs.parse_range(add_reg_input)
                        if not parsed_regs:
                            st.error("Invalid registration number(s).")
                        else:
                            scan_tasks = [(int(r), str(add_sess_id), str(add_exam_id)) for r in parsed_regs]
                            with st.spinner(f"Scanning {len(scan_tasks)} student(s) against portal..."):
                                found_results = cs.run_batch_scan_engine(
                                    tasks=scan_tasks,
                                    pro_id=profile_data.get('pro_id'),
                                    exam_id=add_exam_id,
                                    all_sessions=st.session_state.sessions,
                                    num_threads=5
                                )
                            if found_results:
                                st.session_state['add_student_found'] = found_results
                                st.session_state['add_student_sess_id'] = add_sess_id
                                st.rerun()
                            else:
                                st.warning("No students found for those registrations in the selected exam.")
                
                # Display found students with checkboxes
                if 'add_student_found' in st.session_state and st.session_state['add_student_found']:
                    found = st.session_state['add_student_found']
                    existing_regs_set = {(r[0], str(r[1])) if isinstance(r, list) else (r, 'AUTO') for r in profile_data.get('regs', [])}
                    stored_sess_id = st.session_state.get('add_student_sess_id', 'AUTO')
                    new_in_found = sum(1 for res in found if (int(res.get('Registration No', res.get('Reg', 0))), str(stored_sess_id)) not in existing_regs_set)
                    dup_in_found = len(found) - new_in_found
                    
                    if dup_in_found:
                        st.warning(f"Found {len(found)} student(s) — {dup_in_found} already in profile (will update info if re-added).")
                    else:
                        st.success(f"Found {len(found)} new student(s):")
                    
                    selected = []
                    for i, res in enumerate(found):
                        reg = int(res.get('Registration No', res.get('Reg', '0')))
                        name = res.get('Name', 'Unknown')
                        is_dup = (reg, str(stored_sess_id)) in existing_regs_set
                        label = f"{'[Update] ' if is_dup else ''}{name} ({reg}){' — already in profile' if is_dup else ''}"
                        checked = st.checkbox(
                            label,
                            value=not is_dup,  # New students checked by default, duplicates unchecked
                            key=f"add_student_check_{i}"
                        )
                        if checked:
                            selected.append(res)
                    
                    col_confirm, col_cancel = st.columns(2)
                    with col_confirm:
                        if st.button("Confirm & Add Selected", width='stretch', type="primary"):
                            if not selected:
                                st.error("No students selected.")
                            else:
                                stored_sess_id = st.session_state.get('add_student_sess_id', 'AUTO')
                                # Check which students already exist in the profile
                                existing_regs = {(r[0], str(r[1])) if isinstance(r, list) else (r, 'AUTO') for r in profile_data.get('regs', [])}
                                new_count = 0
                                updated_count = 0
                                for res in selected:
                                    reg = int(res.get('Registration No', res.get('Reg', 0)))
                                    name = str(res.get('Name', 'Unknown'))
                                    if (reg, str(stored_sess_id)) in existing_regs:
                                        updated_count += 1
                                    else:
                                        new_count += 1
                                    db.upsert_student(p_selected, reg, name, str(stored_sess_id))
                                
                                # Cleanup
                                del st.session_state['add_student_found']
                                if 'add_student_sess_id' in st.session_state:
                                    del st.session_state['add_student_sess_id']
                                st.cache_data.clear()
                                # Informative feedback
                                if new_count and updated_count:
                                    st.success(f"Added {new_count} new student(s) and updated {updated_count} existing student(s) in '{p_selected}'.")
                                elif new_count:
                                    st.success(f"Added {new_count} new student(s) to '{p_selected}'!")
                                else:
                                    st.info(f"All {updated_count} student(s) already existed in '{p_selected}'. Their info has been refreshed.")
                                time.sleep(1.5)
                                st.rerun()
                    
                    with col_cancel:
                        if st.button("Cancel", width='stretch'):
                            del st.session_state['add_student_found']
                            if 'add_student_sess_id' in st.session_state:
                                del st.session_state['add_student_sess_id']
                            st.rerun()
 
    st.divider()

ui.add_contact_section()
