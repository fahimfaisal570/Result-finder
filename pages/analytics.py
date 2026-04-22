import streamlit as st
import pandas as pd
import numpy as np
import os
import altair as alt
import sys
import time
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import ui_components as ui

st.set_page_config(page_title="Result Analytics", page_icon="favicon.ico", layout="wide")
ui.inject_essential_ui()

# Add parent dir for database import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db

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

def get_promotion_rules(exam_label):
    import re
    promo_target = None
    is_even_sem = False
    yr = None
    
    yr_match = re.search(r"(\d)[a-z]{2}\s*Yr", exam_label, re.IGNORECASE)
    sem_match = re.search(r"(\d)[a-z]{2}\s*Sem", exam_label, re.IGNORECASE)
    
    if yr_match:
        yr = int(yr_match.group(1))
        if yr == 1: promo_target = 2.00
        elif yr == 2: promo_target = 2.25
        elif yr == 3: promo_target = 2.50
        elif yr == 4: promo_target = 2.75
        
    if sem_match:
        sem = int(sem_match.group(1))
        is_even_sem = (sem == 2)
        
    return promo_target, is_even_sem, yr

def get_performance_archetypes(df_pivot, df_main, promo_target=None, is_even_sem=False, is_first_sem=False, promo_yr=None):
    """
    Identifies academic personas based on State (current), Pattern (variance), and Trend (trajectory).
    """
    if df_pivot.empty or df_main.empty: return None
    
    # 1. Merge Pivot (variance) with Main (sgpa, cgpa)
    data = df_pivot.dropna().copy()
    if len(data) < 4: return None # Statistical minimum

    # Features: Mean (Strength) and Variance (Consistency)
    features = pd.DataFrame(index=data.index)
    features['std_gp'] = data.std(axis=1).fillna(0)
    
    # Merge with df_main to get SGPA & CGPA for momentum/state
    features = features.merge(df_main[['reg_no', 'sgpa', 'cgpa']], left_index=True, right_on='reg_no', how='left')
    features.set_index('reg_no', inplace=True)
    features['momentum'] = features['sgpa'] - features['cgpa'] if not is_first_sem else 0.0
    
    # 2. Dynamic Thresholds (Percentile Quartiles)
    p75_sgpa = features['sgpa'].quantile(0.75)
    p50_sgpa = features['sgpa'].quantile(0.50)
    
    rising_threshold = 0.15
    slipping_threshold = -0.15

    # 3. Compound Labeling Heuristic
    def get_compound_status(row):
        base = "Average"
        detail = "Average"
        target_sgpa = 0.0

        if promo_target is not None and promo_yr is not None:
            sem_index = (promo_yr * 2) - 1
            # Calculate target SGPA to reach promo_target by end of year
            # Inverse of: max_possible_cgpa = ((row['cgpa'] * sem_index) + (S * 1.1)) / (sem_index + 1.1)
            target_sgpa = (promo_target * (sem_index + 1.1) - row['cgpa'] * sem_index) / 1.1
            target_sgpa = max(0.0, round(target_sgpa, 2))
        
        # Promotion overrides define the lowest tier
        if promo_target is not None:
            if row['cgpa'] < promo_target:
                if is_even_sem:
                    base = "Non-Promoted (Failed)"
                else:
                    if promo_yr is not None:
                        sem_index = (promo_yr * 2) - 1
                        max_possible_cgpa = ((row['cgpa'] * sem_index) + (4.00 * 1.1)) / (sem_index + 1.1)
                        if max_possible_cgpa < promo_target:
                            base = "Readd"
                        else:
                            base = "Critical (Action Req.)"
                    else:
                        base = "Critical (Action Req.)"
                detail = base
            elif row['cgpa'] <= (promo_target + 0.15):
                base = "At-Risk (Promotion)"
                detail = base
                
        # If not overridden by the absolute promotion system, assign relative batch percentile state
        if detail == "Average":
            if row['sgpa'] >= p75_sgpa or row['cgpa'] >= 3.5:
                base = "Top"
                detail = "Top"
            elif row['sgpa'] >= p50_sgpa:
                base = "Steady"
                detail = "Steady"
            else:
                base = "Average"
                detail = "Average"
                
        trend = ""
        if not is_first_sem and row['cgpa'] > 0:
            variance_ratio = (row['sgpa'] - row['cgpa']) / row['cgpa']
            if variance_ratio >= 0.05:
                trend = " ↑ (Improving)"
            elif variance_ratio <= -0.05:
                trend = " ↓ (Declining)"
            
        return pd.Series([f"{base}{trend}", detail, target_sgpa])

    features[['Archetype', 'Detailed_Status', 'Target_SGPA']] = features.apply(get_compound_status, axis=1)
    return features[['Archetype', 'Detailed_Status', 'std_gp', 'Target_SGPA']]

