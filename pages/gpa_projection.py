import streamlit as st
import pandas as pd
import numpy as np
import os
import re
import sys
import time
import json
import ui_components as ui

st.set_page_config(page_title="GPA Projection & Graduation Planner", page_icon="favicon.ico", layout="wide")
ui.inject_essential_ui()

# Add parent dir for database & scraper import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
import cli_scraper as cs
import ml_predictor

if "is_admin" not in st.session_state:
    st.session_state.is_admin = True

if '_deep_cache' not in st.session_state:
    st.session_state._deep_cache = {}

# --- Header & Back Link ---
st.page_link("app.py", label="← Back to Dashboard", icon=":material/arrow_back:")
st.title("GPA Projection & Graduation Planner")
st.markdown("Search any student across all batches to run deep history analysis, target CGPA calculations, and multi-semester simulations.")

profiles = db.get_profiles()
if not profiles:
    st.warning("No saved profiles found. Run a scan or create a batch first.")
    st.stop()

# --- Sidebar Filters ---
st.sidebar.header("Filters")
sorted_profile_names = sorted(list(profiles.keys()))
profile_filter = st.sidebar.selectbox(
    "Filter by Batch (Optional):",
    ["All Batches"] + sorted_profile_names
)
filter_profile_name = None if profile_filter == "All Batches" else profile_filter

# Single Search Bar in Main Area
query_input = st.text_input(
    "Search student by name or registration number:",
    placeholder="Type student name (e.g. Fahim) or reg no (e.g. 210101)...",
    key="gpa_proj_search"
)
query = query_input.strip()

# --- Helpers ---
def exam_label(e):
    name = e.get('exam_name') or f"Exam {e['exam_id']}"
    pattern = r'(?i)(\d[A-Za-z]+)\s+year\s+(\d[A-Za-z]+)\s+Semester.*?(?:of\s+)?(\d{4})'
    match = re.search(pattern, name)
    if match:
        name = f"{match.group(1).capitalize()} Yr {match.group(2).capitalize()} Sem'{match.group(3)[-2:]}"
    elif len(name) > 40:
        name = name[:37] + "…"
    return f"{name} [{e['exam_id']}]"

@st.cache_data(ttl=3600)
def _pre_warm_resources(pro_id):
    cs.warm_connection_pool(num_connections=6)
    cs.fetch_programs_and_sessions()
    if pro_id:
        cs.fetch_exams(pro_id)
    return True

def _run_deep_analysis(reg_no, stu_name, sess_id, profile_name, pro_id, latest_exam_label):
    if not pro_id:
        return None
    _programs, _sessions = cs.fetch_programs_and_sessions()
    _all_exams = cs.fetch_exams(pro_id) if pro_id else {}
    if not _all_exams:
        return None

    _filtered_eids = cs.get_relevant_exams(sess_id, _sessions, _all_exams)
    _tasks = [(int(reg_no), sess_id, _eid) for _eid in _filtered_eids]

    _history = cs.run_batch_scan_engine(
        tasks=_tasks,
        pro_id=pro_id,
        exam_id="0",
        all_sessions=_sessions,
        num_threads=15
    )

    if not _history:
        return None

    for rec in _history:
        eid = rec.get('_exam_id')
        if eid and eid in _all_exams:
            rec['_exam_name'] = _all_exams[eid]

    return db.compute_deep_analysis(_history, profile_name, latest_exam_label)

