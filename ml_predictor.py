import numpy as np
import pandas as pd
import re
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.neighbors import KNeighborsRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import database as db

def parse_semester_from_name(exam_name: str) -> int:
    """Parses semester number (1-8) from exam name."""
    if not exam_name:
        return 0
    ename_lower = str(exam_name).lower()
    
    # Filter out retakes
    RETAKE_KEYWORDS = ["retake", "re-take", "improvement", "special", "make-up", "makeup", "supplementary"]
    if any(kw in ename_lower for kw in RETAKE_KEYWORDS):
        return 0
        
    SEM_PATTERN = re.compile(
        r'(\d+(?:st|nd|rd|th)\s+year\s+\d+(?:st|nd|rd|th)\s+semester)',
        re.IGNORECASE
    )
    m = SEM_PATTERN.search(ename_lower)
    sem_label = m.group(1).title().strip() if m else ename_lower.title().strip()
    
    yr_match = re.search(r'(\d)[a-z]{2}\s*Yr', sem_label, re.IGNORECASE)
    sem_match = re.search(r'(\d)[a-z]{2}\s*Sem', sem_label, re.IGNORECASE)
    if not yr_match:
        yr_match = re.search(r'(\d)[a-z]{2}\s*Year', sem_label, re.IGNORECASE)
    if not sem_match:
        sem_match = re.search(r'(\d)[a-z]{2}\s*Semester', sem_label, re.IGNORECASE)
        
    if yr_match and sem_match:
        yr = int(yr_match.group(1))
        sem_in_yr = int(sem_match.group(1))
        if sem_in_yr > 2:
            return sem_in_yr
        else:
            return (yr - 1) * 2 + sem_in_yr
    elif sem_match:
        return int(sem_match.group(1))
    return 0

def get_dept_semester_averages(dept: str, exclude_profile: str) -> dict[int, float]:
    """Computes average GPA for semesters 1-8 across other profiles in the same department."""
    dept_lower = dept.strip().lower()
    averages = {}
    gpas_by_sem = {i: [] for i in range(1, 9)}
    
    try:
        with db.get_connection() as conn:
            cur = conn.execute("""
                SELECT profile_name, exam_name, gpa
                FROM exam_results
                WHERE gpa > 0.0
            """)
            rows = cur.fetchall()
            
            for profile_name, exam_name, gpa in rows:
                if profile_name.lower() == exclude_profile.lower():
                    continue
                if not profile_name.lower().startswith(dept_lower):
                    continue
                
                sem_num = parse_semester_from_name(exam_name)
                if 1 <= sem_num <= 8:
                    gpas_by_sem[sem_num].append(gpa)
                    
        for sem, gpas in gpas_by_sem.items():
            if gpas:
                averages[sem] = float(np.mean(gpas))
            else:
                averages[sem] = 3.00  # Default fallback
    except Exception:
        pass
        
    # Fill in any missing semesters with default
    for sem in range(1, 9):
        if sem not in averages:
            averages[sem] = 3.00
            
    return averages

def compute_backlog_history(effective_grades: dict, dept: str, current_semester: int) -> dict[int, int]:
    """
    Computes the backlog count at the start of each semester (1 to current_semester).
    A subject is considered a backlog at the start of semester t if:
      - It belongs to semesters 1..t-1
      - The student's grade point at the end of semester t-1 was < 2.0
    """
    backlogs_at_start = {sem: 0 for sem in range(1, current_semester + 2)}
    
    # We group courses by their semester
    courses_by_sem = {}
    for code, g in effective_grades.items():
        sem = db.get_semester_from_code(code, dept)
        if sem <= 0:
            continue
        if sem not in courses_by_sem:
            courses_by_sem[sem] = []
        courses_by_sem[sem].append((code, g['gp'], g.get('exam_id'), g.get('source')))
        
    main_exam_ids = {}
    for sem, courses in courses_by_sem.items():
        main_ids = [int(eid) for _, _, eid, src in courses if src == 'main' and eid]
        if main_ids:
            main_exam_ids[sem] = max(main_ids)
            
    for t in range(2, current_semester + 2):
        backlog_count = 0
        # Check all courses in semesters 1..t-1
        for sem in range(1, t):
            for code, final_gp, final_eid, source in courses_by_sem.get(sem, []):
                if final_gp < 2.0:
                    backlog_count += 1
                elif source != 'main' and final_eid:
                    try:
                        final_eid_int = int(final_eid)
                    except ValueError:
                        final_eid_int = 0
                    
                    t_minus_1_eid = main_exam_ids.get(t - 1)
                    if t_minus_1_eid and final_eid_int > t_minus_1_eid:
                        backlog_count += 1
        backlogs_at_start[t] = backlog_count
        
    return backlogs_at_start