def get_strategic_insights(df_main, df_sub, df_pivot, archetypes, is_first_sem=False):
    """
    Generates high-level leadership insights for the Department Head.
    """
    insights = {}
    
    # 1. Performance & Honours
    valid_main = df_main[df_main['sgpa'] > 0].copy()
    if not valid_main.empty:
        if is_first_sem:
            insights['mean_sgpa'] = valid_main['sgpa'].mean().round(2)
        else:
            insights['batch_momentum'] = (valid_main['sgpa'].mean() - valid_main['cgpa'].mean()).round(2)
            
        insights['honours_count'] = len(valid_main[valid_main['cgpa'] >= 3.5 if not is_first_sem else valid_main['sgpa'] >= 3.5])
        insights['honours_pct'] = (insights['honours_count'] / len(valid_main)) * 100
    
    # 2. Risk Tally
    if archetypes is not None:
        risk_mask = archetypes['Archetype'].str.contains("At Risk", case=False)
        insights['risk_count'] = risk_mask.sum()
        insights['improving_count'] = archetypes['Archetype'].str.contains("Improving", case=False).sum()
        
        # Promotion specific trackers mapped via Detailed_Status
        insights['promo_risk_count'] = archetypes['Detailed_Status'].str.contains("At-Risk \(Promotion\)", case=False).sum()
        insights['critical_count'] = archetypes['Detailed_Status'].str.contains("Critical", case=False).sum()
        insights['math_fail_count'] = archetypes['Detailed_Status'].str.contains("Readd", case=False).sum()
        insights['failed_count'] = archetypes['Detailed_Status'].str.contains("Non-Promoted \(Failed\)", case=False).sum()

        # Collect student reg_no + name lists for each alert category
        arc_with_info = archetypes.merge(df_main[['reg_no', 'name']], left_index=True, right_on='reg_no', how='left').set_index('reg_no')
        def _student_list(mask_series):
            regs = archetypes[mask_series].index.tolist()
            rows = arc_with_info.loc[arc_with_info.index.isin(regs), ['name', 'Target_SGPA']].reset_index()
            return [(r['reg_no'], r['name'], r['Target_SGPA']) for _, r in rows.iterrows()]
        
        insights['readd_students']    = _student_list(archetypes['Detailed_Status'].str.contains("Readd", case=False))
        insights['failed_students']   = _student_list(archetypes['Detailed_Status'].str.contains("Non-Promoted \(Failed\)", case=False))
        insights['critical_students'] = _student_list(archetypes['Detailed_Status'].str.contains("Critical", case=False))
        insights['risk_students']     = _student_list(archetypes['Detailed_Status'].str.contains("At-Risk \(Promotion\)", case=False))

    # 3. Subject Bottlenecks (The "Killer" Subject)
    if not df_sub.empty:
        sub_stats = df_sub[df_sub['gp'] >= 0].groupby(['subject_code', 'subject_name'])['gp'].mean().reset_index()
        if not sub_stats.empty:
            bottleneck = sub_stats.iloc[sub_stats['gp'].idxmin()]
            star = sub_stats.iloc[sub_stats['gp'].idxmax()]
            insights['bottleneck'] = f"{bottleneck['subject_code']} ({bottleneck['subject_name']})"
            insights['bottleneck_gp'] = bottleneck['gp'].round(2)
            insights['star'] = f"{star['subject_code']} ({star['subject_name']})"
            insights['star_gp'] = star['gp'].round(2)

    # 4. Synergy Detection (Correlations)
    if not df_pivot.empty and len(df_pivot.columns) > 1:
        corr_matrix = df_pivot.corr()
        corr_matrix.index.name = 's1'
        corr_matrix.columns.name = 's2'
        corr = corr_matrix.unstack().reset_index()
        corr.columns = ['s1', 's2', 'coeff']
        
        corr = corr[corr['s1'] != corr['s2']] # Remove self-correlation
        if not corr.empty:
            top_corr = corr.sort_values('coeff', ascending=False).iloc[0]
            insights['synergy'] = (top_corr['s1'], top_corr['s2'], top_corr['coeff'].round(2))

    return insights

# ---------------------------------------------------------------------------
# UI Setup
# ---------------------------------------------------------------------------

st.page_link("app.py", label="← Back to Dashboard", icon="🏠")
st.title("📊 Integrated Batch Analytics")
st.markdown("Measuring first-chance performance, cohort bottlenecks, and strategic eligibility.")

