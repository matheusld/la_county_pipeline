# IRR Analysis & Merged Scores

**Approach:** averaged composite scores (Claude + GPT) / 2, per-dimension averaging, human-review flag where |Δ composite| > 3.0.

## 1. Inter-Rater Reliability Statistics (shared docs, n=6,988)

| Statistic | Value | Interpretation |
|---|---|---|
| Cohen κ (unweighted, tiers) | 0.1327 | Slight |
| Cohen κ (quadratic-weighted) | 0.2500 | Fair |
| ICC(2,1) — composite scores | 0.2914 | Poor |
| Krippendorff α — composite | 0.2652 | Fair |
| Pearson r — composite | 0.3222 | — |

> **Note:** Unweighted κ remains slight while quadratic-weighted κ is fair, so exact tier matches are still fragile even though near-miss tier disagreement has improved. ICC and α remain low, reflecting residual dimension-level bias identified in the scoring comparison. Treat contested documents as requiring human review rather than as stable automated classifications.

## 2. Scatterplot

See [`irr_scatterplot.png`](irr_scatterplot.png) — composite score scatter and tier confusion matrix.

## 3. Resolution Strategy: Averaged Composites

For all **6,988 shared docs**, the merged composite is the arithmetic mean of Claude and GPT composites. Sub-dimension scores are also averaged. Tier is re-derived from the averaged composite using the standard formula.

- Docs flagged as **contested** (|Δ composite| > 3.0): **654**
- Docs unique to Claude (carried over as-is): **437**
- Docs unique to GPT (carried over as-is): **277**
- **Total merged corpus:** 7,702 docs

## 4. Sensitivity Analysis

Do conclusions change depending on which scorer's output is used?

### Tier distribution — shared docs only

| Tier | Claude-only | GPT-only | **Averaged** |
|---|---|---|---|
| T1 | 217 | 71 | **21** |
| T2 | 1,275 | 634 | **855** |
| T3 | 4,027 | 3,868 | **4,852** |
| T4 | 1,469 | 2,415 | **1,260** |

### Tier stability across versions

| Comparison | % same tier |
|---|---|
| Claude vs GPT | 48.7% |
| Claude vs Averaged | 74.5% |
| GPT vs Averaged | 66.9% |

### Agreement With Resolved Tiers

The **resolved tier** is the final tier assigned after combining both scorers' sub-scores. Two versions are shown: the averaged tier, based on simple averaged Claude/GPT scores, and the final clipped tier, which also applies the intersection ceiling. These statistics are **not** independent inter-rater reliability; they show how closely each scorer aligns with the tier used for the final review set.

| Comparison | Cohen κ | Quadratic κ | % same tier |
|---|---:|---:|---:|
| Claude vs GPT (raw IRR) | 0.1327 | 0.2500 | 48.7% |
| Claude vs averaged resolved tier | 0.5271 | 0.6924 | 74.5% |
| GPT vs averaged resolved tier | 0.3896 | 0.5513 | 66.9% |
| Claude vs final clipped resolved tier | 0.5164 | 0.6837 | 74.0% |
| GPT vs final clipped resolved tier | 0.3950 | 0.5522 | 67.3% |

### T1 (highest-priority) document stability

| Set | Count |
|---|---|
| T1 in Claude only | 217 |
| T1 in GPT only | 71 |
| T1 in **both** (robust T1) | 9 |
| T1 in averaged | 21 |

> **Interpretation:** Documents in T1 under *both* scorers (9) are the most robust high-priority candidates — their relevance is confirmed regardless of model-specific operationalization differences. Documents in T1 under only one scorer should be treated as contested and flagged for human review.

## 5. Contested Documents

**654** documents have a composite divergence > 3.0 points and should be reviewed by a human coder before inclusion in the final corpus.

| Filename | Claude | GPT | Δ | Claude tier | GPT tier |
|---|---|---|---|---|---|
| 2020-03-31_144967_DHS_REPORT_08-1665_144967.pdf | 8.15 | 0.3 | +7.85 | T1 | T4 |
| 2023-11-07_185772_Revised_motion_by_Supervisors_Horvath | 8.4 | 0.75 | +7.65 | T1 | T4 |
| 2025-06-17_204142_Motion_by_Supervisor_Solis_25-3371_20 | 7.9 | 0.45 | +7.45 | T1 | T4 |
| 2022-01-25_1-25-22_Board_Meeting_Transcript_1118909.pdf | 7.75 | 0.45 | +7.30 | T1 | T4 |
| 2021-02-09_153603_Presentation_19-7713_153603.pdf | 7.65 | 0.45 | +7.20 | T1 | T4 |
| 2023-02-07_177455_Board_Letter_23-0499_177455.pdf | 7.6 | 0.45 | +7.15 | T1 | T4 |
| 2026-03-17_213493_Board_Letter_26-1481_213493.pdf | 9.5 | 2.45 | +7.05 | T1 | T3 |
| 2026-02-12_Youre_The_Chair_-_Com_Networking_Summit_-_2- | 7.6 | 0.6 | +7.00 | T1 | T4 |
| 2023-02-28_178395_Report_23-0881_178395.pdf | 7.85 | 0.9 | +6.95 | T1 | T4 |
| 2022-11-29_175329_Public_CommentCorrespondence_11-1977_ | 7.4 | 0.45 | +6.95 | T1 | T4 |
| 2021-08-10_08-10-21_Board_Meeting_Transcript_C_1111561. | 7.2 | 0.45 | +6.75 | T1 | T4 |
| 2021-12-07_164004_LACCB_BL_21-4628_164004.pdf | 8.35 | 1.7 | +6.65 | T1 | T3 |
| 2023-04-04_179166_Board_Letter_23-1276_179166.pdf | 7.55 | 0.9 | +6.65 | T1 | T4 |
| 2024-08-06_193957_Public_CommentCorrespondence_24-3171_ | 7.25 | 0.6 | +6.65 | T1 | T4 |
| 2024-08-06_193942_Public_CommentCorrespondence_24-3166_ | 7.9 | 1.3 | +6.60 | T1 | T3 |
| 2021-01-26_153156_Public_Comment_13-0268_153156.pdf | 8.3 | 1.8 | +6.50 | T1 | T3 |
| 2024-04-09_190332_Report_24-1334_190332.pdf | 7.55 | 1.05 | +6.50 | T1 | T3 |
| 2021-10-19_162017_2020-000606-1-5_Housing_Element_Updat | 7.35 | 0.95 | +6.40 | T1 | T4 |
| 2021-08-31_161412_Report_21-3358_161412.pdf | 7.3 | 0.9 | +6.40 | T1 | T4 |
| 2023-11-07_185645_Public_CommentCorrespondence_23-4056_ | 6.7 | 0.3 | +6.40 | T1 | T4 |

*(+634 more — see `s07_merged.jsonl` where `contested=true`)*

---
*Outputs: `s07_merged.jsonl` (full merged corpus), `irr_scatterplot.png`*