@st.fragment
def render_provisional_simulator(profile_name):
    """Standalone GPA projection for provisional batches — no portal contact."""
    st.subheader(f"Graduation CGPA Simulator ({profile_name})")
    st.markdown(
        "Project your graduation CGPA by entering expected performance for each semester. "
        "Use **Summary** mode for a quick GPA estimate, or **Detailed** to set per-course grades."
    )
    
    _dept = db.get_dept_from_profile(profile_name)
    target_key = f"prov_target_{profile_name}"
    target_cgpa = st.slider(
        "Target Graduation CGPA", min_value=2.00, max_value=4.00,
        value=3.00, step=0.05, key=target_key
    )
    
    all_semesters = []
    for sem_n in range(1, 9):
        cr = db.get_semester_total_credits(_dept, sem_n)
        if cr > 0:
            all_semesters.append({"semester": sem_n, "credits": cr})
    
    required_avg = round(target_cgpa, 2)
    st.info(f"Required average GPA across all semesters to hit target: **{required_avg:.2f}**")
    st.divider()
    
    _sim_inputs = []
    for _sem_info in all_semesters:
        _sem_n = _sem_info["semester"]
        _sem_cr = _sem_info["credits"]
        
        _mode_key = f"prov_mode_{profile_name}_{_sem_n}"
        _use_detailed = st.session_state.get(_mode_key, False)
        _include_key = f"prov_include_{profile_name}_{_sem_n}"
        
        with st.container(border=True):
            _hdr_c0, _hdr_c1, _hdr_c2, _hdr_c3 = st.columns([0.3, 2.5, 1.2, 1.2])
            with _hdr_c0:
                _include = st.checkbox("Incl", value=True, key=_include_key, label_visibility="collapsed")
            with _hdr_c1:
                _yr = (_sem_n - 1) // 2 + 1
                _s = 1 if _sem_n % 2 == 1 else 2
                st.markdown(f"**Year {_yr} Semester {_s}** ({_sem_cr:.2f} cr)")
            with _hdr_c2:
                st.toggle("Detailed", value=_use_detailed, key=_mode_key, disabled=not _include)
            _use_detailed = st.session_state.get(_mode_key, False)
            
            if not _include:
                st.caption("Excluded from projection.")
                continue
            
            if _use_detailed:
                _courses = db.get_semester_courses(_dept, _sem_n, include_all_electives=True)
                _course_grades = []
                _det_points = 0.0
                _det_credits = 0.0
                
                if not _courses:
                    st.info(f"No course mapping found for Semester {_sem_n}.")
                else:
                    _dept_clean = str(_dept).strip().upper()
                    _is_elective_sem = False
                    if ("CSE" in _dept_clean and _sem_n in (7, 8)) or ("CIVIL" in _dept_clean and _sem_n == 8):
                        _is_elective_sem = True

                    _total_sel_credits = 0.0
                    _credit_cap = db.get_semester_total_credits(_dept, _sem_n)

                    if _is_elective_sem:
                        for _c in _courses:
                            if not _c.get('is_elective', False):
                                _total_sel_credits += _c['credit']
                            else:
                                _chk_key = f"prov_select_{profile_name}_{_sem_n}_{_c['code']}"
                                if st.session_state.get(_chk_key, False):
                                    _total_sel_credits += _c['credit']

                        st.info(f"Selected Elective Credits: **{_total_sel_credits:.2f}** / **{_credit_cap:.2f}** cr")

                    for _c in _courses:
                        _is_selected = True
                        _disable_chk = False
                        
                        if _is_elective_sem and _c.get('is_elective', False):
                            _chk_key = f"prov_select_{profile_name}_{_sem_n}_{_c['code']}"
                            _is_checked = st.session_state.get(_chk_key, False)
                            if not _is_checked:
                                if _total_sel_credits >= _credit_cap or (_total_sel_credits + _c['credit'] > _credit_cap):
                                    _disable_chk = True
                            
                            _cg_c0, _cg_c1, _cg_c2 = st.columns([0.18, 2.82, 1.0])
                            with _cg_c0:
                                _is_selected = st.checkbox(
                                    "Select", value=False, key=_chk_key,
                                    disabled=_disable_chk, label_visibility="collapsed"
                                )
                        else:
                            _cg_c0, _cg_c1, _cg_c2 = st.columns([0.18, 2.82, 1.0])
                            with _cg_c0:
                                if _is_elective_sem:
                                    st.checkbox("Core", value=True, disabled=True, key=f"prov_core_chk_{profile_name}_{_sem_n}_{_c['code']}", label_visibility="collapsed")
                                else:
                                    st.markdown(" ")
                                    
                        with _cg_c1:
                            _c_label = _c.get('label', _c['code'])
                            _c_name_str = f" | *{_c['name']}*" if _c.get('name') else ""
                            if _disable_chk:
                                st.markdown(f"<span style='color: gray;'>`{_c_label}`{_c_name_str} &mdash; {_c['credit']:.2f} cr (Cap reached)</span>", unsafe_allow_html=True)
                            else:
                                st.markdown(f"`{_c_label}`{_c_name_str} &mdash; {_c['credit']:.2f} cr")
                                
                        with _cg_c2:
                            _gp_key = f"prov_gp_{profile_name}_{_sem_n}_{_c['code']}"
                            if _is_selected:
                                _VALID_FUTURE_GPA_OPTIONS = [0.00, 2.00, 2.25, 2.50, 2.75, 3.00, 3.25, 3.50, 3.75, 4.00]
                                _gp_val = st.select_slider(
                                    "GP", options=_VALID_FUTURE_GPA_OPTIONS, value=3.25,
                                    format_func=lambda x: "F" if x == 0.00 else f"{x:.2f}",
                                    key=_gp_key, label_visibility="collapsed"
                                )
                                _course_grades.append({'code': _c['code'], 'credit': _c['credit'], 'gp': _gp_val})
                                _det_points += _gp_val * _c['credit']
                                _det_credits += _c['credit']
                            else:
                                st.markdown("<span style='color: gray; font-size: 0.85rem; padding-top: 5px; display: inline-block;'>Excluded</span>", unsafe_allow_html=True)

                    if _det_credits > 0:
                        _calc_gpa = round(_det_points / _det_credits, 2)
                        st.success(f"Calculated GPA: **{_calc_gpa:.2f}** ({_det_credits:.2f} / {_sem_cr:.2f} cr filled)")
                    else:
                        st.caption("Enter course GPs above to calculate GPA.")
                
                _sim_inputs.append({'semester': _sem_n, 'mode': 'detailed', 'gpa': None, 'course_grades': _course_grades})
            else:
                with _hdr_c3:
                    _gpa_key = f"prov_gpa_{profile_name}_{_sem_n}"
                    _gpa_val = st.number_input(
                        "Expected GPA", min_value=0.00, max_value=4.00,
                        value=3.00, step=0.05, key=_gpa_key, label_visibility="collapsed"
                    )
                _sim_inputs.append({'semester': _sem_n, 'mode': 'summary', 'gpa': _gpa_val, 'course_grades': None})
    
    _result = db.compute_graduation_cgpa_from_inputs(
        adj_cgpa=0.0, adj_credits=0.0, remaining_semester_inputs=_sim_inputs, dept=_dept
    )
    
    st.markdown("---")
    _c1, _c2, _c3 = st.columns(3)
    with _c1:
        st.metric("Projected Graduation CGPA", f"{_result['graduation_cgpa']:.2f}")
    with _c2:
        st.metric("Total Credits", f"{_result['grand_total_credits']:.2f} cr")
    with _c3:
        _diff = _result['graduation_cgpa'] - target_cgpa
        st.metric("vs Target", f"{_diff:+.2f}", delta_color="normal" if _diff >= 0 else "inverse")
    
    with st.expander("Per-Semester Breakdown"):
        _bd_df = pd.DataFrame(_result['per_semester_detail'])
        _bd_df.columns = ['Semester', 'GPA', 'Credits', 'Quality Points']
        st.dataframe(_bd_df, hide_index=True, width="stretch")
    
    _g = _result['graduation_cgpa']
    if _g >= 3.75: st.success(f"**First Class with Distinction!** Projected: {_g:.2f}")
    elif _g >= 3.50: st.success(f"**First Class!** Projected: {_g:.2f}")
    elif _g >= 3.25: st.info(f"**Second Class (Upper).** Projected: {_g:.2f}")
    elif _g >= 2.75: st.info(f"**Second Class.** Projected: {_g:.2f}")
    elif _g >= 2.00: st.warning(f"**Pass.** Projected: {_g:.2f}")
    else: st.error(f"**Below graduation threshold.** Projected: {_g:.2f}")

