import streamlit as st
import pandas as pd
import sys
import os
import json

# Setup page config and essential UI
st.set_page_config(page_title="Pending Retake & Improvement Finder", page_icon="favicon.ico", layout="wide")

# Add parent dir for database import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
import ui_components as ui

ui.inject_essential_ui()

st.page_link("app.py", label="← Back to Dashboard", icon=":material/arrow_back:")
st.title("Pending Retake & Improvement Finder")
st.markdown("Filter students across department batches with uncleared retakes or eligible improvements.")

profiles = db.get_profiles()
if not profiles:
    st.warning("No saved profiles found. Please scan or import profiles first.")
    st.stop()

# --- Sidebar Controls ---
st.sidebar.header("Filter Criteria")

# 1. Department Selection
dept = st.sidebar.selectbox("Select Department:", ["CSE", "EEE", "Civil"])

# Find matching profiles for department
matching_profiles = [
    p for p in profiles.keys()
    if db.get_dept_from_profile(p).upper() == dept.upper()
]

if not matching_profiles:
    st.info(f"No profiles found for department {dept}.")
    st.stop()

st.sidebar.caption(f"Batches in {dept}: {', '.join(sorted(matching_profiles))}")

# 2. Semester Selection (Single Select)
SEMESTER_MAP = {
    1: "1st Year 1st Semester",
    2: "1st Year 2nd Semester",
    3: "2nd Year 1st Semester",
    4: "2nd Year 2nd Semester",
    5: "3rd Year 1st Semester",
    6: "3rd Year 2nd Semester",
    7: "4th Year 1st Semester",
    8: "4th Year 2nd Semester",
}

selected_sem_label = st.sidebar.selectbox(
    "Select Semester:",
    options=list(SEMESTER_MAP.values())
)

selected_sem_num = [num for num, label in SEMESTER_MAP.items() if label == selected_sem_label][0]
selected_sem_nums = [selected_sem_num]

# 3. Optional Course Code Filter
credit_map = getattr(db, "_credit_map", {})
dept_credit_map = credit_map.get(dept, {})
all_courses = set()

if isinstance(dept_credit_map, dict):
    for code in dept_credit_map.keys():
        if db.get_semester_from_code(code, dept) == selected_sem_num:
            all_courses.add(code)

all_courses = sorted(list(all_courses))
selected_courses = st.sidebar.multiselect(
    "Select Specific Courses (Optional):",
    options=all_courses,
    help="Leave empty to search all courses in the selected semester."
)

st.sidebar.divider()

# 4. Criteria Type Filter
criteria_type = st.sidebar.radio(
    "Filter Criteria Type:",
    ["All Pending (Retakes & Improvements)", "Pending Retakes Only (GP < 2.0)", "Improvement Candidates Only (2.0 ≤ GP ≤ 2.75)"]
)

# 5. Special Retake Filter
special_filter = st.sidebar.radio(
    "Special Retake Status:",
    ["All", "Normal Only", "Special Retake Only"]
)

btn_find = st.sidebar.button("Find Students", type="primary")

