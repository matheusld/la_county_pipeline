#!/usr/bin/env python3
"""
IRR stats + merged output + sensitivity analysis + scatterplot.
Outputs to comparison/
"""
import json, csv
from pathlib import Path
from collections import Counter
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import cohen_kappa_score
from scripts.consensus_metrics import consensus_kappas

BASE     = Path(__file__).parent
CLAUDE_F = BASE / "claude" / "s06_scored.jsonl"
GPT_F    = BASE / "gpt"    / "s06_scored.jsonl"
OUT      = BASE / "comparison"
OUT.mkdir(exist_ok=True)

WEIGHTS = dict(carefirst=0.25, ai_governance=0.25, intersection=0.35, evidentiary=0.15)
DIMS    = ["score_carefirst","score_ai_governance","score_intersection","score_evidentiary"]

def composite(r):
    return (r["score_carefirst"]    * WEIGHTS["carefirst"]
          + r["score_ai_governance"] * WEIGHTS["ai_governance"]
          + r["score_intersection"]  * WEIGHTS["intersection"]
          + r["score_evidentiary"]   * WEIGHTS["evidentiary"])

def tier(comp, r):
    if comp >= 6.0 and (r["score_carefirst"] >= 5 or r["score_ai_governance"] >= 5): return 1
    if comp >= 3.5: return 2
    if comp >= 1.0: return 3
    return 4

def load(path):
    docs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        r = json.loads(line)
        r["composite"] = round(composite(r), 4)
        r["tier"] = tier(r["composite"], r)
        docs[r["doc_id"]] = r
    return docs

print("Loading …")
claude = load(CLAUDE_F)
gpt    = load(GPT_F)
shared = sorted(set(claude) & set(gpt))
n      = len(shared)
print(f"Shared: {n:,}")

# ── Arrays ────────────────────────────────────────────────────────────────────
c_comp  = np.array([claude[d]["composite"] for d in shared])
g_comp  = np.array([gpt[d]["composite"]    for d in shared])
c_tier  = np.array([claude[d]["tier"]       for d in shared])
g_tier  = np.array([gpt[d]["tier"]          for d in shared])

# ── 1. IRR stats ──────────────────────────────────────────────────────────────

# Cohen's kappa (unweighted and quadratic-weighted) on tiers
kappa_uw = cohen_kappa_score(c_tier, g_tier)
kappa_wq = cohen_kappa_score(c_tier, g_tier, weights="quadratic")

# Pearson r
pearson_r = float(np.corrcoef(c_comp, g_comp)[0, 1])

# ICC(2,1) — two-way random, absolute agreement, single measures
# Formula: (MSb - MSw) / (MSb + (k-1)*MSw + k*(MSbg-MSw)/n)
# Simpler two-rater formulation: ICC(2,1) = (MSb - MSe) / (MSb + MSe + 2*(MSr-MSe)/n)
# Using the standard two-way mixed ICC(3,1) for consistency model:
def icc_two_way(x, y):
    k = 2
    n_s = len(x)
    grand_mean = (x.mean() + y.mean()) / 2
    data = np.vstack([x, y])          # 2 × n
    # SS
    ss_b = k * np.sum((data.mean(axis=0) - grand_mean)**2)
    ss_w = np.sum((data - data.mean(axis=0))**2)
    ss_r = n_s * np.sum((data.mean(axis=1) - grand_mean)**2)
    ss_e = ss_w - ss_r
    # MS
    ms_b = ss_b / (n_s - 1)
    ms_r = ss_r / (k - 1)
    ms_e = ss_e / ((n_s - 1) * (k - 1))
    # ICC(2,1) absolute
    icc = (ms_b - ms_e) / (ms_b + (k-1)*ms_e + k*(ms_r - ms_e)/n_s)
    return float(icc)

icc = icc_two_way(c_comp, g_comp)

# Krippendorff's alpha (ratio metric, continuous composites)
def krippendorff_alpha(x, y):
    # Vectorized interval metric (avoids O(n^2) Python loop)
    D_o = (np.sum((x - y)**2) * 2) / (2 * len(x))
    all_vals = np.concatenate([x, y])
    # E[d²] = Var(all_vals)*2  (for interval metric across all pairs)
    mu = all_vals.mean()
    D_e = 2 * np.mean((all_vals - mu)**2)
    return float(1 - D_o / D_e)

