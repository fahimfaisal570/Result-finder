import streamlit as st
import pandas as pd
import numpy as np
import os
import re
import altair as alt
import sys
import time
import json
import ui_components as ui

st.set_page_config(page_title="Result Analytics", page_icon="favicon.ico", layout="wide")
ui.inject_essential_ui()

# Add parent dir for database import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
import cli_scraper as cs

if "is_admin" not in st.session_state:
    st.session_state.is_admin = True

# ---------------------------------------------------------------------------
# Helper Logic
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def load_base_df(profile_name, exam_id):
  results = db.get_student_data_for_exam(profile_name, exam_id)
  df = pd.DataFrame(results)
  return df

@st.cache_data(ttl=60)
def load_subject_df(profile_name, exam_id):
  results = db.get_subject_data_for_exam(profile_name, exam_id)
  return pd.DataFrame(results)

@st.cache_data(ttl=300)
def load_exams(profile_name):
  return db.get_exams_for_profile(profile_name)

@st.cache_data(ttl=300)
def load_retake_stats(profile_name):
  return db.get_retake_success_stats(profile_name)

@st.cache_data(ttl=300)
def load_batch_max_semester(profile_name):
  val = db.get_batch_max_semester(profile_name)
  return val if val > 0 else None

@st.cache_data(ttl=300)
def load_longitudinal(profile_name, max_semester):
  return db.get_longitudinal_data(profile_name, max_semester)

def get_promotion_rules(exam_label):
  promo_target = None
  is_even_sem = False
  yr = None
  
  yr_match = re.search(r"(\d)[a-z]{2}\s*Yr", exam_label, re.IGNORECASE)
  if not yr_match:
    yr_match = re.search(r"(\d)[a-z]{2}\s*Year", exam_label, re.IGNORECASE)
    
  sem_match = re.search(r"(\d)[a-z]{2}\s*Sem", exam_label, re.IGNORECASE)
  if not sem_match:
    sem_match = re.search(r"(\d)[a-z]{2}\s*Semester", exam_label, re.IGNORECASE)
    
  if sem_match:
    sem = int(sem_match.group(1))
    is_even_sem = (sem % 2 == 0)
    if not yr_match:
      yr = (sem - 1) // 2 + 1
      
  if yr_match:
    yr = int(yr_match.group(1))
    
  if yr is not None:
    if yr == 1: promo_target = 2.00
    elif yr == 2: promo_target = 2.25
    elif yr == 3: promo_target = 2.50
    elif yr == 4: promo_target = None  # No promotion threshold/graduation risk check for Year 4
    
  return promo_target, is_even_sem, yr

# ---------------------------------------------------------------------------
# UI Setup
# ---------------------------------------------------------------------------

st.page_link("app.py", label="← Back to Dashboard", icon=":material/arrow_back:")
st.title("Integrated Batch Analytics")
st.markdown("Measuring first-chance performance, cohort bottlenecks, and strategic eligibility.")

profiles = db.get_profiles()
if not profiles:
  st.warning("No saved profiles found. Run a scan first.")
  st.stop()

# ---------------------------------------------------------------------------
# SIDEBAR — Connectivity & Selection
# ---------------------------------------------------------------------------
st.sidebar.header("Slice & Dice (OLAP)")

sorted_profiles = sorted(list(profiles.keys()))
profile_name = st.sidebar.selectbox("Select Batch:", sorted_profiles)

@st.fragment
def render_provisional_simulator(profile_name):
    """Standalone GPA projection for provisional batches — no portal contact."""
    st.subheader("Graduation CGPA Simulator")
    st.markdown(
        "Project your graduation CGPA by entering expected performance for each semester. "
        "Use **Summary** mode for a quick GPA estimate, or **Detailed** to set per-course grades."
    )
    
    _dept = db.get_dept_from_profile(profile_name)
    
    # --- Target Graduation CGPA ---
    target_key = f"prov_target_{profile_name}"
    target_cgpa = st.slider(
        "Target Graduation CGPA", min_value=2.00, max_value=4.00,
        value=3.00, step=0.05, key=target_key
    )
    
    # --- Build all 8 semesters as "remaining" ---
    all_semesters = []
    for sem_n in range(1, 9):
        cr = db.get_semester_total_credits(_dept, sem_n)
        if cr > 0:
            all_semesters.append({"semester": sem_n, "credits": cr})
    
    # Required avg GPA for target (with 0 credits completed)
    required_avg = round(target_cgpa, 2)  # With 0 credits done, required = target itself
    
    if target_cgpa > 4.00:
        st.error("Impossible — maximum CGPA is 4.00.")
    else:
        st.info(f"Required average GPA across all semesters to hit target: **{required_avg:.2f}**")
    
    st.divider()
    
    # --- Per-semester input (reuse existing Summary/Detailed UI pattern) ---
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
                _include = st.checkbox("Incl", value=True, key=_include_key,
                                       label_visibility="collapsed")
            with _hdr_c1:
                _yr = (_sem_n - 1) // 2 + 1
                _s = 1 if _sem_n % 2 == 1 else 2
                st.markdown(f"**Year {_yr} Semester {_s}** ({_sem_cr:.2f} cr)")
            with _hdr_c2:
                st.toggle("Detailed", value=_use_detailed, key=_mode_key,
                          disabled=not _include)
            _use_detailed = st.session_state.get(_mode_key, False)
            
            if not _include:
                st.caption("Excluded from projection.")
                continue
            
            if _use_detailed:
                # Per-course grade input (reuse existing elective-aware UI)
                _courses = db.get_semester_courses(_dept, _sem_n, include_all_electives=True)
                _course_grades = []
                _det_points = 0.0
                _det_credits = 0.0
                
                if not _courses:
                    st.info(f"No course mapping found for Semester {_sem_n}.")
                else:
                    # Pre-pass to compute total selected credits for elective-enabled semesters
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
                            
                            # Enforce the hard cap
                            if not _is_checked:
                                if _total_sel_credits >= _credit_cap or (_total_sel_credits + _c['credit'] > _credit_cap):
                                    _disable_chk = True
                            
                            _cg_c0, _cg_c1, _cg_c2 = st.columns([0.18, 2.82, 1.0])
                            with _cg_c0:
                                _is_selected = st.checkbox(
                                    "Select",
                                    value=False,
                                    key=_chk_key,
                                    disabled=_disable_chk,
                                    label_visibility="collapsed"
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
                                    "GP",
                                    options=_VALID_FUTURE_GPA_OPTIONS,
                                    value=3.25,
                                    format_func=lambda x: "F" if x == 0.00 else f"{x:.2f}",
                                    key=_gp_key,
                                    label_visibility="collapsed"
                                )
                                _course_grades.append({
                                    'code': _c['code'],
                                    'credit': _c['credit'],
                                    'gp': _gp_val,
                                })
                                _det_points += _gp_val * _c['credit']
                                _det_credits += _c['credit']
                            else:
                                st.markdown("<span style='color: gray; font-size: 0.85rem; padding-top: 5px; display: inline-block;'>Excluded</span>", unsafe_allow_html=True)

                    if _det_credits > 0:
                        _calc_gpa = round(_det_points / _det_credits, 2)
                        st.success(
                            f"Calculated GPA: **{_calc_gpa:.2f}** "
                            f"({_det_credits:.2f} / {_sem_cr:.2f} cr filled)"
                        )
                    else:
                        st.caption("Enter course GPs above to calculate GPA.")
                
                _sim_inputs.append({
                    'semester': _sem_n, 'mode': 'detailed',
                    'gpa': None, 'course_grades': _course_grades
                })
            else:
                # Summary GPA input
                with _hdr_c3:
                    _gpa_key = f"prov_gpa_{profile_name}_{_sem_n}"
                    _gpa_val = st.number_input(
                        "Expected GPA", min_value=0.00, max_value=4.00,
                        value=3.00, step=0.05, key=_gpa_key,
                        label_visibility="collapsed"
                    )
                _sim_inputs.append({
                    'semester': _sem_n, 'mode': 'summary',
                    'gpa': _gpa_val, 'course_grades': None
                })
    
    # --- Compute Result ---
    _result = db.compute_graduation_cgpa_from_inputs(
        adj_cgpa=0.0,        # No prior academic history
        adj_credits=0.0,     # No credits completed
        remaining_semester_inputs=_sim_inputs,
        dept=_dept,
    )
    
    # --- Display ---
    st.markdown("---")
    _c1, _c2, _c3 = st.columns(3)
    with _c1:
        st.metric("Projected Graduation CGPA", f"{_result['graduation_cgpa']:.2f}")
    with _c2:
        st.metric("Total Credits", f"{_result['grand_total_credits']:.2f} cr")
    with _c3:
        _diff = _result['graduation_cgpa'] - target_cgpa
        st.metric("vs Target", f"{_diff:+.2f}",
                  delta_color="normal" if _diff >= 0 else "inverse")
    
    # Per-semester breakdown
    with st.expander("Per-Semester Breakdown"):
        _bd_df = pd.DataFrame(_result['per_semester_detail'])
        _bd_df.columns = ['Semester', 'GPA', 'Credits', 'Quality Points']
        st.dataframe(_bd_df, hide_index=True, use_container_width=True)
    
    # Classification
    _g = _result['graduation_cgpa']
    if _g >= 3.75: st.success(f"**First Class with Distinction!** Projected: {_g:.2f}")
    elif _g >= 3.50: st.success(f"**First Class!** Projected: {_g:.2f}")
    elif _g >= 3.25: st.info(f"**Second Class (Upper).** Projected: {_g:.2f}")
    elif _g >= 2.75: st.info(f"**Second Class.** Projected: {_g:.2f}")
    elif _g >= 2.00: st.warning(f"**Pass.** Projected: {_g:.2f}")
    else: st.error(f"**Below graduation threshold.** Projected: {_g:.2f}")

