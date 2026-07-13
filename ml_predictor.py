import numpy as np
import database as db

def predict_future_gpas(
    deep_result: dict,
    dept: str,
    total_sems: int = 8,
    overrides: dict | None = None
) -> dict | None:
    """
    Predicts remaining semester GPAs using the student's own adjusted GPA history.
    Requires >= 2 completed semesters in the deep cache.
    Returns None if insufficient data.
    
    Method: 50/50 blend of linear trend + exponential moving average.
    """
    if not deep_result:
        return None
        
    effective_grades = deep_result.get("effective_grades", {})
    current_semester = deep_result.get("current_semester", 0)
    official_records = deep_result.get("official_semester_records", {})
    
    if current_semester < 2:
        return None
    
    breakdown = db.compute_per_semester_breakdown(
        effective_grades=effective_grades,
        dept=dept,
        current_semester=current_semester,
        overrides=overrides,
        official_records=official_records
    )
    
    if len(breakdown) < 2:
        return None
    
    sem_nums = [s['semester'] for s in breakdown]
    gpas = [s['computed_gpa'] for s in breakdown]
    credits = [s['credits'] for s in breakdown]
    
    # Linear trend (polyfit)
    slope, intercept = np.polyfit(sem_nums, gpas, 1)
    
    # Exponential moving average (α=0.6, recency-biased)
    alpha = 0.6
    ema = gpas[0]
    for g in gpas[1:]:
        ema = alpha * g + (1 - alpha) * ema
    
    # Forecast remaining semesters
    predictions = {}
    last_ema = ema
    for target_sem in range(current_semester + 1, total_sems + 1):
        linear_pred = slope * target_sem + intercept
        # Simple step-wise EMA update for forecast
        last_ema = alpha * (predictions.get(target_sem - 1, gpas[-1])) + (1 - alpha) * last_ema
        blended = 0.5 * linear_pred + 0.5 * last_ema
        predictions[target_sem] = float(np.clip(blended, 0.0, 4.0))
    
    # Compute predicted graduation CGPA (credit-weighted)
    total_points = sum(g * c for g, c in zip(gpas, credits))
    total_credits = sum(credits)
    
    for sem_num, pred_gpa in predictions.items():
        sem_cr = db.get_semester_total_credits(dept, sem_num)
        if sem_cr <= 0:
            sem_cr = 20.0
        total_points += pred_gpa * sem_cr
        total_credits += sem_cr
    
    grad_cgpa = total_points / total_credits if total_credits > 0 else 0.0
    
    return {
        'predictions': predictions,          # {sem_num: predicted_gpa}
        'predicted_grad_cgpa': round(grad_cgpa, 2),
        'current_cgpa': deep_result.get('true_cgpa', 0.0),
        'trend_slope': round(slope, 4),      # positive = improving, negative = declining
        'semesters_completed': len(breakdown),
        'completed_gpas': gpas,
        'completed_sems': sem_nums,
    }