profiles = db.get_profiles()
if not profiles:
    st.warning("⚠️ No saved profiles found. Run a scan first.")
    st.stop()

# ---------------------------------------------------------------------------
# SIDEBAR — Connectivity & Selection
# ---------------------------------------------------------------------------
st.sidebar.header("🧊 Slice & Dice (OLAP)")

sorted_profiles = sorted(list(profiles.keys()))
profile_name = st.sidebar.selectbox("📂 Select Batch:", sorted_profiles)

if not profile_name:
    st.stop()

exams = load_exams(profile_name)
if not exams:
    st.warning("⚠️ No exam data found for this batch. Ingest a semester first.")
    st.stop()

# Build display labels: "Exam Name (exam_id)" — latest on top
def exam_label(e):
    name = e.get('exam_name') or f"Exam {e['exam_id']}"
    
    # Intelligently condense names like "B.Sc. in Computer Science... 3rd year 1st Semester... of 2024"
    import re
    pattern = r'(?i)(\d[A-Za-z]+)\s+year\s+(\d[A-Za-z]+)\s+Semester.*?(?:of\s+)?(\d{4})'
    match = re.search(pattern, name)
    if match:
        name = f"{match.group(1).capitalize()} Yr {match.group(2).capitalize()} Sem '{match.group(3)[-2:]}"
    elif len(name) > 40:
        name = name[:37] + "…"
        
    return f"{name}  [{e['exam_id']}]"

exam_options = {exam_label(e): e for e in exams}
selected_label = st.sidebar.selectbox("📅 Select Semester:", list(exam_options.keys()))
selected_exam  = exam_options[selected_label]
exam_id        = selected_exam['exam_id']

st.sidebar.divider()

# ---------------------------------------------------------------------------
# Exam Management expander
# ---------------------------------------------------------------------------
with st.sidebar.expander("⚙️ Exam Management", expanded=False):
    scanned_at = selected_exam.get('scanned_at')
    scan_time  = time.strftime('%Y-%m-%d %H:%M', time.localtime(scanned_at)) if scanned_at else "Unknown"
    st.markdown(f"**Exam ID:** `{exam_id}`")
    st.markdown(f"**Students ingested:** {selected_exam.get('student_count', '?')}")
    st.markdown(f"**Last scanned:** {scan_time}")

    st.markdown("---")
    st.markdown("**⚠️ Danger Zone**")
    confirm_delete = st.checkbox("✅ Confirm — I want to delete this exam scan", key=f"del_confirm_{exam_id}")
    if st.button("🗑️ Delete This Exam Scan", type="primary", disabled=not confirm_delete):
        db.delete_exam(profile_name, exam_id)
        st.cache_data.clear()
        st.success(f"Exam `{exam_id}` deleted. Student roster preserved.")
        st.rerun()

# ---------------------------------------------------------------------------
# Load data scoped to selected exam
# ---------------------------------------------------------------------------
df_raw     = load_base_df(profile_name, exam_id)
df_sub_raw = load_subject_df(profile_name, exam_id)

if df_raw.empty:
    st.info("No exam results found for this semester. Try selecting a different exam or rescanning.")
    st.stop()

# ---------------------------------------------------------------------------
# SIDEBAR — Slice & Dice filters
# ---------------------------------------------------------------------------
subjects_available = sorted(df_sub_raw['subject_code'].unique().tolist()) if not df_sub_raw.empty else []
selected_subjects  = st.sidebar.multiselect("📚 Slice by Subjects:", subjects_available, default=subjects_available)
cgpa_range         = st.sidebar.slider("🎓 CGPA Range:", 0.0, 4.0, (0.0, 4.0))

