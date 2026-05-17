"""Stage 4 — Deduplication.

Exact: group by doc_id (SHA-256), keep first.
Near: 5-gram shingle Jaccard > 0.80 over first 300 words (lowercased).
When near-dupe found, keep the one with more text; mark the other.
"""
import json
import os
from collections import defaultdict

OUTPUT_FOLDER = r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\claude"
INP = os.path.join(OUTPUT_FOLDER, "s03_normalized.jsonl")
OUT = os.path.join(OUTPUT_FOLDER, "s04_deduped.jsonl")


def shingles(text, k=5):
    words = text.lower().split()[:300]
    if len(words) < k:
        return set()
    return set(tuple(words[i:i+k]) for i in range(len(words)-k+1))


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def main():
    rows = []
    with open(INP, "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))

    is_dup = [False] * len(rows)
    dup_of = [None] * len(rows)

    # 1) Exact dupes by doc_id
    by_id = defaultdict(list)
    for i, r in enumerate(rows):
        by_id[r["doc_id"]].append(i)
    exact_dups = 0
    for doc_id, idxs in by_id.items():
        if len(idxs) > 1:
            keeper = idxs[0]
            for j in idxs[1:]:
                is_dup[j] = True
                dup_of[j] = rows[keeper]["doc_id"]
                exact_dups += 1

    # 2) Near-duplicates among non-exact-dup, eligible (success, not too short) docs
    eligible = [
        i for i, r in enumerate(rows)
        if not is_dup[i]
        and r.get("extraction_status") == "success"
        and not r.get("too_short", False)
    ]

    # Compute shingles once
    sh = {}
    for i in eligible:
        sh[i] = shingles(rows[i].get("normalized_text") or "")

    # Bucket by first 5-gram to reduce comparisons; fall back to all-pairs within bucket
    buckets = defaultdict(list)
    for i in eligible:
        s = sh[i]
        if not s:
            continue
        # use a few keys (first 3 sorted shingles) to seed buckets
        keys = sorted(s)[:3]
        for k in keys:
            buckets[k].append(i)

    near_dups = 0
    for key, members in buckets.items():
        if len(members) < 2:
            continue
        for a_idx in range(len(members)):
            i = members[a_idx]
            if is_dup[i]:
                continue
            for b_idx in range(a_idx + 1, len(members)):
                j = members[b_idx]
                if is_dup[j] or is_dup[i]:
                    continue
                sim = jaccard(sh[i], sh[j])
                if sim > 0.80:
                    # keep the one with more text
                    li = rows[i].get("normalized_word_count", 0)
                    lj = rows[j].get("normalized_word_count", 0)
                    if li >= lj:
                        keep, drop = i, j
                    else:
                        keep, drop = j, i
                    is_dup[drop] = True
                    dup_of[drop] = rows[keep]["doc_id"]
                    near_dups += 1

    with open(OUT, "w", encoding="utf-8") as fout:
        for i, r in enumerate(rows):
            rec = {
                "doc_id": r["doc_id"],
                "filename": r["filename"],
                "original_path": r["original_path"],
                "file_type": r.get("file_type"),
                "extraction_status": r.get("extraction_status"),
                "normalized_word_count": r.get("normalized_word_count", 0),
                "too_short": r.get("too_short", False),
                "is_duplicate": bool(is_dup[i]),
                "duplicate_of": dup_of[i],
            }
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")

    total = len(rows)
    unique = sum(1 for x in is_dup if not x)
    print(f"Total: {total}")
    print(f"Exact duplicates: {exact_dups}")
    print(f"Near duplicates: {near_dups}")
    print(f"Unique (non-duplicate): {unique}")
    print(f"Wrote: {OUT}")


if __name__ == "__main__":
    main()
