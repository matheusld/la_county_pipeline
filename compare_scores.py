#!/usr/bin/env python3
"""
Compare Claude vs GPT scoring runs.
Outputs: compare_report.md, compare_detail.jsonl, compare_tier_diff.csv
"""
import json, csv, sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import date

BASE = Path(__file__).parent
CLAUDE_FILE = BASE / "claude" / "s06_scored.jsonl"
GPT_FILE    = BASE / "gpt"    / "s06_scored.jsonl"
OUT_DIR     = BASE / "comparison"
OUT_DIR.mkdir(exist_ok=True)

WEIGHTS = dict(carefirst=0.25, ai_governance=0.25, intersection=0.35, evidentiary=0.15)

def composite(rec):
    return (rec["score_carefirst"]   * WEIGHTS["carefirst"]
          + rec["score_ai_governance"] * WEIGHTS["ai_governance"]
          + rec["score_intersection"]  * WEIGHTS["intersection"]
          + rec["score_evidentiary"]   * WEIGHTS["evidentiary"])

def tier(comp, rec):
    if comp >= 6.0 and (rec["score_carefirst"] >= 5 or rec["score_ai_governance"] >= 5):
        return 1
    if comp >= 3.5: return 2
    if comp >= 1.0: return 3
    return 4

def load(path):
    docs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        comp = composite(rec)
        rec["composite"] = round(comp, 4)
        rec["tier"] = tier(comp, rec)
        docs[rec["doc_id"]] = rec
    return docs

print("Loading …")
claude = load(CLAUDE_FILE)
gpt    = load(GPT_FILE)

shared = set(claude) & set(gpt)
only_claude = set(claude) - set(gpt)
only_gpt    = set(gpt)   - set(claude)

print(f"Claude: {len(claude):,}  GPT: {len(gpt):,}  Shared: {len(shared):,}")
print(f"Only in Claude: {len(only_claude):,}  Only in GPT: {len(only_gpt):,}")

# ── Per-doc diff for shared docs ──────────────────────────────────────────────
detail_rows = []
fields = ["score_carefirst", "score_ai_governance", "score_intersection", "score_evidentiary"]

for did in shared:
    c = claude[did]; g = gpt[did]
    delta_comp = round(c["composite"] - g["composite"], 4)
    row = {
        "doc_id":    did,
        "filename":  c["filename"],
        "tier_claude": c["tier"],
        "tier_gpt":    g["tier"],
        "tier_change": c["tier"] - g["tier"],        # negative = Claude upgraded
        "comp_claude": c["composite"],
        "comp_gpt":    g["composite"],
        "delta_comp":  delta_comp,
    }
    for f in fields:
        row[f"claude_{f}"] = c[f]
        row[f"gpt_{f}"]    = g[f]
        row[f"delta_{f}"]  = c[f] - g[f]
    detail_rows.append(row)

detail_rows.sort(key=lambda r: abs(r["delta_comp"]), reverse=True)

detail_path = OUT_DIR / "compare_detail.jsonl"
with detail_path.open("w", encoding="utf-8") as fh:
    for row in detail_rows:
        fh.write(json.dumps(row) + "\n")

# ── Tier-change CSV ───────────────────────────────────────────────────────────
tier_csv_path = OUT_DIR / "compare_tier_diff.csv"
tier_cols = ["doc_id","filename","tier_claude","tier_gpt","tier_change",
             "comp_claude","comp_gpt","delta_comp"]
with tier_csv_path.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=tier_cols, extrasaction="ignore")
    w.writeheader()
    for row in sorted(detail_rows, key=lambda r: r["tier_change"]):
        w.writerow(row)

# ── Aggregate stats ───────────────────────────────────────────────────────────
def stats(vals):
    n = len(vals)
    if n == 0: return {}
    s = sorted(vals)
    mean = sum(s)/n
    med  = s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2
    return {"n":n,"mean":round(mean,3),"median":round(med,3),
            "min":round(s[0],3),"max":round(s[-1],3)}

def tier_dist(docs):
    c = Counter(v["tier"] for v in docs.values())
    return {f"T{i}": c.get(i,0) for i in range(1,5)}

shared_claude = {d: claude[d] for d in shared}
shared_gpt    = {d: gpt[d]    for d in shared}

# agreement on tier
agree = sum(1 for d in shared if claude[d]["tier"] == gpt[d]["tier"])
claude_higher = sum(1 for d in shared if claude[d]["tier"] < gpt[d]["tier"])  # lower tier number = higher
gpt_higher    = sum(1 for d in shared if claude[d]["tier"] > gpt[d]["tier"])

# correlation of composites on shared set
cx = [claude[d]["composite"] for d in shared]
gy = [gpt[d]["composite"]    for d in shared]
n  = len(shared)
mx, my = sum(cx)/n, sum(gy)/n
cov = sum((a-mx)*(b-my) for a,b in zip(cx,gy)) / n
sx  = (sum((a-mx)**2 for a in cx)/n)**0.5
sy  = (sum((b-my)**2 for b in gy)/n)**0.5
corr = cov/(sx*sy) if sx and sy else float("nan")

# biggest divergences
top10_higher_claude = sorted(detail_rows, key=lambda r: -r["delta_comp"])[:10]   # delta > 0 = Claude higher
top10_higher_gpt    = sorted(detail_rows, key=lambda r:  r["delta_comp"])[:10]   # delta < 0 = GPT higher

# ── Markdown report ───────────────────────────────────────────────────────────
md_lines = []
A = md_lines.append

A("# Claude vs GPT Scoring Comparison\n")
A(f"**Research question:** Bridging LA County care-first governance with AI/tech governance\n")
A(f"**Date:** {date.today().isoformat()}\n")

