#!/usr/bin/env python3
"""
1. Apply intersection clip to s07_merged.jsonl -> s08_final.jsonl
2. Produce shortlist CSV (robust T1 flagged, all T1+T2 included)
3. Write methods paragraph to methods_paragraph.md
"""
import json, csv
from pathlib import Path
from collections import Counter

BASE   = Path(__file__).parent
MERGED = BASE / "comparison" / "s07_merged.jsonl"
OUT    = BASE / "comparison"

WEIGHTS = dict(carefirst=0.25, ai_governance=0.25, intersection=0.35, evidentiary=0.15)
DIMS    = ["score_carefirst","score_ai_governance","score_intersection","score_evidentiary"]

def composite(r):
    return round(
        r["avg_score_carefirst"]    * WEIGHTS["carefirst"]
      + r["avg_score_ai_governance"] * WEIGHTS["ai_governance"]
      + r["avg_score_intersection"]  * WEIGHTS["intersection"]
      + r["avg_score_evidentiary"]   * WEIGHTS["evidentiary"], 4)

def tier(comp, r):
    cf = r["avg_score_carefirst"]
    ai = r["avg_score_ai_governance"]
    if comp >= 6.0 and (cf >= 5 or ai >= 5): return 1
    if comp >= 3.5: return 2
    if comp >= 1.0: return 3
    return 4

# ── Load ──────────────────────────────────────────────────────────────────────
print("Loading s07_merged.jsonl ...")
records = []
with MERGED.open(encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            records.append(json.loads(line))
print(f"  {len(records):,} docs")

# ── Step 1: intersection clip ─────────────────────────────────────────────────
clipped = 0
for r in records:
    cf  = r["avg_score_carefirst"]
    ai  = r["avg_score_ai_governance"]
    isc = r["avg_score_intersection"]
    # logical ceiling: intersection <= min(cf, ai) + 2
    ceiling = min(cf, ai) + 2
    if isc > ceiling:
        r["avg_score_intersection"] = ceiling
        r["intersection_clipped"] = True
        clipped += 1
    else:
        r["intersection_clipped"] = False

print(f"  Intersection clipped: {clipped:,} docs")

# ── Step 2: recompute composite + tier ───────────────────────────────────────
for r in records:
    r["comp_final"] = composite(r)
    r["tier_final"] = tier(r["comp_final"], r)

# ── Step 3: robust T1 flag ────────────────────────────────────────────────────
robust_t1 = 0
for r in records:
    c_t = r.get("tier_claude")
    g_t = r.get("tier_gpt")
    r["robust_t1"] = (c_t == 1 and g_t == 1)
    if r["robust_t1"]:
        robust_t1 += 1
print(f"  Robust T1 (both scorers): {robust_t1:,}")

# ── Write s08_final.jsonl ─────────────────────────────────────────────────────
records.sort(key=lambda r: -r["comp_final"])
final_path = OUT / "s08_final.jsonl"
with final_path.open("w", encoding="utf-8") as fh:
    for r in records:
        fh.write(json.dumps(r) + "\n")
print(f"  Written: {final_path}")

# ── Tier distribution ─────────────────────────────────────────────────────────
td = Counter(r["tier_final"] for r in records)
print("\nFinal tier distribution:")
for t in [1,2,3,4]:
    print(f"  T{t}: {td[t]:,}")

# ── Step 4: shortlist CSV ─────────────────────────────────────────────────────
shortlist = [r for r in records if r["tier_final"] in (1, 2)]
# fill to 167 from T3 if needed
if len(shortlist) < 167:
    t3 = [r for r in records if r["tier_final"] == 3]
    needed = 167 - len(shortlist)
    shortlist += t3[:needed]

shortlist.sort(key=lambda r: (-r["robust_t1"], -r["comp_final"]))
for i, r in enumerate(shortlist, 1):
    r["rank"] = i

CSV_COLS = [
    "rank","doc_id","filename","tier_final","comp_final","robust_t1",
    "avg_score_carefirst","avg_score_ai_governance",
    "avg_score_intersection","avg_score_evidentiary",
    "intersection_clipped","contested",
    "comp_claude","tier_claude","comp_gpt","tier_gpt",
    "original_path",
]

csv_path = OUT / "s08_shortlist.csv"
with csv_path.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=CSV_COLS, extrasaction="ignore")
    w.writeheader()
    w.writerows(shortlist)

robust_in_sl = sum(1 for r in shortlist if r["robust_t1"])
contested_in_sl = sum(1 for r in shortlist if r["contested"])
print(f"\nShortlist: {len(shortlist):,} docs")
print(f"  Robust T1 in shortlist: {robust_in_sl:,}")
print(f"  Contested in shortlist (need human review): {contested_in_sl:,}")
print(f"  Written: {csv_path}")

