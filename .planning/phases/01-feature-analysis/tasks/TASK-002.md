---
id: TASK-002
title: Pearson correlation + MDI importance tables
status: pending
dependencies: [TASK-001]
complexity: low
agent: claude
---

## Description

Ensure `compute_correlations()` and `compute_mdi_importance()` print
clean ASCII tables after the baseline block. Tables must have aligned
columns and no Unicode box-drawing characters.

## Acceptance Criteria

- [ ] Correlation table appears in output, sorted by |corr| descending
- [ ] MDI table appears in output, sorted by importance descending
- [ ] All column separators are ASCII dashes `-`
