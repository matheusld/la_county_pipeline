"""Stage 9 — Final shortlist (Tier 1 + Tier 2 + top Tier 3 to fill to 167)."""
import csv
import json
import os

OUTPUT_FOLDER = r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\claude"
S07 = os.path.join(OUTPUT_FOLDER, "s07_ranked.jsonl")
S03 = os.path.join(OUTPUT_FOLDER, "s03_normalized.jsonl")
OUT_JSONL = os.path.join(OUTPUT_FOLDER, "s09_shortlist.jsonl")
OUT_CSV = os.path.join(OUTPUT_FOLDER, "s09_shortlist.csv")
TARGET = 167


def main():
    text_by_id = {}
    with open(S03, "r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            text_by_id.setdefault(r["doc_id"], r.get("normalized_text") or "")

    rows = []
    with open(S07, "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))

    t1 = [r for r in rows if r.get("tier") == 1]
    t2 = [r for r in rows if r.get("tier") == 2]
    t3 = [r for r in rows if r.get("tier") == 3]

    selected = list(t1) + list(t2)
    if len(selected) < TARGET:
        t3.sort(key=lambda r: r.get("composite", 0.0), reverse=True)
        need = TARGET - len(selected)
        selected += t3[:need]

    selected.sort(key=lambda r: r.get("composite", 0.0), reverse=True)

    for i, r in enumerate(selected, 1):
        r["rank"] = i

    with open(OUT_JSONL, "w", encoding="utf-8") as f:
        for r in selected:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    cols = [
        "rank", "doc_id", "filename", "original_path", "tier", "composite",
        "score_carefirst", "score_ai_governance", "score_intersection",
        "score_evidentiary", "keyword_score", "keyword_matches",
        "rationale", "text_preview",
    ]
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in selected:
            txt = text_by_id.get(r["doc_id"], "")
            preview = " ".join(txt.split()[:300])
            kw = r.get("keyword_matches") or []
            kw_str = ";".join(kw) if isinstance(kw, list) else str(kw)
            w.writerow([
                r.get("rank"), r["doc_id"], r["filename"], r.get("original_path"),
                r.get("tier"), r.get("composite"),
                r.get("score_carefirst"), r.get("score_ai_governance"),
                r.get("score_intersection"), r.get("score_evidentiary"),
                r.get("keyword_score"), kw_str,
                r.get("rationale"), preview,
            ])

    from collections import Counter
    tier_counts = Counter(r["tier"] for r in selected)
    print(f"Shortlist size: {len(selected)}")
    print(f"  by tier: {dict(tier_counts)}")
    print(f"Wrote: {OUT_JSONL}")
    print(f"Wrote: {OUT_CSV}")


if __name__ == "__main__":
    main()