exams = load_exams(profile_name)
_is_provisional = profiles.get(profile_name, {}).get('is_provisional', False)

if not exams and not _is_provisional:
  st.warning("No exam data found for this batch. Ingest a semester first.")
  st.stop()

if not exams and _is_provisional:
  st.info(
    "🔶 **Provisional Batch** — No exam results published yet. "
    "The exam monitor will auto-detect, scan, run readd detection, "
    "and promote this batch when results appear on the portal.\n\n"
    "Use the **Graduation CGPA Simulator** below to project future performance."
  )
  
  # --- Student Roster ---
  p_data = profiles.get(profile_name, {})
  roster = [{"Reg No": r[0], "Session": r[1], "Name": r[2]} for r in p_data.get("regs", [])]
  if roster:
    with st.expander(f"📋 Student Roster ({len(roster)} students)", expanded=False):
      st.dataframe(pd.DataFrame(roster), hide_index=True, use_container_width=True)
  
  # --- Standalone Graduation CGPA Simulator ---
  st.divider()
  render_provisional_simulator(profile_name)
  
  ui.add_contact_section()
  st.stop()

# Build display labels: "Exam Name (exam_id)" — latest on top
def exam_label(e):
  name = e.get('exam_name') or f"Exam {e['exam_id']}"
  
  # Intelligently condense names like "B.Sc. in Computer Science... 3rd year 1st Semester... of 2024"
  pattern = r'(?i)(\d[A-Za-z]+)\s+year\s+(\d[A-Za-z]+)\s+Semester.*?(?:of\s+)?(\d{4})'
  match = re.search(pattern, name)
  if match:
    name = f"{match.group(1).capitalize()} Yr {match.group(2).capitalize()} Sem'{match.group(3)[-2:]}"
  elif len(name) > 40:
    name = name[:37] + "…"
    
  return f"{name} [{e['exam_id']}]"

exam_options = {exam_label(e): e for e in exams}
selected_label = st.sidebar.selectbox("Select Semester:", list(exam_options.keys()))
selected_exam = exam_options[selected_label]
exam_id    = selected_exam['exam_id']

st.sidebar.divider()

# ---------------------------------------------------------------------------
# Exam Management expander
# ---------------------------------------------------------------------------
with st.sidebar.expander("Exam Management", expanded=False):
  scanned_at = selected_exam.get('scanned_at')
  scan_time = time.strftime('%Y-%m-%d %H:%M', time.localtime(scanned_at)) if scanned_at else "Unknown"
  st.markdown(f"**Exam ID:** `{exam_id}`")
  st.markdown(f"**Students ingested:** {selected_exam.get('student_count','?')}")
  st.markdown(f"**Last scanned:** {scan_time}")

  st.markdown("---")
  st.markdown("**⚠️ Danger Zone**")
  if st.session_state.get("is_admin", False):
    confirm_delete = st.checkbox("Confirm — I want to delete this exam scan", key=f"del_confirm_{exam_id}")
    if st.button("Delete This Exam Scan", type="primary", disabled=not confirm_delete):
      db.delete_exam(profile_name, exam_id)
      st.cache_data.clear()
      st.success(f"Exam `{exam_id}` deleted. Student roster preserved.")
      st.rerun()
  else:
    st.info("🔒 Admin access required to manage exam scans.")

# ---------------------------------------------------------------------------
# Load data scoped to selected exam
# ---------------------------------------------------------------------------
df_raw   = load_base_df(profile_name, exam_id)
df_sub_raw = load_subject_df(profile_name, exam_id)

max_semester = load_batch_max_semester(profile_name)

_longitudinal_raw = load_longitudinal(profile_name, max_semester)
if _longitudinal_raw:
  df_longitudinal = pd.DataFrame([
    {**entry,'reg_no': reg}
    for reg, entries in _longitudinal_raw.items()
    for entry in entries
  ])
else:
  df_longitudinal = None

if df_raw.empty:
  st.info("No exam results found for this semester. Try selecting a different exam or rescanning.")
  st.stop()

# --- Readd Notification Disclaimer ---
notify_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "readd_notifications.json")
try:
  if os.path.exists(notify_file):
    with open(notify_file, "r") as nf:
      notif_data = json.load(nf)
    key = f"{profile_name}_{exam_id}"
    if key in notif_data and notif_data[key]:
      readds = notif_data[key]
      readd_names = ", ".join([f"{r['name']} ({r['reg_no']})" for r in readds])
      st.caption(f"ℹ **Note:** {readd_names} joined this batch in this exam (Readmitted).")
except Exception:
  pass
# --------------------------------------


# ---------------------------------------------------------------------------
# SIDEBAR — Slice & Dice filters
# ---------------------------------------------------------------------------
subjects_available = sorted(df_sub_raw['subject_code'].unique().tolist()) if not df_sub_raw.empty else []
selected_subjects = st.sidebar.multiselect("Slice by Subjects:", subjects_available, default=subjects_available)
cgpa_range     = st.sidebar.slider("CGPA Range:", 0.0, 4.0, (0.0, 4.0))

st.sidebar.divider()
show_strategic_brief = st.sidebar.toggle("Strategic Insights Mode", value=False, help="Display an executive summary for the Department Head.")
st.sidebar.info("Analytics engine optimized for university graduation standards.")

# ---------------------------------------------------------------------------
# INCOMPLETE HISTORY DETECTION (Readd / Cross-Batch Students)
# Checks if any student has fewer exam records than the profile's scan count.
# This is the signature of a readd student whose previous batch semesters
# were never scanned into this profile.
# ---------------------------------------------------------------------------
_incomplete_students = db.get_incomplete_history_students(profile_name)
if _incomplete_students:
  with st.expander(
    f"⚠️ Incomplete Scan History Detected — {len(_incomplete_students)} Student(s)",
    expanded=False
  ):
    st.warning(
      "The following student(s) have fewer semester records than this batch has published. "
      "They are likely **readd students** whose Year 1 results exist under a previous batch. "
      "Click **Scan & Fix** to retrieve their full academic history from the portal and recalculate their CGPA accurately.",
      icon="🔍"
    )

    _p_data  = profiles.get(profile_name, {})
    _pro_id  = _p_data.get("pro_id", "")

    for _s in _incomplete_students:
      _col1, _col2 = st.columns([4, 1])
      _col1.markdown(
        f"**{_s['name']}** &nbsp; `{_s['reg_no']}` &nbsp;|&nbsp; "
        f"Found **{_s['student_exam_count']}** / **{_s['profile_exam_count']}** semester(s)"
      )
      _fix_key = f"fix_{profile_name}_{_s['reg_no']}"
      if _col2.button("Scan & Fix", key=_fix_key, type="primary"):

        st.info(f"🔍 Scanning full academic history for **{_s['name']}** ({_s['reg_no']})…")

        # Fetch portal session list and full exam catalogue for this program
        with st.spinner("Fetching portal data…"):
          _programs, _sessions = cs.fetch_programs_and_sessions()
          _all_exams = cs.fetch_exams(_pro_id) if _pro_id else {}

        if not _all_exams:
          st.error("Could not load exam list. Portal may be down.")
        else:
          # Smart Scope: filter exams to the student's cohort year
          _sess_id = _s.get("sess_id", "AUTO") or "AUTO"
          _filtered_eids = cs.get_relevant_exams(_sess_id, _sessions, _all_exams)
          _tasks = [(_s['reg_no'], _sess_id, _eid) for _eid in _filtered_eids]

          _prog_bar = st.progress(0, text=f"Scanning {len(_filtered_eids)} exams…")
          def _fix_progress(cur, tot, txt=None):
            _prog_bar.progress(cur / tot if tot else 0,
                      text=txt or f"Scanned {cur}/{tot}")

          with st.spinner("Running deep scan (1–3 min)…"):
            _history = cs.run_batch_scan_engine(
              tasks=_tasks,
              pro_id=_pro_id,
              exam_id="0",
              all_sessions=_sessions,
              progress_callback=_fix_progress,
              num_threads=15
            )
          _prog_bar.empty()

          if not _history:
            st.warning("No results found. Portal may be busy. Try again later.")
          else:
            _saved = db.save_cross_batch_history(
              profile_name=profile_name,
              reg_no=_s['reg_no'],
              scanned_history=_history,
              exam_name_map=_all_exams
            )
            if _saved:
              st.success(
                f"Successfully resolved **{_saved}** semester(s) for "
                f"**{_s['name']}**. Analytics will now reflect the correct CGPA."
              )
              st.cache_data.clear()
              st.rerun()
            else:
              st.warning("Scan completed but no new main semester data was found for this student.")

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
df_sub = df_sub_raw[df_sub_raw['subject_code'].isin(selected_subjects)].copy() if not df_sub_raw.empty else df_sub_raw
df_main = df_raw[(df_raw['cgpa'] >= cgpa_range[0]) & (df_raw['cgpa'] <= cgpa_range[1])].copy()

