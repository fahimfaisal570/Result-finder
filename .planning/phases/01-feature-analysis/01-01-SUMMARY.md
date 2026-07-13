# Phase 01 Summary — ML Feature Importance & Ablation Study

**Dataset:** 2,345 training samples across 14 profiles  
**Script:** `analyze_features.py`  
**Status:** COMPLETE — all 6 tasks done

---

## Results

### Baseline (all 6 features)
| MAE   | RMSE   | R²     |
|-------|--------|--------|
| 0.253 | 0.3472 | 0.3827 |

---

### Feature Importance Ranking

| Rank | Feature       | Corr   | MDI    | Permutation | Verdict  |
|------|---------------|--------|--------|-------------|----------|
| 1    | last_gpa      | 0.6306 | 0.7111 | 0.1761      | CRITICAL |
| 2    | difficulty    | 0.3629 | 0.1629 | 0.0490      | CRITICAL |
| 3    | prior_cgpa    | 0.5610 | 0.0673 | 0.0151      | Keep     |
| 4    | gpa_momentum  | 0.3113 | 0.0301 | 0.0060      | DROP     |
| 5    | target_sem    | 0.2826 | 0.0219 | 0.0065      | DROP     |
| 6    | backlog_count | 0.3496 | 0.0067 | 0.0017      | DROP*    |

*backlog_count: DROP by ablation but improves accuracy when paired with last_gpa+difficulty

---

### Single-Feature Ablation (drop-one CV)

| Dropped       | MAE    | dMAE    | dR²     | Verdict |
|---------------|--------|---------|---------|---------|
| gpa_momentum  | 0.2525 | -0.0005 | +0.0032 | DROP    |
| backlog_count | 0.2525 | -0.0005 | +0.0011 | DROP    |
| target_sem    | 0.2525 | -0.0005 | -0.0005 | DROP    |
| last_gpa      | 0.2532 | +0.0002 | -0.0011 | KEEP    |
| prior_cgpa    | 0.2533 | +0.0003 | +0.0004 | KEEP    |
| difficulty    | 0.2585 | +0.0055 | -0.0292 | **KEEP** |

---

### Best Feature Subset (Exhaustive Search)

**Winner: `last_gpa, difficulty, backlog_count` (size 3)**

| MAE    | RMSE   | R²     | vs Baseline         |
|--------|--------|--------|---------------------|
| 0.2513 | 0.3431 | 0.3978 | dMAE=-0.0017, dR²=+0.0151 |

This 3-feature subset **outperforms** the full 6-feature model.

---

## Recommendation

- **Drop:** `gpa_momentum`, `target_sem` (add noise, no benefit)
- **Drop (borderline):** `prior_cgpa` — minimal contribution but keeps context for low-semester students
- **`difficulty` is the single most impactful non-GPA feature** — dropping it costs 0.0055 MAE and -0.0292 R²
- **Optimal minimal set:** `last_gpa + difficulty + backlog_count`
