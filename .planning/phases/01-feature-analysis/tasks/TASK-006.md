---
id: TASK-006
title: Summary recommendation block
status: pending
dependencies: [TASK-005]
complexity: low
agent: claude
---

## Description

Final section: print a clear ASCII recommendation:
1. Features where DROPPING improved accuracy (delta MAE < 0) -> "Consider removing"
2. Features critical to keep (delta MAE > 0.005 when dropped) -> "Keep"
3. Best overall subset name + its MAE/R2 vs baseline

Also print whether any feature subset beats the full-6-feature baseline.

## Acceptance Criteria

- [ ] Summary block clearly labels DROP candidates and KEEP-critical features
- [ ] Baseline comparison is explicit ("Best subset beats baseline by X MAE" or "Baseline is already optimal")
- [ ] Script exits 0 after printing summary