# Resilience Detection: Is this the first semester scan?
# In 1st Sem, portal often repeats GPA as CGPA. Detect by equality or sum.
is_first_sem = (df_main['cgpa'].sum() == 0) or \
        (df_main['gpa'].equals(df_main['cgpa'])) or \
        ("1st Yr 1st Sem" in selected_label)

df_pivot = pd.DataFrame()
if not df_sub.empty:
  df_pivot = df_sub.pivot_table(index='reg_no', columns='subject_code', values='gp', aggfunc='first')

# Extract promotion conditions
promo_target, is_even_sem, promo_yr = get_promotion_rules(selected_label)


# ---------------------------------------------------------------------------
# STRATEGIC INSIGHT BRIEF
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Deep Analysis Helpers (shared by Strategic Insights + GPA Projection tab)
# ---------------------------------------------------------------------------
if '_deep_cache' not in st.session_state:
  st.session_state._deep_cache = {} # keyed by f"{profile_name}_{reg}"

@st.cache_data(ttl=3600)
def _pre_warm_resources(pro_id):
  """Concurrently pre-warm the connection pool and pre-fetch program/session/exam metadata."""
  import cli_scraper as cs
  cs.warm_connection_pool(num_connections=6)
  cs.fetch_programs_and_sessions()
  if pro_id:
    cs.fetch_exams(pro_id)
  return True

_p_data_init = profiles.get(profile_name, {})
_pro_id_init = _p_data_init.get("pro_id", "")
if _pro_id_init:
  _pre_warm_resources(_pro_id_init)

def _run_deep_analysis(reg_no, stu_name, sess_id):
  """Fetch full student record from portal and compute precise analysis."""

  _p_data = profiles.get(profile_name, {})
  _pro_id = _p_data.get("pro_id", "")
  if not _pro_id:
    return None

  _sess_id = sess_id

  # Fetch portal data
  _programs, _sessions = cs.fetch_programs_and_sessions()
  _all_exams = cs.fetch_exams(_pro_id) if _pro_id else {}
  if not _all_exams:
    return None

  # Smart Scope: filter exams to student's cohort year
  _filtered_eids = cs.get_relevant_exams(_sess_id, _sessions, _all_exams)
  _tasks = [(int(reg_no), _sess_id, _eid) for _eid in _filtered_eids]

  # Run scan
  _history = cs.run_batch_scan_engine(
    tasks=_tasks,
    pro_id=_pro_id,
    exam_id="0",
    all_sessions=_sessions,
    num_threads=15
  )

  if not _history:
    return None

  # Attach exam names
  for rec in _history:
    eid = rec.get('_exam_id')
    if eid and eid in _all_exams:
      rec['_exam_name'] = _all_exams[eid]

  # Run precise computation
  return db.compute_deep_analysis(_history, profile_name, selected_label)


def _render_deep_result(result, reg, name="", sess_id="AUTO"):
  """Render the deep analysis result inline."""
  if result is None:
    cache_key = f"{profile_name}_{reg}_{sess_id}"
    retry_key = f"retry_{profile_name}_{exam_id}_{reg}_{sess_id}"
    cols_err = st.columns([0.05, 0.55, 0.4])
    with cols_err[1]:
      st.caption("⚠ Could not fetch records — portal may be busy or student not found.")
    with cols_err[2]:
      if st.button("Retry", key=retry_key, help="Re-run deep analysis for this student"):
        del st.session_state._deep_cache[cache_key]
        st.rerun()
    return

  # --- True CGPA vs Official ---
  diff = result['cgpa_diff']
  diff_str = f"+{diff:.2f}" if diff > 0 else f"{diff:.2f}"

  cols = st.columns([1, 1, 1])
  with cols[0]:
    st.metric(
      "True CGPA",
      f"{result['true_cgpa']:.2f}",
      delta=f"{diff_str} vs official {result['official_cgpa']:.2f}",
      delta_color="normal" if diff >= 0 else "inverse"
    )
  with cols[1]:
    if result['precise_target_gpa'] > 0:
      target_val = result['precise_target_gpa']
      if target_val > 4.0:
        st.metric("Precise Target GPA", "Impossible", delta=f"{target_val:.2f} > 4.00", delta_color="inverse")
      else:
        st.metric("Precise Target GPA", f"{target_val:.2f}",
             delta=f"Next sem ({result['next_sem_credits']:.2f} cr)")
    else:
      st.metric("Target GPA", "N/A", delta="Even sem / computed")
  with cols[2]:
    st.metric("Pending Retakes", f"{result['pending_retake_count']}",
         delta=f"{result['total_credits']:.2f} cr completed")

  # --- Pending retakes detail ---
  if result['pending_retakes']:
    with st.expander(f" {result['pending_retake_count']} Subject(s) Still Failing"):
      for pr in result['pending_retakes']:
        gp_display = f"{pr['gp']:.2f}" if pr['gp'] > 0 else "F"
        badge = "—" if pr['source'] =='retake_improved' else "—"
        st.markdown(f"{badge} **{pr['code']}** — GP: {gp_display} ({pr['credit']:.2f} cr)")

  st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp; Analyzed {result['effective_grade_count']} subjects across {result['semesters_found']} semester(s)")

# Pre-calculate personas and insights for the brief and tabs
archetypes = db.get_performance_archetypes(df_pivot, df_main, promo_target=promo_target, is_even_sem=is_even_sem, is_first_sem=is_first_sem, promo_yr=promo_yr)
insights = db.get_strategic_insights(df_main, df_sub, df_pivot, archetypes, is_first_sem=is_first_sem)

