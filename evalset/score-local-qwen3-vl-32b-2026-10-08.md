# Extraction score: local

Test set: evalset (30 notices, labels sha256 2705dba73def)
Model: local/Qwen/Qwen3-VL-32B-Instruct-FP8; prompt extract-v3; parser parse-v1

| Measure | Score |
|---|---|
| Facts found (recall) | 75% (67/89) |
| - event | 82% (41/50) |
| - deadline | 58% (11/19) |
| - form | 100% (7/7) |
| - payment | 100% (2/2) |
| - amendment | 55% (6/11) |
| Claims that match a labelled fact (precision) | 17% (67/403) |
| Actionable or not, per notice | 83% (25/30) |
| Notices with an expect_no violation | 2 of 15 |
| Claims grounded in the original | 96% (388/403) |

Field accuracy on matched facts:

| Field | Correct |
|---|---|
| amount | 67% (4/6) |
| date | 85% (44/52) |
| end_date | 78% (7/9) |
| form | 100% (11/11) |
| no_invented_date | 67% (2/3) |
| optional | 50% (3/6) |
| parent_attendance | 83% (5/6) |
| payment | 89% (8/9) |

What one notice hands a family:

| Measure | Score |
|---|---|
| Obligations proposed | 108 from 30 notices |
| Per notice | 3.6 (1.5 of them decisions) |
| Notices asking for more than 5 decisions | 1 of 30 |
| Worst single notice | 23 |

A task is a decision somebody has to make. A calendar note is a date they only
need to know. An accuracy table cannot show this, and it is what a family feels first.

| Notice | Found | Claims | Matched | Asks | Actionable (exp/pred) | expect_no violated |
|---|---|---|---|---|---|---|
| en-001 | 11/12 | 62 | 11 | 6 decide, 9 note | yes/yes | - |
| en-002 | 2/2 | 6 | 2 | 1 decide, 1 note | yes/yes | - |
| en-003 | 0/13 | 0 | 0 | 0 decide, 0 note | yes/no | - |
| en-004 | 1/2 | 8 | 1 | 2 decide, 0 note | yes/yes | - |
| en-005 | 1/1 | 1 | 1 | 1 decide, 0 note | yes/yes | - |
| en-007 | 1/1 | 5 | 1 | 5 decide, 0 note | yes/no | - |
| en-008 | 0/0 | 0 | 0 | 0 decide, 0 note | no/no | - |
| en-009 | 2/2 | 7 | 2 | 2 decide, 0 note | yes/yes | - |
| en-010 | 1/1 | 5 | 1 | 1 decide, 1 note | yes/yes | - |
| en-011 | 2/3 | 6 | 2 | 2 decide, 0 note | yes/yes | - |
| en-012 | 1/1 | 3 | 1 | 2 decide, 0 note | yes/yes | - |
| en-013 | 6/7 | 44 | 6 | 0 decide, 6 note | yes/yes | - |
| en-014 | 5/5 | 24 | 5 | 0 decide, 0 note | yes/yes | - |
| en-015 | 4/4 | 41 | 4 | 2 decide, 9 note | yes/yes | - |
| en-016 | 5/5 | 54 | 5 | 2 decide, 21 note | yes/yes | - |
| en-017 | 1/1 | 4 | 1 | 1 decide, 0 note | yes/yes | - |
| en-018 | 0/0 | 4 | 0 | 0 decide, 0 note | no/no | - |
| en-019 | 3/3 | 4 | 3 | 3 decide, 0 note | yes/yes | - |
| en-020 | 5/5 | 6 | 5 | 0 decide, 6 note | yes/yes | - |
| en-021 | 1/1 | 3 | 1 | 0 decide, 0 note | yes/yes | - |
| en-022 | 2/2 | 21 | 2 | 1 decide, 3 note | yes/yes | - |
| en-023 | 2/3 | 7 | 2 | 2 decide, 1 note | yes/yes | - |
| en-024 | 3/3 | 7 | 3 | 1 decide, 1 note | yes/yes | - |
| en-025 | 1/1 | 9 | 1 | 0 decide, 1 note | yes/yes | - |
| en-026 | 0/0 | 17 | 0 | 1 decide, 0 note | no/yes | deadline |
| en-027 | 1/1 | 17 | 1 | 2 decide, 2 note | yes/yes | event date |
| en-028 | 3/3 | 22 | 3 | 5 decide, 0 note | yes/yes | - |
| syn-med-001 | 0/2 | 5 | 0 | 0 decide, 0 note | yes/no | - |
| syn-bill-001 | 1/1 | 2 | 1 | 2 decide, 0 note | yes/yes | - |
| syn-travel-001 | 2/4 | 9 | 2 | 1 decide, 2 note | yes/no | - |