def engineer_features(
    gpa_history: list[float],
    credits_history: list[float],
    backlogs_history: list[int],
    batch_sem_averages: dict[int, float],
    target_sem: int
) -> np.ndarray:
    """
    Constructs a fixed-width feature vector representing the student's history up to target_sem.
    """
    # 1. Last GPA
    last_gpa = gpa_history[-1] if gpa_history else 0.0
    
    # 2. Prior CGPA (credit-weighted)
    total_points = sum(g * c for g, c in zip(gpa_history, credits_history))
    total_credits = sum(credits_history)
    prior_cgpa = total_points / total_credits if total_credits > 0 else 0.0
    
    # 3. GPA Momentum
    gpa_momentum = last_gpa - prior_cgpa
    
    # 4. Semester Difficulty Index (batch average for target_sem)
    difficulty = batch_sem_averages.get(target_sem, 3.00)
    
    # 5. Backlog Count at the start of target_sem
    backlog_count = backlogs_history[-1] if backlogs_history else 0
    
    return np.array([
        last_gpa,
        prior_cgpa,
        gpa_momentum,
        difficulty,
        float(backlog_count),
        float(target_sem)
    ], dtype=np.float32)

def build_training_data(
    deep_cache: dict,
    profile_name: str,
    dept: str
) -> tuple[np.ndarray, np.ndarray, dict[int, float]]:
    """
    Builds the training dataset from the deep cache of all students in the batch.
    """
    X_list = []
    y_list = []
    
    # First, let's extract each student's semester breakdown
    student_histories = {}
    for key, deep_result in deep_cache.items():
        if not key.startswith(f"{profile_name}_") or deep_result is None:
            continue
            
        effective_grades = deep_result.get("effective_grades", {})
        current_semester = deep_result.get("current_semester", 0)
        official_records = deep_result.get("official_semester_records", {})
        
        if current_semester < 2:
            continue
            
        breakdown = db.compute_per_semester_breakdown(
            effective_grades=effective_grades,
            dept=dept,
            current_semester=current_semester,
            official_records=official_records
        )
        
        backlog_history = compute_backlog_history(effective_grades, dept, current_semester)
        
        student_histories[key] = {
            'breakdown': breakdown,
            'backlogs': backlog_history
        }
        
    # Compute batch average GPAs for each semester
    batch_sem_gpas = {i: [] for i in range(1, 9)}
    for key, history in student_histories.items():
        for sem in history['breakdown']:
            sem_num = sem['semester']
            gpa = sem['computed_gpa']
            if 1 <= sem_num <= 8:
                batch_sem_gpas[sem_num].append(gpa)
                
    batch_sem_averages = {}
    dept_averages = get_dept_semester_averages(dept, profile_name)
    
    for sem in range(1, 9):
        if batch_sem_gpas[sem]:
            batch_sem_averages[sem] = float(np.mean(batch_sem_gpas[sem]))
        else:
            batch_sem_averages[sem] = dept_averages.get(sem, 3.00)
            
    # Now build the training samples using a sliding window
    for key, history in student_histories.items():
        breakdown = history['breakdown']
        backlogs = history['backlogs']
        
        gpas = [sem['computed_gpa'] for sem in breakdown]
        credits = [sem['credits'] for sem in breakdown]
        
        K = len(breakdown)
        for t in range(2, K + 1):
            sub_gpas = gpas[:t-1]
            sub_credits = credits[:t-1]
            sub_backlogs = [backlogs[i] for i in range(1, t)]
            
            features = engineer_features(sub_gpas, sub_credits, sub_backlogs, batch_sem_averages, t)
            target = gpas[t-1]
            
            X_list.append(features)
            y_list.append(target)
            
    if not X_list:
        return np.empty((0, 6)), np.empty((0,)), batch_sem_averages
        
    return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.float32), batch_sem_averages

