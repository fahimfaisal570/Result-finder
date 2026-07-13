---
id: TASK-011
title: Update tests/test_ml_predictor.py
status: pending
dependencies: [TASK-010]
complexity: low
agent: claude
---

## Description
Modify `tests/test_ml_predictor.py`:
1. In `test_engineer_features_clipping`, assert `features.shape == (3,)` and assert the correct values matching the 3-feature array index mapping.
2. In `test_build_training_data_and_ensemble`, assert `X.shape[1] == 3`.
3. In `test_forecast_to_graduation`, scale the dummy data to shape `(10, 3)` instead of `(10, 6)`.
