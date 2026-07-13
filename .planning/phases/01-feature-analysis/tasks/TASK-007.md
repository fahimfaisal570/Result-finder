---
id: TASK-007
title: Implement Method 2 & 3 Feature Engineering
status: pending
dependencies: []
complexity: medium
agent: claude
---

## Description
Write code in `analyze_features_v2.py` to extract:
1. Lag features: `gpa_lag1` (most recent), `gpa_lag2`, `gpa_lag3`. Fill missing lags with overall student's prior GPA or baseline (3.0).
2. Volatility: standard deviation of all available past GPAs.
3. Trend slope: linear regression slope (or simple diff if fewer than 3 semesters) of past GPAs.
4. Weighted decay GPA: exponential/linear decay giving more weight to recent semesters (e.g., weights: [0.6, 0.3, 0.1]).