# Execute Search
if btn_find or "pending_finder_results" in st.session_state:
    if btn_find:
        st.session_state.pending_finder_results = None

        if not selected_sem_nums:
            st.warning("Please select at least one semester.")
            st.stop()

        results = []
        special_lookup = db.build_special_exam_lookup(dept)

        # Count total students across matching profiles
        total_students = sum(len(profiles[p].get('regs', [])) for p in matching_profiles)
        progress_bar = st.progress(0, text=f"Analyzing {total_students} students across {len(matching_profiles)} batches...")
        scanned_count = 0

        for p_name in sorted(matching_profiles):
            batch_first_years = db.get_batch_first_participation_years(p_name)
            student_list = profiles[p_name].get('regs', [])

            for reg_no, sess_id, name in student_list:
                scanned_count += 1
                progress_bar.progress(
                    scanned_count / total_students if total_students else 1.0,
                    text=f"Analyzing [{scanned_count}/{total_students}]: {name} ({reg_no})"
                )

                raw_recs = db.get_student_raw_records_from_db(p_name, reg_no)
                if not raw_recs:
                    continue

                deep_res = db.compute_deep_analysis(raw_recs, p_name, "4th Yr 2nd Sem")
                if not deep_res:
                    continue

                adv_proj = db.compute_advanced_projection(
                    deep_result=deep_res,
                    effective_grades=deep_res.get('effective_grades', {}),
                    retake_records=deep_res.get('retake_records', []),
                    profile_name=p_name,
                    special_exam_lookup=special_lookup,
                    batch_first_years=batch_first_years,
                )

                # Process pending retakes
                if "Improvements" not in criteria_type:
                    for pr in adv_proj.get('pending_retakes', []):
                        sem_num = pr.get('semester', 0)
                        code = pr.get('code', '')
                        is_special = pr.get('is_special', False)

                        if sem_num in selected_sem_nums:
                            if not selected_courses or code in selected_courses:
                                if special_filter == "All" or (special_filter == "Special Retake Only" and is_special) or (special_filter == "Normal Only" and not is_special):
                                    results.append({
                                        "Student Name": name,
                                        "Registration": reg_no,
                                        "Original Session": sess_id or "AUTO",
                                        "Batch": p_name,
                                        "Subject Code": code,
                                        "Subject Name": pr.get('name', ''),
                                        "Current GP": round(float(pr.get('current_gp', 0.0)), 2),
                                        "Type": "Pending Retake (Failing)",
                                        "Special Retake?": "Yes" if is_special else "No",
                                        "Semester": SEMESTER_MAP.get(sem_num, f"Semester {sem_num}")
                                    })

                # Process improvement candidates
                if "Retakes Only" not in criteria_type:
                    for ic in adv_proj.get('improvement_candidates', []):
                        sem_num = ic.get('semester', 0)
                        code = ic.get('code', '')
                        is_special = ic.get('is_special', False)

                        if sem_num in selected_sem_nums:
                            if not selected_courses or code in selected_courses:
                                if special_filter == "All" or (special_filter == "Special Retake Only" and is_special) or (special_filter == "Normal Only" and not is_special):
                                    results.append({
                                        "Student Name": name,
                                        "Registration": reg_no,
                                        "Original Session": sess_id or "AUTO",
                                        "Batch": p_name,
                                        "Subject Code": code,
                                        "Subject Name": ic.get('name', ''),
                                        "Current GP": round(float(ic.get('current_gp', 0.0)), 2),
                                        "Type": "Improvement Candidate",
                                        "Special Retake?": "Yes" if is_special else "No",
                                        "Semester": SEMESTER_MAP.get(sem_num, f"Semester {sem_num}")
                                    })

        progress_bar.empty()
        st.session_state.pending_finder_results = pd.DataFrame(results)

    df_results = st.session_state.pending_finder_results

    if df_results is None or df_results.empty:
        st.success("🎉 No students found matching the selected criteria!")
    else:
        # Display Metrics Summary
        m1, m2, m3, m4 = st.columns(4)
        unique_students = df_results["Registration"].nunique()
        total_items = len(df_results)
        retakes_cnt = len(df_results[df_results["Type"].str.contains("Retake")])
        improvements_cnt = len(df_results[df_results["Type"].str.contains("Improvement")])

        m1.metric("Matching Students", unique_students)
        m2.metric("Total Pending Items", total_items)
        m3.metric("Pending Retakes (Fail)", retakes_cnt)
        m4.metric("Improvement Eligible", improvements_cnt)

        st.divider()

        # Download & Table view
        col_hdr, col_dl = st.columns([3, 1])
        col_hdr.subheader(f"Found {len(df_results)} Record(s)")

        csv_data = df_results.to_csv(index=False).encode('utf-8')
        col_dl.download_button(
            label="📥 Download CSV Report",
            data=csv_data,
            file_name=f"{dept}_pending_retakes_report.csv",
            mime="text/csv",
            type="primary"
        )

        st.dataframe(
            df_results,
            use_container_width=True,
            hide_index=True
        )
