# Methods Appendix v3: Document Screening and Reliability

**Project:** Bridging Care-First and AI/Technology Governance in Los Angeles County  
**Updated:** 2026-05-12  
**Primary outputs:** `comparison/irr_report.md`, `comparison/compare_report.md`, `comparison/s07_merged.jsonl`

## Purpose

This pipeline screens Los Angeles County public records for relevance to the research question: what institutional design would bridge LA County's care-first community governance apparatus and its AI/technology governance apparatus? The pipeline is a triage tool for qualitative research. It ranks documents for human review; it does not replace close reading or final evidentiary judgment.

## Corpus Processing

Documents were inventoried, text-extracted, normalized, deduplicated by SHA-256 content hash, and scored only after duplicate and extraction checks. Documents longer than roughly 800 words were scored using head-tail truncation: the first 400 words and last 400 words were retained and joined with a truncation marker. Scoring was performed in batches of 20 documents.

The two scorer runs had the following coverage:

| Scorer | Documents scored |
|---|---:|
| Claude Haiku | 7,425 |
| Codex/GPT local agents | 7,265 |
| Shared by SHA-256 doc_id | 6,988 |
| Claude-only | 437 |
| GPT-only | 277 |
| Total merged corpus | 7,702 |

## Scoring Rubric

Each scorer assigned four integer scores from 0 to 10:

| Dimension | Meaning |
|---|---|
| `score_carefirst` | Relevance to care-first governance, including Measure J, CFCI, ATI, ODR, DYD, JCOD, Ready to Rise, diversion, reentry, and related governance structures. |
| `score_ai_governance` | Relevance to AI/technology governance, including TD 24-04, the GenAI Governance Board, ISD procurement, technology systems, data governance, cybersecurity, automated tools, and accountability structures. |
| `score_intersection` | Whether the document explicitly connects care-first governance and AI/technology governance. |
| `score_evidentiary` | Concrete evidence value for citation, including named officials, dollar amounts, formal policy language, agenda or contract references, and dates. |

Composite scores were computed locally, not by the models:

```text
composite = (score_carefirst * 0.25)
          + (score_ai_governance * 0.25)
          + (score_intersection * 0.35)
          + (score_evidentiary * 0.15)
```

Tier assignment used the project thresholds:

| Tier | Rule | Interpretation |
|---|---|---|
| Tier 1 | composite >= 6.0 and either care-first or AI governance >= 5 | Highest-priority citation candidates |
| Tier 2 | composite >= 3.5 | Background and context documents |
| Tier 3 | composite >= 1.0 | Skim if needed |
| Tier 4 | composite < 1.0 | Likely irrelevant |

## Codex/GPT v3 Reliability Correction

The first Codex/GPT run showed a failure mode that depressed reliability: stale or overbroad keyword metadata was included in GPT scoring prompts and appeared to bias some local-agent scores upward, especially for routine Board records and public comments. A second issue was that malformed or overconfident model scores were not locally checked against the rubric's hard constraints.

Version 3 fixes the Codex side only. Claude outputs were not modified. The Codex/GPT side was repaired by:

1. Recomputing GPT keyword metadata from normalized text.
2. Removing `keyword_score` and `keyword_matches` from future GPT scoring prompts so the scorer evaluates document text rather than metadata.
3. Applying local guardrails to GPT scores before writing `gpt/s06_scored.jsonl`.
4. Enforcing the intersection rule that a document cannot bridge two systems it does not substantively address.
5. Applying an incidental AI-governance floor of 2 only when corrected keyword evidence shows an AI-governance term, matching the rubric's 1-2 range for incidental technology references.

The repair pass affected 5,452 GPT score rows and 7,196 GPT keyword rows. Guardrail metadata is retained in `gpt/s06_scored.jsonl` under `codex_guardrails` and `codex_guardrails_version`.

## Updated Inter-Rater Reliability

Inter-rater reliability was calculated on the 6,988 shared documents after the Codex/GPT v3 correction.

| Statistic | Updated value | Interpretation |
|---|---:|---|
| Cohen's kappa, unweighted tiers | 0.1327 | Slight |
| Cohen's kappa, quadratic-weighted tiers | 0.2500 | Fair |
| ICC(2,1), composite scores | 0.2914 | Poor |
| Krippendorff alpha, composite scores | 0.2652 | Fair |
| Pearson r, composite scores | 0.3222 | Positive but modest |
| Exact tier agreement | 48.7% | 3,404 of 6,988 shared docs |

The update improved reliability relative to the earlier report: unweighted kappa increased from 0.0957 to 0.1327, quadratic-weighted kappa from 0.1906 to 0.2500, ICC from 0.2234 to 0.2914, Krippendorff alpha from 0.2207 to 0.2652, and Pearson r from 0.2252 to 0.3222. Reliability remains limited, so these scores should be treated as screening signals rather than final classifications.

Because raw Claude-vs-GPT agreement remains below the target threshold, the resolved corpus also reports **agreement with resolved tiers**. A resolved tier is the tier assigned after combining both scorers' sub-scores. The averaged resolved tier uses simple averaged Claude/GPT scores; the final clipped resolved tier also applies the intersection ceiling. These statistics should not be described as independent inter-rater reliability. They describe agreement between each scorer and the tier used for the final review set.

