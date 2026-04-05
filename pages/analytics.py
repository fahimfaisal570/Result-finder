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

st.set_page_config(page_title="Result Analytics", page_icon="📊", layout="wide")
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

def get_performance_archetypes(df_pivot, n_clusters=4):
    if df_pivot.empty: return None
    data = df_pivot.dropna().copy()
    if len(data) < n_clusters: return None

    # Feature Engineering: Mean (Strength) and Variance (Consistency)
    features = pd.DataFrame(index=data.index)
    features['mean_gp'] = data.mean(axis=1)
    features['std_gp'] = data.std(axis=1).fillna(0)

    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(features)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(scaled_data)

    features['Cluster'] = clusters
    centroids = features.groupby('Cluster').mean()

    mapping = {}
    if len(centroids) == 4:
        sorted_by_mean = centroids.sort_values(by='mean_gp', ascending=False)
        top_tier    = sorted_by_mean.iloc[:2]
        bottom_tier = sorted_by_mean.iloc[2:]

        # Among top: high variance = Specialist
        if top_tier.iloc[0]['std_gp'] > top_tier.iloc[1]['std_gp']:
            specialist_id     = top_tier.index[0]
            consistent_high_id = top_tier.index[1]
        else:
            specialist_id     = top_tier.index[1]
            consistent_high_id = top_tier.index[0]

        # Among bottom: higher mean = Average, lower = Struggling
        average_id   = bottom_tier.index[0]
        struggling_id = bottom_tier.index[1]

        mapping = {
            consistent_high_id: 'Consistent High',
            specialist_id:      'Specialist (High Variance)',
            average_id:         'Medium / Average',
            struggling_id:      'Struggling / Below Avg'
        }
    else:
        mapping = {c: f"Cluster {c}" for c in centroids.index}

    features['Archetype'] = features['Cluster'].map(mapping)
    return features[['Archetype']]

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

# Connection Status Indicator
is_cloud = db.is_using_turso()
status_color = "#10b981" if is_cloud else "#3b82f6"
status_label = "Cloud (Turso)" if is_cloud else "Local (SQLite)"
st.sidebar.markdown(f"""
    <div style='padding: 10px; border-radius: 8px; background: rgba(128,128,128,0.1); border-left: 5px solid {status_color}; margin-bottom: 20px;'>
        <div style='font-size: 0.75rem; color: #858585; text-transform: uppercase;'>Storage Engine</div>
        <div style='font-weight: bold; color: {status_color};'>{status_label}</div>
    </div>
""", unsafe_allow_html=True)

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
st.sidebar.info("Analytics engine optimized for university graduation standards.")

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
df_sub  = df_sub_raw[df_sub_raw['subject_code'].isin(selected_subjects)].copy() if not df_sub_raw.empty else df_sub_raw
df_main = df_raw[(df_raw['cgpa'] >= cgpa_range[0]) & (df_raw['cgpa'] <= cgpa_range[1])].copy()

df_pivot = pd.DataFrame()
if not df_sub.empty:
    df_pivot = df_sub.pivot_table(index='reg_no', columns='subject_code', values='gp', aggfunc='first')

