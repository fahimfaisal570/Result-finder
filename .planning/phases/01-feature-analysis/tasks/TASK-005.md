---
id: TASK-005
title: Exhaustive subset search (sizes 2-5)
status: pending
dependencies: [TASK-004]
complexity: medium
agent: claude
---

## Description

Ensure `best_subset_search()`:
- Iterates all C(6,k) combinations for k in [2,3,4,5]
- Evaluates each subset with TimeSeriesSplit CV (same as baseline)
- Prints top-5 per size, sorted by MAE ascending
- Final line: best overall subset vs baseline (delta MAE, delta R2)

## Acceptance Criteria

- [ ] Subset search table prints for each size 2,3,4,5
- [ ] "Best overall subset" block at end compares vs baseline
- [ ] No Unicode in output