@st.fragment
def render_student_projection_card(row):
    reg = row["reg_no"]
    sess_id = row.get("sess_id", "AUTO")
    name = row.get("name", f"Reg {reg}")
    profile_name = row["profile_name"]
    pro_id = row.get("pro_id", "")
    latest_gpa = row.get("latest_gpa", 0.0)
    latest_cgpa = row.get("latest_cgpa", 0.0)
    exam_count = row.get("exam_count", 0)

    if pro_id:
        _pre_warm_resources(pro_id)

    cache_key = f"{profile_name}_{reg}_{sess_id}"
    btn_key = f"proj_deep_{profile_name}_standalone_{reg}_{sess_id}"

    with st.container(border=True):
        hdr_col1, hdr_col2, hdr_col3, hdr_col4 = st.columns([3, 1.2, 1.2, 1.8])
        hdr_col1.markdown(f"**{name}** &nbsp; `{reg}` &nbsp; <span style='background:rgba(22, 163, 74, 0.15); color:#16A34A; padding:2px 8px; border-radius:12px; font-size:0.8rem; font-weight:600;'>{profile_name}</span>", unsafe_allow_html=True)
        hdr_col2.markdown(f"Latest GPA &nbsp;**{latest_gpa:.2f}**")
        hdr_col3.markdown(f"Latest CGPA &nbsp;**{latest_cgpa:.2f}**")

        already_done = cache_key in st.session_state._deep_cache

        if already_done:
            deep_res = st.session_state._deep_cache[cache_key]
            hdr_col4.markdown("✅ **Analysed**")

            if deep_res is None:
                retry_key = f"retry_{profile_name}_standalone_{reg}_{sess_id}"
                cols_err = st.columns([0.05, 0.55, 0.4])
                with cols_err[1]:
                    st.caption("⚠️ Could not fetch records — portal may be busy or student not found.")
                with cols_err[2]:
                    if st.button("Retry", key=retry_key, help="Re-run deep analysis for this student"):
                        del st.session_state._deep_cache[cache_key]
                        st.rerun()
            else:
                dept = db.get_dept_from_profile(profile_name)
                if f'_special_lookup_{dept}' not in st.session_state:
                    st.session_state[f'_special_lookup_{dept}'] = db.build_special_exam_lookup(dept)
                special_lookup = st.session_state[f'_special_lookup_{dept}']
                batch_first_years = db.get_batch_first_participation_years(profile_name)

                adv_proj = db.compute_advanced_projection(
                    deep_result=deep_res,
                    effective_grades=deep_res.get('effective_grades', {}),
                    retake_records=deep_res.get('retake_records', []),
                    profile_name=profile_name,
                    special_exam_lookup=special_lookup,
                    batch_first_years=batch_first_years,
                )
                
                def _semester_label(sem_num):
                    yr = (sem_num - 1) // 2 + 1
                    s = 1 if sem_num % 2 == 1 else 2
                    return f"{yr}-{s}"

                overrides = {}
                for pr in adv_proj['pending_retakes']:
                    chk_key = f"chk_{profile_name}_{reg}_{pr['code']}"
                    will_pass = st.session_state.get(chk_key, False)
                    if will_pass:
                        tgt_key = f"tgt_{profile_name}_{reg}_{pr['code']}"
                        overrides[pr['code']] = st.session_state.get(tgt_key, 2.00)
                    else:
                        overrides[pr['code']] = pr['current_gp']
                
                for ic in adv_proj['improvement_candidates']:
                    key = f"tgt_{profile_name}_{reg}_{ic['code']}"
                    overrides[ic['code']] = st.session_state.get(key, ic['current_gp'])

                adj_cgpa, adj_credits = db.compute_adjusted_cgpa(deep_res.get('effective_grades', {}), overrides)
                cgpa_gain = adj_cgpa - deep_res['true_cgpa']

                adj_pending_retake_count = 0
                for code, g in deep_res.get('effective_grades', {}).items():
                    gp = g['gp']
                    if code in overrides:
                        if overrides[code] > gp:
                            gp = overrides[code]
                    if gp < 2.0:
                        adj_pending_retake_count += 1

                adj_precise_target_gpa = 0.0
                if deep_res.get('promo_target') is not None and deep_res.get('next_sem_credits', 0) > 0:
                    adj_precise_target_gpa = (
                        deep_res['promo_target'] * (adj_credits + deep_res['next_sem_credits']) -
                        adj_cgpa * adj_credits
                    ) / deep_res['next_sem_credits']
                    adj_precise_target_gpa = max(0.0, round(adj_precise_target_gpa, 2))

                # --- Metrics Row ---
                diff = adj_cgpa - deep_res['official_cgpa']
                diff_str = f"+{diff:.2f}" if diff > 0 else f"{diff:.2f}"
                cols = st.columns([1, 1, 1])
                with cols[0]:
                    st.metric("True CGPA", f"{adj_cgpa:.2f}",
                         delta=f"{diff_str} vs official {deep_res['official_cgpa']:.2f}", delta_color="normal" if diff >= 0 else "inverse")
                with cols[1]:
                    if adj_precise_target_gpa > 0:
                        target_val = adj_precise_target_gpa
                        if target_val > 4.0:
                            st.metric("Precise Target GPA", "Impossible", delta=f"{target_val:.2f} > 4.00", delta_color="inverse")
                        else:
                            st.metric("Precise Target GPA", f"{target_val:.2f}", delta=f"Next sem ({deep_res['next_sem_credits']:.2f} cr)")
                    else:
                        st.metric("Target GPA", "N/A", delta="Even sem / computed")
                with cols[2]:
                    st.metric("Pending Retakes", f"{adj_pending_retake_count}", delta=f"{deep_res['total_credits']:.2f} cr completed")

                # --- Semester Breakdown ---
                _current_sem = deep_res.get("current_semester", 0)
                _official_sem_records = deep_res.get('official_semester_records', {})
                _sem_breakdown = db.compute_per_semester_breakdown(
                    effective_grades=deep_res.get('effective_grades', {}),
                    dept=dept,
                    current_semester=_current_sem,
                    overrides=overrides,
                    official_records=_official_sem_records,
                    profile_name=profile_name,
                )

                if _sem_breakdown:
                    with st.expander("Semester-wise GPA & CGPA Breakdown", expanded=False):
                        _hdr = st.columns([1, 1.2, 1.2, 1.2, 1.2, 0.8])
                        _hdr[0].markdown("**Semester**")
                        _hdr[1].markdown("**Official GPA**")
                        _hdr[2].markdown("**Adjusted GPA**")
                        _hdr[3].markdown("**Official CGPA**")
                        _hdr[4].markdown("**Adjusted CGPA**")
                        _hdr[5].markdown("**Credits**")
                        st.markdown("---")

                        for _sb in _sem_breakdown:
                            _row = st.columns([1, 1.2, 1.2, 1.2, 1.2, 0.8])
                            _row[0].markdown(f"**{_sb['label']}**")
                            _o_gpa = _sb.get('official_gpa')
                            _row[1].markdown(f"{_o_gpa:.2f}" if _o_gpa is not None else "—")
                            _gpa_diff = ""
                            if _o_gpa is not None and _o_gpa > 0:
                                _delta_g = _sb['computed_gpa'] - _o_gpa
                                if abs(_delta_g) >= 0.01:
                                    _color = "green" if _delta_g > 0 else "red"
                                    _gpa_diff = f" :{_color}[({_delta_g:+.2f})]"
                            _row[2].markdown(f"{_sb['computed_gpa']:.2f}{_gpa_diff}")
                            _o_cgpa = _sb.get('official_cgpa')
                            _row[3].markdown(f"{_o_cgpa:.2f}" if _o_cgpa is not None else "—")
                            _adj_diff = ""
                            if _o_cgpa is not None and _o_cgpa > 0:
                                _delta = _sb['computed_cgpa'] - _o_cgpa
                                if abs(_delta) >= 0.01:
                                    _color = "green" if _delta > 0 else "red"
                                    _adj_diff = f" :{_color}[({_delta:+.2f})]"
                            _row[4].markdown(f"{_sb['computed_cgpa']:.2f}{_adj_diff}")
                            _row[5].markdown(f"{_sb['credits']:.2f}")

                # --- ML Forecast ---
                pred_results = ml_predictor.predict_future_gpas(deep_res, dept, overrides=overrides)
                if pred_results:
                    with st.expander("Future GPA Forecast (ML-driven)", expanded=False):
                        p_c1, p_c2 = st.columns(2)
                        delta_cgpa = pred_results['predicted_grad_cgpa'] - adj_cgpa
                        trend_text = "Improving" if pred_results['trend_slope'] > 0.05 else "Declining" if pred_results['trend_slope'] < -0.05 else "Stable"
                        
                        p_c1.metric(
                            label="Predicted Graduation CGPA",
                            value=f"{pred_results['predicted_grad_cgpa']:.2f}",
                            delta=f"{delta_cgpa:+.2f} vs current Adjusted" if abs(delta_cgpa) >= 0.01 else "No change"
                        )
                        p_c2.markdown(f"**Trajectory Trend:** **{trend_text}** (Slope: {pred_results['trend_slope']:.4f})")
                        pred_text = ", ".join([f"Sem {s}: {g:.2f}" for s, g in pred_results['predictions'].items()])
                        st.info(f"**Forecasted Semesters:** {pred_text}")

                def _render_semester_grouped(items, render_fn):
                    from itertools import groupby
                    for sem_num, group in groupby(items, key=lambda x: x.get('semester', 0)):
                        group_list = list(group)
                        if sem_num > 0:
                            has_special = any(item.get('is_special') for item in group_list)
                            special_suffix = " :red[(Special)]" if has_special else ""
                            st.markdown(f"**━━ Semester {_semester_label(sem_num)}{special_suffix} ━━**")
                        else:
                            st.markdown("**━━ Other ━━**")
                        for item in group_list:
                            render_fn(item)

                if adv_proj['pending_retakes']:
                    with st.expander(f"{len(adv_proj['pending_retakes'])} Subject(s) Still Failing"):
                        def _render_retake(pr):
                            cc0, cc1, cc2 = st.columns([0.4, 3, 1])
                            with cc0:
                                will_pass_key = f"chk_{profile_name}_{reg}_{pr['code']}"
                                will_pass = st.checkbox("Pass", value=False, key=will_pass_key, label_visibility="collapsed")
                            with cc1:
                                gp_display = f"{pr['current_gp']:.2f}" if pr['current_gp'] > 0 else "F"
                                status_icon = "✅" if will_pass else "❌"
                                name_str = f" | *{pr['name']}*" if pr.get('name') else ""
                                st.markdown(f"{status_icon} **{pr['code']}**{name_str} \u2014 GP: {gp_display} ({pr['credit']:.2f} cr)")
                            with cc2:
                                if will_pass:
                                    key = f"tgt_{profile_name}_{reg}_{pr['code']}"
                                    st.number_input("Target GP", min_value=2.00, max_value=4.00, value=overrides.get(pr['code'], 2.00), step=0.25, key=key, label_visibility="collapsed")
                                else:
                                    st.caption("—")
                        _render_semester_grouped(adv_proj['pending_retakes'], _render_retake)
                
                if adv_proj['improvement_candidates']:
                    with st.expander(f"{len(adv_proj['improvement_candidates'])} Improvement Candidates"):
                        def _render_improvement(ic):
                            cc1, cc2 = st.columns([3, 1])
                            with cc1:
                                name_str = f" | *{ic['name']}*" if ic.get('name') else ""
                                st.markdown(f"**{ic['code']}**{name_str} \u2014 GP: {ic['current_gp']:.2f} ({ic['credit']:.2f} cr)")
                            with cc2:
                                key = f"tgt_{profile_name}_{reg}_{ic['code']}"
                                st.number_input("Target GP", min_value=ic['current_gp'], max_value=4.00, value=overrides[ic['code']], step=0.25, key=key, label_visibility="collapsed")
                        _render_semester_grouped(adv_proj['improvement_candidates'], _render_improvement)

                if adv_proj['already_attempted']:
                    with st.expander(f"Already Attempted ({len(adv_proj['already_attempted'])})"):
                        st.caption("These courses were previously retaken/improved but GP is still ≤ 2.75.")
                        def _render_attempted(aa):
                            name_str = f" | *{aa['name']}*" if aa.get('name') else ""
                            st.markdown(f"⚠️ **{aa['code']}**{name_str} \u2014 GP: {aa['current_gp']:.2f} | {aa['reason']}")
                        _render_semester_grouped(adv_proj['already_attempted'], _render_attempted)

                if adv_proj['ineligible_retake_cleared']:
                    _n_retake = sum(1 for x in adv_proj['ineligible_retake_cleared'] if x.get('clear_type') !='improvement_cleared')
                    _n_improv = sum(1 for x in adv_proj['ineligible_retake_cleared'] if x.get('clear_type') =='improvement_cleared')
                    _counts_parts = []
                    if _n_retake: _counts_parts.append(f"{_n_retake} retake")
                    if _n_improv: _counts_parts.append(f"{_n_improv} improvement")
                    _counts_str = ", ".join(_counts_parts) if _counts_parts else str(len(adv_proj['ineligible_retake_cleared']))
                    with st.expander(f"Cleared (not improvable, {_counts_str})"):
                        def _render_cleared(irc):
                            name_str = f" | *{irc['name']}*" if irc.get('name') else ""
                            _orig = irc.get('original_gp', irc['current_gp'])
                            _delta = irc['current_gp'] - _orig
                            badge = f' <span style="background:#22c55e;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.8em;">+{_delta:.2f} improved</span>' if _delta > 0 else ""
                            st.markdown(f"**{irc['code']}**{name_str} \u2014 GP: {irc['current_gp']:.2f}{badge} | {irc['reason']}", unsafe_allow_html=True)
                        _render_semester_grouped(adv_proj['ineligible_retake_cleared'], _render_cleared)

                st.caption(f"Analyzed {deep_res['effective_grade_count']} subjects across {deep_res['semesters_found']} semester(s)")

                # --- Graduation Target Calculator ---
                st.markdown("---")
                st.markdown("##### Graduation Target Calculator")
                _remaining_sems = max(0, 8 - _current_sem)

                if _remaining_sems == 0:
                    st.success(f"This student has completed all 8 semesters. Final Adjusted CGPA: **{adj_cgpa:.2f}**")
                    target_cgpa = float(adj_cgpa)
                    proj = {
                        'target_grad_cgpa': target_cgpa, 'already_met': True, 'is_achievable': True,
                        'required_avg_gpa': 0.0, 'remaining_semesters': 0, 'remaining_credits': 0.0,
                        'remaining_credits_breakdown': []
                    }
                else:
                    target_key = f"target_cgpa_{profile_name}_{reg}"
                    target_cgpa = st.slider(
                        "Target Graduation CGPA", min_value=2.00, max_value=4.00,
                        value=max(2.00, min(4.00, float(adj_cgpa))), step=0.05, key=target_key
                    )
                    proj = db.compute_graduation_projection(
                        deep_result=deep_res, target_grad_cgpa=target_cgpa, dept=dept,
                        adj_cgpa=adj_cgpa, adj_credits=adj_credits,
                    )

                    p_c1, p_c2, p_c3 = st.columns(3)
                    with p_c1:
                        if proj["already_met"]:
                            st.metric("Required Avg GPA", "Already Met", delta=f"Current Adj: {proj['current_true_cgpa']:.2f}")
                        elif not proj["is_achievable"]:
                            st.metric("Required Avg GPA", "Impossible", delta=f"Needs {proj['required_avg_gpa']:.2f} > 4.00", delta_color="inverse")
                        else:
                            st.metric("Required Avg GPA", f"{proj['required_avg_gpa']:.2f}", delta="per semester on avg")
                    with p_c2:
                        st.metric("Adjusted CGPA", f"{adj_cgpa:.2f}", delta=f"+{cgpa_gain:.2f} from targets" if cgpa_gain > 0 else None)
                    with p_c3:
                        st.metric("Remaining Semesters", proj["remaining_semesters"], delta=f"{proj['remaining_credits']:.2f} credits left")

                    if proj["already_met"]:
                        st.success(f"**{name}** already has an Adjusted CGPA of **{proj['current_true_cgpa']:.2f}**, which exceeds the target of **{target_cgpa:.2f}**.")
                    elif not proj["is_achievable"]:
                        st.error(f"**Mathematically impossible.** Even with a perfect 4.00 in all {proj['remaining_semesters']} remaining semester(s), the target cannot be reached.")
                    elif proj["required_avg_gpa"] >= 3.75:
                        st.warning(f"**Very challenging.** Needs an average GPA of **{proj['required_avg_gpa']:.2f}** across remaining semester(s).")
                    elif proj["required_avg_gpa"] >= 3.25:
                        st.info(f"**Ambitious but achievable.** Needs **{proj['required_avg_gpa']:.2f}** avg GPA over remaining semester(s).")
                    else:
                        st.success(f"**Well within reach.** Needs **{proj['required_avg_gpa']:.2f}** avg GPA over remaining semester(s).")

                    # --- Graduation CGPA Simulator ---
                    st.markdown("---")
                    st.markdown("##### Graduation CGPA Simulator")
                    st.caption("Input your expected performance for each remaining semester. Mix Summary or Detailed modes.")

                    _sim_semester_inputs = []
                    for _sem_info in proj["remaining_credits_breakdown"]:
                        _sem_n = _sem_info["semester"]
                        _sem_cr = _sem_info["credits"]
                        _mode_key = f"sim_mode_{profile_name}_{reg}_{_sem_n}"
                        _use_detailed = st.session_state.get(_mode_key, False)
                        _include_key = f"sim_include_{profile_name}_{reg}_{_sem_n}"

                        with st.container(border=True):
                            _hdr_c0, _hdr_c1, _hdr_c2, _hdr_c3 = st.columns([0.3, 2.5, 1.2, 1.2])
                            with _hdr_c0:
                                _include = st.checkbox("Incl", value=True, key=_include_key, label_visibility="collapsed")
                            with _hdr_c1:
                                st.markdown(f"**Semester {_sem_n}** ({_sem_cr:.2f} cr)")
                            with _hdr_c2:
                                st.toggle("Detailed", value=_use_detailed, key=_mode_key, disabled=not _include)
                            _use_detailed = st.session_state.get(_mode_key, False)

                            if not _include:
                                st.caption("Semester excluded from projection calculation.")
                                continue

                            if _use_detailed:
                                _courses = db.get_semester_courses(dept, _sem_n, include_all_electives=True)
                                _course_grades = []
                                _det_points = 0.0
                                _det_credits = 0.0

                                if not _courses:
                                    st.info(f"No course mapping found for Semester {_sem_n}.")
                                else:
                                    _dept_clean = str(dept).strip().upper()
                                    _is_elective_sem = ("CSE" in _dept_clean and _sem_n in (7, 8)) or ("CIVIL" in _dept_clean and _sem_n == 8)
                                    _total_sel_credits = 0.0
                                    _credit_cap = db.get_semester_total_credits(dept, _sem_n)

                                    if _is_elective_sem:
                                        for _c in _courses:
                                            if not _c.get('is_elective', False):
                                                _total_sel_credits += _c['credit']
                                            else:
                                                _chk_key = f"sim_select_{profile_name}_{reg}_{_sem_n}_{_c['code']}"
                                                if st.session_state.get(_chk_key, False):
                                                    _total_sel_credits += _c['credit']

                                        st.info(f"Selected Elective Credits: **{_total_sel_credits:.2f}** / **{_credit_cap:.2f}** cr")

                                    for _c in _courses:
                                        _is_selected = True
                                        _disable_chk = False
                                        if _is_elective_sem and _c.get('is_elective', False):
                                            _chk_key = f"sim_select_{profile_name}_{reg}_{_sem_n}_{_c['code']}"
                                            _is_checked = st.session_state.get(_chk_key, False)
                                            if not _is_checked:
                                                if _total_sel_credits >= _credit_cap or (_total_sel_credits + _c['credit'] > _credit_cap):
                                                    _disable_chk = True
                                            _cg_c0, _cg_c1, _cg_c2 = st.columns([0.18, 2.82, 1.0])
                                            with _cg_c0:
                                                _is_selected = st.checkbox("Select", value=False, key=_chk_key, disabled=_disable_chk, label_visibility="collapsed")
                                        else:
                                            _cg_c0, _cg_c1, _cg_c2 = st.columns([0.18, 2.82, 1.0])
                                            with _cg_c0:
                                                if _is_elective_sem:
                                                    st.checkbox("Core", value=True, disabled=True, key=f"sim_core_chk_{profile_name}_{reg}_{_sem_n}_{_c['code']}", label_visibility="collapsed")
                                                else:
                                                    st.markdown(" ")
                                        with _cg_c1:
                                            _c_label = _c.get('label', _c['code'])
                                            _c_name_str = f" | *{_c['name']}*" if _c.get('name') else ""
                                            if _disable_chk:
                                                st.markdown(f"<span style='color: gray;'>`{_c_label}`{_c_name_str} &mdash; {_c['credit']:.2f} cr (Cap reached)</span>", unsafe_allow_html=True)
                                            else:
                                                st.markdown(f"`{_c_label}`{_c_name_str} &mdash; {_c['credit']:.2f} cr")
                                        with _cg_c2:
                                            _gp_key = f"sim_gp_{profile_name}_{reg}_{sess_id}_{_sem_n}_{_c['code']}"
                                            if _is_selected:
                                                _VALID_FUTURE_GPA_OPTIONS = [0.00, 2.00, 2.25, 2.50, 2.75, 3.00, 3.25, 3.50, 3.75, 4.00]
                                                _gp_val = st.select_slider("GP", options=_VALID_FUTURE_GPA_OPTIONS, value=3.25, format_func=lambda x: "F" if x == 0.00 else f"{x:.2f}", key=_gp_key, label_visibility="collapsed")
                                                _course_grades.append({'code': _c['code'], 'credit': _c['credit'], 'gp': _gp_val})
                                                _det_points += _gp_val * _c['credit']
                                                _det_credits += _c['credit']
                                            else:
                                                st.markdown("<span style='color: gray; font-size: 0.85rem; padding-top: 5px; display: inline-block;'>Excluded</span>", unsafe_allow_html=True)

                                    if _det_credits > 0:
                                        _calc_gpa = round(_det_points / _det_credits, 2)
                                        st.success(f"Calculated GPA: **{_calc_gpa:.2f}** ({_det_credits:.2f} / {_sem_cr:.2f} cr filled)")
                                    else:
                                        st.caption("Enter course GPs above to calculate GPA.")

                                _sim_semester_inputs.append({'semester': _sem_n, 'mode':'detailed', 'gpa': None, 'course_grades': _course_grades})
                            else:
                                with _hdr_c3:
                                    _gpa_key = f"sim_gpa_{profile_name}_{reg}_{sess_id}_{_sem_n}"
                                    _gpa_val = st.number_input("Expected GPA", min_value=0.00, max_value=4.00, value=3.00, step=0.05, key=_gpa_key, label_visibility="collapsed")
                                _sim_semester_inputs.append({'semester': _sem_n, 'mode':'summary', 'gpa': _gpa_val, 'course_grades': None})

                    _sim_result = db.compute_graduation_cgpa_from_inputs(
                        adj_cgpa=adj_cgpa, adj_credits=adj_credits,
                        remaining_semester_inputs=_sim_semester_inputs, dept=dept,
                    )

                    st.markdown("---")
                    _sim_c1, _sim_c2, _sim_c3 = st.columns(3)
                    with _sim_c1:
                        _grad_cgpa = _sim_result['graduation_cgpa']
                        _grad_delta = _grad_cgpa - adj_cgpa
                        st.metric("Projected Graduation CGPA", f"{_grad_cgpa:.2f}", delta=f"{_grad_delta:+.2f} from current adjusted", delta_color="normal" if _grad_delta >= 0 else "inverse")
                    with _sim_c2:
                        st.metric("Total Credits (All 8 Sems)", f"{_sim_result['grand_total_credits']:.2f} cr")
                    with _sim_c3:
                        st.metric("New Credits Projected", f"{_sim_result['total_new_credits']:.2f} cr", delta=f"from {len(_sim_semester_inputs)} semester(s)")

                    with st.expander("Per-Semester Breakdown"):
                        _bd_df = pd.DataFrame(_sim_result['per_semester_detail'])
                        _bd_df.columns = ['Semester','GPA','Credits','Quality Points']
                        st.dataframe(_bd_df, hide_index=True, width='stretch')

                    if _grad_cgpa >= 3.75: st.success(f"**First Class with Distinction!** Projected CGPA: {_grad_cgpa:.2f}")
                    elif _grad_cgpa >= 3.50: st.success(f"**First Class!** Projected CGPA: {_grad_cgpa:.2f}")
                    elif _grad_cgpa >= 3.25: st.info(f"**Second Class (Upper).** Projected CGPA: {_grad_cgpa:.2f}")
                    elif _grad_cgpa >= 2.75: st.info(f"**Second Class.** Projected CGPA: {_grad_cgpa:.2f}")
                    elif _grad_cgpa >= 2.00: st.warning(f"**Pass.** Projected CGPA: {_grad_cgpa:.2f}")
                    else: st.error(f"**Below minimum graduation threshold.** Projected CGPA: {_grad_cgpa:.2f}")

                    # --- Reset & PDF Actions ---
                    st.markdown("---")
                    _act_spacer, act_col1, act_col2 = st.columns([2, 1, 1])
                    with act_col1:
                        reset_btn_key = f"reset_sim_{profile_name}_{reg}"
                        if st.button("Reset Simulation", key=reset_btn_key, width="stretch"):
                            keys_to_remove = []
                            for k in list(st.session_state.keys()):
                                if (k.startswith(f"chk_{profile_name}_{reg}_") or 
                                    k.startswith(f"tgt_{profile_name}_{reg}_") or 
                                    k.startswith(f"target_cgpa_{profile_name}_{reg}") or
                                    k.startswith(f"sim_mode_{profile_name}_{reg}_") or
                                    k.startswith(f"sim_include_{profile_name}_{reg}_") or
                                    k.startswith(f"sim_select_{profile_name}_{reg}_") or
                                    k.startswith(f"sim_gp_{profile_name}_{reg}_") or
                                    k.startswith(f"sim_gpa_{profile_name}_{reg}_")):
                                    keys_to_remove.append(k)
                            for k in keys_to_remove:
                                del st.session_state[k]
                            st.rerun()
                    with act_col2:
                        pdf_btn_key = f"pdf_sim_{profile_name}_{reg}"
                        pdf_grad_proj = {
                            'target_grad_cgpa': target_cgpa, 'already_met': proj['already_met'],
                            'is_achievable': proj['is_achievable'], 'required_avg_gpa': proj['required_avg_gpa']
                        }
                        try:
                            pdf_data = db.generate_student_projection_pdf(
                                student_name=name, reg_no=reg, profile_name=profile_name,
                                deep_res=deep_res, adv_proj=adv_proj, overrides=overrides,
                                adj_cgpa=adj_cgpa, adj_credits=adj_credits,
                                precise_target_gpa=adj_precise_target_gpa,
                                sem_breakdown=_sem_breakdown, grad_proj=pdf_grad_proj, dept=dept
                            )
                            st.download_button(
                                label="Save as PDF", data=pdf_data,
                                file_name=f"GPA_Projection_{reg}_{name.replace(' ', '_')}.pdf",
                                mime="application/pdf", key=pdf_btn_key, width="stretch"
                            )
                        except Exception as pdf_err:
                            st.error(f"Could not generate PDF: {pdf_err}")
        else:
            with hdr_col4:
                if st.button("Deep Analysis", key=btn_key, help=f"Fetch full record for {name} and compute True CGPA + projections", width="stretch"):
                    exams = db.get_exams_for_profile(profile_name)
                    latest_exam_lbl = exam_label(exams[0]) if exams else ""
                    with st.spinner(f"Scanning full academic history for {name} ({reg})… 1–2 min."):
                        result = _run_deep_analysis(reg, name, sess_id, profile_name, pro_id, latest_exam_lbl)
                    st.session_state._deep_cache[cache_key] = result
                    st.rerun(scope="fragment")