A("## 1. Coverage\n")
A(f"| | Count |")
A(f"|---|---|")
A(f"| Claude scored | {len(claude):,} |")
A(f"| GPT scored | {len(gpt):,} |")
A(f"| Shared (same doc_id) | {len(shared):,} |")
A(f"| Only in Claude | {len(only_claude):,} |")
A(f"| Only in GPT | {len(only_gpt):,} |\n")

A("## 2. Tier Distribution\n")
cd = tier_dist(claude); gd = tier_dist(gpt)
cd_s = tier_dist(shared_claude); gd_s = tier_dist(shared_gpt)
A("### All docs (each scorer's full set)\n")
A(f"| Tier | Claude | GPT |")
A(f"|---|---|---|")
for t in ["T1","T2","T3","T4"]:
    A(f"| {t} | {cd[t]:,} | {gd[t]:,} |")
A("")
A("### Shared docs only\n")
A(f"| Tier | Claude | GPT |")
A(f"|---|---|---|")
for t in ["T1","T2","T3","T4"]:
    A(f"| {t} | {cd_s[t]:,} | {gd_s[t]:,} |")
A("")

A("## 3. Tier Agreement (shared docs)\n")
A(f"| | Count | % |")
A(f"|---|---|---|")
A(f"| Same tier | {agree:,} | {agree/len(shared)*100:.1f}% |")
A(f"| Claude higher tier (lower #) | {claude_higher:,} | {claude_higher/len(shared)*100:.1f}% |")
A(f"| GPT higher tier (lower #) | {gpt_higher:,} | {gpt_higher/len(shared)*100:.1f}% |\n")

A("## 4. Composite Score Statistics (shared docs)\n")
cs = stats(cx); gs = stats(gy)
A(f"| Metric | Claude | GPT |")
A(f"|---|---|---|")
for k in ["mean","median","min","max"]:
    A(f"| {k.title()} | {cs[k]} | {gs[k]} |")
A(f"| Pearson r (composite) | {corr:.4f} | — |\n")

A("## 5. Per-dimension Mean (shared docs)\n")
A(f"| Dimension | Claude mean | GPT mean | Delta |")
A(f"|---|---|---|---|")
for f in fields:
    cv = sum(claude[d][f] for d in shared)/n
    gv = sum(gpt[d][f]    for d in shared)/n
    A(f"| {f.replace('score_','')} | {cv:.3f} | {gv:.3f} | {cv-gv:+.3f} |")
A("")

A("## 6. Biggest Scoring Divergences\n")
A("### Claude scored much higher than GPT (top 10 by Δ composite)\n")
A(f"| Filename | Claude | GPT | Δ |")
A(f"|---|---|---|---|")
for r in top10_higher_claude:
    A(f"| {r['filename'][:60]} | {r['comp_claude']} | {r['comp_gpt']} | {r['delta_comp']:+.2f} |")
A("")
A("### GPT scored much higher than Claude (top 10 by Δ composite)\n")
A(f"| Filename | Claude | GPT | Δ |")
A(f"|---|---|---|---|")
for r in top10_higher_gpt:
    A(f"| {r['filename'][:60]} | {r['comp_claude']} | {r['comp_gpt']} | {r['delta_comp']:+.2f} |")
A("")

A("## 7. Tier Upgrades / Downgrades\n")
upgrades   = [(r['filename'], r['tier_claude'], r['tier_gpt']) for r in detail_rows if r['tier_change'] < 0]
downgrades = [(r['filename'], r['tier_claude'], r['tier_gpt']) for r in detail_rows if r['tier_change'] > 0]
A(f"- **Claude assigned a higher tier** (lower number) than GPT for **{len(upgrades):,}** shared docs.")
A(f"- **GPT assigned a higher tier** than Claude for **{len(downgrades):,}** shared docs.\n")

if upgrades[:5]:
    A("#### Sample — Claude upgraded vs GPT\n")
    A("| Filename | Claude tier | GPT tier |")
    A("|---|---|---|")
    for fn, ct, gt in upgrades[:5]:
        A(f"| {fn[:70]} | T{ct} | T{gt} |")
    A("")

if downgrades[:5]:
    A("#### Sample — GPT upgraded vs Claude\n")
    A("| Filename | Claude tier | GPT tier |")
    A("|---|---|---|")
    for fn, ct, gt in downgrades[:5]:
        A(f"| {fn[:70]} | T{ct} | T{gt} |")
    A("")

A("## 8. Docs Unique to Each Run\n")
A(f"Files scored **only by Claude** ({len(only_claude):,}):")
for did in list(only_claude)[:5]:
    A(f"- {claude[did]['filename']}")
if len(only_claude) > 5: A(f"- *(+{len(only_claude)-5} more)*")
A("")
A(f"Files scored **only by GPT** ({len(only_gpt):,}):")
for did in list(only_gpt)[:5]:
    A(f"- {gpt[did]['filename']}")
if len(only_gpt) > 5: A(f"- *(+{len(only_gpt)-5} more)*")
A("")

A("---")
A(f"*Outputs: `comparison/compare_detail.jsonl` (per-doc diff), `comparison/compare_tier_diff.csv` (tier changes)*")

report_path = OUT_DIR / "compare_report.md"
report_path.write_text("\n".join(md_lines), encoding="utf-8")

print(f"\nDone.")
print(f"  Report  : {report_path}")
print(f"  Detail  : {detail_path}")
print(f"  Tier CSV: {tier_csv_path}")
print(f"\nKey numbers:")
print(f"  Shared docs     : {len(shared):,}")
print(f"  Tier agreement  : {agree/len(shared)*100:.1f}%")
print(f"  Pearson r       : {corr:.4f}")
print(f"  Composite mean  Claude={cs['mean']}  GPT={gs['mean']}")
