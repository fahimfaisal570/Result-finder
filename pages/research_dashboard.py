import streamlit as st
import pandas as pd
import numpy as np
import os
import sys
import json
import altair as alt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ui_components as ui
import database as db

from research.run_experiments import run_all_experiments
from research.ablation import run_ablation_suite
from research.benchmark_manual import run_manual_benchmark
from research.error_analysis import analyze_system_errors
from research.temporal import compute_subject_difficulty_drift, compute_cohort_trend_shifts

st.set_page_config(page_title="Research & Benchmark Dashboard", page_icon="favicon.ico", layout="wide")
ui.inject_essential_ui()

st.page_link("app.py", label="← Back to Main Dashboard", icon=":material/arrow_back:")
st.title("🔬 Research & Evaluation Dashboard")
st.markdown("Quantitative evaluation, baseline comparisons, ablation deltas, and institutional benchmark metrics.")

# Trigger pipeline evaluation on demand
with st.sidebar:
    st.header("Research Controls")
    if st.button("🚀 Re-Run Evaluation Pipeline", use_container_width=True):
        with st.spinner("Executing experiment runner and ablation suite..."):
            run_all_experiments()
            run_ablation_suite()
            run_manual_benchmark()
            analyze_system_errors()
            st.success("Pipeline executed cleanly!")

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "results")

# Ensure results exist
exp_file = os.path.join(RESULTS_DIR, "experiment_results.json")
if not os.path.exists(exp_file):
    run_all_experiments(dry_run=True)
    run_ablation_suite()
    run_manual_benchmark()
    analyze_system_errors()

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Model Benchmarks", 
    "🧪 Ablation Studies", 
    "📈 Temporal & Difficulty Analytics", 
    "⏱️ Manual vs System Benchmarking", 
    "🔍 Diagnostic & Error Log"
])

# --- TAB 1: MODEL BENCHMARKS ---
with tab1:
    st.subheader("GPA Forecasting & Re-Admission Benchmark Summary")
    if os.path.exists(exp_file):
        with open(exp_file, "r", encoding="utf-8") as f:
            exp_data = json.load(f)
            
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### GPA Forecasting Baselines (Error Comparison)")
            fc_dict = exp_data.get("forecasting_benchmark", {})
            fc_df = pd.DataFrame.from_dict(fc_dict, orient="index").reset_index()
            fc_df.columns = ["Model", "MAE", "RMSE"]
            st.dataframe(fc_df, use_container_width=True)
            
            # Altair bar chart
            chart_data = fc_df.melt(id_vars=["Model"], value_vars=["MAE", "RMSE"], var_name="Metric", value_name="Error")
            c = alt.Chart(chart_data).mark_bar().encode(
                x=alt.X('Model:N', sort=None),
                y='Error:Q',
                color='Metric:N',
                column='Metric:N'
            ).properties(height=300)
            st.altair_chart(c, use_container_width=True)

        with col2:
            st.markdown("#### Re-Admission Classification Metrics")
            readd_dict = exp_data.get("readmission_benchmark", {})
            readd_df = pd.DataFrame.from_dict(readd_dict, orient="index").reset_index()
            readd_df.columns = ["Algorithm", "Precision", "Recall", "F1 Score"]
            st.dataframe(readd_df, use_container_width=True)

# --- TAB 2: ABLATION STUDIES ---
with tab2:
    st.subheader("Component Impact & Ablation Study")
    st.markdown("Quantifying performance degradation when individual subsystem components are disabled.")
    abl_file = os.path.join(RESULTS_DIR, "ablation_results.json")
    if os.path.exists(abl_file):
        with open(abl_file, "r", encoding="utf-8") as f:
            abl_data = json.load(f)
        abl_df = pd.DataFrame.from_dict(abl_data, orient="index").fillna("-")
        st.dataframe(abl_df, use_container_width=True)

# --- TAB 3: TEMPORAL ANALYTICS ---
with tab3:
    st.subheader("Subject Difficulty Drift & Cohort Dynamics")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Subject Difficulty Ranking")
        drift_df = compute_subject_difficulty_drift()
        if not drift_df.empty:
            st.dataframe(drift_df, use_container_width=True)
        else:
            st.info("Run a profile scan to generate subject difficulty indices.")
            
    with col2:
        st.markdown("#### Cohort Semester Trend Shifts")
        cohort_df = compute_cohort_trend_shifts()
        if not cohort_df.empty:
            st.dataframe(cohort_df, use_container_width=True)
        else:
            st.info("Run batch scans to view longitudinal cohort trends.")

# --- TAB 4: MANUAL BENCHMARKING ---
with tab4:
    st.subheader("Benchmarking Against Manual Workflow")
    man_file = os.path.join(RESULTS_DIR, "manual_benchmark.json")
    if os.path.exists(man_file):
        with open(man_file, "r", encoding="utf-8") as f:
            man_data = json.load(f)
            
        m1, m2, m3 = st.columns(3)
        m1.metric("Manual Hours Required", f"{man_data.get('overall_manual_hours')} hrs")
        m2.metric("System Hours Required", f"{man_data.get('overall_automated_hours')} hrs")
        m3.metric("Overall Speedup Factor", f"{man_data.get('overall_speedup_factor')}x")
        
        st.divider()
        st.markdown("#### Task-by-Task Efficiency Breakdown")
        tasks_df = pd.DataFrame(man_data.get("task_breakdown", []))
        st.dataframe(tasks_df, use_container_width=True)

# --- TAB 5: ERROR LOGS & ROBUSTNESS ---
with tab5:
    st.subheader("Error Analysis & Robustness Diagnostics")
    err_file = os.path.join(RESULTS_DIR, "error_report.json")
    rob_file = os.path.join(RESULTS_DIR, "robustness_report.json")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Failure Mode Distribution")
        if os.path.exists(err_file):
            with open(err_file, "r", encoding="utf-8") as f:
                err_data = json.load(f)
            st.json(err_data)
    with col2:
        st.markdown("#### Fault Tolerance & Stress Test Results")
        if os.path.exists(rob_file):
            with open(rob_file, "r", encoding="utf-8") as f:
                rob_data = json.load(f)
            st.json(rob_data)