if show_strategic_brief:
  
  with st.container(border=True):
    st.subheader("Strategic Analysis Brief")
    
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    
    # Metric 1: Performance / Momentum
    if is_first_sem:
      m_col1.metric("Mean Semester GPA", f"{insights.get('mean_gpa', 0):.2f}", 
             delta="Initial Baseline")
    else:
      momentum = insights.get('batch_momentum', 0)
      rounded_mom = round(momentum, 2)
      delta_text = "Improving" if rounded_mom > 0 else ("Declining" if rounded_mom < 0 else "Steady")
      m_col1.metric("Batch Momentum", f"{momentum:+.2f}" if rounded_mom != 0.0 else "0.00", 
             delta=delta_text,
             delta_color="normal" if rounded_mom != 0.0 else "off")
    
    # Metric 2: Honours Pipeline
    m_col2.metric("Honours Pipeline", f"{insights.get('honours_count', 0)}", 
           f"{insights.get('honours_pct', 0):.1f}% of batch")
    
    # Metric 3: Active Risk
    m_col3.metric("Active Risk Case", f"{insights.get('risk_count', 0)}" if not is_first_sem else "N/A", 
           "Slipping / Critical" if not is_first_sem else "Baseline Semester")
    
    # Metric 4: Discovery / Trend
    m_col4.metric("Rising Stars" if not is_first_sem else "Top Potential", 
           f"{insights.get('improving_count', 0)}" if not is_first_sem else f"{insights.get('honours_count', 0)}", 
           "Positive Trend" if not is_first_sem else "High Performers")

    st.markdown("---")
    
    # Narrative Section
    b_col1, b_col2 = st.columns(2)
    
    with b_col1:
      st.markdown("##### Academic Pressures")
      
      def _render_student_list(student_data):
        for reg, name, target, sess_id in student_data:
          show_target = not is_even_sem or target > 4.0
          
          if show_target:
            target_str = f"Target: **{target:.2f}**" if target <= 4.0 else "**Impossible (>4.0)**"
            st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• **{name}** `{reg}` &nbsp;|&nbsp; Next Sem {target_str}")
          else:
            st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• **{name}** `{reg}`")

          # Deep Analysis button
          cache_key = f"{profile_name}_{reg}_{sess_id}"
          btn_key = f"deep_{profile_name}_{exam_id}_{reg}_{sess_id}"

          if cache_key in st.session_state._deep_cache:
            cached = st.session_state._deep_cache[cache_key]
            if cached is None:
              _render_deep_result(None, reg, name, sess_id)
            else:
              _render_deep_result(cached, reg, name, sess_id)
          else:
            if st.button("Deep Analysis", key=btn_key, help=f"Fetch full record for {name} and compute precise CGPA, target, and pending retakes"):
              with st.spinner(f"Scanning full academic history for {name} ({reg})… This takes 1-2 minutes."):
                result = _run_deep_analysis(reg, name, sess_id)
              st.session_state._deep_cache[cache_key] = result
              st.rerun()

      m_ct = len(insights.get('readd_students', []))
      f_ct = len(insights.get('failed_students', []))
      c_ct = len(insights.get('critical_students', []))
      r_ct = len(insights.get('risk_students', []))

      if m_ct > 0:
        st.error(f"**Readd Alert:** {m_ct} Student(s) have too high of a credit/GP deficit to meet Year {promo_yr} {promo_target} CGPA threshold.")
        _render_student_list(insights.get('readd_students', []))
      if f_ct > 0:
        st.error(f"**Failed Promotion:** {f_ct} Student(s) did not meet the Year {promo_yr} {promo_target} CGPA promotion threshold.")
        _render_student_list(insights.get('failed_students', []))
      if c_ct > 0:
        st.error(f"**Critically At-Risk:** {c_ct} Student(s) are below the Year {promo_yr} {promo_target} CGPA threshold. High probability of failing promotion.")
        _render_student_list(insights.get('critical_students', []))
      if r_ct > 0:
        st.warning(f"**At-Risk:** {r_ct} Student(s) are hovering dangerously close (+0.15 margin) to the Year {promo_yr} {promo_target} cutoff.")
        _render_student_list(insights.get('risk_students', []))
      
      if 'bottleneck' in insights:
        st.warning(f"**Bottleneck Identified:** The subject **{insights['bottleneck']}** has the lowest cohort average (**{insights['bottleneck_gp']} GP**).")
      
      if 'synergy' in insights:
        s1, s2, val = insights['synergy']
        st.info(f"**Syllabus Synergy:** High performance correlation (**{val}**) detected between **{s1}** and **{s2}**.")

    with b_col2:
      st.markdown("##### Leadership Intelligence")
      if is_first_sem:
        st.info("**Initial Talent Discovery:** This is the baseline semester. Use this scan to identify the natural technical aptitude of the new cohort.")
      else:
        momentum = insights.get('batch_momentum', 0)
        mom_str = f"{momentum:+.2f}" if round(momentum, 2) != 0.0 else "0.00"
        st.info(f"**Batch Momentum:** {mom_str} GP points shift compared to historical CGPA.")

st.divider()

# ---------------------------------------------------------------------------
# TABS
# ---------------------------------------------------------------------------
tabs = st.tabs(["Baseline Insight", "Trends", "Advanced Patterns", "Cube Pivot", "Clearing List", "GPA Projection"])

# =========================================================================
# TAB 1: BASELINE
# =========================================================================
with tabs[0]:
  has_failed_count = int(df_main['first_chance_fail'].sum())
  all_passed_count = len(df_main) - has_failed_count
  pass_rate = (all_passed_count / len(df_main)) * 100 if not df_main.empty else 0

  # Calculate medians and total active students
  valid_gpas = df_main[df_main['gpa'] > 0]['gpa']
  valid_cgpas = df_main[df_main['cgpa'] > 0]['cgpa']
  median_gpa = valid_gpas.median() if not valid_gpas.empty else 0.0
  median_cgpa = valid_cgpas.median() if not valid_cgpas.empty else 0.0
  total_active_students = len(df_main)

  # High-End Metric Cards Row 1
  met_row1 = st.columns(3)
  with met_row1[0]:
    if is_first_sem:
      st.metric("Batch Mean GPA", f"{insights.get('mean_gpa', 0.0):.2f}")
    else:
      mom_val = insights.get('batch_momentum', 0.0)
      mom_str = f"{mom_val:+.2f} GP" if round(mom_val, 2) != 0.0 else "0.00 GP"
      st.metric("Batch Momentum", mom_str, help="Shift compared to historical baseline CGPA")
  with met_row1[1]:
    st.metric("Honours Roster", f"{insights.get('honours_count', 0)} ({insights.get('honours_pct', 0.0):.1f}%)", help="Students with CGPA >= 3.50")
  with met_row1[2]:
    st.metric("Active Students", f"{total_active_students}", help="Total students with active results in this semester")

  # High-End Metric Cards Row 2
  met_row2 = st.columns(3)
  with met_row2[0]:
    st.metric("Median CGPA", f"{median_cgpa:.2f}" if not is_first_sem else "N/A", help="Middle CGPA value of the batch up to this semester")
  with met_row2[1]:
    st.metric("Median GPA", f"{median_gpa:.2f}", help="Middle GPA value of this semester's results")
  with met_row2[2]:
    st.metric("Overall Pass Rate (1st Attempt)", f"{pass_rate:.1f}%", help="Percentage of students who passed all subjects in their first attempt.")

  st.divider()

  # Row 1: GPA Distribution & First-Chance Pass Ratio aligned side-by-side
  row1_c1, row1_c2 = st.columns([1.6, 1])

  with row1_c1:
    st.markdown("#### GPA Distribution (This Semester Only)")
    dist_df = df_main[df_main['gpa'] > 0].copy()
    
    # High-leverage axis anchoring: Remove the'0.0 - 2.0' void
    curr_min = dist_df['gpa'].min() if not dist_df.empty else 0.0
    axis_start = max(0.0, float(np.floor(curr_min * 5) / 5) - 0.2)
    
    dist_chart = alt.Chart(dist_df).mark_bar().encode(
      alt.X("gpa:Q",
         bin=alt.Bin(maxbins=40, extent=[axis_start, 4.0], step=0.05), # Preciser bins
         title="Semester GPA (GPA)",
         scale=alt.Scale(domain=[axis_start, 4], nice=False)),
      alt.Y('count()', title='Student Count'),
      tooltip=[
        alt.Tooltip('gpa:Q', bin=alt.Bin(maxbins=40, extent=[axis_start, 4.0], step=0.05), title='GPA Band'),
        alt.Tooltip('count()', title='Students')
      ]
    ).properties(height=300)
    st.altair_chart(dist_chart, width='stretch')
    st.caption(f"Visualized spread from {axis_start:.2f} (Semester Minimum Focus)")

  with row1_c2:
    st.markdown("#### First-Chance Pass Ratio")
    status_df = pd.DataFrame({
     'Status': ['Passed (1st Chance)','Failed (Any Subject)'],
     'Count': [all_passed_count, has_failed_count]
    })
    pie = alt.Chart(status_df).mark_arc(innerRadius=60, outerRadius=100).encode(
      theta="Count:Q",
      color=alt.Color("Status:N", scale=alt.Scale(
        domain=['Passed (1st Chance)','Failed (Any Subject)'],
        range=['#10b981','#ef4444']
      ), legend=alt.Legend(orient="bottom")),
      tooltip=['Status','Count']
    ).properties(height=300, width='container')
    st.altair_chart(pie, width='stretch')
    st.caption("Students who failed ≥1 subject in their main attempt are counted as Failed.")

  st.divider()

  # Row 2: Subject Difficulty Ranking
  st.markdown("#### Subject Difficulty Ranking (Bottleneck Capacity)")
  if not df_sub.empty:
    df_sub_pass = df_sub[df_sub['gp'] >= 2.0]
    sub_avg = df_sub_pass.groupby('subject_code')['gp'].mean().reset_index()
    # Map codes to names from the data for tooltips
    code_to_name = df_sub.set_index('subject_code')['subject_name'].to_dict()
    sub_avg['subject_name'] = sub_avg['subject_code'].map(code_to_name)
    sub_avg = sub_avg.sort_values('gp')
    sub_avg['base_gp'] = 2.0

    bar = alt.Chart(sub_avg).mark_bar(color="#f59e0b", cornerRadiusEnd=4).encode(
      x=alt.X('gp:Q', title='Mean Grade Point (Pass Only)', scale=alt.Scale(domain=[2, 4])),
      x2='base_gp:Q',
      y=alt.Y('subject_code:N', sort='-x', title='Subject',
          axis=alt.Axis(labelPadding=15, labelLimit=400)),
      tooltip=['subject_code','subject_name', alt.Tooltip('gp:Q', format='.2f')]
    ).properties(height=max(250, len(sub_avg) * 40))
    st.altair_chart(bar, width='stretch')
    st.caption("Lower average GPA = systemic difficulty. Only passing grades (≥2.0) are averaged.")
  else:
    st.info("No subject data available.")

  st.divider()

  # End of Stethoscope baseline tab

  # Row 4: Grade Distribution Breakdown
  st.markdown("#### Grade Distribution Breakdown")
  if not df_sub.empty:
    def gp_to_letter(gp):
      if gp >= 4.0: return'A+'
      elif gp >= 3.75: return'A'
      elif gp >= 3.5: return'A-'
      elif gp >= 3.25: return'B+'
      elif gp >= 3.0: return'B'
      elif gp >= 2.75: return'B-'
      elif gp >= 2.5: return'C+'
      elif gp >= 2.25: return'C'
      elif gp >= 2.0: return'D'
      else: return'F'

    def gp_to_order(gp):
      if gp >= 4.0: return 1
      elif gp >= 3.75: return 2
      elif gp >= 3.5: return 3
      elif gp >= 3.25: return 4
      elif gp >= 3.0: return 5
      elif gp >= 2.75: return 6
      elif gp >= 2.5: return 7
      elif gp >= 2.25: return 8
      elif gp >= 2.0: return 9
      else: return 10
      
    dist_df = df_sub.copy()
    dist_df['letter'] = dist_df['gp'].apply(gp_to_letter)
    dist_df['letter_order'] = dist_df['gp'].apply(gp_to_order)

    # 100% Stacked Bar
    color_scale = alt.Scale(
      domain=['A+','A','A-','B+','B','B-','C+','C','D','F'],
      range=[
       '#166534','#15803d','#22c55e', # Greens (A)
       '#1e3a8a','#1d4ed8','#3b82f6', # Blues (B)
       '#b45309','#d97706','#f59e0b', # Ambers/Oranges (C, D)
       '#ef4444' # Red (F)
      ]
    )

    dist_bar = alt.Chart(dist_df).mark_bar().encode(
      x=alt.X('count(reg_no):Q', stack='normalize', title='Percentage of Students', axis=alt.Axis(format='%')),
      y=alt.Y('subject_code:N', title='Subject'),
      color=alt.Color('letter:N', scale=color_scale, legend=alt.Legend(title="Grade", orient="right")),
      order=alt.Order('letter_order:Q', sort='ascending'),
      tooltip=['subject_code','subject_name','letter','count(reg_no)']
    ).properties(height=max(250, len(dist_df['subject_code'].unique()) * 40))
    
    st.altair_chart(dist_bar, width='stretch')
  else:
    st.info("No subject data available.")

