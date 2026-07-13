---
id: TASK-008
title: Implement Method 1 Semester-Specific Models
status: pending
dependencies: [TASK-007]
complexity: medium
agent: claude
---

## Description
Write logic in `analyze_features_v2.py` that partitions the dataset by target semester (2..8) and trains/evaluates separate model ensembles for each target semester, using only the features appropriate for that semester.
For example, predicting target_sem=3 will use features constructed up to semester 2.
