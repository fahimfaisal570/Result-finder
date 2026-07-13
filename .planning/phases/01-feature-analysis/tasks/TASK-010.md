---
id: TASK-010
title: Update ml_predictor.py to use 3 features
status: pending
dependencies: []
complexity: low
agent: claude
---

## Description
Modify `ml_predictor.py`:
1. In `engineer_features`, return a `np.array` containing only `[last_gpa, difficulty, backlog_count]`.
2. In `build_training_data`, change default return value from `np.empty((0, 6))` to `np.empty((0, 3))`.
