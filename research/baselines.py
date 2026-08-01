"""
research/baselines.py — Baseline Comparison Framework
Provides 2-4 baseline methods for each core algorithmic component for comparative research evaluation.
"""

import numpy as np

# ---------------------------------------------------------------------------
# 1. GPA Forecasting Baselines
# ---------------------------------------------------------------------------

def forecast_last_value(gpas: list[float]) -> float:
    """Naive baseline: predict next semester GPA = last semester GPA."""
    if not gpas:
        return 0.0
    return float(np.clip(gpas[-1], 0.0, 4.0))

def forecast_moving_average(gpas: list[float], window: int = 3) -> float:
    """Moving average baseline over last N semesters."""
    if not gpas:
        return 0.0
    recent = gpas[-window:]
    return float(np.clip(np.mean(recent), 0.0, 4.0))

def forecast_ema_only(gpas: list[float], alpha: float = 0.6) -> float:
    """Exponential Moving Average (EMA) baseline without linear trend."""
    if not gpas:
        return 0.0
    ema = gpas[0]
    for g in gpas[1:]:
        ema = alpha * g + (1 - alpha) * ema
    return float(np.clip(ema, 0.0, 4.0))

import warnings

def forecast_linear_only(sem_nums: list[int], gpas: list[float], target_sem: int) -> float:
    """Linear regression trend baseline."""
    if len(gpas) < 2:
        return float(gpas[-1]) if gpas else 0.0
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', np.RankWarning)
        slope, intercept = np.polyfit(sem_nums, gpas, 1)
    pred = slope * target_sem + intercept
    return float(np.clip(pred, 0.0, 4.0))

def forecast_hybrid(sem_nums: list[int], gpas: list[float], target_sem: int, alpha: float = 0.6, blend: float = 0.5) -> float:
    """Full hybrid model: 50/50 blend of linear trend + EMA (matching ml_predictor.py)."""
    if len(gpas) < 2:
        return float(gpas[-1]) if gpas else 0.0
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', np.RankWarning)
        slope, intercept = np.polyfit(sem_nums, gpas, 1)
    linear_pred = slope * target_sem + intercept
    
    ema = gpas[0]
    for g in gpas[1:]:
        ema = alpha * g + (1 - alpha) * ema
        
    blended = blend * linear_pred + (1 - blend) * ema
    return float(np.clip(blended, 0.0, 4.0))



# ---------------------------------------------------------------------------
# 2. Re-Admission Detection Baselines
# ---------------------------------------------------------------------------

def detect_readd_simple_overlap(candidate_codes: set[str], reference_codes: set[str]) -> bool:
    """Baseline 1: Re-admitted if ANY subject overlaps."""
    return len(candidate_codes & reference_codes) > 0

def detect_readd_reg_matching(candidate_reg: int, existing_regs: set[int]) -> bool:
    """Baseline 2: Re-admitted if registration number matches an existing registry."""
    return candidate_reg in existing_regs

def detect_readd_fingerprinting(
    candidate_codes: set[str],
    reference_codes: set[str],
    candidate_count: int,
    reference_count: int,
    overlap_min: float = 0.50,
    load_min: float = 0.70
) -> bool:
    """Full method: Subject-overlap fingerprinting with dual filter."""
    if not reference_codes:
        return False
    overlap = candidate_codes & reference_codes
    overlap_ratio = len(overlap) / len(reference_codes)
    load_ratio = candidate_count / reference_count if reference_count > 0 else 0
    return overlap_ratio >= overlap_min and load_ratio >= load_min


# ---------------------------------------------------------------------------
# 3. CGPA Reconstruction Baselines
# ---------------------------------------------------------------------------

def cgpa_portal_raw(portal_cgpa: float | None) -> float:
    """Baseline 1: Portal provided raw CGPA."""
    return float(portal_cgpa) if portal_cgpa is not None else 0.0

def cgpa_naive_mean(gpas: list[float]) -> float:
    """Baseline 2: Unweighted mean of semester SGPAs."""
    if not gpas:
        return 0.0
    return float(np.mean(gpas))

def cgpa_credit_weighted(gpas: list[float], credits: list[float]) -> float:
    """Full method: True credit-weighted CGPA."""
    total_cr = sum(credits)
    if total_cr <= 0:
        return 0.0
    total_pts = sum(g * c for g, c in zip(gpas, credits))
    return float(total_pts / total_cr)
