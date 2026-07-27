"""
research/explainer.py — Explanation Output & Confidence Scoring Layer
Provides human-readable, research-grade decision logic and uncertainty/confidence scores for all system inference.
"""

import numpy as np
from research.config import THRESHOLDS

def explain_readd_classification(
    candidate_subjects: set[str],
    reference_subjects: set[str],
    candidate_count: int,
    reference_count: int
) -> dict:
    """Explains re-admission detection logic and returns confidence metrics."""
    if not reference_subjects:
        return {
            "is_readd": False,
            "confidence": 0.0,
            "reason": "Reference subject fingerprint empty or missing.",
            "metrics": {"overlap_ratio": 0.0, "load_ratio": 0.0}
        }
        
    overlap = candidate_subjects & reference_subjects
    overlap_ratio = len(overlap) / len(reference_subjects)
    load_ratio = candidate_count / reference_count if reference_count > 0 else 0.0

    min_overlap = THRESHOLDS.get("readd_overlap_min", 0.50)
    min_load = THRESHOLDS.get("readd_load_min", 0.70)

    is_readd = (overlap_ratio >= min_overlap) and (load_ratio >= min_load)
    
    # Confidence is calculated as normalized distance above/below decision boundary
    boundary_score = (overlap_ratio / min_overlap + load_ratio / min_load) / 2.0
    confidence = float(np.clip(boundary_score / 1.5, 0.40, 0.99)) if is_readd else float(np.clip(1.0 - boundary_score, 0.40, 0.99))

    reason = (
        f"Passed dual-filter ({overlap_ratio:.0%} overlap >= {min_overlap:.0%}, {load_ratio:.0%} load >= {min_load:.0%})."
        if is_readd else
        f"Filtered out as guest/ghost ({overlap_ratio:.0%} overlap, {load_ratio:.0%} load)."
    )

    return {
        "is_readd": is_readd,
        "confidence": round(confidence, 4),
        "reason": reason,
        "metrics": {
            "overlap_ratio": round(overlap_ratio, 4),
            "load_ratio": round(load_ratio, 4),
            "overlap_count": len(overlap),
            "reference_count": len(reference_subjects)
        }
    }

def explain_prediction(prediction_result: dict | None) -> dict:
    """Explains GPA forecasting decision breakdown."""
    if not prediction_result:
        return {"explainable": False, "reason": "Insufficient historical semester records (< 2)."}
        
    slope = prediction_result.get("trend_slope", 0.0)
    conf = prediction_result.get("prediction_confidence", 0.8)
    margin = prediction_result.get("confidence_margin", 0.2)
    
    trend_desc = "improving trajectory" if slope > 0.05 else ("declining trajectory" if slope < -0.05 else "stable trajectory")
    
    return {
        "explainable": True,
        "predicted_grad_cgpa": prediction_result.get("predicted_grad_cgpa"),
        "confidence_score": conf,
        "confidence_95_margin": margin,
        "reason": f"Model identified a {trend_desc} (slope={slope:+.4f}) across {prediction_result.get('semesters_completed')} semesters using a 50/50 linear+EMA blend.",
        "breakdown": {
            "trend_slope": slope,
            "semesters_completed": prediction_result.get("semesters_completed"),
            "predictions_by_semester": prediction_result.get("predictions")
        }
    }

def explain_academic_state(state: str, cgpa: float, promo_target: float | None = None) -> dict:
    """Explains student academic state taxonomy classification."""
    reasons = {
        "regular": "Student is on normal academic track with no failed/retake flags.",
        "readmitted": "Student detected as re-admitted from a senior batch via subject fingerprinting.",
        "at_risk": f"Student CGPA ({cgpa:.2f}) falls below promotion requirement threshold ({promo_target:.2f}).",
        "high_performer": f"Student CGPA ({cgpa:.2f}) meets or exceeds high performer threshold (3.75).",
        "declining": "Student shows a significant negative GPA trajectory over consecutive semesters.",
        "retake_candidate": "Student has active retake subjects pending clearance.",
        "stable": "Student performance remains steady within a +/-0.05 CGPA band."
    }
    return {
        "academic_state": state,
        "cgpa": cgpa,
        "promo_target": promo_target,
        "explanation": reasons.get(state, f"Classified as {state}.")
    }