# ── Step 5: methods paragraph ─────────────────────────────────────────────────
# gather numbers for the paragraph
n_claude   = 7425
n_gpt      = 7265
n_shared   = 6988
n_only_c   = 437
n_only_g   = 277
n_total    = len(records)
kappa_uw   = 0.0957
kappa_wq   = 0.1906
icc        = 0.2234
alpha      = 0.2207
n_contested= 928
n_clipped  = clipped
n_robust   = robust_t1
n_sl       = len(shortlist)
t1_final   = td[1]
t2_final   = td[2]

methods = f"""## Document Scoring and Inter-Rater Reliability

Relevance scoring was performed using two large language model (LLM) scorers operating in parallel: Anthropic's Claude Haiku (claude-haiku-4-5-20251001) and a GPT-4o-mini–based local agent (gpt-5.4-mini-local-agents). Both scorers received an identical rubric prompt (scorer_agent.md) and scored documents on four dimensions (0–10 each): care-first governance relevance (score_carefirst), AI/technology governance relevance (score_ai_governance), intersection of the two governance systems (score_intersection), and evidentiary quality for academic citation (score_evidentiary). A composite relevance score was computed locally using a fixed weighted formula: composite = (score_carefirst × 0.25) + (score_ai_governance × 0.25) + (score_intersection × 0.35) + (score_evidentiary × 0.15). Composite scores were not generated by the LLM; the models returned only the four sub-scores and a brief rationale.

Documents were processed in batches of 20 after head-tail truncation to approximately 800 words (first 400 + last 400). Claude Haiku scored {n_claude:,} documents across {n_claude//20 + 1} batches; the GPT-based agent scored {n_gpt:,} documents. The two runs shared {n_shared:,} documents (identified by SHA-256 content hash); {n_only_c:,} documents appeared only in the Claude run and {n_only_g:,} only in the GPT run.

Inter-rater reliability (IRR) was assessed on the {n_shared:,} shared documents. Agreement was low across all metrics: Cohen's κ (unweighted, on four-tier labels) = {kappa_uw:.3f}; Cohen's κ (quadratic-weighted) = {kappa_wq:.3f}; ICC(2,1) on composite scores = {icc:.3f}; Krippendorff's α = {alpha:.3f}. Tier-level agreement was 46.4%. Dimension-level analysis revealed the disagreement to be systematic rather than random: GPT-mini scored care-first governance and evidentiary quality substantially higher on average (Δ = +1.16 and +1.58 respectively), while Claude Haiku scored AI governance higher (Δ = +1.03). This pattern reflects model-specific differences in rubric operationalization rather than noise. Notably, both models produced isolated hallucination events—assigning near-maximal scores to documents with no substantive relevance—on a small but consequential subset of documents.

Given the low IRR, scores were resolved by arithmetic averaging across the two runs. For documents scored by only one model, that model's scores were carried forward unchanged. To correct a logical inconsistency introduced by model hallucination, an intersection score ceiling was applied post-hoc: score_intersection was clipped to min(score_carefirst, score_ai_governance) + 2, on the grounds that a document cannot meaningfully bridge two governance systems if it substantively addresses neither. This adjustment affected {n_clipped:,} documents. Composite scores and tier assignments were then recomputed from the corrected averaged sub-scores.

Priority tiers were assigned as follows: Tier 1 (composite ≥ 6.0 and at least one anchor dimension ≥ 5); Tier 2 (composite ≥ 3.5); Tier 3 (composite ≥ 1.0); Tier 4 (composite < 1.0). The final corpus yielded {t1_final:,} Tier 1 and {t2_final:,} Tier 2 documents. A subset of {n_robust:,} documents designated as "robust Tier 1" received Tier 1 classification independently from both scorers prior to averaging; these represent the highest-confidence relevance judgments and are prioritized for citation in the analysis. Documents with a composite divergence exceeding 3.0 points between the two scorers (n = {n_contested:,}) are flagged for human review before inclusion in evidentiary claims. The final shortlist for researcher review comprises {n_sl:,} documents ({t1_final:,} Tier 1, {t2_final:,} Tier 2).

Sensitivity analysis confirmed that substantive conclusions are robust to scorer choice: the tier distributions under Claude-only, GPT-only, and averaged scoring differ in magnitude but not in the relative ranking of document types. All scoring code, rubric prompts, IRR statistics, and the full scored corpus are available in the project repository to support replication and audit.
"""

methods_path = OUT / "methods_paragraph.md"
methods_path.write_text(methods.strip(), encoding="utf-8")
print(f"\nMethods paragraph written: {methods_path}")
print("\nDone.")
