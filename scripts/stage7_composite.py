"""Stage 7 — Composite + tier."""
import json
import os
from collections import Counter

OUTPUT_FOLDER = r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\claude"
S06 = os.path.join(OUTPUT_FOLDER, "s06_scored.jsonl")
OUT = os.path.join(OUTPUT_FOLDER, "s07_ranked.jsonl")


def composite(cf, ag, ix, ev):
    return cf * 0.25 + ag * 0.25 + ix * 0.35 + ev * 0.15


def tier_for(comp, cf, ag):
    if comp >= 6.0 and (cf >= 5 or ag >= 5):
        return 1
    if comp >= 3.5:
        return 2
    if comp >= 1.0:
        return 3
    return 4


def main():
    seen = set()
    counts = Counter()
    n = 0
    with open(S06, "r", encoding="utf-8") as fin, open(OUT, "w", encoding="utf-8") as fout:
        for line in fin:
            r = json.loads(line)
            if r["doc_id"] in seen:
                continue
            seen.add(r["doc_id"])
            cf = r.get("score_carefirst", 0) or 0
            ag = r.get("score_ai_governance", 0) or 0
            ix = r.get("score_intersection", 0) or 0
            ev = r.get("score_evidentiary", 0) or 0
            c = composite(cf, ag, ix, ev)
            t = tier_for(c, cf, ag)
            r["composite"] = round(c, 4)
            r["tier"] = t
            counts[t] += 1
            n += 1
            fout.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Total ranked: {n}")
    for t in (1, 2, 3, 4):
        print(f"  Tier {t}: {counts[t]}")
    print(f"Wrote: {OUT}")


if __name__ == "__main__":
    main()