alpha = krippendorff_alpha(c_comp, g_comp)

print(f"  Cohen kappa (unweighted): {kappa_uw:.4f}")
print(f"  Cohen kappa (quadratic):  {kappa_wq:.4f}")
print(f"  ICC(2,1):                 {icc:.4f}")
print(f"  Krippendorff alpha:       {alpha:.4f}")
print(f"  Pearson r:                {pearson_r:.4f}")

# ── 2. Scatterplot ────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
fig.suptitle("Claude vs GPT Scoring — Shared Documents (n={:,})".format(n), fontsize=13, y=1.01)

# 2a — composite scatter
ax = axes[0]
ax.scatter(g_comp, c_comp, alpha=0.25, s=8, color="#1f77b4", rasterized=True)
lim = [0, max(c_comp.max(), g_comp.max()) + 0.5]
ax.plot(lim, lim, "r--", lw=1, label="perfect agreement")
ax.set_xlabel("GPT composite", fontsize=11)
ax.set_ylabel("Claude composite", fontsize=11)
ax.set_title(f"Composite scores\nPearson r = {pearson_r:.3f}  |  ICC(2,1) = {icc:.3f}", fontsize=10)
ax.set_xlim(lim); ax.set_ylim(lim)
ax.legend(fontsize=9)

# 2b — tier confusion heatmap
conf = np.zeros((4, 4), dtype=int)
for ct, gt in zip(c_tier, g_tier):
    conf[ct-1, gt-1] += 1
im = axes[1].imshow(conf, cmap="Blues")
axes[1].set_xticks(range(4)); axes[1].set_yticks(range(4))
axes[1].set_xticklabels(["GPT T1","GPT T2","GPT T3","GPT T4"])
axes[1].set_yticklabels(["Claude T1","Claude T2","Claude T3","Claude T4"])
axes[1].set_title(
    f"Tier agreement\nκ (unweighted) = {kappa_uw:.3f}  |  κ (quadratic) = {kappa_wq:.3f}",
    fontsize=10)
for i in range(4):
    for j in range(4):
        axes[1].text(j, i, f"{conf[i,j]:,}", ha="center", va="center",
                     fontsize=8, color="white" if conf[i,j] > conf.max()*0.5 else "black")
plt.colorbar(im, ax=axes[1], shrink=0.8)

plt.tight_layout()
scatter_path = OUT / "irr_scatterplot.png"
fig.savefig(scatter_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"  Scatterplot -> {scatter_path}")

# ── 3. Averaged composites + merged output ───────────────────────────────────
CONTESTED_THRESH = 3.0
merged = []
for did in shared:
    c = claude[did]; g = gpt[did]
    delta = c["composite"] - g["composite"]
    avg_comp = round((c["composite"] + g["composite"]) / 2, 4)
    # average each sub-dimension too
    avg_dims = {f: round((c[f] + g[f]) / 2, 2) for f in DIMS}
    avg_tier = tier(avg_comp, {
        "score_carefirst":    avg_dims["score_carefirst"],
        "score_ai_governance": avg_dims["score_ai_governance"],
    })
    contested = abs(delta) > CONTESTED_THRESH
    merged.append({
        "doc_id":            did,
        "filename":          c["filename"],
        "original_path":     c["original_path"],
        # averaged scores
        "comp_avg":          avg_comp,
        "tier_avg":          avg_tier,
        **{f"avg_{f}": avg_dims[f] for f in DIMS},
        # individual runs
        "comp_claude":       c["composite"],
        "tier_claude":       c["tier"],
        "comp_gpt":          g["composite"],
        "tier_gpt":          g["tier"],
        "delta_comp":        round(delta, 4),
        "contested":         contested,
    })

# add docs unique to each scorer (use their score as-is, flag source)
for did in set(claude) - set(gpt):
    c = claude[did]
    merged.append({
        "doc_id": did, "filename": c["filename"], "original_path": c["original_path"],
        "comp_avg": c["composite"], "tier_avg": c["tier"],
        **{f"avg_{f}": c[f] for f in DIMS},
        "comp_claude": c["composite"], "tier_claude": c["tier"],
        "comp_gpt": None, "tier_gpt": None,
        "delta_comp": None, "contested": False,
    })
