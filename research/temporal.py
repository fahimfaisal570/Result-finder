"""
research/temporal.py — Temporal Analysis Layer
Time-series analytics for semester-over-semester GPA deltas, subject difficulty drift, retake recovery, and cohort shifts.
"""

import pandas as pd
import numpy as np
from research.dataset import get_research_dataframe

def compute_semester_gpa_deltas(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Computes semester-over-semester GPA change per student."""
    if df is None:
        df = get_research_dataframe()
    if df.empty:
        return pd.DataFrame()

    df_sorted = df.sort_values(["anon_student_id", "semester"])
    df_sorted["prev_gpa"] = df_sorted.groupby("anon_student_id")["actual_outcome"].shift(1)
    df_sorted["gpa_delta"] = df_sorted["actual_outcome"] - df_sorted["prev_gpa"]
    return df_sorted[["anon_student_id", "department", "semester", "actual_outcome", "prev_gpa", "gpa_delta"]].dropna()

def compute_subject_difficulty_drift(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Computes mean grade point and failure rate per subject across sessions/semesters."""
    if df is None:
        df = get_research_dataframe()
    if df.empty:
        return pd.DataFrame()

    grouped = df.groupby(["department", "subject_code"]).agg(
        student_count=("grade_point", "count"),
        mean_grade_point=("grade_point", "mean"),
        std_grade_point=("grade_point", "std"),
        fail_rate=("grade_point", lambda x: (x == 0.0).sum() / len(x))
    ).reset_index()
    
    # Subject difficulty index: lower mean grade point + higher fail rate = higher difficulty
    grouped["difficulty_index"] = round((4.0 - grouped["mean_grade_point"]) + (grouped["fail_rate"] * 2.0), 2)
    return grouped.sort_values("difficulty_index", ascending=False)

def compute_cohort_trend_shifts(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Computes cohort-level average GPA and variance by semester."""
    if df is None:
        df = get_research_dataframe()
    if df.empty:
        return pd.DataFrame()

    return df.groupby(["department", "session", "semester"]).agg(
        cohort_size=("actual_outcome", "count"),
        mean_gpa=("actual_outcome", "mean"),
        median_gpa=("actual_outcome", "median"),
        std_gpa=("actual_outcome", "std")
    ).reset_index()

def compute_retake_recovery_delta(df: pd.DataFrame | None = None) -> dict:
    """Measures average GPA recovery after retaking a failed or low-grade subject."""
    if df is None:
        df = get_research_dataframe()
    if df.empty:
        return {"avg_recovery_delta": 0.0, "sample_size": 0}

    retakes = df[df["retake_flag"] == 1]
    if retakes.empty:
        return {"avg_recovery_delta": 0.0, "sample_size": 0}

    avg_grade_retake = retakes["grade_point"].mean()
    # Baseline assumption: initial failed grade was 0.0 or < 2.0
    return {
        "avg_recovery_delta": round(float(avg_grade_retake - 0.0), 2),
        "post_retake_mean_gp": round(float(avg_grade_retake), 2),
        "sample_size": len(retakes)
    }
