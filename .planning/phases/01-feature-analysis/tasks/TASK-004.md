---
id: TASK-004
title: Single-feature drop-one ablation
status: pending
dependencies: [TASK-003]
complexity: medium
agent: claude
---

## Description

Ensure `single_feature_ablation()` correctly:
- Runs `evaluate_subset()` for each of 6 drop-one feature combinations
- Computes delta = (subset MAE) - (baseline MAE)
- Sorts by delta ascending (most improvement first)
- Verdicts: "DROP" (delta<0), "EQUAL" (delta==0), "KEEP" (delta>0)
- Prints an ASCII table with columns: Dropped | MAE | RMSE | R2 | dMAE | dRMSE | dR2 | Verdict

## Acceptance Criteria

- [ ] Ablation table prints with exactly 6 rows
- [ ] Verdict column present and correct
- [ ] No Unicode arrows or symbols
