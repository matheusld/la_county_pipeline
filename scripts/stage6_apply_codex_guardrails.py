"""Repair existing Codex/GPT Stage 6 scores with local rubric guardrails.

This script is for already-scored GPT runs. It:
- backs up gpt/s06_scored.jsonl once;
- recomputes keyword metadata from gpt/s03_normalized.jsonl;
- enforces Codex scoring guardrails on each row;
- rewrites only gpt/s06_scored.jsonl.

Claude files are never read or written.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison")
sys.path.insert(0, str(ROOT))

from scripts.codex_scoring_guardrails import (  # noqa: E402
    apply_keyword_floors,
    sanitize_score,
    truncate_words,
    write_jsonl,
)
from scripts.stage5_keyword import keyword_score_text  # noqa: E402


OUTPUT_FOLDER = ROOT / "gpt"
S03 = OUTPUT_FOLDER / "s03_normalized.jsonl"
S05 = OUTPUT_FOLDER / "s05_keyword_scored.jsonl"
S06 = OUTPUT_FOLDER / "s06_scored.jsonl"
BACKUP = OUTPUT_FOLDER / "s06_scored.pre_codex_guardrails.jsonl"


def load_prompt_texts() -> dict[str, str]:
    texts: dict[str, str] = {}
    with S03.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            texts.setdefault(row["doc_id"], truncate_words(row.get("normalized_text") or ""))
    return texts


def load_keyword_metadata() -> dict[str, tuple[float, list[str]]]:
    metadata: dict[str, tuple[float, list[str]]] = {}
    if not S05.exists():
        return metadata
    with S05.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            metadata[row["doc_id"]] = (
                float(row.get("keyword_score") or 0.0),
                row.get("keyword_matches") or [],
            )
    return metadata


def score_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    fields = [
        "score_carefirst",
        "score_ai_governance",
        "score_intersection",
        "score_evidentiary",
    ]
    return any(before.get(field) != after.get(field) for field in fields)


def main() -> int:
    if not S06.exists():
        print(f"Missing {S06}; run Stage 6 first.")
        return 2
    if not BACKUP.exists():
        shutil.copy2(S06, BACKUP)
        print(f"Backed up original scores to {BACKUP}")
    else:
        print(f"Using existing backup {BACKUP}")

    prompt_texts = load_prompt_texts()
    keyword_metadata = load_keyword_metadata()
    rows: list[dict[str, Any]] = []
    changed = 0
    guardrail_counts: Counter[str] = Counter()
    keyword_changed = 0

    with S06.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            prompt_text = prompt_texts.get(row["doc_id"], "")
            sanitized = sanitize_score(row, prompt_text)
            if row["doc_id"] in keyword_metadata:
                kw_score, kw_matches = keyword_metadata[row["doc_id"]]
            else:
                kw_score, kw_matches = keyword_score_text(prompt_text)
            sanitized = apply_keyword_floors(sanitized, kw_matches)
            if score_changed(row, sanitized):
                changed += 1
            for reason in sanitized.get("codex_guardrails", []):
                guardrail_counts[reason.split(":", 1)[0]] += 1

            if row.get("keyword_score") != round(kw_score, 4) or row.get("keyword_matches") != kw_matches:
                keyword_changed += 1

            row.update(
                {
                    "keyword_score": round(kw_score, 4),
                    "keyword_matches": kw_matches,
                    "score_carefirst": sanitized["score_carefirst"],
                    "score_ai_governance": sanitized["score_ai_governance"],
                    "score_intersection": sanitized["score_intersection"],
                    "score_evidentiary": sanitized["score_evidentiary"],
                }
            )
            row.pop("codex_guardrails", None)
            if sanitized.get("codex_guardrails"):
                row["codex_guardrails"] = sanitized["codex_guardrails"]
            row["codex_guardrails_version"] = "2026-05-12"
            rows.append(row)

    write_jsonl(S06, rows)
    print(
        json.dumps(
            {
                "rows": len(rows),
                "score_rows_changed": changed,
                "keyword_rows_changed": keyword_changed,
                "guardrail_counts": dict(guardrail_counts),
                "output": str(S06),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
