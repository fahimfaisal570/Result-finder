import streamlit as st
import pandas as pd
import sys
import os

# Setup page config and essential UI
st.set_page_config(page_title="Pending Retake & Improvement Finder", page_icon="favicon.ico", layout="wide")

# Add parent dir for database import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
import ui_components as ui
import cli_scraper as cs

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

# Short labels understood by compute_deep_analysis (e.g. "2nd Yr 1st Sem")
_EXAM_LABEL_MAP = {
    1: "1st Yr 1st Sem",
    2: "1st Yr 2nd Sem",
    3: "2nd Yr 1st Sem",
    4: "2nd Yr 2nd Sem",
    5: "3rd Yr 1st Sem",
    6: "3rd Yr 2nd Sem",
    7: "4th Yr 1st Sem",
    8: "4th Yr 2nd Sem",
}

SEM_PATTERN_MAP = {
    1: "%1st year 1st semester%",
    2: "%1st year 2nd semester%",
    3: "%2nd year 1st semester%",
    4: "%2nd year 2nd semester%",
    5: "%3rd year 1st semester%",
    6: "%3rd year 2nd semester%",
    7: "%4th year 1st semester%",
    8: "%4th year 2nd semester%",
}

selected_sem_label = st.sidebar.selectbox(
    "Select Semester:",
    options=list(SEMESTER_MAP.values())
)

selected_sem_num = [num for num, label in SEMESTER_MAP.items() if label == selected_sem_label][0]
selected_sem_nums = [selected_sem_num]
selected_exam_label = _EXAM_LABEL_MAP[selected_sem_num]

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
    ["Retake", "Improvement", "All"],
    index=2
)

# 5. Special Retake Filter
special_filter = st.sidebar.radio(
    "Special Retake Status:",
    ["Special", "Normal", "All"],
    index=2
)

btn_find = st.sidebar.button("Find Students", type="primary")

RETAKE_KEYWORDS = ['retake', 're-take', 'improvement', 'special', 'make-up', 'makeup', 'supplementary', 'short']