for did in set(gpt) - set(claude):
    g = gpt[did]
    merged.append({
        "doc_id": did, "filename": g["filename"], "original_path": g["original_path"],
        "comp_avg": g["composite"], "tier_avg": g["tier"],
        **{f"avg_{f}": g[f] for f in DIMS},
        "comp_claude": None, "tier_claude": None,
        "comp_gpt": g["composite"], "tier_gpt": g["tier"],
        "delta_comp": None, "contested": False,
    })

merged.sort(key=lambda r: -r["comp_avg"])

merged_path = OUT / "s07_merged.jsonl"
with merged_path.open("w", encoding="utf-8") as fh:
    for r in merged:
        fh.write(json.dumps(r) + "\n")
print(f"  Merged JSONL -> {merged_path}  ({len(merged):,} docs)")

contested_docs = [r for r in merged if r["contested"]]
print(f"  Contested (|delta|>3.0): {len(contested_docs):,}")

# ── 4. Sensitivity analysis ───────────────────────────────────────────────────
def tier_dist(docs, tier_key):
    c = Counter(r[tier_key] for r in docs if r[tier_key] is not None)
    return {f"T{i}": c.get(i, 0) for i in range(1, 5)}

shared_merged = [r for r in merged if r["comp_claude"] is not None and r["comp_gpt"] is not None]
consensus = consensus_kappas(shared_merged)

td_claude = tier_dist(shared_merged, "tier_claude")
td_gpt    = tier_dist(shared_merged, "tier_gpt")
td_avg    = tier_dist(shared_merged, "tier_avg")

# Tier-level agreement rates across the three versions
def pct_same_tier(a_key, b_key):
    same = sum(1 for r in shared_merged if r[a_key] == r[b_key])
    return same / len(shared_merged) * 100

agree_c_avg = pct_same_tier("tier_claude", "tier_avg")
agree_g_avg = pct_same_tier("tier_gpt",    "tier_avg")
agree_c_g   = pct_same_tier("tier_claude", "tier_gpt")

# ── 5. Markdown report ────────────────────────────────────────────────────────
md = []
A = md.append

A("# IRR Analysis & Merged Scores\n")
A("**Approach:** averaged composite scores (Claude + GPT) / 2, per-dimension averaging, "
  "human-review flag where |Δ composite| > 3.0.\n")

A("## 1. Inter-Rater Reliability Statistics (shared docs, n={:,})\n".format(n))
A("| Statistic | Value | Interpretation |")
A("|---|---|---|")

def kappa_label(k):
    if k < 0.20: return "Slight"
    if k < 0.40: return "Fair"
    if k < 0.60: return "Moderate"
    if k < 0.80: return "Substantial"
    return "Almost perfect"

def icc_label(v):
    if v < 0.50: return "Poor"
    if v < 0.75: return "Moderate"
    if v < 0.90: return "Good"
    return "Excellent"

A(f"| Cohen κ (unweighted, tiers) | {kappa_uw:.4f} | {kappa_label(kappa_uw)} |")
A(f"| Cohen κ (quadratic-weighted) | {kappa_wq:.4f} | {kappa_label(kappa_wq)} |")
A(f"| ICC(2,1) — composite scores | {icc:.4f} | {icc_label(icc)} |")
A(f"| Krippendorff α — composite | {alpha:.4f} | {kappa_label(alpha)} |")
A(f"| Pearson r — composite | {pearson_r:.4f} | — |")
A("")
A("> **Note:** Unweighted κ remains slight while quadratic-weighted κ is fair, "
  "so exact tier matches are still fragile even though near-miss tier disagreement "
  "has improved. ICC and α remain low, reflecting residual dimension-level bias "
  "identified in the scoring comparison. Treat contested documents as requiring "
  "human review rather than as stable automated classifications.\n")

A("## 2. Scatterplot\n")
A("See [`irr_scatterplot.png`](irr_scatterplot.png) — composite score scatter and tier confusion matrix.\n")

A("## 3. Resolution Strategy: Averaged Composites\n")
A("For all **6,988 shared docs**, the merged composite is the arithmetic mean of "
  "Claude and GPT composites. Sub-dimension scores are also averaged. "
  "Tier is re-derived from the averaged composite using the standard formula.\n")
A(f"- Docs flagged as **contested** (|Δ composite| > 3.0): **{len(contested_docs):,}**")
A(f"- Docs unique to Claude (carried over as-is): **{len(set(claude)-set(gpt)):,}**")
A(f"- Docs unique to GPT (carried over as-is): **{len(set(gpt)-set(claude)):,}**")
A(f"- **Total merged corpus:** {len(merged):,} docs\n")