@st.fragment
def render_paginated_projections(proj_df):
    if proj_df.empty:
        st.warning("No students match your search criteria.")
        return

    st.markdown(f"Found **{len(proj_df)} student record(s)** across batches — click Deep Analysis to run projections.")
    st.divider()

    PAGE_SIZE = 10
    total_pages = max(1, (len(proj_df) + PAGE_SIZE - 1) // PAGE_SIZE)

    if "standalone_proj_page" not in st.session_state:
        st.session_state.standalone_proj_page = 0
    if st.session_state.standalone_proj_page >= total_pages:
        st.session_state.standalone_proj_page = 0

    page = st.session_state.standalone_proj_page
    page_df = proj_df.iloc[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    for _, row in page_df.iterrows():
        render_student_projection_card(row)

    if total_pages > 1:
        nav_c1, nav_c2, nav_c3 = st.columns([1, 2, 1])
        with nav_c1:
            if st.button("← Previous", key="standalone_proj_prev", disabled=(page == 0)):
                st.session_state.standalone_proj_page -= 1
                st.rerun(scope="fragment")
        with nav_c2:
            st.markdown(f"<div style='text-align:center;padding-top:6px'>Page {page+1} of {total_pages}</div>", unsafe_allow_html=True)
        with nav_c3:
            if st.button("Next →", key="standalone_proj_next", disabled=(page >= total_pages - 1)):
                st.session_state.standalone_proj_page += 1
                st.rerun(scope="fragment")

# --- Main Search Logic ---
if not query and not filter_profile_name:
    pass
else:
    q_lower = query.lower().strip() if query else ""
    if q_lower and any(kw in q_lower for kw in ["prov", "provisional", "provincial"]):
        st.subheader("Provisional Batch Graduation CGPA Simulators")
        st.caption("Select a department below to simulate 8-semester graduation CGPA without portal exam data:")
        prov_tabs = st.tabs(["CSE Department", "EEE Department", "Civil Department"])
        with prov_tabs[0]:
            render_provisional_simulator("cse provisional")
        with prov_tabs[1]:
            render_provisional_simulator("eee provisional")
        with prov_tabs[2]:
            render_provisional_simulator("civil provisional")
    else:
        # Fetch results from DB
        raw_results = db.search_students_across_profiles(query=query, filter_profile=filter_profile_name)
        
        if not raw_results:
            # Check if selected batch is provisional
            if filter_profile_name and profiles.get(filter_profile_name, {}).get("is_provisional", False):
                render_provisional_simulator(filter_profile_name)
            else:
                st.warning("No students found matching your search query.")
        else:
            results_df = pd.DataFrame(raw_results)
            render_paginated_projections(results_df)

st.divider()
ui.add_contact_section()
