---
id: TASK-003
title: Permutation importance
status: pending
dependencies: [TASK-002]
complexity: low
agent: claude
---

## Description

Ensure `compute_permutation_importance()` runs via sklearn's
`permutation_importance` on a Random Forest trained on the full dataset,
with n_repeats=10. Results printed as ASCII table sorted by mean importance desc.
Std shown as "+/- X.XXXX" (no Unicode plusminus).

## Acceptance Criteria

- [ ] Permutation table appears with 6 rows (one per feature)
- [ ] No +/- Unicode character; use "+/-" instead