A("## 4. Sensitivity Analysis\n")
A("Do conclusions change depending on which scorer's output is used?\n")
A("### Tier distribution — shared docs only\n")
A("| Tier | Claude-only | GPT-only | **Averaged** |")
A("|---|---|---|---|")
for t in ["T1","T2","T3","T4"]:
    A(f"| {t} | {td_claude[t]:,} | {td_gpt[t]:,} | **{td_avg[t]:,}** |")
A("")
A("### Tier stability across versions\n")
A("| Comparison | % same tier |")
A("|---|---|")
A(f"| Claude vs GPT | {agree_c_g:.1f}% |")
A(f"| Claude vs Averaged | {agree_c_avg:.1f}% |")
A(f"| GPT vs Averaged | {agree_g_avg:.1f}% |")
A("")

A("### Agreement With Resolved Tiers\n")
A("The **resolved tier** is the final tier assigned after combining both scorers' "
  "sub-scores. Two versions are shown: the averaged tier, based on simple averaged "
  "Claude/GPT scores, and the final clipped tier, which also applies the intersection "
  "ceiling. These statistics are **not** independent inter-rater reliability; they "
  "show how closely each scorer aligns with the tier used for the final review set.\n")
A("| Comparison | Cohen κ | Quadratic κ | % same tier |")
A("|---|---:|---:|---:|")
for label, key in [
    ("Claude vs GPT (raw IRR)", "claude_vs_gpt"),
    ("Claude vs averaged resolved tier", "claude_vs_avg"),
    ("GPT vs averaged resolved tier", "gpt_vs_avg"),
    ("Claude vs final clipped resolved tier", "claude_vs_final"),
    ("GPT vs final clipped resolved tier", "gpt_vs_final"),
]:
    m = consensus[key]
    A(
        f"| {label} | {m['unweighted_kappa']:.4f} | "
        f"{m['quadratic_weighted_kappa']:.4f} | {m['same_tier_pct']:.1f}% |"
    )
A("")

# Check if T1 set is stable
t1_claude = {d for d in shared if claude[d]["tier"] == 1}
t1_gpt    = {d for d in shared if gpt[d]["tier"]    == 1}
t1_avg    = {r["doc_id"] for r in shared_merged if r["tier_avg"] == 1}
t1_both   = t1_claude & t1_gpt
A("### T1 (highest-priority) document stability\n")
A(f"| Set | Count |")
A(f"|---|---|")
A(f"| T1 in Claude only | {len(t1_claude):,} |")
A(f"| T1 in GPT only | {len(t1_gpt):,} |")
A(f"| T1 in **both** (robust T1) | {len(t1_both):,} |")
A(f"| T1 in averaged | {len(t1_avg):,} |")
A("")
A("> **Interpretation:** Documents in T1 under *both* scorers ({:,}) are the most "
  "robust high-priority candidates — their relevance is confirmed regardless of "
  "model-specific operationalization differences. Documents in T1 under only one "
  "scorer should be treated as contested and flagged for human review.\n".format(len(t1_both)))

A("## 5. Contested Documents\n")
A(f"**{len(contested_docs):,}** documents have a composite divergence > 3.0 points and should be "
  "reviewed by a human coder before inclusion in the final corpus.\n")
if contested_docs:
    A("| Filename | Claude | GPT | Δ | Claude tier | GPT tier |")
    A("|---|---|---|---|---|---|")
    for r in sorted(contested_docs, key=lambda x: -abs(x["delta_comp"]))[:20]:
        A(f"| {r['filename'][:55]} | {r['comp_claude']} | {r['comp_gpt']} | "
          f"{r['delta_comp']:+.2f} | T{r['tier_claude']} | T{r['tier_gpt']} |")
    if len(contested_docs) > 20:
        A(f"\n*(+{len(contested_docs)-20} more — see `s07_merged.jsonl` where `contested=true`)*")
A("")

A("---")
A("*Outputs: `s07_merged.jsonl` (full merged corpus), `irr_scatterplot.png`*")

report_path = OUT / "irr_report.md"
report_path.write_text("\n".join(md), encoding="utf-8")
print(f"  IRR report -> {report_path}")
print("\nDone.")