# =========================================================================
# TAB 2: TRENDS
# =========================================================================
with tabs[1]:
  st.subheader("Longitudinal Trends & Benchmarking")
  
  if df_longitudinal is None or df_longitudinal.empty:
    st.info("No longitudinal data available for this profile. Try scanning more semesters.")
  else:
    # Section 3.1: Batch GPA Trajectory Chart
    if max_semester:
      st.caption(f"ℹ️ **Batch Progress Cap:** Showing data up to Semester {max_semester} (excluding future results of readmitted students)")
    st.markdown("#### Batch GPA Trajectory")
    
    median_df = df_longitudinal.groupby('semester_num')['gpa'].median().reset_index()
    median_df['name'] ='Batch Median'
    median_df['reg_no'] = 0
    median_df['is_median'] = True
    
    chart_df = df_longitudinal.copy()
    chart_df['is_median'] = False
    chart_df = pd.concat([chart_df, median_df], ignore_index=True)
    
    # Spotlight selector
    student_list = ["None"] + sorted(df_longitudinal['name'].unique().tolist())
    spotlight = st.selectbox("Spotlight Student:", student_list)
    
    # Determine opacity and color dynamically based on spotlight
    def get_opacity(row):
      if row['is_median']: return 1.0
      if spotlight == "None": return 0.3
      return 1.0 if row['name'] == spotlight else 0.05
      
    def get_color(row):
      if row['is_median']: return'#ffffff'
      return'#ef4444' if row['name'] == spotlight else'#3b82f6'

    def get_stroke_dash(row):
      return [5, 5] if row['is_median'] else [0]
      
    chart_df['opacity'] = chart_df.apply(get_opacity, axis=1)
    chart_df['color'] = chart_df.apply(get_color, axis=1)
    chart_df['strokeDash'] = chart_df.apply(get_stroke_dash, axis=1)

    traj_chart = alt.Chart(chart_df).mark_line(point=True).encode(
      x=alt.X('semester_num:O', title='Semester Index'),
      y=alt.Y('gpa:Q', title='GPA', scale=alt.Scale(domain=[1.5, 4.0], clamp=True)),
      detail='reg_no:N',
      color=alt.Color('color:N', scale=None),
      opacity=alt.Opacity('opacity:Q', scale=None),
      strokeDash=alt.StrokeDash('strokeDash:N', scale=None),
      tooltip=['name','reg_no','semester_label','gpa']
    ).properties(height=400)
    
    st.altair_chart(traj_chart, width='stretch')
    
    st.divider()

    # Section 3.2: Student Trajectory Metrics Table
    st.markdown("#### Student Trajectory Metrics")
    
    metrics = []
    for reg, group in df_longitudinal.groupby('reg_no'):
      if len(group) < 2:
        metrics.append({
         'reg_no': reg,'name': group.iloc[0]['name'],'peak': group['gpa'].max(),
         'valley': group['gpa'].min(),'consistency': 1.0,'trajectory':'Stable'
        })
        continue
        
      sorted_group = group.sort_values('semester_num')
      gpas = sorted_group['gpa'].tolist()
      sem_nums = sorted_group['semester_num'].tolist()
      peak = max(gpas)
      valley = min(gpas)
      consistency = max(0.0, 1.0 - float(np.std(gpas)))
      
      # Use actual sem_nums as independent variable for polyfit to prevent distortion
      try:
        if len(set(sem_nums)) >= 2:
          slope, _ = np.polyfit(sem_nums, gpas, 1)
        else:
          slope = 0.0
      except Exception:
        slope = 0.0
      
      if slope > 0.08:
        traj = "Rising"
      elif slope < -0.08:
        traj = "Declining"
      else:
        valley_idx = gpas.index(valley)
        if 0 < valley_idx < len(gpas) - 1:
          if gpas[0] - valley > 0.2 and gpas[-1] - valley > 0.2:
            traj = "Recovery (V-shape)"
          else:
            traj = "Stable"
        else:
          traj = "Stable"
          
      metrics.append({
       'reg_no': reg,'name': sorted_group.iloc[0]['name'],'peak': round(peak, 2),
       'valley': round(valley, 2),'consistency': round(consistency, 2),
       'trajectory': traj
      })
      
    metrics_df = pd.DataFrame(metrics).sort_values('consistency', ascending=False)
    st.dataframe(metrics_df, hide_index=True, width='stretch')



