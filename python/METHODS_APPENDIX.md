# Appendix: Document Screening Methodology

**Project:** Bridging Care-First and AI Governance in LA County
**Prepared for:** Derek Steele, Social Justice Learning Institute
**UC Berkeley Goldman School of Public Policy — MPP Capstone, Spring 2026**

---

## The Problem

LA County government produces thousands of public records — Board of Supervisors
agendas, motion letters, departmental reports, contracts, budget documents, and
meeting transcripts. Reviewing all of them by hand to find those relevant to this
research question is not feasible. This pipeline automates the first pass.

The goal is not to replace human judgment. It is to reduce 9,000+ documents to a
ranked shortlist that a researcher can read carefully in the time available for
qualitative analysis.

---

## How It Works

**Step 1 — Text extraction.** Each document is converted to plain text. PDFs are
processed with a text-extraction library; scanned or image-based PDFs fall back to
optical character recognition (OCR). Documents that cannot be read are flagged but
kept in the record.

**Step 2 — Deduplication.** Near-identical documents are identified by comparing
overlapping word patterns between every pair of documents. Documents judged more
than 85% similar to an earlier document are marked as duplicates and skipped in
later steps, saving cost and avoiding double-counting.

**Step 3 — Independent scoring by two AI models.** Every non-duplicate document is
submitted to two AI models — GPT-5.4-mini (OpenAI) and Claude Haiku (Anthropic) —
operating independently with the same instructions. Each model reads the document
text and scores it on four dimensions from 0 to 10:

| Dimension | What it measures |
|-----------|-----------------|
| **Care-first relevance** | How much does the document address Measure J, CFCI, ODR, DYD, ATI, or related care-first structures? |
| **AI/tech governance relevance** | How much does it address TD 24-04, the GenAI Governance Board, ISD procurement, or AI policy in county contexts? |
| **Intersection** | Does the document explicitly connect the two governance systems? (0 = neither mentioned; 10 = bridging them is the central subject) |
| **Evidentiary quality** | Does it contain concrete, citable evidence — named officials, dollar amounts, contract numbers, direct quotes, specific dates? |

A single composite score is then calculated locally by the pipeline using a fixed
weighted formula: intersection receives the highest weight (35%) because documents
that explicitly link the two governance systems are the primary research target;
care-first and AI governance each receive 25%; evidentiary quality receives 15%.

Claude Haiku scored 7,425 documents; GPT-5.4-mini scored 7,265. The two runs shared
6,988 documents identified by content fingerprint.

**Step 4 — Cross-model comparison and score resolution.** The two models' scores are
compared using standard statistical measures of agreement between two independent
raters — a practice called inter-rater reliability (IRR) assessment. Agreement was
low: Cohen's κ (kappa, a measure of agreement beyond chance) = 0.10; ICC
(intraclass correlation coefficient, a consistency measure on a continuous scale)
= 0.22. Only 46% of shared documents landed in the same tier. This is not unusual
when two different model families apply the same rubric — they operationalize the
criteria differently.

Dimension-level analysis showed the disagreement is systematic, not random. GPT-mini
scored care-first governance and evidentiary quality higher on average (+1.2 and +1.6
points respectively); Claude Haiku scored AI governance higher (+1.0 points). Both
models also produced a small number of hallucination events — assigning near-maximal
scores to documents with no substantive relevance to the research question.

To resolve this, all four sub-scores were averaged across the two models for each
shared document. A logical correction was also applied: the intersection score was
capped at two points above the lower of the two primary dimension scores, on the
grounds that a document cannot meaningfully bridge two governance systems if it
substantively addresses neither. This correction affected 402 documents.

Composite scores and tier assignments were then recomputed from the corrected averaged
scores. Documents are assigned to one of four tiers:

- **Tier 1** — high composite (≥ 6.0) with substantive content on at least one primary
  dimension. These warrant citation in the paper. **65 documents.**
- **Tier 2** — moderate composite (≥ 3.5). Useful background. **1,398 documents.**
- **Tier 3** — low composite (≥ 1.0). Skim only.
- **Tier 4** — composite below 1.0. Likely irrelevant.