def train_ensemble(X: np.ndarray, y: np.ndarray) -> list[dict]:
    """
    Trains 6 models and computes cross-validation metrics.
    """
    models_config = [
        ("Linear Regression", LinearRegression()),
        ("Ridge Regression", Ridge(alpha=1.0)),
        ("Lasso Regression", Lasso(alpha=0.01)),
        ("Random Forest", RandomForestRegressor(n_estimators=50, max_depth=5, random_state=42)),
        ("Gradient Boosting", GradientBoostingRegressor(n_estimators=50, max_depth=3, random_state=42)),
        ("KNN Regressor", KNeighborsRegressor(n_neighbors=min(5, max(2, len(X) // 10)) if len(X) > 0 else 5))
    ]
    
    trained_models = []
    num_samples = len(X)
    folds = min(5, num_samples) if num_samples >= 2 else 2
    
    for name, model in models_config:
        if num_samples > 0:
            model.fit(X, y)
            
        cv_maes = []
        cv_rmses = []
        cv_r2s = []
        
        if num_samples >= 5:
            indices = np.arange(num_samples)
            np.random.seed(42)
            np.random.shuffle(indices)
            splits = np.array_split(indices, folds)
            
            for i in range(folds):
                test_idx = splits[i]
                train_idx = np.setdiff1d(indices, test_idx)
                
                if len(train_idx) == 0 or len(test_idx) == 0:
                    continue
                    
                X_tr, y_tr = X[train_idx], y[train_idx]
                X_te, y_te = X[test_idx], y[test_idx]
                
                from sklearn.base import clone
                temp_model = clone(model)
                temp_model.fit(X_tr, y_tr)
                preds = temp_model.predict(X_te)
                
                cv_maes.append(mean_absolute_error(y_te, preds))
                cv_rmses.append(np.sqrt(mean_squared_error(y_te, preds)))
                try:
                    cv_r2s.append(r2_score(y_te, preds))
                except Exception:
                    cv_r2s.append(0.0)
                    
            mae = float(np.mean(cv_maes)) if cv_maes else 0.0
            rmse = float(np.mean(cv_rmses)) if cv_rmses else 0.0
            r2 = float(np.mean(cv_r2s)) if cv_r2s else 0.0
        else:
            if num_samples > 0:
                preds = model.predict(X)
                mae = mean_absolute_error(y, preds)
                rmse = np.sqrt(mean_squared_error(y, preds))
                try:
                    r2 = r2_score(y, preds)
                except Exception:
                    r2 = 0.0
            else:
                mae, rmse, r2 = 0.0, 0.0, 0.0
                
        trained_models.append({
            'name': name,
            'model': model,
            'mae': mae,
            'rmse': rmse,
            'r2': r2
        })
        
    return trained_models

def forecast_to_graduation(
    models: list[dict],
    completed_gpas: list[float],
    completed_credits: list[float],
    completed_backlogs: list[int],
    batch_sem_averages: dict[int, float],
    start_sem: int,
    total_sems: int = 8
) -> dict:
    """
    Recursively forecasts GPAs for all remaining semesters up to graduation.
    """
    gpas = list(completed_gpas)
    credits = list(completed_credits)
    backlogs = list(completed_backlogs)
    
    model_forecasts = {m['name']: {} for m in models}
    ensemble_forecast = {}
    
    weights = []
    for m in models:
        mae = m['mae']
        w = 1.0 / (mae + 1e-4)
        weights.append(w)
    total_w = sum(weights)
    weights = [w / total_w for w in weights]
    
    current_gpas = list(gpas)
    current_backlogs = list(backlogs)
    
    for target_sem in range(start_sem, total_sems + 1):
        features = engineer_features(current_gpas, credits[:target_sem-1], current_backlogs, batch_sem_averages, target_sem)
        
        preds = []
        for idx, m_dict in enumerate(models):
            m = m_dict['model']
            p = float(m.predict(features.reshape(1, -1))[0])
            p = float(np.clip(p, 0.0, 4.0))
            model_forecasts[m_dict['name']][target_sem] = p
            preds.append(p)
            
        ens_p = sum(p * w for p, w in zip(preds, weights))
        ens_p = float(np.clip(ens_p, 0.0, 4.0))
        ensemble_forecast[target_sem] = ens_p
        
        current_gpas.append(ens_p)
        current_backlogs.append(0)
        
    return {
        'ensemble_forecast': ensemble_forecast,
        'model_forecasts': model_forecasts
    }