# =========================================================================
# TAB 3: ADVANCED PATTERNS
# =========================================================================
with tabs[2]:
  st.subheader("Academic Variance & Pattern Extraction")

  st.markdown("#### Subject Performance Variance")
  if not df_sub.empty:
    df_sub_boxplot = df_sub[df_sub['gp'] >= 2.0]
    if not df_sub_boxplot.empty:
      # Fix: Altair mark_boxplot components are'box','median','rule','outliers','ticks'
      box = alt.Chart(df_sub_boxplot).mark_boxplot(
        extent='min-max', 
        clip=True,
        median={'color':'white','thickness': 2},
        rule={'color':'white'},
        ticks={'color':'white'}
      ).encode(
        x=alt.X('subject_code:N', title='Subject',
            axis=alt.Axis(labelAngle=-45, labelPadding=10)),
        y=alt.Y('gp:Q', title='Grade Point',
            scale=alt.Scale(domain=[2.0, 4.0], clamp=True)),
        color=alt.value("#ec4899")
      ).properties(height=450)
      st.altair_chart(box, width='stretch')
    else:
      st.info("No passing grades to display in this view.")
  else:
    st.info("No subject data available.")

  st.divider()

  col_m1, col_m2 = st.columns(2)

  with col_m1:
    st.markdown("#### Performance Personas (Strategic Quadrant)")
    if not df_pivot.empty:
      # Use the new compound persona logic
      clusters = db.get_performance_archetypes(df_pivot, df_main, promo_target=promo_target, is_even_sem=is_even_sem, is_first_sem=is_first_sem, promo_yr=promo_yr)
      if clusters is not None:
        clust_df = df_main.merge(clusters, left_on='reg_no', right_index=True)
        
        # Strategic Quadrant (Y: Performance, X: Momentum/Variance)
        x_col ='momentum' if not is_first_sem else'std_gp'
        x_title ='Academic Momentum' if not is_first_sem else'Subject Variance (Lower = More Consistent)'
        
        # Mobile-first locator selectbox
        student_list = ["None"] + sorted(clust_df['name'].unique().tolist())
        spotlight_student = st.selectbox("Spotlight Focus (Find Student)", student_list, index=0)
        
        # Space-Themed Visual Color Mapping grouped by status
        color_map = {
          "Vanguards": "#10b981",          # Vibrant Mint (Consistent top performers)
          "Rising Stars": "#06b6d4",       # Electric Teal (On track to topper)
          "Fading Stars": "#f59e0b",       # Golden Amber (Toppers falling from grace)
          "Stable Orbits": "#3b82f6",      # Classic Blue (Stable average)
          "Drifting Orbits": "#ff0055",    # Neon Crimson Red (At risk of failing promotion)
          "Grounded Orbits": "#881337"     # Deep Crimson Wine (Failed promotion)
        }
 
        danger_archetypes = ["Grounded Orbits"]
        
        base_scatter = alt.Chart(clust_df).mark_circle(size=130).encode(
          x=alt.X(f'{x_col}:Q', title=x_title, 
              axis=alt.Axis(grid=True),
              scale=alt.Scale(domain=[clust_df[x_col].min()-0.1, clust_df[x_col].max()+0.1])),
          y=alt.Y('gpa:Q', title='Semester GPA (GPA)', 
              scale=alt.Scale(domain=[clust_df['gpa'].min()-0.2, 4.1])),
          color=alt.Color('Detailed_Status:N', 
                  scale=alt.Scale(domain=list(color_map.keys()), range=list(color_map.values())),
                  legend=alt.Legend(orient="bottom", columns=2, titleLimit=0, labelLimit=0),
                  title='Status'),
          opacity=alt.condition(
            alt.FieldOneOfPredicate(field='Detailed_Status', oneOf=danger_archetypes),
            alt.value(0.0),
            alt.value(1.0)
          ),
          tooltip=['name', alt.Tooltip('reg_no:N', title='Reg No'),'Archetype',
               alt.Tooltip('gpa:Q', format='.2f', title='Current GPA'),
               alt.Tooltip('cgpa:Q', format='.2f', title='Historical Average'),
               alt.Tooltip(f'{x_col}:Q', format='.2f', title=x_title)]
        )
        
        df_danger = clust_df[clust_df['Detailed_Status'].isin(danger_archetypes)]
        if not df_danger.empty:
          danger_overlay = alt.Chart(df_danger).mark_text(text='⚠️', size=14, color='#f59e0b').encode(
            x=f'{x_col}:Q', y='gpa:Q',
            tooltip=['name', alt.Tooltip('reg_no:N', title='Reg No'),'Archetype',
                 alt.Tooltip('gpa:Q', format='.2f', title='Current GPA'),
                 alt.Tooltip('cgpa:Q', format='.2f', title='Historical Average'),
                 alt.Tooltip(f'{x_col}:Q', format='.2f', title=x_title)]
          )
          scatter = (base_scatter + danger_overlay).properties(height=450).interactive()
        else:
          scatter = base_scatter.properties(height=450).interactive()
          
        if spotlight_student != "None":
          df_spot = clust_df[clust_df['name'] == spotlight_student]
          if not df_spot.empty:
            spot_overlay = alt.Chart(df_spot).mark_circle(
              size=400, color='transparent', stroke='#fbbf24', strokeWidth=3
            ).encode(x=f'{x_col}:Q', y='gpa:Q')
            scatter = scatter + spot_overlay
        
        # Add a vertical zero-line for clarity in momentum mode
        final_chart = scatter
        if not is_first_sem:
          v_line = alt.Chart(pd.DataFrame({'x': [0]})).mark_rule(color='gray', strokeDash=[5,5]).encode(x='x')
          final_chart = v_line + scatter
        
        st.altair_chart(final_chart, width='stretch')
        caption = "**Right of center**: Improving performance | **Top Quadrant**: Excellence" if not is_first_sem else "**Top Quadrant**: Excellence | **Specialists**: Identified by subject variance."
        st.caption(caption)
        
        # Mobile-Friendly Companion Data Table
        with st.expander("View Quadrant Data Matrix (Tap-Free)"):
          st_view_df = clust_df[['reg_no','name','gpa','cgpa','Archetype']].sort_values('gpa', ascending=False)
          st_view_df = st_view_df.rename(columns={'reg_no':'Reg','name':'Name','gpa':'GPA','cgpa':'CGPA','Archetype':'Status'})
          st.dataframe(st_view_df, width='stretch', hide_index=True)
      else:
        st.info("Not enough students for clustering (need ≥4 with complete subject data).")
    else:
      st.info("No pivot data available.")

  with col_m2:
    st.markdown("#### Subject Dependency Heatmap")
    if not df_pivot.empty and len(selected_subjects) > 1:
      corr_matrix = df_pivot.corr()
      corr_matrix.index.name  ='Subject A'
      corr_matrix.columns.name ='Subject B'
      corr_flat = corr_matrix.stack().reset_index()
      corr_flat.columns = ['Subject A','Subject B','Correlation']
      heatmap = alt.Chart(corr_flat).mark_rect().encode(
        x=alt.X('Subject A:N', axis=alt.Axis(labelAngle=-45)),
        y='Subject B:N',
        color=alt.Color('Correlation:Q', scale=alt.Scale(scheme='redblue', domain=[-1, 1]), legend=alt.Legend(orient="bottom", title="Correlation", gradientLength=200, titleLimit=0)),
        tooltip=['Subject A','Subject B', alt.Tooltip('Correlation:Q', format='.2f')]
      ).properties(height=400, width='container')
      st.altair_chart(heatmap, width='stretch')
    else:
      st.info("Select ≥2 subjects for the correlation heatmap.")

# =========================================================================
# TAB 4: CUBE PIVOT
# =========================================================================
with tabs[3]:
  st.subheader("Interactive Pivot Dimension")
  pivot_type = st.radio(
    "Cube Rotation:",
    ["Show Breakdown per Student", "Show Summary per Subject"],
    horizontal=True
  )
  if not df_pivot.empty:
    if "Student" in pivot_type:
      st.dataframe(df_pivot, width='stretch')
    else:
      flipped = df_sub.pivot_table(
        index='subject_code', columns='reg_no', values='gp', aggfunc='first'
      )
      st.dataframe(flipped, width='stretch')
  else:
    st.info("No data to pivot.")

# =========================================================================
# TAB 5: CLEARING LIST
# =========================================================================
with tabs[4]:
  st.subheader("Semester-End Clearing List")
  st.markdown("Track eligibility for improvements and retakes after this semester's main exam.")

  csv = df_main.to_csv(index=False).encode('utf-8')
  st.download_button(
    "Export Clearing List",
    csv,
    f"clearing_list_{profile_name}_{exam_id}.csv",
    "text/csv"
  )

  disp_cols = ['reg_no','name','gpa','cgpa','result_status','improvement_count','retake_count']
  disp_df = df_main.sort_values('cgpa', ascending=False).reset_index(drop=True)
  st.dataframe(disp_df[disp_cols], width='stretch')



