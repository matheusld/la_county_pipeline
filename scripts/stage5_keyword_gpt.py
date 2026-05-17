"""Stage 5 — recompute keyword scores for the Codex/GPT output folder.

This intentionally leaves the Claude folder untouched. It reuses the current
keyword matcher from scripts/stage5_keyword.py and writes only gpt/s05.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison")
sys.path.insert(0, str(ROOT))

from scripts.stage5_keyword import keyword_score_text  # noqa: E402


OUTPUT_FOLDER = ROOT / "gpt"
DEDUP = OUTPUT_FOLDER / "s04_deduped.jsonl"
NORM = OUTPUT_FOLDER / "s03_normalized.jsonl"
OUT = OUTPUT_FOLDER / "s05_keyword_scored.jsonl"


def main() -> int:
    n = 0
    n_scored = 0
    with NORM.open("r", encoding="utf-8", errors="replace") as fnorm, DEDUP.open(
        "r", encoding="utf-8", errors="replace"
    ) as fdedup, OUT.open("w", encoding="utf-8", errors="replace") as fout:
        for nline, dline in zip(fnorm, fdedup):
            nrec = json.loads(nline)
            drec = json.loads(dline)
            if nrec["doc_id"] != drec["doc_id"]:
                raise RuntimeError(
                    f"Order mismatch at row {n}: norm={nrec['doc_id']} dedup={drec['doc_id']}"
                )
            n += 1
            if (
                drec.get("is_duplicate")
                or drec.get("too_short")
                or drec.get("extraction_status") != "success"
            ):
                kw_score = 0.0
                kw_matches: list[str] = []
            else:
                kw_score, kw_matches = keyword_score_text(nrec.get("normalized_text") or "")
                n_scored += 1
            drec["keyword_score"] = round(kw_score, 4)
            drec["keyword_matches"] = kw_matches
            fout.write(json.dumps(drec, ensure_ascii=False) + "\n")
            if n % 1000 == 0:
                print(f"  processed {n}", flush=True)

    print(f"Total rows: {n}, keyword-scored: {n_scored}")
    print(f"Wrote: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
