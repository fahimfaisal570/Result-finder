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
exams = load_exams(profile_name)
_is_provisional = profiles.get(profile_name, {}).get('is_provisional', False)

if not exams and not _is_provisional:
  st.warning("No exam data found for this batch. Ingest a semester first.")
  st.stop()

if not exams and _is_provisional:
  st.info(
    "🔶 **Provisional Batch** — No exam results published yet. "
    "The exam monitor will auto-detect, scan, run readd detection, "
    "and promote this batch when results appear on the portal."
  )
  
  # --- Student Roster ---
  p_data = profiles.get(profile_name, {})
  roster = [{"Reg No": r[0], "Session": r[1], "Name": r[2]} for r in p_data.get("regs", [])]
  if roster:
    with st.expander(f"📋 Student Roster ({len(roster)} students)", expanded=False):
      st.dataframe(pd.DataFrame(roster), hide_index=True, width="stretch")
  
  # --- Link to GPA Projection Page ---
  st.divider()
  st.page_link("pages/gpa_projection.py", label="Open GPA Projection & Graduation Planner →", icon=":material/trending_up:")
  st.caption("Use the standalone GPA Projection page to simulate graduation CGPA for this batch.")
  
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
if not df_sub_raw.empty:
  _tot_stus = df_raw['reg_no'].nunique() if not df_raw.empty else len(df_sub_raw['reg_no'].unique())
  _counts = df_sub_raw.groupby('subject_code')['reg_no'].nunique()
  _min_th = max(2, int(_tot_stus * 0.15)) if _tot_stus >= 5 else 1
  default_cohort_subjects = sorted(_counts[_counts >= _min_th].index.tolist())
  subjects_available = sorted(df_sub_raw['subject_code'].unique().tolist())
else:
  default_cohort_subjects = []
  subjects_available = []

selected_subjects = st.sidebar.multiselect("Slice by Subjects:", subjects_available, default=default_cohort_subjects)
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

def get_clean_subject_pivot(df_sub, mode="standardized", show_code=False, hide_rare_retakes=True):
    if df_sub.empty:
        return pd.DataFrame(), []
        
    total_students = df_sub['reg_no'].nunique()
    if total_students == 0:
        return pd.DataFrame(), []
        
    counts = df_sub.groupby('subject_code')['reg_no'].nunique()
    
    min_cohort_threshold = max(2, int(total_students * 0.15)) if total_students >= 5 else 1
    retake_subs = counts[counts < min_cohort_threshold].index.tolist()
    
    if mode == "full_raw":
        return df_sub.pivot_table(index='reg_no', columns='subject_code', values='gp', aggfunc='first'), retake_subs

    df_clean = df_sub[~df_sub['subject_code'].isin(retake_subs)] if hide_rare_retakes else df_sub
    
    if mode == "raw_cohort":
        if df_clean.empty:
            return pd.DataFrame(), retake_subs
        return df_clean.pivot_table(index='reg_no', columns='subject_code', values='gp', aggfunc='first'), retake_subs

    clean_counts = df_clean.groupby('subject_code')['reg_no'].nunique()
    core_subs = clean_counts[clean_counts >= max(2, int(total_students * 0.6))].index.tolist()
    elec_subs = clean_counts[clean_counts < max(2, int(total_students * 0.6))].index.tolist()
    
    records = []
    for reg, grp in df_clean.groupby('reg_no'):
        row = {'reg_no': reg}
        for cs in core_subs:
            sub_row = grp[grp['subject_code'] == cs]
            row[cs] = sub_row['gp'].iloc[0] if not sub_row.empty else None
            
        elec_grp = grp[grp['subject_code'].isin(elec_subs)].sort_values('subject_code')
        for i, (_, erow) in enumerate(elec_grp.iterrows(), 1):
            col_name = f'Elective {i}'
            val = erow['gp']
            row[col_name] = f'{val:.2f} ({erow["subject_code"]})' if show_code else val
            
        records.append(row)
        
    df_out = pd.DataFrame(records)
    if not df_out.empty:
        df_out = df_out.set_index('reg_no')
    return df_out, retake_subs