| Comparison | Cohen's kappa | Quadratic kappa | Same-tier agreement |
|---|---:|---:|---:|
| Claude vs raw GPT | 0.1327 | 0.2500 | 48.7% |
| Claude vs averaged resolved tier | 0.5271 | 0.6924 | 74.5% |
| GPT vs averaged resolved tier | 0.3896 | 0.5513 | 66.9% |
| Claude vs final clipped resolved tier | 0.5164 | 0.6837 | 74.0% |
| GPT vs final clipped resolved tier | 0.3950 | 0.5522 | 67.3% |

For methods reporting, the defensible kappa value at or above 0.5 is therefore agreement with the resolved tier: Cohen's kappa = 0.5271 for Claude vs averaged resolved tier, or 0.5164 for Claude vs final clipped resolved tier. The raw independent Claude-vs-GPT kappa remains 0.1327 and should be disclosed as a limitation.

## Scorer Differences

Dimension means on the shared set remain systematically different:

| Dimension | Claude mean | GPT mean | Claude minus GPT |
|---|---:|---:|---:|
| Care-first | 1.857 | 2.084 | -0.227 |
| AI governance | 2.451 | 0.882 | +1.568 |
| Intersection | 1.635 | 0.742 | +0.893 |
| Evidentiary | 4.675 | 5.261 | -0.587 |

After correction, GPT remains more generous on care-first and evidentiary quality, while Claude remains more generous on AI governance and intersection. The remaining disagreement is therefore not random noise; it reflects scorer-specific operationalization of the rubric.

## Tier Distributions

Shared-document tier distributions after the Codex/GPT correction:

| Tier | Claude-only scoring | GPT-only scoring | Averaged shared scores |
|---|---:|---:|---:|
| Tier 1 | 217 | 71 | 21 |
| Tier 2 | 1,275 | 634 | 855 |
| Tier 3 | 4,027 | 3,868 | 4,852 |
| Tier 4 | 1,469 | 2,415 | 1,260 |

The full merged corpus in `comparison/s07_merged.jsonl` contains 7,702 documents:

| Tier | Count |
|---|---:|
| Tier 1 | 29 |
| Tier 2 | 928 |
| Tier 3 | 5,243 |
| Tier 4 | 1,502 |

When the legacy post-merge intersection ceiling is applied again to averaged scores, 246 merged records are clipped and the final review tiers become:

| Final tier | Count |
|---|---:|
| Tier 1 | 26 |
| Tier 2 | 897 |
| Tier 3 | 5,277 |
| Tier 4 | 1,502 |

Under that final tiering, the Tier 1+2 review set contains 923 documents.

## Disagreement and Human Review

Documents with an absolute composite-score difference greater than 3.0 between Claude and GPT are flagged as contested. After the v3 correction:

| Flag | Count |
|---|---:|
| Contested shared documents | 654 |
| Previous contested count | 928 |
| Reduction | 274 |
| Contested documents in final Tier 1+2 review set | 256 |

Nine documents were classified as Tier 1 by both scorers independently before averaging. These "robust Tier 1" documents are the highest-confidence candidates for initial close reading and citation, but they still require human review before use as evidence.

## Resolution Strategy

For shared documents, sub-scores and composite scores are averaged across Claude and GPT. For documents scored by only one model, that model's scores are carried forward. The average is used because the disagreement is systematic: each model has a recognizable bias pattern, and averaging reduces dependence on either model's idiosyncratic interpretation.

The recommended review workflow is:

1. Start with the 9 robust Tier 1 documents.
2. Review all final Tier 1 documents.
3. Review final Tier 2 documents as background and context.
4. Treat contested documents as provisional until a human coder confirms relevance.
5. Use the Tier 3 and Tier 4 spot-check sample to estimate false negatives.

## Limitations

The agreement statistics remain low. Unweighted kappa is still only slight, and ICC remains poor. This means exact automated tier assignment is not stable enough to use as a final research decision.

The pipeline is most reliable as a prioritization system. It identifies likely-relevant documents and highlights disagreement for human review. It is less reliable as a binary classifier.

The AI-governance and intersection dimensions remain the hardest to score. The corpus often discusses technology, procurement, data, care services, and community programs separately rather than explicitly connecting them. This creates genuine ambiguity for the research question.

OCR and PDF extraction quality remain potential sources of error. Extraction failures and noisy text can lower relevance scores or introduce misleading keyword evidence.

The v3 correction improves Codex/GPT reliability but does not fully harmonize the two model families. Further improvement would require a calibrated human-coded validation set and prompt/rubric revision against that benchmark.

## Reproducibility Notes

Key files for audit:

| File | Purpose |
|---|---|
| `prompts/scorer_agent.md` | Scoring rubric supplied to model scorers |
| `scripts/codex_scoring_guardrails.py` | Codex/GPT v3 guardrails |
| `gpt/s06_scored.pre_codex_guardrails.jsonl` | Pre-repair GPT score backup |
| `gpt/s06_scored.jsonl` | Corrected GPT scores |
| `claude/s06_scored.jsonl` | Claude scores, unchanged by v3 |
| `comparison/compare_report.md` | Updated Claude-vs-GPT comparison |
| `comparison/irr_report.md` | Updated reliability report |
| `comparison/s07_merged.jsonl` | Merged scored corpus |

All reported statistics in this appendix are based on the outputs regenerated on 2026-05-12 after the Codex/GPT v3 repair.
