"""Stage 8 — Spot-check sample of Tier 3+4 docs (10%, seed=42)."""
import csv
import json
import math
import os
import random

OUTPUT_FOLDER = r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\claude"
S07 = os.path.join(OUTPUT_FOLDER, "s07_ranked.jsonl")
S03 = os.path.join(OUTPUT_FOLDER, "s03_normalized.jsonl")
OUT = os.path.join(OUTPUT_FOLDER, "s08_spotcheck.csv")


def main():
    text_by_id = {}
    with open(S03, "r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            text_by_id.setdefault(r["doc_id"], r.get("normalized_text") or "")

    pool = []
    with open(S07, "r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("tier") in (3, 4):
                pool.append(r)

    n_sample = max(1, math.ceil(len(pool) * 0.10))
    rng = random.Random(42)
    sample = rng.sample(pool, k=n_sample) if n_sample <= len(pool) else pool

    cols = [
        "doc_id", "filename", "tier", "composite",
        "score_carefirst", "score_ai_governance",
        "score_intersection", "score_evidentiary",
        "keyword_score", "rationale", "text_preview",
        "review_status", "reviewer_notes",
    ]
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in sample:
            txt = text_by_id.get(r["doc_id"], "")
            preview = " ".join(txt.split()[:400])
            w.writerow([
                r["doc_id"], r["filename"], r.get("tier"), r.get("composite"),
                r.get("score_carefirst"), r.get("score_ai_governance"),
                r.get("score_intersection"), r.get("score_evidentiary"),
                r.get("keyword_score"), r.get("rationale"),
                preview, "", "",
            ])
    print(f"Pool size (Tier 3+4): {len(pool)}")
    print(f"Sample size: {len(sample)}")
    print(f"Wrote: {OUT}")


if __name__ == "__main__":
    main()
