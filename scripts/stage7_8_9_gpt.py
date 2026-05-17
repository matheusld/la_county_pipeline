"""Stages 7-9 for the Codex GPT output folder."""

from __future__ import annotations

import csv
import json
import math
import random
from pathlib import Path
from typing import Any


OUTPUT_FOLDER = Path(r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\gpt")
S03 = OUTPUT_FOLDER / "s03_normalized.jsonl"
S06 = OUTPUT_FOLDER / "s06_scored.jsonl"
S07 = OUTPUT_FOLDER / "s07_ranked.jsonl"
S08 = OUTPUT_FOLDER / "s08_spotcheck.csv"
S09_JSONL = OUTPUT_FOLDER / "s09_shortlist.jsonl"
S09_CSV = OUTPUT_FOLDER / "s09_shortlist.csv"


def composite(row: dict[str, Any]) -> float:
    return (
        (row.get("score_carefirst") or 0) * 0.25
        + (row.get("score_ai_governance") or 0) * 0.25
        + (row.get("score_intersection") or 0) * 0.35
        + (row.get("score_evidentiary") or 0) * 0.15
    )


def tier_for(score: float, carefirst: int, ai_governance: int) -> int:
    if score >= 6.0 and (carefirst >= 5 or ai_governance >= 5):
        return 1
    if score >= 3.5:
        return 2
    if score >= 1.0:
        return 3
    return 4


def text_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    with S03.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            lookup.setdefault(row["doc_id"], row.get("normalized_text") or "")
    return lookup


def main() -> int:
    if not S06.exists():
        print(f"Missing {S06}; run Stage 6 first.")
        return 2

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with S06.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["doc_id"] in seen:
                continue
            seen.add(row["doc_id"])
            score = composite(row)
            row["composite"] = round(score, 4)
            row["tier"] = tier_for(
                score,
                int(row.get("score_carefirst") or 0),
                int(row.get("score_ai_governance") or 0),
            )
            rows.append(row)

    with S07.open("w", encoding="utf-8", errors="replace") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    texts = text_lookup()

    low_pool = [r for r in rows if r.get("tier") in (3, 4)]
    sample_size = math.ceil(len(low_pool) * 0.10)
    sample = random.Random(42).sample(low_pool, k=sample_size) if sample_size else []
    with S08.open("w", encoding="utf-8", newline="", errors="replace") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "doc_id",
                "filename",
                "tier",
                "composite",
                "score_carefirst",
                "score_ai_governance",
                "score_intersection",
                "score_evidentiary",
                "keyword_score",
                "rationale",
                "text_preview",
                "review_status",
                "reviewer_notes",
            ]
        )
        for row in sample:
            preview = " ".join(texts.get(row["doc_id"], "").split()[:400])
            writer.writerow(
                [
                    row["doc_id"],
                    row["filename"],
                    row.get("tier"),
                    row.get("composite"),
                    row.get("score_carefirst"),
                    row.get("score_ai_governance"),
                    row.get("score_intersection"),
                    row.get("score_evidentiary"),
                    row.get("keyword_score"),
                    row.get("rationale"),
                    preview,
                    "",
                    "",
                ]
            )

    selected = [r for r in rows if r.get("tier") in (1, 2)]
    if len(selected) < 167:
        tier3 = sorted(
            [r for r in rows if r.get("tier") == 3],
            key=lambda r: r.get("composite", 0),
            reverse=True,
        )
        selected.extend(tier3[: 167 - len(selected)])
    selected.sort(key=lambda r: r.get("composite", 0), reverse=True)
    for rank, row in enumerate(selected, 1):
        row["rank"] = rank

    with S09_JSONL.open("w", encoding="utf-8", errors="replace") as f:
        for row in selected:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with S09_CSV.open("w", encoding="utf-8", newline="", errors="replace") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "rank",
                "doc_id",
                "filename",
                "original_path",
                "tier",
                "composite",
                "score_carefirst",
                "score_ai_governance",
                "score_intersection",
                "score_evidentiary",
                "keyword_score",
                "keyword_matches",
                "rationale",
                "text_preview",
            ]
        )
        for row in selected:
            preview = " ".join(texts.get(row["doc_id"], "").split()[:300])
            matches = row.get("keyword_matches") or []
            writer.writerow(
                [
                    row.get("rank"),
                    row["doc_id"],
                    row["filename"],
                    row.get("original_path"),
                    row.get("tier"),
                    row.get("composite"),
                    row.get("score_carefirst"),
                    row.get("score_ai_governance"),
                    row.get("score_intersection"),
                    row.get("score_evidentiary"),
                    row.get("keyword_score"),
                    ";".join(matches) if isinstance(matches, list) else str(matches),
                    row.get("rationale"),
                    preview,
                ]
            )

    counts = {tier: sum(1 for r in rows if r.get("tier") == tier) for tier in (1, 2, 3, 4)}
    print(
        json.dumps(
            {
                "ranked": len(rows),
                "tier_counts": counts,
                "spotcheck": len(sample),
                "shortlist": len(selected),
                "shortlist_csv": str(S09_CSV),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
