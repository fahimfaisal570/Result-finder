# Phase 01 Plan 02 Summary — Sequence-Aware Methods without PyTorch

**Dataset:** 2,345 training samples across 14 profiles  
**Script:** `analyze_features_v2.py`  
**Status:** COMPLETE

---

## Performance Comparison

| Model Configuration | Ensemble MAE | Performance Change |
|--------------------|--------------|-------------------|
| **1. Baseline (Old 6 features)** | **0.2516** | Baseline (0.0%) |
| **2. Advanced Features + Lags** | **0.2532** | -0.64% MAE (Worse) |
| **3. Per-Semester Models** | **0.2615** | -3.93% MAE (Worse) |

---

## Verdict & Key Findings

1. **Overfitting on Small Data:** 
   Splitting models by target semester (Method 1) reduced the sample sizes significantly (e.g., Sem 8 got only 99 samples). Smaller sample sizes made the individual ensembles perform *worse* than a single global ensemble that learns across all semesters using the `target_sem` feature.
   
2. **Lag Features Added Noise:** 
   Adding lag GPAs, volatility, and trend slopes (Method 2 & 3) slightly increased error compared to the simpler `last_gpa` and `prior_cgpa` features.
   
3. **ponytail constraint (Keep it Simple):**
   The baseline 6-feature global model remains the most optimal and robust architecture.