# =========================================================================
# TAB 6: GPA PROJECTION
# =========================================================================
with tabs[5]:
  st.subheader("GPA Projection & Graduation Planner")
  st.markdown(
    "Run a deep analysis for any student to see their **True CGPA**, "
    "**pending retakes**, and compute the **minimum average GPA** needed "
    "to reach any target graduation CGPA."
  )
  st.info(
    "**How it works:** Click **Deep Analysis** next to a student. "
    "The app fetches their full academic history from the portal, computes "
    "their credit-weighted True CGPA, then uses the semester credit map to "
    "project how much they need to score in remaining semesters."
  )

  # Search + filter bar
  proj_search = st.text_input(
    "Search student by name or reg no:",
    placeholder="Search by name or registration number...",
    key="proj_search"
  )

  proj_df = df_main.copy()
  if proj_search.strip():
    q = proj_search.strip().lower()
    proj_df = proj_df[
      proj_df["name"].str.lower().str.contains(q, na=False) |
      proj_df["reg_no"].astype(str).str.contains(q, na=False)
    ]

  proj_df = proj_df.sort_values("cgpa", ascending=False).reset_index(drop=True)

  # GPA Projection Card Fragment
  @st.fragment
  def render_student_projection_card(row, profile_name, exam_id):
    """Renders a single student card with full fragment isolation."""
    reg = row["reg_no"]
    sess_id = row.get("sess_id", "AUTO")
    name = row.get("name", f"Reg {reg}")
    gpa = row.get("gpa", 0.0)
    cgpa = row.get("cgpa", 0.0)

    cache_key = f"{profile_name}_{reg}_{sess_id}"
    btn_key  = f"proj_deep_{profile_name}_{exam_id}_{reg}_{sess_id}"

    with st.container(border=True):
      hdr_col1, hdr_col2, hdr_col3, hdr_col4 = st.columns([3, 1, 1, 2])
      hdr_col1.markdown(f"**{name}** &nbsp; `{reg}`")
      hdr_col2.markdown(f"GPA &nbsp;**{gpa:.2f}**")
      hdr_col3.markdown(f"CGPA &nbsp;**{cgpa:.2f}**")

      already_done = cache_key in st.session_state._deep_cache

      if already_done:
        deep_res = st.session_state._deep_cache[cache_key]
        hdr_col4.markdown("✅ **Analysed**")

        if deep_res is None:
          retry_key = f"retry_{profile_name}_{exam_id}_{reg}_{sess_id}"
          cols_err = st.columns([0.05, 0.55, 0.4])
          with cols_err[1]:
            st.caption("⚠️ Could not fetch records — portal may be busy or student not found.")
          with cols_err[2]:
            if st.button("Retry", key=retry_key, help="Re-run deep analysis for this student"):
              del st.session_state._deep_cache[cache_key]
              st.rerun()
        else:
          # ponytail: cache special lookup in session_state per dept to avoid redundant DB queries during paging
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
          
          # --- Semester label helper ---
          def _semester_label(sem_num):
            yr = (sem_num - 1) // 2 + 1
            s = 1 if sem_num % 2 == 1 else 2
            return f"{yr}-{s}"

          # --- Collect Overrides from session_state ---
          overrides = {}
          for pr in adv_proj['pending_retakes']:
            chk_key = f"chk_{profile_name}_{reg}_{pr['code']}"
            will_pass = st.session_state.get(chk_key, False)
            
            if will_pass:
              tgt_key = f"tgt_{profile_name}_{reg}_{pr['code']}"
              if tgt_key in st.session_state:
                overrides[pr['code']] = st.session_state[tgt_key]
              else:
                overrides[pr['code']] = 2.00
            else:
              overrides[pr['code']] = pr['current_gp']
          
          for ic in adv_proj['improvement_candidates']:
            key = f"tgt_{profile_name}_{reg}_{ic['code']}"
            if key in st.session_state:
              overrides[ic['code']] = st.session_state[key]
            else:
              overrides[ic['code']] = ic['current_gp']

          # --- Compute Adjusted CGPA ---
          adj_cgpa, adj_credits = db.compute_adjusted_cgpa(deep_res.get('effective_grades', {}), overrides)
          cgpa_gain = adj_cgpa - deep_res['true_cgpa']

          # --- Compute Adjusted Pending Retakes ---
          adj_pending_retake_count = 0
          for code, g in deep_res.get('effective_grades', {}).items():
            gp = g['gp']
            if code in overrides:
              if overrides[code] > gp:
                gp = overrides[code]
            if gp < 2.0:
              adj_pending_retake_count += 1

          # --- Compute Adjusted Precise Target GPA ---
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

          # === SEMESTER-WISE GPA/CGPA BREAKDOWN ===
          _dept = db.get_dept_from_profile(profile_name)
          _current_sem = deep_res.get("current_semester", 0)
          _official_sem_records = deep_res.get('official_semester_records', {})

          _sem_breakdown = db.compute_per_semester_breakdown(
            effective_grades=deep_res.get('effective_grades', {}),
            dept=_dept,
            current_semester=_current_sem,
            overrides=overrides,
            official_records=_official_sem_records,
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

          # --- ML Future GPA Prediction ---
          import ml_predictor
          pred_results = ml_predictor.predict_future_gpas(deep_res, _dept, overrides=overrides)
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
              
              # Show predicted remaining semesters
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

          # --- Expanders for Retakes and Improvements ---
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
              st.caption("These courses were previously retaken/improved but GP is still \u2264 2.75. They remain as improvement candidates above.")
              def _render_attempted(aa):
                name_str = f" | *{aa['name']}*" if aa.get('name') else ""
                st.markdown(f"⚠️ **{aa['code']}**{name_str} \u2014 GP: {aa['current_gp']:.2f} | {aa['reason']}")
              _render_semester_grouped(adv_proj['already_attempted'], _render_attempted)

          if adv_proj['ineligible_retake_cleared']:
            _n_retake = sum(1 for x in adv_proj['ineligible_retake_cleared'] if x.get('clear_type') !='improvement_cleared')
            _n_improv = sum(1 for x in adv_proj['ineligible_retake_cleared'] if x.get('clear_type') =='improvement_cleared')
            _counts_parts = []
            if _n_retake:
              _counts_parts.append(f"{_n_retake} retake")
            if _n_improv:
              _counts_parts.append(f"{_n_improv} improvement")
            _counts_str = ", ".join(_counts_parts) if _counts_parts else str(len(adv_proj['ineligible_retake_cleared']))
            with st.expander(f"Cleared (not improvable, {_counts_str})"):
              def _render_cleared(irc):
                name_str = f" | *{irc['name']}*" if irc.get('name') else ""
                _orig = irc.get('original_gp', irc['current_gp'])
                _delta = irc['current_gp'] - _orig
                if _delta > 0:
                  badge = f' <span style="background:#22c55e;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.8em;">+{_delta:.2f} improved</span>'
                else:
                  badge = ""
                st.markdown(
                  f"**{irc['code']}**{name_str} \u2014 GP: {irc['current_gp']:.2f}{badge} | {irc['reason']}",
                  unsafe_allow_html=True
                )
              _render_semester_grouped(adv_proj['ineligible_retake_cleared'], _render_cleared)

          st.caption(f"Analyzed {deep_res['effective_grade_count']} subjects across {deep_res['semesters_found']} semester(s)")

          # --- Graduation Target Calculator ---
          st.markdown("---")
          st.markdown("##### Graduation Target Calculator")
          _dept = db.get_dept_from_profile(profile_name)
          _current_sem = deep_res.get("current_semester", 0)
          _remaining_sems = max(0, 8 - _current_sem)

          if _remaining_sems == 0:
            st.success(
              f"This student has completed all 8 semesters. "
              f"Final Adjusted CGPA: **{adj_cgpa:.2f}**"
            )
          else:
            target_key = f"target_cgpa_{profile_name}_{reg}"
            target_cgpa = st.slider(
              "Target Graduation CGPA",
              min_value=2.00,
              max_value=4.00,
              value=max(2.00, min(4.00, float(adj_cgpa))),
              step=0.05,
              key=target_key
            )

            proj = db.compute_graduation_projection(
              deep_result=deep_res,
              target_grad_cgpa=target_cgpa,
              dept=_dept,
              adj_cgpa=adj_cgpa,
              adj_credits=adj_credits,
            )

            p_c1, p_c2, p_c3 = st.columns(3)
            with p_c1:
              if proj["already_met"]:
                st.metric("Required Avg GPA", "Already Met",
                     delta=f"Current Adj: {proj['current_true_cgpa']:.2f}")
              elif not proj["is_achievable"]:
                st.metric("Required Avg GPA", "Impossible",
                     delta=f"Needs {proj['required_avg_gpa']:.2f} > 4.00",
                     delta_color="inverse")
              else:
                st.metric("Required Avg GPA",
                     f"{proj['required_avg_gpa']:.2f}",
                     delta="per semester on avg")
            with p_c2:
              st.metric("Adjusted CGPA", f"{adj_cgpa:.2f}",
                   delta=f"+{cgpa_gain:.2f} from targets" if cgpa_gain > 0 else None)
            with p_c3:
              st.metric("Remaining Semesters", proj["remaining_semesters"],
                   delta=f"{proj['remaining_credits']:.2f} credits left")

            # Per-semester breakdown
            if proj["remaining_credits_breakdown"]:
              with st.expander("Remaining Semester Credit Breakdown"):
                bd_cols = st.columns(len(proj["remaining_credits_breakdown"]))
                for ci, sem_info in enumerate(proj["remaining_credits_breakdown"]):
                  bd_cols[ci].metric(
                    f"Sem {sem_info['semester']}",
                    f"{sem_info['credits']:.2f} cr"
                  )

            # Status message
            if proj["already_met"]:
              st.success(
                f"**{name}** already has an Adjusted CGPA of "
                f"**{proj['current_true_cgpa']:.2f}**, which exceeds the "
                f"target of **{target_cgpa:.2f}**. Maintain performance!"
              )
            elif not proj["is_achievable"]:
              st.error(
                f"**Mathematically impossible.** Even with a perfect "
                f"4.00 in all {proj['remaining_semesters']} remaining semester(s), "
                f"the target CGPA of **{target_cgpa:.2f}** cannot be reached. "
                f"Consider adjusting the target."
              )
            elif proj["required_avg_gpa"] >= 3.75:
              st.warning(
                f"**Very challenging.** Needs an average GPA of "
                f"**{proj['required_avg_gpa']:.2f}** across "
                f"**{proj['remaining_semesters']}** remaining semester(s). "
                f"Consistent top performance required."
              )
            elif proj["required_avg_gpa"] >= 3.25:
              st.info(
                f"**Ambitious but achievable.** Needs **{proj['required_avg_gpa']:.2f}** "
                f"avg GPA over {proj['remaining_semesters']} semester(s)."
              )
            else:
              st.success(
                f"**Well within reach.** Needs **{proj['required_avg_gpa']:.2f}** "
                f"avg GPA over {proj['remaining_semesters']} semester(s). "
                f"Stay consistent!"
              )

            # --- Graduation CGPA Simulator ---
            st.markdown("---")
            st.markdown("##### Graduation CGPA Simulator")
            st.caption(
              "Input your expected performance for each remaining semester. "
              "Use **Summary** mode for a quick GPA estimate, or expand "
              "**Detailed** mode to set per-course grades. You can mix both."
            )

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
                  _include = st.checkbox("Incl", value=True, key=_include_key, label_visibility="collapsed", help="Include this semester in projection")
                with _hdr_c1:
                  st.markdown(f"**Semester {_sem_n}** ({_sem_cr:.2f} cr)")
                with _hdr_c2:
                  st.toggle(
                    "Detailed", value=_use_detailed, key=_mode_key,
                    help="Toggle to enter per-course grades",
                    disabled=not _include
                  )
                # Re-read after widget render
                _use_detailed = st.session_state.get(_mode_key, False)

                if not _include:
                  st.caption("Semester excluded from projection calculation.")
                  continue

                if _use_detailed:
                  # --- Detailed per-course input ---
                  _courses = db.get_semester_courses(_dept, _sem_n, include_all_electives=True)
                  _course_grades = []
                  _det_points = 0.0
                  _det_credits = 0.0

                  if not _courses:
                    st.info(f"No course mapping found for Semester {_sem_n}.")
                  else:
                    # Pre-pass to compute total selected credits for elective-enabled semesters
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
                        
                        # Enforce the hard cap
                        if not _is_checked:
                          if _total_sel_credits >= _credit_cap or (_total_sel_credits + _c['credit'] > _credit_cap):
                            _disable_chk = True
                        
                        _cg_c0, _cg_c1, _cg_c2 = st.columns([0.18, 2.82, 1.0])
                        with _cg_c0:
                          _is_selected = st.checkbox(
                            "Select",
                            value=False,
                            key=_chk_key,
                            disabled=_disable_chk,
                            label_visibility="collapsed"
                          )
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
                          # Restrict GP options using select_slider: 0.00 (Fail), 2.00 to 4.00
                          _VALID_FUTURE_GPA_OPTIONS = [0.00, 2.00, 2.25, 2.50, 2.75, 3.00, 3.25, 3.50, 3.75, 4.00]
                          _gp_val = st.select_slider(
                            "GP",
                            options=_VALID_FUTURE_GPA_OPTIONS,
                            value=3.25,
                            format_func=lambda x: "F" if x == 0.00 else f"{x:.2f}",
                            key=_gp_key,
                            label_visibility="collapsed"
                          )
                          _course_grades.append({
                            'code': _c['code'],
                            'credit': _c['credit'],
                            'gp': _gp_val,
                          })
                          _det_points += _gp_val * _c['credit']
                          _det_credits += _c['credit']
                        else:
                          st.markdown("<span style='color: gray; font-size: 0.85rem; padding-top: 5px; display: inline-block;'>Excluded</span>", unsafe_allow_html=True)

                    # Show calculated GPA for this semester
                    if _det_credits > 0:
                      _calc_gpa = round(_det_points / _det_credits, 2)
                      st.success(
                        f"Calculated GPA: **{_calc_gpa:.2f}** "
                        f"({_det_credits:.2f} / {_sem_cr:.2f} cr filled)"
                      )
                    else:
                      st.caption("Enter course GPs above to calculate GPA.")

                  _sim_semester_inputs.append({
                   'semester': _sem_n,
                   'mode':'detailed',
                   'gpa': None,
                   'course_grades': _course_grades,
                  })
                else:
                  # --- Summary GPA input ---
                  with _hdr_c3:
                    _gpa_key = f"sim_gpa_{profile_name}_{reg}_{sess_id}_{_sem_n}"
                    _gpa_val = st.number_input(
                      "Expected GPA", min_value=0.00, max_value=4.00,
                      value=3.00, step=0.05,
                      key=_gpa_key,
                      label_visibility="collapsed"
                    )

                  _sim_semester_inputs.append({
                   'semester': _sem_n,
                   'mode':'summary',
                   'gpa': _gpa_val,
                   'course_grades': None,
                  })

            # --- Compute Graduation CGPA ---
            _sim_result = db.compute_graduation_cgpa_from_inputs(
              adj_cgpa=adj_cgpa,
              adj_credits=adj_credits,
              remaining_semester_inputs=_sim_semester_inputs,
              dept=_dept,
            )

            # --- Display Result ---
            st.markdown("---")
            _sim_c1, _sim_c2, _sim_c3 = st.columns(3)
            with _sim_c1:
              _grad_cgpa = _sim_result['graduation_cgpa']
              _grad_delta = _grad_cgpa - adj_cgpa
              st.metric(
                "Projected Graduation CGPA",
                f"{_grad_cgpa:.2f}",
                delta=f"{_grad_delta:+.2f} from current adjusted",
                delta_color="normal" if _grad_delta >= 0 else "inverse"
              )
            with _sim_c2:
              st.metric(
                "Total Credits (All 8 Sems)",
                f"{_sim_result['grand_total_credits']:.2f} cr"
              )
            with _sim_c3:
              st.metric(
                "New Credits Projected",
                f"{_sim_result['total_new_credits']:.2f} cr",
                delta=f"from {len(_sim_semester_inputs)} semester(s)"
              )

            # Per-semester breakdown table
            with st.expander("Per-Semester Breakdown"):
              _bd_df = pd.DataFrame(_sim_result['per_semester_detail'])
              _bd_df.columns = ['Semester','GPA','Credits','Quality Points']
              st.dataframe(_bd_df, hide_index=True, width='stretch')

            # Graduation status message
            if _grad_cgpa >= 3.75:
              st.success(f"**First Class with Distinction!** Projected CGPA: {_grad_cgpa:.2f}")
            elif _grad_cgpa >= 3.50:
              st.success(f"**First Class!** Projected CGPA: {_grad_cgpa:.2f}")
            elif _grad_cgpa >= 3.25:
              st.info(f"**Second Class (Upper).** Projected CGPA: {_grad_cgpa:.2f}")
            elif _grad_cgpa >= 2.75:
              st.info(f"**Second Class.** Projected CGPA: {_grad_cgpa:.2f}")
            elif _grad_cgpa >= 2.00:
              st.warning(f"**Pass.** Projected CGPA: {_grad_cgpa:.2f}")
            else:
              st.error(f"**Below minimum graduation threshold.** Projected CGPA: {_grad_cgpa:.2f}")

      else:
        if hdr_col4.button("Deep Analysis", key=btn_key,
                  help=f"Fetch full record for {name} and compute True CGPA + projections"):
          with st.spinner(f"Scanning full academic history for {name} ({reg})\u2026 1\u20132 min."):
            result = _run_deep_analysis(reg, name, sess_id)
          st.session_state._deep_cache[cache_key] = result
          st.rerun(scope="fragment")

      st.write("") # spacing between students

  # ── Pagination + call-site ──────────────────────────────────────────────
  @st.fragment
  def render_paginated_projections(proj_df, profile_name, exam_id):
    if proj_df.empty:
      st.warning("No students match your search.")
      return

    st.markdown(
      f"**{len(proj_df)} student(s)** in this exam \u2014 click Deep Analysis to unlock projections."
    )
    st.divider()

    PAGE_SIZE = 10
    total_pages = max(1, (len(proj_df) + PAGE_SIZE - 1) // PAGE_SIZE)

    if "proj_page" not in st.session_state:
      st.session_state.proj_page = 0
    if st.session_state.proj_page >= total_pages:
      st.session_state.proj_page = 0

    page     = st.session_state.proj_page
    page_df  = proj_df.iloc[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    for _, row in page_df.iterrows():
      render_student_projection_card(row, profile_name, exam_id)

    # Pagination controls
    if total_pages > 1:
      nav_c1, nav_c2, nav_c3 = st.columns([1, 2, 1])
      with nav_c1:
        if st.button("← Previous", key="proj_prev", disabled=(page == 0)):
          st.session_state.proj_page -= 1
          st.rerun(scope="fragment")
      with nav_c2:
        st.markdown(
          f"<div style='text-align:center;padding-top:6px'>Page {page+1} of {total_pages}</div>",
          unsafe_allow_html=True
        )
      with nav_c3:
        if st.button("Next →", key="proj_next", disabled=(page >= total_pages - 1)):
          st.session_state.proj_page += 1
          st.rerun(scope="fragment")

  render_paginated_projections(proj_df, profile_name, exam_id)

ui.add_contact_section()
