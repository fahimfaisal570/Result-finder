---
id: TASK-001
title: Fix Unicode + load real data from DB
status: pending
dependencies: []
complexity: medium
agent: claude
---

## Description

Rewrite `analyze_features.py` so it:
1. Uses only ASCII printable characters in all print() calls (no Unicode symbols).
2. Loads training data correctly from the live SQLite database by:
   - Calling `db.get_profiles()` to iterate all profiles
   - For each profile, querying the raw exam records per student using
     `db.get_connection()` to query `exam_results` + `subject_grades`
   - Calling `db.compute_deep_analysis(raw_records, profile_name, latest_exam_label)`
     to produce the deep result dict keyed as `{profile_name}_{reg_no}_{sess_id}`
   - Passing the resulting `deep_cache` to `ml_predictor.build_training_data()`
3. Bails out cleanly (no traceback) if fewer than 10 training samples are found.
4. Sets `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')`
   at the top so output works cross-platform.

## Acceptance Criteria

- [ ] `python analyze_features.py` exits with code 0 (or prints an early-exit message and exits 0)
- [ ] No UnicodeEncodeError on a Windows CP-1252 terminal
- [ ] Dataset shape line prints with real sample count