st.sidebar.divider()
show_strategic_brief = st.sidebar.toggle("📜 Strategic Insights Mode", value=False, help="Display an executive summary for the Department Head.")
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
        expanded=True
    ):
        st.warning(
            "The following student(s) have fewer semester records than this batch has published. "
            "They are likely **readd students** whose Year 1 results exist under a previous batch. "
            "Click **Scan & Fix** to retrieve their full academic history from the portal and recalculate their CGPA accurately.",
            icon="🔍"
        )

        _p_data    = profiles.get(profile_name, {})
        _pro_id    = _p_data.get("pro_id", "")

        for _s in _incomplete_students:
            _col1, _col2 = st.columns([4, 1])
            _col1.markdown(
                f"**{_s['name']}** &nbsp; `{_s['reg_no']}` &nbsp;|&nbsp; "
                f"Found **{_s['student_exam_count']}** / **{_s['profile_exam_count']}** semester(s)"
            )
            _fix_key = f"fix_{profile_name}_{_s['reg_no']}"
            if _col2.button("🔄 Scan & Fix", key=_fix_key, type="primary"):
                import cli_scraper as cs
                import re as _re

                st.info(f"🔍 Scanning full academic history for **{_s['name']}** ({_s['reg_no']})…")

                # Fetch portal session list and full exam catalogue for this program
                with st.spinner("Fetching portal data…"):
                    _programs, _sessions = cs.fetch_programs_and_sessions()
                    _all_exams = cs.fetch_exams(_pro_id) if _pro_id else {}

                if not _all_exams:
                    st.error("❌ Could not load exam list. Portal may be down.")
                else:
                    # Smart Scope: filter exams to the student's cohort year
                    _sess_id = _s.get("sess_id", "AUTO") or "AUTO"
                    _start_year = 0
                    if _sess_id and _sess_id != "AUTO":
                        _sname = _sessions.get(_sess_id, "")
                        _ym = _re.search(r"20(\d{2})", _sname)
                        if _ym:
                            _start_year = int("20" + _ym.group(1))

                    _YEAR_PAT = _re.compile(r'\b(20\d{2})\b')
                    _filtered_eids = []
                    for _eid, _ename in _all_exams.items():
                        if _start_year:
                            _ey_matches = _YEAR_PAT.findall(_ename)
                            _ey = int(_ey_matches[-1]) if _ey_matches else 0
                            if _ey and _ey < (_start_year - 1):
                                continue
                        _filtered_eids.append(_eid)

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
                                f"✅ Successfully resolved **{_saved}** semester(s) for "
                                f"**{_s['name']}**. Analytics will now reflect the correct CGPA."
                            )
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.warning("Scan completed but no new main semester data was found for this student.")

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
df_sub  = df_sub_raw[df_sub_raw['subject_code'].isin(selected_subjects)].copy() if not df_sub_raw.empty else df_sub_raw
df_main = df_raw[(df_raw['cgpa'] >= cgpa_range[0]) & (df_raw['cgpa'] <= cgpa_range[1])].copy()

# Resilience Detection: Is this the first semester scan?
# In 1st Sem, portal often repeats SGPA as CGPA. Detect by equality or sum.
is_first_sem = (df_main['cgpa'].sum() == 0) or \
               (df_main['sgpa'].equals(df_main['cgpa'])) or \
               ("1st Yr 1st Sem" in selected_label)

df_pivot = pd.DataFrame()
if not df_sub.empty:
    df_pivot = df_sub.pivot_table(index='reg_no', columns='subject_code', values='gp', aggfunc='first')

# Extract promotion conditions
promo_target, is_even_sem, promo_yr = get_promotion_rules(selected_label)