**Step 5 — Disagreement flagging.** When the two models' composite scores differ by
more than 3.0 points, the document is flagged as contested. Of 6,988 shared documents,
928 were flagged this way. Contested documents in the shortlist are marked for human
review before being cited as primary evidence, because a gap that large typically
means one model responded to something the other ignored — or that one model
hallucinated.

**Step 6 — Shortlist.** All Tier 1 and Tier 2 documents are merged and sorted by
composite score. The final shortlist contains **1,463 documents** (65 Tier 1,
1,398 Tier 2). A subset of **20 documents** classified as Tier 1 independently by
both models before averaging — called "robust Tier 1" — represent the
highest-confidence relevance judgments and are the recommended starting point for
close reading and direct citation. Shortlisted documents flagged as contested (464 of
1,463) should be read before being cited as primary evidence.

**Step 7 — Spot-check.** A random 10% sample of low-priority documents (Tier 3 and
Tier 4, not flagged for disagreement) is drawn using a fixed random seed. A human
reviewer reads each sampled document and records whether the pipeline's low-priority
classification was correct. This estimates the false-negative rate — how often a
relevant document was incorrectly deprioritized.

---

## Why Two Models?

Any single AI model has systematic tendencies: it may consistently overweight or
underweight certain types of policy language, misread jargon from a particular
agency, or be insensitive to the specific LA County context. Running two models
independently provides a partial check against these tendencies. Documents where
both models agree are classified with higher confidence. Documents where they
disagree surface borderline cases that might otherwise be silently discarded.

This is not a peer-review process. The models are not judging each other's reasoning;
they are simply scoring the same document in isolation, and their outputs are compared
after the fact.

In practice, the two models showed distinct biases that partially cancelled each
other out through averaging. GPT-mini tended to read care-first and evidentiary
content more generously; Claude Haiku tended to read AI governance content more
broadly. Averaging their scores produces a composite that is less dependent on either
model's particular interpretation of the rubric. The 20 robust Tier 1 documents —
those rated highest by both models independently — are the subset least sensitive to
these individual biases.

---

## Limitations

**The pipeline screens for relevance, not quality.** A document may score high because
it mentions the right programs and officials without actually advancing the research
argument. High-ranked documents still require careful human reading.

**OCR introduces noise.** Scanned PDFs, especially older ones, often contain
recognition errors that distort the text the models receive. A document with poor
OCR quality will tend to score lower than its content warrants. Extraction status is
recorded for every document; researchers should be alert to OCR-flagged documents in
the shortlist.

**The intersection dimension is the hardest to score reliably.** The research question
asks about a gap that is largely implicit in the documentary record — the two governance
systems rarely discuss each other directly. Models are instructed to score highly only
when an explicit connection is present, which means documents that gesture toward the
gap without naming it may be underscored. Inspection of extreme disagreement cases
also revealed that both models occasionally assign high intersection scores to
documents with no substantive content on either primary dimension — a hallucination
pattern corrected post-hoc by capping intersection at min(care-first, AI governance) + 2.

**The shortlist exceeds the original target.** The pipeline was designed to produce
roughly 167 documents for close reading. In practice, 1,463 documents scored above
the Tier 2 threshold and all are included rather than artificially truncated. The
robust Tier 1 set (20 documents) and the full Tier 1 set (65 documents) are the
natural starting points if time is limited.

**The spot-check estimates but does not eliminate false negatives.** A 10% sample of
low-priority documents provides a statistical estimate of how many relevant documents
the pipeline missed. It does not guarantee that all missed documents are identified.
If the spot-check escalation rate is high (say, above 15%), the pipeline's threshold
settings should be revisited before the shortlist is treated as comprehensive.

**Prompt dependency.** The scoring criteria are embedded in a text prompt given to
both models. Changes to that prompt would change the scores. Post-hoc analysis
identified two rubric weaknesses — ambiguous anchor points for the care-first and
AI governance dimensions, and an underspecified evidentiary checklist — that
contributed to the low inter-rater reliability. A revised prompt (scorer_agent.md)
addresses these issues and is available in the project repository for future runs.
The version used for this corpus is archived alongside the scored output.

---

*Full technical documentation, source code, and output files are available in the
project repository. The scoring prompt is `prompts/scorer_agent.md`; IRR statistics
and per-document score deltas are in `comparison/irr_report.md` and
`comparison/compare_detail.jsonl`.*