# Execute Search
if btn_find or "pending_finder_results" in st.session_state:
    if btn_find:
        st.session_state.pending_finder_results = None

        if not selected_sem_nums:
            st.warning("Please select at least one semester.")
            st.stop()

        results = []
        with st.status(f"🔍 Searching {dept} — {selected_sem_label}...", expanded=True) as status_box:
            status_box.write("Step 1/4: Locating eligible department batches...")
            special_lookup = db.build_special_exam_lookup(dept)

            # STAGE 1: Find eligible batches that have taken the main exam for the selected semester
            sem_pattern = SEM_PATTERN_MAP[selected_sem_num]
            eligible_batches = []

            with db.get_connection() as conn:
                placeholders = ",".join(["?"] * len(matching_profiles))
                query = f"""
                    SELECT DISTINCT er.profile_name
                    FROM exam_results er
                    WHERE er.profile_name IN ({placeholders})
                      AND LOWER(er.exam_name) LIKE ?
                      AND LOWER(er.exam_name) NOT LIKE '%retake%'
                      AND LOWER(er.exam_name) NOT LIKE '%re-take%'
                      AND LOWER(er.exam_name) NOT LIKE '%improvement%'
                      AND LOWER(er.exam_name) NOT LIKE '%special%'
                      AND LOWER(er.exam_name) NOT LIKE '%make-up%'
                      AND LOWER(er.exam_name) NOT LIKE '%makeup%'
                      AND LOWER(er.exam_name) NOT LIKE '%supplementary%'
                """
                params = list(matching_profiles) + [sem_pattern]
                rows = conn.execute(query, params).fetchall()
                eligible_batches = [r[0] for r in rows]

            if not eligible_batches:
                status_box.update(label="No main exam records found.", state="complete", expanded=False)
                st.info(f"No scanned main exam records found for {selected_sem_label} in {dept}.")
                st.stop()

            # Build semester course list for Stage 2 SQL filter.
            target_course_codes = selected_courses

            # Pre-load batch first participation years
            batch_first_years_map = {
                b: db.get_batch_first_participation_years(b) for b in eligible_batches
            }

            # Improvement window guard
            sem_key = f"{(selected_sem_num - 1) // 2 + 1}-{1 if selected_sem_num % 2 == 1 else 2}"
            improvement_years = special_lookup.get(sem_key, [])
            latest_impr_year = max(improvement_years) if improvement_years else 0
            improvement_eligible_batches = set(
                b for b in eligible_batches
                if (first_yr := batch_first_years_map[b].get(selected_sem_num)) is not None
                and (not latest_impr_year or latest_impr_year - first_yr <= 2)
            ) if criteria_type != "Retake" else set(eligible_batches)

            # Stage 2 GP threshold
            if criteria_type == "Retake":
                gp_filter = "sg.grade_point < 2.0"
            elif criteria_type == "Improvement":
                gp_filter = "sg.grade_point BETWEEN 2.0 AND 2.75"
            else:  # All
                gp_filter = "sg.grade_point <= 2.75"

            # STAGE 2: Filter candidate students
            status_box.write("Step 2/4: Querying candidate student records...")
            candidates = []
            with db.get_connection() as conn:
                b_placeholders = ",".join(["?"] * len(eligible_batches))
                
                if target_course_codes:
                    c_placeholders = ",".join(["?"] * len(target_course_codes))
                    sql_candidates = f"""
                        SELECT DISTINCT sg.profile_name, sg.reg_no, s.name, s.sess_id
                        FROM subject_grades sg
                        JOIN exam_results er ON sg.profile_name = er.profile_name 
                          AND sg.reg_no = er.reg_no AND sg.exam_id = er.exam_id
                        JOIN students s ON sg.profile_name = s.profile_name AND sg.reg_no = s.reg_no
                        WHERE sg.profile_name IN ({b_placeholders})
                          AND {gp_filter}
                          AND sg.subject_code IN ({c_placeholders})
                          AND LOWER(er.exam_name) NOT LIKE '%retake%'
                          AND LOWER(er.exam_name) NOT LIKE '%re-take%'
                          AND LOWER(er.exam_name) NOT LIKE '%improvement%'
                          AND LOWER(er.exam_name) NOT LIKE '%special%'
                          AND LOWER(er.exam_name) NOT LIKE '%make-up%'
                          AND LOWER(er.exam_name) NOT LIKE '%makeup%'
                          AND LOWER(er.exam_name) NOT LIKE '%supplementary%'
                        ORDER BY sg.profile_name DESC, sg.reg_no ASC
                    """
                    sql_params = list(eligible_batches) + list(target_course_codes)
                else:
                    sql_candidates = f"""
                        SELECT DISTINCT sg.profile_name, sg.reg_no, s.name, s.sess_id
                        FROM subject_grades sg
                        JOIN exam_results er ON sg.profile_name = er.profile_name 
                          AND sg.reg_no = er.reg_no AND sg.exam_id = er.exam_id
                        JOIN students s ON sg.profile_name = s.profile_name AND sg.reg_no = s.reg_no
                        WHERE sg.profile_name IN ({b_placeholders})
                          AND {gp_filter}
                          AND LOWER(er.exam_name) LIKE ?
                          AND LOWER(er.exam_name) NOT LIKE '%retake%'
                          AND LOWER(er.exam_name) NOT LIKE '%re-take%'
                          AND LOWER(er.exam_name) NOT LIKE '%improvement%'
                          AND LOWER(er.exam_name) NOT LIKE '%special%'
                          AND LOWER(er.exam_name) NOT LIKE '%make-up%'
                          AND LOWER(er.exam_name) NOT LIKE '%makeup%'
                          AND LOWER(er.exam_name) NOT LIKE '%supplementary%'
                        ORDER BY sg.profile_name DESC, sg.reg_no ASC
                    """
                    sql_params = list(eligible_batches) + [sem_pattern]

                candidates = conn.execute(sql_candidates, sql_params).fetchall()

            if not candidates:
                status_box.update(label="No candidates found.", state="complete", expanded=False)
                st.success("🎉 No candidate students with low grades found in the selected criteria!")
                st.stop()

            # STAGE 3: Fast-load exam schedules & build portal tasks
            status_box.write(f"Step 3/4: Checking portal exam schedules for {len(candidates)} candidate student(s)...")
            candidate_tasks = []
            seen_reg = set()
            pro_exams_cache = {}

            for p_name, reg_no, name, sess_id in candidates:
                reg_int = int(reg_no)
                if reg_int in seen_reg:
                    continue
                seen_reg.add(reg_int)

                stu_sess = sess_id or "AUTO"
                p_data = profiles.get(p_name, {})
                pro_id = p_data.get("pro_id", "")
                if not pro_id:
                    continue

                if pro_id not in pro_exams_cache:
                    # Fetch full portal exam list (cached hourly) merged with local DB exams
                    portal_exams = cs.fetch_exams(pro_id) or {}
                    db_exams = db.get_profile_known_exams(p_name)
                    merged = dict(portal_exams)
                    merged.update(db_exams)
                    pro_exams_cache[pro_id] = merged
                p_exams = pro_exams_cache[pro_id]

                if not p_exams:
                    continue

                existing_recs = db.get_student_raw_records_from_db(p_name, reg_int)
                existing_eids = set(str(r.get('_exam_id')) for r in existing_recs)

                min_main_eid = 0
                for r in existing_recs:
                    ename = r.get('_exam_name', '')
                    if not any(kw in ename.lower() for kw in RETAKE_KEYWORDS):
                        try:
                            eid_val = int(r.get('_exam_id', 0))
                            if min_main_eid == 0 or eid_val < min_main_eid:
                                min_main_eid = eid_val
                        except (ValueError, TypeError):
                            pass

                missing_eids = []
                for eid, ename in p_exams.items():
                    if str(eid) in existing_eids:
                        continue

                    try:
                        if min_main_eid > 0 and int(eid) < min_main_eid:
                            continue
                    except ValueError:
                        pass

                    missing_eids.append(eid)

                for eid in missing_eids:
                    candidate_tasks.append((reg_int, stu_sess, eid, p_name, pro_id))

            if candidate_tasks:
                status_box.write(f"Verifying {len(candidate_tasks)} exam results on portal...")
                tasks_by_profile = {}
                for reg_int, stu_sess, eid, p_name, pro_id in candidate_tasks:
                    key = (p_name, pro_id)
                    if key not in tasks_by_profile:
                        tasks_by_profile[key] = []
                    tasks_by_profile[key].append((reg_int, stu_sess, eid))

                total_candidate_tasks = len(candidate_tasks)
                completed_overall = [0]

                progress_bar = st.progress(
                    0.0,
                    text=f"Verifying retake/special exam results on portal (0/{total_candidate_tasks} tasks)..."
                )

                for (p_name, pro_id), t_list in tasks_by_profile.items():
                    p_exams = pro_exams_cache.get(pro_id) or cs.fetch_exams(pro_id) or {}

                    def make_progress_cb(batch_p_name, offset):
                        def cb(current, total, status_text=None):
                            done = offset + current
                            pct = min(1.0, max(0.0, done / total_candidate_tasks))
                            progress_bar.progress(
                                pct,
                                text=f"Checking retake portal for {batch_p_name} ({done}/{total_candidate_tasks} tasks)..."
                            )
                        return cb

                    batch_history = cs.run_batch_scan_engine(
                        tasks=t_list,
                        pro_id=pro_id,
                        exam_id="0",
                        all_sessions={"0": ""},
                        progress_callback=make_progress_cb(p_name, completed_overall[0]),
                        num_threads=30
                    )
                    completed_overall[0] += len(t_list)

                    for rec in (batch_history or []):
                        eid = rec.get('_exam_id')
                        reg_val = rec.get('Registration No') or rec.get('reg_no')
                        try:
                            r_int = int(reg_val)
                            if eid and rec:
                                db.upsert_exam_result(
                                    profile_name=p_name,
                                    res=rec,
                                    exam_id=str(eid),
                                    exam_name=p_exams.get(eid, ''),
                                    sess_id=rec.get('sess_id', 'AUTO')
                                )
                        except (ValueError, TypeError):
                            pass

                progress_bar.empty()

            # STAGE 4: Compute deep analysis on complete history
            status_box.write("Step 4/4: Analysing student academic histories & CGPA projections...")
            unique_candidates = []
            seen_reg_pre = set()
            for row in candidates:
                r = int(row[1])
                if r not in seen_reg_pre:
                    seen_reg_pre.add(r)
                    unique_candidates.append(row)

            analysis_bar = st.progress(
                0.0,
                text=f"Analysing student history (0/{len(unique_candidates)})..."
            )
            seen_reg = set()
            for idx, (p_name, reg_no, name, sess_id) in enumerate(unique_candidates, start=1):
                analysis_bar.progress(
                    min(1.0, idx / max(len(unique_candidates), 1)),
                    text=f"Analysing {name} ({idx}/{len(unique_candidates)})..."
                )
                reg_int = int(reg_no)
                if reg_int in seen_reg:
                    continue
                seen_reg.add(reg_int)

                raw_recs = db.get_student_raw_records_from_db(p_name, reg_int)
                if not raw_recs:
                    continue

                deep_res = db.compute_deep_analysis(raw_recs, p_name, selected_exam_label)
                if not deep_res:
                    continue

                adv_proj = db.compute_advanced_projection(
                    deep_result=deep_res,
                    effective_grades=deep_res.get('effective_grades', {}),
                    retake_records=deep_res.get('retake_records', []),
                    profile_name=p_name,
                    special_exam_lookup=special_lookup,
                    batch_first_years=batch_first_years_map.get(p_name, {}),
                )

                # Process pending retakes (GP < 2.0)
                if criteria_type != "Improvement":
                    for pr in adv_proj.get('pending_retakes', []):
                        sem_num = pr.get('semester', 0)
                        code = pr.get('code', '')
                        is_special = pr.get('is_special', False)

                        if sem_num in selected_sem_nums:
                            if not selected_courses or code in selected_courses:
                                if special_filter == "All" or (special_filter == "Special" and is_special) or (special_filter == "Normal" and not is_special):
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

                # Process improvement candidates (2.0 <= GP <= 2.75)
                if criteria_type != "Retake" and p_name in improvement_eligible_batches:
                    for ic in adv_proj.get('improvement_candidates', []):
                        sem_num = ic.get('semester', 0)
                        code = ic.get('code', '')
                        is_special = ic.get('is_special', False)

                        if sem_num in selected_sem_nums:
                            if not selected_courses or code in selected_courses:
                                if special_filter == "All" or (special_filter == "Special" and is_special) or (special_filter == "Normal" and not is_special):
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

            analysis_bar.empty()
            status_box.update(label="✅ Search completed!", state="complete", expanded=False)

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
            width="stretch",
            hide_index=True
        )