# ---------------------------------------------------------------------------
# STRATEGIC INSIGHT BRIEF
# ---------------------------------------------------------------------------
if show_strategic_brief:
    # Pre-calculate personas for the brief
    archetypes = get_performance_archetypes(df_pivot, df_main, promo_target=promo_target, is_even_sem=is_even_sem, is_first_sem=is_first_sem, promo_yr=promo_yr)
    insights = get_strategic_insights(df_main, df_sub, df_pivot, archetypes, is_first_sem=is_first_sem)
    
    with st.container(border=True):
        st.subheader("📜 Strategic Analysis Brief")
        
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        
        # Metric 1: Performance / Momentum
        if is_first_sem:
            m_col1.metric("Mean Semester GPA", f"{insights.get('mean_sgpa', 0):.2f}", 
                         delta="Initial Baseline")
        else:
            momentum = insights.get('batch_momentum', 0)
            m_col1.metric("Batch Momentum", f"{momentum:+.2f}", 
                         delta="Improving" if momentum > 0 else "Declining",
                         delta_color="normal")
        
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
            st.markdown("##### 🚧 Academic Pressures")
            
            # Promotion Warning Injections
            m_ct = insights.get('math_fail_count', 0)
            f_ct = insights.get('failed_count', 0)
            c_ct = insights.get('critical_count', 0)
            r_ct = insights.get('promo_risk_count', 0)
            
            def _render_student_list(student_data):
                for reg, name, target in student_data:
                    # Hide target after even semesters unless it's impossible (>4.0)
                    show_target = not is_even_sem or target > 4.0
                    
                    if show_target:
                        target_str = f"Target: **{target:.2f}**" if target <= 4.0 else "**Impossible (>4.0)**"
                        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• **{name}** `{reg}` &nbsp;|&nbsp; Next Sem {target_str}")
                    else:
                        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• **{name}** `{reg}`")

            if m_ct > 0:
                st.error(f"**⛔ {m_ct} Student(s) Readd Alert:** Deficit too high to reach Year {promo_yr} **{promo_target} CGPA** threshold even with perfect SGPA next semester.")
                _render_student_list(insights.get('readd_students', []))
            if f_ct > 0:
                st.error(f"**🔴 {f_ct} Student(s) Failed Promotion:** Did not meet the Year {promo_yr} **{promo_target} CGPA** threshold.")
                _render_student_list(insights.get('failed_students', []))
            if c_ct > 0:
                st.error(f"**🚨 {c_ct} Student(s) Critically At-Risk:** Falling below the {promo_target} threshold mid-year. High probability of failing promotion.")
                _render_student_list(insights.get('critical_students', []))
            if r_ct > 0:
                st.warning(f"**⚠️ {r_ct} Student(s) At-Risk:** Hovering dangerously close (+0.15 margin) to the {promo_target} year-end cutoff.")
                _render_student_list(insights.get('risk_students', []))
            
            if 'bottleneck' in insights:
                st.warning(f"**Bottleneck Identified:** The subject **{insights['bottleneck']}** has the lowest cohort average (**{insights['bottleneck_gp']} GP**).")
            
            if 'synergy' in insights:
                s1, s2, val = insights['synergy']
                st.info(f"**Syllabus Synergy:** High performance correlation (**{val}**) detected between **{s1}** and **{s2}**.")

        with b_col2:
            st.markdown("##### 🚀 Leadership Intelligence")
            if is_first_sem:
                st.info("**Initial Talent Discovery:** This is the baseline semester. Use this scan to identify the natural technical aptitude of the new cohort.")
            else:
                momentum = insights.get('batch_momentum', 0)
                if momentum > 0.1:
                    st.success(f"**Positive Shift:** The batch performed **{momentum} GP points** better than their historical baseline.")
                elif momentum < -0.1:
                    st.error(f"**Fatigue Alert:** Batch performance is **{abs(momentum)} points below** historical averages.")
                else:
                    st.info("**Steady State:** The cohort is maintaining their historical GPA standards.")
            
            if not is_first_sem and insights.get('improving_count', 0) > 5:
                st.success("**Excellence Rotation:** A high number of 'Rising Stars' detected, suggesting a healthy, competitive environment.")

st.divider()

# ---------------------------------------------------------------------------
# TABS
# ---------------------------------------------------------------------------
tabs = st.tabs(["⭐ Baseline Insight", "🧪 Advanced Patterns", "🌀 Cube Pivot", "🏆 Clearing List"])