# ---------------------------------------------------------------------------
# Top-level metric strip
# ---------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Students (Filtered)", f"{len(df_main)}", f"{(len(df_main)/len(df_raw))*100:.1f}% of batch")
col2.metric("Subjects in View", len(selected_subjects))
avg_cgpa = df_main[df_main['cgpa'] > 0]['cgpa'].mean()
col3.metric("Avg CGPA (Filtered)", f"{avg_cgpa:.2f}" if not pd.isna(avg_cgpa) else "—")
avg_sgpa = df_main[df_main['sgpa'] > 0]['sgpa'].mean()
col4.metric("Avg SGPA (This Sem)", f"{avg_sgpa:.2f}" if not pd.isna(avg_sgpa) else "—")

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
        status_df = pd.DataFrame({
            'Status': ['Passed (1st Chance)', 'Failed (Any Subject)'],
            'Count':  [all_passed_count, has_failed_count]
        })
        pie = alt.Chart(status_df).mark_arc(innerRadius=60, outerRadius=100).encode(
            theta="Count:Q",
            color=alt.Color("Status:N", scale=alt.Scale(
                domain=['Passed (1st Chance)', 'Failed (Any Subject)'],
                range=['#10b981', '#ef4444']
            )),
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
        sub_avg = sub_avg.sort_values('gp')
        sub_avg['base_gp'] = 2.0
        bar = alt.Chart(sub_avg).mark_bar(color="#f59e0b", cornerRadiusEnd=4).encode(
            x=alt.X('gp:Q', title='Mean Grade Point (Pass Only)', scale=alt.Scale(domain=[2, 4])),
            x2='base_gp:Q',
            y=alt.Y('subject_code:N', sort='-x', title='Subject',
                    axis=alt.Axis(labelPadding=15, labelLimit=400)),
            tooltip=['subject_code', alt.Tooltip('gp:Q', format='.2f')]
        ).properties(height=max(250, len(sub_avg) * 40))
        st.altair_chart(bar, use_container_width=True)
        st.caption("Lower average GPA = systemic difficulty. Only passing grades (≥2.0) are averaged.")
    else:
        st.info("No subject data available.")

    st.divider()

    # Row 3: Achievement Gradient (rank vs CGPA)
    st.markdown("#### 📉 Achievement Gradient (Rank vs CGPA)")
    rank_df = df_main[df_main['cgpa'] > 0].sort_values('cgpa', ascending=False).copy()
    rank_df['Rank'] = range(1, len(rank_df) + 1)
    
    # Adaptive Y-axis to prevent 'distances taken too far'
    gpa_min = rank_df['cgpa'].min() if not rank_df.empty else 0.0
    y_start = max(0.0, float(gpa_min) - 0.2)
    
    line = alt.Chart(rank_df).mark_line(point=True, color="#8b5cf6").encode(
        x=alt.X('Rank:Q', title='Student Rank'),
        y=alt.Y('cgpa:Q', title='Cumulative GPA', scale=alt.Scale(domain=[y_start, 4.0], clamp=True)),
        tooltip=['name', alt.Tooltip('cgpa:Q', format='.2f'), 'Rank']
    ).properties(height=350)
    st.altair_chart(line, use_container_width=True)

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
        st.markdown("#### 👽 Performance Archetypes (Clustering)")
        if not df_pivot.empty:
            clusters = get_performance_archetypes(df_pivot)
            if clusters is not None:
                clust_df = df_main.merge(clusters, left_on='reg_no', right_index=True)
                
                # Dynamic Fallback: In 1st semester, CGPA is typically 0. Use SGPA instead.
                use_sgpa = clust_df['cgpa'].sum() == 0
                y_col = 'sgpa' if use_sgpa else 'cgpa'
                y_title = "Semester GPA (SGPA)" if use_sgpa else "Cumulative GPA"
                
                domain  = ['Consistent High', 'Specialist (High Variance)', 'Medium / Average', 'Struggling / Below Avg']
                
                scatter = alt.Chart(clust_df).mark_circle(size=120).encode(
                    x=alt.X('reg_no:N', axis=alt.Axis(labels=False), title='Students'),
                    y=alt.Y(f'{y_col}:Q', title=y_title, 
                            scale=alt.Scale(domain=[clust_df[y_col].min() - 0.2, 4.1] if not clust_df.empty else [0, 4.5])),
                    color=alt.Color('Archetype:N'),
                    tooltip=['name', 'Archetype',
                             alt.Tooltip('cgpa:Q', format='.2f', title='CGPA'),
                             alt.Tooltip('sgpa:Q', format='.2f', title='SGPA')]
                ).properties(height=400).interactive()
                st.altair_chart(scatter, use_container_width=True)
                if use_sgpa:
                    st.caption("ℹ️ Applied 1st-semester fallback: Visualizing distribution based on **SGPA**.")
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
                color=alt.Color('Correlation:Q', scale=alt.Scale(scheme='redblue', domain=[-1, 1])),
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