df_pivot, _retake_subs_detected = get_clean_subject_pivot(df_sub, mode="raw_cohort", hide_rare_retakes=True)

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
tabs = st.tabs(["Baseline Insight", "Trends", "Advanced Patterns", "Cube Pivot", "Clearing List"])

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
  mean_gpa = valid_gpas.mean() if not valid_gpas.empty else 0.0
  mean_cgpa = valid_cgpas.mean() if not valid_cgpas.empty else 0.0
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
    st.metric("Average CGPA", f"{mean_cgpa:.2f}" if not is_first_sem else "N/A", help="Average CGPA value of the batch up to this semester")
  with met_row2[1]:
    st.metric("Average GPA", f"{mean_gpa:.2f}", help="Average GPA value of this semester's results")
  with met_row2[2]:
    st.metric("Overall Pass Rate (1st Attempt)", f"{pass_rate:.1f}%", help="Percentage of students who passed all subjects in their first attempt.")

  st.divider()

  # Row 1: GPA Distribution & First-Chance Pass Ratio aligned side-by-side
  row1_c1, spacer, row1_c2 = st.columns([1.2, 0.1, 1.2])

  with row1_c1:
    st.markdown("#### GPA Distribution (This Semester Only)")
    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
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
    st.markdown("#### Batch Performance Breakdown")

    # --- Tier color mapping ---
    tier_colors = {
      'Distinction (3.7–4.00)': '#166534',
      '1st Class (3.5–3.69)': '#22c55e',
      '2nd Class (3.0–3.49)': '#3b82f6',
      '3rd Class (2.0–2.99)': '#f59e0b',
      'Failed (Subject)': '#ef4444',
      'Non-Promoted': '#ef4444',
      'At Risk': '#ef4444',
    }

    def classify_gpa_tiers(df, failed_count=0):
      """Classify students into semester GPA tiers."""
      passed = df[df['first_chance_fail'] == False] if 'first_chance_fail' in df.columns else df
      counts = {
        'Distinction (3.7–4.00)': int((passed['gpa'] >= 3.70).sum()),
        '1st Class (3.5–3.69)': int(((passed['gpa'] >= 3.50) & (passed['gpa'] < 3.70)).sum()),
        '2nd Class (3.0–3.49)': int(((passed['gpa'] >= 3.00) & (passed['gpa'] < 3.50)).sum()),
        '3rd Class (2.0–2.99)': int(((passed['gpa'] >= 2.00) & (passed['gpa'] < 3.00)).sum()),
      }
      if failed_count > 0:
        counts['Failed (Subject)'] = failed_count
      return [{'Tier': k, 'Count': v} for k, v in counts.items() if v > 0]

    def classify_cgpa_tiers(df, promo_target_val, is_even_sem_val, promo_yr_val):
      """Classify students into CGPA tiers. Red tier adapts by context."""
      show_red = promo_target_val is not None and promo_yr_val != 4
      red_label = 'Non-Promoted' if is_even_sem_val else 'At Risk'

      if show_red and promo_target_val:
        non_promoted_count = int((df['cgpa'] < promo_target_val).sum())
        promoted = df[df['cgpa'] >= promo_target_val]
      else:
        non_promoted_count = 0
        promoted = df

      counts = {
        'Distinction (3.7–4.00)': int((promoted['cgpa'] >= 3.70).sum()),
        '1st Class (3.5–3.69)': int(((promoted['cgpa'] >= 3.50) & (promoted['cgpa'] < 3.70)).sum()),
        '2nd Class (3.0–3.49)': int(((promoted['cgpa'] >= 3.00) & (promoted['cgpa'] < 3.50)).sum()),
        '3rd Class (2.0–2.99)': int(((promoted['cgpa'] >= 2.00) & (promoted['cgpa'] < 3.00)).sum()),
      }
      if non_promoted_count > 0:
        counts[red_label] = non_promoted_count
      return [{'Tier': k, 'Count': v} for k, v in counts.items() if v > 0]

    # --- Build charts ---
    gpa_tiers = classify_gpa_tiers(df_main, failed_count=has_failed_count)
    gpa_df = pd.DataFrame(gpa_tiers)

    all_tier_domain = list(tier_colors.keys())
    all_tier_range = list(tier_colors.values())

    if is_first_sem:
        # ---- SINGLE RING (1st semester) ----
        chart = alt.Chart(gpa_df).mark_arc(innerRadius=60, outerRadius=80, y=100).encode(
            theta="Count:Q",
            color=alt.Color("Tier:N",
                scale=alt.Scale(domain=all_tier_domain, range=all_tier_range),
                legend=alt.Legend(
                    orient="none",
                    legendX=0,
                    legendY=200,
                    columns=2,
                    title="GPA Tier",
                    labelFontSize=10.2,
                    titleFontSize=11.4,
                    symbolSize=48
                )),
            order=alt.Order("Count:Q", sort="descending"),
            tooltip=['Tier', 'Count']
        ).properties(height=320, padding={"top": 15, "bottom": 5, "left": 10, "right": 10})
        st.altair_chart(chart, width='stretch')
        st.caption("First semester — single ring shows semester GPA tiers only.")
    else:
        # ---- DUAL RING ----
        cgpa_tiers = classify_cgpa_tiers(df_main, promo_target, is_even_sem, promo_yr)
        cgpa_df = pd.DataFrame(cgpa_tiers)

        gpa_df['Ring'] = 'Semester GPA'
        cgpa_df['Ring'] = 'Cumulative CGPA'

        # Outer ring: GPA
        outer = alt.Chart(gpa_df).mark_arc(innerRadius=70, outerRadius=85, y=100).encode(
            theta="Count:Q",
            color=alt.Color("Tier:N",
                scale=alt.Scale(domain=all_tier_domain, range=all_tier_range),
                legend=alt.Legend(
                    orient="none",
                    legendX=0,
                    legendY=200,
                    columns=2,
                    title="Tier",
                    labelFontSize=10.2,
                    titleFontSize=11.4,
                    symbolSize=48
                )),
            order=alt.Order("Count:Q", sort="descending"),
            tooltip=[alt.Tooltip('Ring', title='Ring'), 'Tier', 'Count']
        )

        # Inner ring: CGPA
        inner = alt.Chart(cgpa_df).mark_arc(innerRadius=45, outerRadius=60, y=100).encode(
            theta="Count:Q",
            color=alt.Color("Tier:N",
                scale=alt.Scale(domain=all_tier_domain, range=all_tier_range),
                legend=None),
            order=alt.Order("Count:Q", sort="descending"),
            tooltip=[alt.Tooltip('Ring', title='Ring'), 'Tier', 'Count']
        )

        chart = (outer + inner).properties(height=320, padding={"top": 15, "bottom": 5, "left": 10, "right": 10})
        st.altair_chart(chart, width='stretch')

        # Context-aware caption
        if promo_yr == 4:
            st.caption("Outer ring: Semester GPA | Inner ring: Cumulative CGPA.")
        elif is_even_sem:
            st.caption("Outer: Semester GPA | Inner: Cumulative CGPA. Non-Promoted = CGPA below promotion threshold (confirmed).")
        else:
            st.caption("Outer: Semester GPA | Inner: Cumulative CGPA. At Risk = CGPA currently below promotion threshold.")

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
    dynamic_mode = st.toggle("Dynamic (Live Portal)", key="trends_dynamic_mode")

    if dynamic_mode:
      # ── Dynamic Mode (Deep Analysis Live Fetch) ──────────────────────
      cache_key = f"_trends_dynamic_{profile_name}"

      if st.button("Fetch Latest", key="trends_fetch_btn"):
        _p_data = profiles.get(profile_name, {})
        _pro_id = _p_data.get("pro_id", "")
        if not _pro_id:
          st.warning("Portal ID not configured for this profile. Use static mode.")
        else:
          dept = db.get_dept_from_profile(profile_name)
          sess_id = _p_data.get("sess_id", "AUTO")
          all_regs = df_longitudinal['reg_no'].unique()

          # Fetch portal metadata once
          _programs, _sessions = cs.fetch_programs_and_sessions()
          _all_exams = cs.fetch_exams(_pro_id) if _pro_id else {}
          if not _all_exams:
            st.warning("Could not fetch exam list from portal.")
          else:
            _filtered_eids = cs.get_relevant_exams(sess_id, _sessions, _all_exams)

            # ponytail: batch ALL students × ALL exams into one engine call
            # instead of N sequential _run_deep_analysis calls.
            # 15 threads now process ~(students × exams) tasks concurrently.
            batch_tasks = [
              (int(reg), sess_id, eid)
              for reg in all_regs
              for eid in _filtered_eids
            ]

            progress = st.progress(0, text="Fetching live data from portal...")
            def _update_progress(current, total, status_text=None):
              frac = current / total if total > 0 else 0
              progress.progress(frac, text=f"Portal scan: {current}/{total} requests...")

            all_history = cs.run_batch_scan_engine(
              tasks=batch_tasks,
              pro_id=_pro_id,
              exam_id="0",
              all_sessions=_sessions,
              progress_callback=_update_progress,
              num_threads=15
            )

            # Attach exam names
            for rec in all_history:
              eid = rec.get('_exam_id')
              if eid and eid in _all_exams:
                rec['_exam_name'] = _all_exams[eid]

            # Group results by student reg_no
            from collections import defaultdict
            student_records = defaultdict(list)
            for rec in all_history:
              sreg = rec.get('Registration No')
              if sreg is not None:
                student_records[int(sreg)].append(rec)

            # Build name lookup
            name_lookup = df_longitudinal.drop_duplicates('reg_no').set_index('reg_no')['name'].to_dict()

            # Compute deep analysis per student
            progress.progress(0.0, text="Computing deep analysis...")
            all_rows = []
            processed = 0
            for reg, records in student_records.items():
              result = db.compute_deep_analysis(records, profile_name, selected_label)
              if result and result.get('effective_grades'):
                breakdown = db.compute_per_semester_breakdown(
                  result['effective_grades'], dept,
                  result['current_semester'],
                  official_records=result.get('official_semester_records')
                )
                stu_name = name_lookup.get(reg, 'Unknown')
                for sem in breakdown:
                  all_rows.append({
                    'reg_no': reg,
                    'name': stu_name,
                    'semester_num': sem['semester'],
                    'semester_label': sem['label'],
                    'gpa': sem['computed_gpa'],
                    'official_gpa': sem['official_gpa'],
                  })
              processed += 1
              progress.progress(processed / len(student_records), text=f"Analysis: {processed}/{len(student_records)} students...")

            progress.empty()
            if all_rows:
              st.session_state[cache_key] = pd.DataFrame(all_rows)
              st.rerun()
            else:
              st.warning("No data could be fetched from portal.")

      # Render from cache
      if cache_key in st.session_state:
        df_dynamic = st.session_state[cache_key]
        st.caption("**Dynamic Mode:** True GPA (retake-adjusted) vs Official GPA live from portal")

        if max_semester:
          st.caption(f"**Batch Progress Cap:** Showing data up to Semester {max_semester}")
        st.markdown("#### Batch GPA Trajectory (Dynamic)")

        # Prepare dual-line chart data: true GPA + official GPA per student
        true_df = df_dynamic[['reg_no','name','semester_num','semester_label','gpa']].copy()
        true_df['line_type'] = 'true'
        true_df['is_median'] = False

        off_df = df_dynamic[['reg_no','name','semester_num','semester_label','official_gpa']].copy()
        off_df = off_df.rename(columns={'official_gpa': 'gpa'})
        off_df['line_type'] = 'official'
        off_df['is_median'] = False

        # Compute median based on True GPA
        median_df = true_df.groupby('semester_num')['gpa'].median().reset_index()
        median_df['name'] = 'Batch Median'
        median_df['reg_no'] = 0
        median_df['is_median'] = True
        median_df['line_type'] = 'median'

        chart_df = pd.concat([true_df, off_df, median_df], ignore_index=True)

        student_list = ["None"] + sorted(df_dynamic['name'].unique().tolist())
        spotlight = st.selectbox("Spotlight Student:", student_list, key="dyn_spotlight")

        def get_dyn_opacity(row):
          if row['is_median']: return 1.0
          if spotlight == "None": return 0.45
          return 1.0 if row['name'] == spotlight else 0.05

        def get_dyn_color(row):
          if row['is_median']:
            return '#ef4444' if spotlight != 'None' else '#f59e0b'  # Red median when spotlight active, else gold
          if row['line_type'] == 'official':
            return '#9ca3af' if row['name'] == spotlight else '#f97316'  # Ashen for spotlight official, orange otherwise
          return '#22c55e'  # True GPA always green

        def get_dyn_stroke_dash(row):
          if row['is_median']: return [5, 5]
          if row['line_type'] == 'official': return [2, 4]
          return [0]

        chart_df['opacity'] = chart_df.apply(get_dyn_opacity, axis=1)
        chart_df['color'] = chart_df.apply(get_dyn_color, axis=1)
        chart_df['strokeDash'] = chart_df.apply(get_dyn_stroke_dash, axis=1)
        chart_df['line_id'] = chart_df['reg_no'].astype(str) + '_' + chart_df['line_type']
        chart_df['strokeWidth'] = chart_df['is_median'].apply(lambda x: 3 if x else 1.5)

        if spotlight != 'None':
          st.caption("**Class Median** (Red Dashed)  ·  **True GPA** (Green Solid)  ·  **Official GPA** (Ash Dotted)  ·  Other students dimmed")
        else:
          st.caption("**Class Median** (Gold Dashed)  ·  **True GPA** (Green Solid)  ·  **Official GPA** (Orange Dotted)")

        traj_chart = alt.Chart(chart_df).mark_line(point=True).encode(
          x=alt.X('semester_num:O', title='Semester Index'),
          y=alt.Y('gpa:Q', title='GPA', scale=alt.Scale(domain=[1.5, 4.0], clamp=True)),
          detail='line_id:N',
          color=alt.Color('color:N', scale=None),
          opacity=alt.Opacity('opacity:Q', scale=None),
          strokeDash=alt.StrokeDash('strokeDash:N', scale=None),
          strokeWidth=alt.StrokeWidth('strokeWidth:Q', scale=None),
          tooltip=['name','reg_no','semester_label','gpa','line_type']
        ).properties(height=400)

        st.altair_chart(traj_chart, width='stretch')

        st.divider()

        # Dynamic Metrics Table (using True GPA)
        st.markdown("#### Student Trajectory Metrics (True GPA)")
        
        metrics = []
        for reg, group in df_dynamic.groupby('reg_no'):
          if len(group) < 2:
            metrics.append({
             'reg_no': reg, 'name': group.iloc[0]['name'], 'peak': group['gpa'].max(),
             'valley': group['gpa'].min(), 'consistency': 1.0, 'trajectory': 'Stable'
            })
            continue
            
          sorted_group = group.sort_values('semester_num')
          gpas = sorted_group['gpa'].tolist()
          sem_nums = sorted_group['semester_num'].tolist()
          peak = max(gpas)
          valley = min(gpas)
          consistency = max(0.0, 1.0 - float(np.std(gpas)))
          
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
           'reg_no': reg, 'name': sorted_group.iloc[0]['name'], 'peak': round(peak, 2),
           'valley': round(valley, 2), 'consistency': round(consistency, 2),
           'trajectory': traj
          })
          
        metrics_df = pd.DataFrame(metrics).sort_values('consistency', ascending=False)
        st.dataframe(metrics_df, hide_index=True, width='stretch')
      else:
        st.info("Click 'Fetch Latest' to perform deep analysis and load live portal data for all students.")

    else:
      # ── Static Mode (Database Cached Results) ────────────────────────
      if max_semester:
        st.caption(f"**Batch Progress Cap:** Showing data up to Semester {max_semester} (excluding future results of readmitted students)")
      st.markdown("#### Batch GPA Trajectory (Static)")
      
      median_df = df_longitudinal.groupby('semester_num')['gpa'].median().reset_index()
      median_df['name'] = 'Batch Median'
      median_df['reg_no'] = 0
      median_df['is_median'] = True
      
      chart_df = df_longitudinal.copy()
      chart_df['is_median'] = False
      chart_df = pd.concat([chart_df, median_df], ignore_index=True)
      
      student_list = ["None"] + sorted(df_longitudinal['name'].unique().tolist())
      spotlight = st.selectbox("Spotlight Student:", student_list)
      
      def get_opacity(row):
        if row['is_median']: return 1.0
        if spotlight == "None": return 0.35
        return 1.0 if row['name'] == spotlight else 0.05
        
      def get_color(row):
        if row['is_median']: return '#f59e0b'        # Gold for Class Median
        return '#ef4444' if row['name'] == spotlight else '#6366f1' # Red spotlight / Indigo students

      def get_stroke_dash(row):
        return [5, 5] if row['is_median'] else [0]
        
      chart_df['opacity'] = chart_df.apply(get_opacity, axis=1)
      chart_df['color'] = chart_df.apply(get_color, axis=1)
      chart_df['strokeDash'] = chart_df.apply(get_stroke_dash, axis=1)
      chart_df['strokeWidth'] = chart_df['is_median'].apply(lambda x: 3 if x else 1.5)

      st.caption("**Class Median** (Gold Dashed)  ·  **Student Lines** (Indigo Solid)  ·  **Spotlight Student** (Red Solid)")

      traj_chart = alt.Chart(chart_df).mark_line(point=True).encode(
        x=alt.X('semester_num:O', title='Semester Index'),
        y=alt.Y('gpa:Q', title='GPA', scale=alt.Scale(domain=[1.5, 4.0], clamp=True)),
        detail='reg_no:N',
        color=alt.Color('color:N', scale=None),
        opacity=alt.Opacity('opacity:Q', scale=None),
        strokeDash=alt.StrokeDash('strokeDash:N', scale=None),
        strokeWidth=alt.StrokeWidth('strokeWidth:Q', scale=None),
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
  
  col_p1, col_p2 = st.columns([2, 1])
  with col_p1:
    pivot_mode = st.radio(
      "View Mode / Structure:",
      [
        "Standardized View (Core + Elective Slots)",
        "Raw Subject Codes (Clean Batch)",
        "Full Raw Matrix (Includes Retakes)",
        "Show Summary per Subject"
      ],
      index=0,
      horizontal=False
    )
  with col_p2:
    show_code_in_elective = st.checkbox("Show Course Code in Elective Slots", value=True, help="Display e.g. '3.75 (CE-801)' instead of plain GP")
    hide_retakes_cb = st.checkbox("Filter Retake-Only Courses (<15% Cohort)", value=True, help="Exclude courses taken by isolated retake/backlog students")

  if not df_sub.empty:
    if "Standardized" in pivot_mode:
      df_display, ret_found = get_clean_subject_pivot(df_sub, mode="standardized", show_code=show_code_in_elective, hide_rare_retakes=hide_retakes_cb)
      st.dataframe(df_display, width='stretch')
      if ret_found:
        st.caption(f"Note: Retake Course(s) Isolated: `{', '.join(ret_found)}` (taken by single retake/backlog student, excluded from main grid).")
    elif "Raw Subject Codes" in pivot_mode:
      df_display, ret_found = get_clean_subject_pivot(df_sub, mode="raw_cohort", hide_rare_retakes=hide_retakes_cb)
      st.dataframe(df_display, width='stretch')
      if ret_found:
        st.caption(f"Note: Retake Course(s) Excluded: `{', '.join(ret_found)}`.")
    elif "Full Raw Matrix" in pivot_mode:
      df_display, ret_found = get_clean_subject_pivot(df_sub, mode="full_raw")
      st.dataframe(df_display, width='stretch')
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



ui.add_contact_section()