# =========================================================================
# TAB 1: BASELINE
# =========================================================================
with tabs[0]:
    st.subheader("High-Level Batch Stethoscope")

    # Row 1: CGPA Distribution & First-Chance Pass Ratio
    row1_c1, row1_c2 = st.columns([1.6, 1])

    with row1_c1:
        st.markdown("#### 📈 SGPA Distribution (This Semester Only)")
        dist_df = df_main[df_main['sgpa'] > 0].copy()
        
        # High-leverage axis anchoring: Remove the '0.0 - 2.0' void
        curr_min = dist_df['sgpa'].min() if not dist_df.empty else 0.0
        import numpy as np
        axis_start = max(0.0, float(np.floor(curr_min * 5) / 5) - 0.2)
        
        dist_chart = alt.Chart(dist_df).mark_bar().encode(
            alt.X("sgpa:Q",
                  bin=alt.Bin(maxbins=40, extent=[axis_start, 4.0], step=0.05), # Preciser bins
                  title="Semester GPA (SGPA)",
                  scale=alt.Scale(domain=[axis_start, 4], nice=False)),
            alt.Y('count()', title='Student Count'),
            tooltip=[
                alt.Tooltip('sgpa:Q', bin=alt.Bin(maxbins=40, extent=[axis_start, 4.0], step=0.05), title='GPA Band'),
                alt.Tooltip('count()', title='Students')
            ]
        ).properties(height=300)
        st.altair_chart(dist_chart, use_container_width=True)
        st.caption(f"Visualized spread from {axis_start:.2f} (Semester Minimum Focus)")

    with row1_c2:
        st.markdown("#### ⭕ First-Chance Pass Ratio")
        has_failed_count  = int(df_main['first_chance_fail'].sum())
        all_passed_count  = len(df_main) - has_failed_count
        
        # Display the Overall Pass Rate as a high-leverage metric
        pass_rate = (all_passed_count / len(df_main)) * 100 if not df_main.empty else 0
        st.metric("Overall Pass Rate (1st Attempt)", f"{pass_rate:.1f}%", 
                  help="Percentage of students who passed all subjects in their first attempt.")

        status_df = pd.DataFrame({
            'Status': ['Passed (1st Chance)', 'Failed (Any Subject)'],
            'Count':  [all_passed_count, has_failed_count]
        })
        pie = alt.Chart(status_df).mark_arc(innerRadius=60, outerRadius=100).encode(
            theta="Count:Q",
            color=alt.Color("Status:N", scale=alt.Scale(
                domain=['Passed (1st Chance)', 'Failed (Any Subject)'],
                range=['#10b981', '#ef4444']
            ), legend=alt.Legend(orient="bottom")),
            tooltip=['Status', 'Count']
        ).properties(height=300)
        st.altair_chart(pie, use_container_width=True)
        st.caption("Students who failed ≥1 subject in their main attempt are counted as Failed.")

    st.divider()

    # Row 2: Subject Difficulty Ranking
    st.markdown("#### 🚧 Subject Difficulty Ranking (Bottleneck Capacity)")
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
            tooltip=['subject_code', 'subject_name', alt.Tooltip('gp:Q', format='.2f')]
        ).properties(height=max(250, len(sub_avg) * 40))
        st.altair_chart(bar, use_container_width=True)
        st.caption("Lower average GPA = systemic difficulty. Only passing grades (≥2.0) are averaged.")
    else:
        st.info("No subject data available.")

    st.divider()

    # Row 3: Achievement Gradient (rank vs CGPA)
    st.markdown("#### 📉 Achievement Gradient (Rank vs GPA)")
    
    # Adaptive Fallback: In 1st semester, CGPA is typically 0. Use SGPA instead.
    use_sgpa_grad = df_main['cgpa'].sum() == 0
    gpa_col = 'sgpa' if use_sgpa_grad else 'cgpa'
    gpa_title = "Semester GPA (SGPA)" if use_sgpa_grad else "Cumulative GPA"
    
    rank_df = df_main[df_main[gpa_col] > 0].sort_values(gpa_col, ascending=False).copy()
    rank_df['Rank'] = range(1, len(rank_df) + 1)
    
    # Adaptive Y-axis to prevent 'distances taken too far'
    gpa_min = rank_df[gpa_col].min() if not rank_df.empty else 0.0
    y_start = max(0.0, float(gpa_min) - 0.2)
    
    line = alt.Chart(rank_df).mark_line(point=True, color="#8b5cf6").encode(
        x=alt.X('Rank:Q', title='Student Rank'),
        y=alt.Y(f'{gpa_col}:Q', title=gpa_title, scale=alt.Scale(domain=[y_start, 4.0], clamp=True)),
        tooltip=['name', alt.Tooltip(f'{gpa_col}:Q', format='.2f', title=gpa_title), 'Rank']
    ).properties(height=350)
    st.altair_chart(line, use_container_width=True)
    if use_sgpa_grad:
        st.caption("ℹ️ First-semester fallback: Ranking based on **SGPA** (Cumulative GPA not yet available).")

