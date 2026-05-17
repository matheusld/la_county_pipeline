# Claude vs GPT Scoring Comparison

**Research question:** Bridging LA County care-first governance with AI/tech governance

**Date:** 2026-05-12

## 1. Coverage

| | Count |
|---|---|
| Claude scored | 7,425 |
| GPT scored | 7,265 |
| Shared (same doc_id) | 6,988 |
| Only in Claude | 437 |
| Only in GPT | 277 |

## 2. Tier Distribution

### All docs (each scorer's full set)

| Tier | Claude | GPT |
|---|---|---|
| T1 | 223 | 71 |
| T2 | 1,333 | 650 |
| T3 | 4,255 | 4,032 |
| T4 | 1,614 | 2,512 |

### Shared docs only

| Tier | Claude | GPT |
|---|---|---|
| T1 | 215 | 71 |
| T2 | 1,276 | 634 |
| T3 | 4,028 | 3,868 |
| T4 | 1,469 | 2,415 |

## 3. Tier Agreement (shared docs)

| | Count | % |
|---|---|---|
| Same tier | 3,404 | 48.7% |
| Claude higher tier (lower #) | 2,548 | 36.5% |
| GPT higher tier (lower #) | 1,036 | 14.8% |

## 4. Composite Score Statistics (shared docs)

| Metric | Claude | GPT |
|---|---|---|
| Mean | 2.351 | 1.791 |
| Median | 2.05 | 1.35 |
| Min | 0.0 | 0.0 |
| Max | 9.5 | 8.4 |
| Pearson r (composite) | 0.3222 | — |

## 5. Per-dimension Mean (shared docs)

| Dimension | Claude mean | GPT mean | Delta |
|---|---|---|---|
| carefirst | 1.857 | 2.084 | -0.227 |
| ai_governance | 2.451 | 0.882 | +1.568 |
| intersection | 1.635 | 0.742 | +0.893 |
| evidentiary | 4.675 | 5.261 | -0.587 |

## 6. Biggest Scoring Divergences

### Claude scored much higher than GPT (top 10 by Δ composite)

| Filename | Claude | GPT | Δ |
|---|---|---|---|
| 2020-03-31_144967_DHS_REPORT_08-1665_144967.pdf | 8.15 | 0.3 | +7.85 |
| 2023-11-07_185772_Revised_motion_by_Supervisors_Horvath_and_ | 8.4 | 0.75 | +7.65 |
| 2025-06-17_204142_Motion_by_Supervisor_Solis_25-3371_204142. | 7.9 | 0.45 | +7.45 |
| 2022-01-25_1-25-22_Board_Meeting_Transcript_1118909.pdf | 7.75 | 0.45 | +7.30 |
| 2021-02-09_153603_Presentation_19-7713_153603.pdf | 7.65 | 0.45 | +7.20 |
| 2023-02-07_177455_Board_Letter_23-0499_177455.pdf | 7.6 | 0.45 | +7.15 |
| 2026-03-17_213493_Board_Letter_26-1481_213493.pdf | 9.5 | 2.45 | +7.05 |
| 2026-02-12_Youre_The_Chair_-_Com_Networking_Summit_-_2-12-20 | 7.6 | 0.6 | +7.00 |
| 2022-11-29_175329_Public_CommentCorrespondence_11-1977_17532 | 7.4 | 0.45 | +6.95 |
| 2023-02-28_178395_Report_23-0881_178395.pdf | 7.85 | 0.9 | +6.95 |

### GPT scored much higher than Claude (top 10 by Δ composite)

| Filename | Claude | GPT | Δ |
|---|---|---|---|
| 2025-08-05_Statement_of_Proceedings_for_852025_1190262.pdf | 0.75 | 6.5 | -5.75 |
| 2024-09-10_194927_Board_Letter_24-3614_194927.pdf | 1.6 | 7.3 | -5.70 |
| 2025-12-02_210125_Motion_by_Supervisor_Horvath_Updates_Follo | 0.75 | 6.3 | -5.55 |
| 2025-12-02_209790_Board_Letter_25-6383_209790.pdf | 1.3 | 6.7 | -5.40 |
| 2020-08-04_147911_Report_8420_20-3985_147911.pdf | 0.15 | 5.3 | -5.15 |
| 2024-08-06_194022_Prevention_and_Promotion_Systems_Governing | 2.25 | 7.35 | -5.10 |
| 2025-05-06_Statement_of_Proceedings_for_562025_1184402.pdf | 1.4 | 6.5 | -5.10 |
| 2021-07-13_160101_Report_71321_21-2832_160101.pdf | 1.75 | 6.8 | -5.05 |
| 2024-09-10_194928_Board_Letter_24-3615_194928.pdf | 1.9 | 6.95 | -5.05 |
| 2025-12-02_209784_Board_Letter_25-6391_209784.pdf | 0.45 | 5.5 | -5.05 |

## 7. Tier Upgrades / Downgrades

- **Claude assigned a higher tier** (lower number) than GPT for **2,548** shared docs.
- **GPT assigned a higher tier** than Claude for **1,036** shared docs.

#### Sample — Claude upgraded vs GPT

| Filename | Claude tier | GPT tier |
|---|---|---|
| 2020-03-31_144967_DHS_REPORT_08-1665_144967.pdf | T1 | T4 |
| 2023-11-07_185772_Revised_motion_by_Supervisors_Horvath_and_Solis_23-4 | T1 | T4 |
| 2025-06-17_204142_Motion_by_Supervisor_Solis_25-3371_204142.pdf | T1 | T4 |
| 2022-01-25_1-25-22_Board_Meeting_Transcript_1118909.pdf | T1 | T4 |
| 2021-02-09_153603_Presentation_19-7713_153603.pdf | T1 | T4 |

#### Sample — GPT upgraded vs Claude

| Filename | Claude tier | GPT tier |
|---|---|---|
| 2025-08-05_Statement_of_Proceedings_for_852025_1190262.pdf | T4 | T1 |
| 2024-09-10_194927_Board_Letter_24-3614_194927.pdf | T3 | T1 |
| 2025-12-02_210125_Motion_by_Supervisor_Horvath_Updates_Following_Clust | T4 | T1 |
| 2025-12-02_209790_Board_Letter_25-6383_209790.pdf | T3 | T1 |
| 2020-08-04_147911_Report_8420_20-3985_147911.pdf | T4 | T2 |

## 8. Docs Unique to Each Run

Files scored **only by Claude** (437):
- 2023-07-11_182157_Board_Letter_23-2490_182157.pdf
- 2024-06-04_191867_Board_Letter_24-2015_191867.pdf
- 2026-02-17_213057_Justice_Care_and_Opportunities_26-1240_213057.pdf
- DO_SH_25043665_1_Redacted.pdf
- 2021-05-18_158024_BL_DPW_21-1805_158024.pdf
- *(+432 more)*

Files scored **only by GPT** (277):
- 2024-08-06_194157_Public_CommentCorrespondence_24-3271_194157.pdf
- 2020-05-12_145643_ORDA_20-2492_145643.pdf
- 2020-05-26_05-26-20_Board_Meeting_Transcript_C_1072917.pdf
- 2025-11-18_209365_Board_Letter_25-6120_209365.pdf
- 2024-03-19_189672_Revised_motion_by_Supervisors_Solis_and_Hahn_24-0991_189672.pdf
- *(+272 more)*

---
*Outputs: `comparison/compare_detail.jsonl` (per-doc diff), `comparison/compare_tier_diff.csv` (tier changes)*