# =========================================================================
# TAB 2: ADVANCED PATTERNS
# =========================================================================
with tabs[1]:
    st.subheader("Academic Variance & Pattern Extraction")

    st.markdown("#### 📦 Subject Performance Variance")
    if not df_sub.empty:
        df_sub_boxplot = df_sub[df_sub['gp'] >= 2.0]
        if not df_sub_boxplot.empty:
            # Fix: Altair mark_boxplot components are 'box', 'median', 'rule', 'outliers', 'ticks'
            box = alt.Chart(df_sub_boxplot).mark_boxplot(
                extent='min-max', 
                clip=True,
                median={'color': 'white', 'thickness': 2},
                rule={'color': 'white'},
                ticks={'color': 'white'}
            ).encode(
                x=alt.X('subject_code:N', title='Subject',
                        axis=alt.Axis(labelAngle=-45, labelPadding=10)),
                y=alt.Y('gp:Q', title='Grade Point',
                        scale=alt.Scale(domain=[2.0, 4.0], clamp=True)),
                color=alt.value("#ec4899")
            ).properties(height=450)
            st.altair_chart(box, use_container_width=True)
        else:
            st.info("No passing grades to display in this view.")
    else:
        st.info("No subject data available.")

    st.divider()

    col_m1, col_m2 = st.columns(2)

    with col_m1:
        st.markdown("#### 👽 Performance Personas (Strategic Quadrant)")
        if not df_pivot.empty:
            # Use the new compound persona logic
            clusters = get_performance_archetypes(df_pivot, df_main, promo_target=promo_target, is_even_sem=is_even_sem, is_first_sem=is_first_sem, promo_yr=promo_yr)
            if clusters is not None:
                clust_df = df_main.merge(clusters, left_on='reg_no', right_index=True)
                clust_df['momentum'] = (clust_df['sgpa'] - clust_df['cgpa']).round(2) if not is_first_sem else 0.0
                
                # Innovative Visualization: Strategic Quadrant (Y: Performance, X: Momentum/Variance)
                # Fallback: In 1st sem, plot vs Subject Variance (Consistency) since momentum is 0
                x_col = 'momentum' if not is_first_sem else 'std_gp'
                x_title = 'Academic Momentum' if not is_first_sem else 'Subject Variance (Lower = More Consistent)'
                
                # Mobile-first locator selectbox
                student_list = ["None"] + sorted(clust_df['name'].unique().tolist())
                spotlight_student = st.selectbox("🔍 Spotlight Focus (Find Student)", student_list, index=0)
                
                # High-Contrast Color Mapping for subcategories (Neon=Improving, Base=Solid, Dark/Muted=Declining)
                color_map = {
                    "Top": "#2563eb",            # Solid Royal Blue
                    "Top ↑ (Improving)": "#06b6d4", # Bright Cyan (Total distinction)
                    "Top ↓ (Declining)": "#1e3a8a", # Deep Dark Navy
                    
                    "Steady": "#16a34a",         # Solid Medium Green
                    "Steady ↑ (Improving)": "#bef264", # Neon Lime Green
                    "Steady ↓ (Declining)": "#14532d", # Dark Forest Green
                    
                    "Average": "#eab308",        # Solid Yellow
                    "Average ↑ (Improving)": "#fef08a", # Pale Bright Yellow
                    "Average ↓ (Declining)": "#78350f", # Dark Muddy Brown
                    
                    "At-Risk (Promotion)": "#f43f5e",                 # Solid Rose
                    "At-Risk (Promotion) ↑ (Improving)": "#fda4af",   # Light Rose Pink
                    "At-Risk (Promotion) ↓ (Declining)": "#9f1239",   # Dark Rose
                    
                    "Critical (Action Req.)": "#9333ea",              # Solid Purple
                    "Critical (Action Req.) ↑ (Improving)": "#d8b4fe",# Bright Lilac
                    "Critical (Action Req.) ↓ (Declining)": "#581c87",# Deep Purple
                    
                    "Non-Promoted (Failed)": "#ef4444",               # Pure Red
                    "Non-Promoted (Failed) ↑ (Improving)": "#fca5a5", # Bright Light Red
                    "Non-Promoted (Failed) ↓ (Declining)": "#7f1d1d", # Near-Black Red
                    
                    "Readd": "#b91c1c",         # Darker Red
                    "Readd ↑ (Improving)": "#f87171",
                    "Readd ↓ (Declining)": "#450a0a"
                }

                # Filter the color map to only include active legends
                active_domains = []
                active_ranges = []
                for k, v in color_map.items():
                    if k in clust_df['Archetype'].values:
                        active_domains.append(k)
                        active_ranges.append(v)

                danger_archetypes = [a for a in active_domains if "Readd" in a or "Non-Promoted" in a]
                
                base_scatter = alt.Chart(clust_df).mark_circle(size=250).encode(
                    x=alt.X(f'{x_col}:Q', title=x_title, 
                            axis=alt.Axis(grid=True),
                            scale=alt.Scale(domain=[clust_df[x_col].min()-0.1, clust_df[x_col].max()+0.1])),
                    y=alt.Y('sgpa:Q', title='Semester GPA (SGPA)', 
                            scale=alt.Scale(domain=[clust_df['sgpa'].min()-0.2, 4.1])),
                    color=alt.Color('Archetype:N', 
                                   scale=alt.Scale(domain=active_domains, range=active_ranges),
                                   legend=alt.Legend(orient="bottom", columns=2, titleLimit=0, labelLimit=0),
                                   title='Status & Trend'),
                    opacity=alt.condition(
                        alt.FieldOneOfPredicate(field='Archetype', oneOf=danger_archetypes),
                        alt.value(0.0),
                        alt.value(1.0)
                    ),
                    tooltip=['name', alt.Tooltip('reg_no:N', title='Reg No'), 'Archetype',
                             alt.Tooltip('sgpa:Q', format='.2f', title='Current SGPA'),
                             alt.Tooltip('cgpa:Q', format='.2f', title='Historical Average'),
                             alt.Tooltip(f'{x_col}:Q', format='.2f', title=x_title)]
                )
                
                df_danger = clust_df[clust_df['Archetype'].isin(danger_archetypes)]
                if not df_danger.empty:
                    danger_overlay = alt.Chart(df_danger).mark_text(text='⛔', size=18).encode(
                        x=f'{x_col}:Q', y='sgpa:Q',
                        tooltip=['name', alt.Tooltip('reg_no:N', title='Reg No'), 'Archetype',
                                 alt.Tooltip('sgpa:Q', format='.2f', title='Current SGPA'),
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
                            size=700, color='transparent', stroke='#fbbf24', strokeWidth=3
                        ).encode(x=f'{x_col}:Q', y='sgpa:Q')
                        scatter = scatter + spot_overlay
                
                # Add a vertical zero-line for clarity in momentum mode
                final_chart = scatter
                if not is_first_sem:
                    v_line = alt.Chart(pd.DataFrame({'x': [0]})).mark_rule(color='gray', strokeDash=[5,5]).encode(x='x')
                    final_chart = v_line + scatter
                
                st.altair_chart(final_chart, use_container_width=True)
                caption = "🚀 **Right of center**: Improving performance | 🏛️ **Top Quadrant**: Excellence" if not is_first_sem else "🏛️ **Top Quadrant**: Excellence | 🎯 **Specialists**: Identified by subject variance."
                st.caption(caption)
                
                # Mobile-Friendly Companion Data Table
                with st.expander("🗃️ View Quadrant Data Matrix (Tap-Free)"):
                    st_view_df = clust_df[['reg_no', 'name', 'sgpa', 'cgpa', 'Archetype']].sort_values('sgpa', ascending=False)
                    st_view_df = st_view_df.rename(columns={'reg_no': 'Reg', 'name': 'Name', 'sgpa': 'SGPA', 'cgpa': 'CGPA', 'Archetype': 'Status'})
                    st.dataframe(st_view_df, use_container_width=True, hide_index=True)
            else:
                st.info("Not enough students for clustering (need ≥4 with complete subject data).")
        else:
            st.info("No pivot data available.")

    with col_m2:
        st.markdown("#### 🤝 Subject Dependency Heatmap")
        if not df_pivot.empty and len(selected_subjects) > 1:
            corr_matrix = df_pivot.corr()
            corr_matrix.index.name   = 'Subject A'
            corr_matrix.columns.name = 'Subject B'
            corr_flat = corr_matrix.stack().reset_index()
            corr_flat.columns = ['Subject A', 'Subject B', 'Correlation']
            heatmap = alt.Chart(corr_flat).mark_rect().encode(
                x=alt.X('Subject A:N', axis=alt.Axis(labelAngle=-45)),
                y='Subject B:N',
                color=alt.Color('Correlation:Q', scale=alt.Scale(scheme='redblue', domain=[-1, 1]), legend=alt.Legend(orient="bottom", title="Correlation", gradientLength=200, titleLimit=0)),
                tooltip=['Subject A', 'Subject B', alt.Tooltip('Correlation:Q', format='.2f')]
            ).properties(height=400, width='container')
            st.altair_chart(heatmap, use_container_width=True)
        else:
            st.info("Select ≥2 subjects for the correlation heatmap.")

# =========================================================================
# TAB 3: PIVOT VIEW
# =========================================================================
with tabs[2]:
    st.subheader("🌀 Interactive Pivot Dimension")
    pivot_type = st.radio(
        "Cube Rotation:",
        ["Show Breakdown per Student", "Show Summary per Subject"],
        horizontal=True
    )
    if not df_pivot.empty:
        if "Student" in pivot_type:
            st.dataframe(df_pivot.fillna("—"), use_container_width=True)
        else:
            flipped = df_sub.pivot_table(
                index='subject_code', columns='reg_no', values='gp', aggfunc='first'
            )
            st.dataframe(flipped.fillna("—"), use_container_width=True)
    else:
        st.info("No data to pivot.")

# =========================================================================
# TAB 4: CLEARING LIST
# =========================================================================
with tabs[3]:
    st.subheader("🏆 Semester-End Clearing List")
    st.markdown("Track eligibility for improvements and retakes after this semester's main exam.")

    csv = df_main.to_csv(index=False).encode('utf-8')
    st.download_button(
        "📥 Export Clearing List",
        csv,
        f"clearing_list_{profile_name}_{exam_id}.csv",
        "text/csv"
    )

    disp_cols = ['reg_no', 'name', 'sgpa', 'cgpa', 'result_status', 'improvement_count', 'retake_count']
    disp_df = df_main.sort_values('cgpa', ascending=False).reset_index(drop=True)
    st.dataframe(disp_df[disp_cols], use_container_width=True)

ui.add_contact_section()
