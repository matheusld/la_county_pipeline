"""Collect local subagent Stage 6 batch results into gpt/s06_scored.jsonl."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison")
sys.path.insert(0, str(ROOT))

from scripts.codex_scoring_guardrails import (  # noqa: E402
    apply_keyword_floors,
    sanitize_score,
    truncate_words,
)
from scripts.stage5_keyword import keyword_score_text  # noqa: E402

OUTPUT_FOLDER = Path(r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\gpt")
SCRATCH = OUTPUT_FOLDER / "local_s06_batches"
MANIFEST = SCRATCH / "manifest.jsonl"
S06 = OUTPUT_FOLDER / "s06_scored.jsonl"
S03 = OUTPUT_FOLDER / "s03_normalized.jsonl"
SCORED_BY = "gpt-5.4-mini-local-agents"


def parse_json_array(text: str) -> list[dict[str, Any]] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, list) else None


def clamp_score(value: Any) -> int:
    try:
        return max(0, min(10, int(value)))
    except Exception:
        return 0


def existing_doc_ids() -> set[str]:
    found: set[str] = set()
    if not S06.exists():
        return found
    with S06.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                found.add(json.loads(line)["doc_id"])
            except Exception:
                pass
    return found


def load_texts() -> dict[str, str]:
    texts: dict[str, str] = {}
    if not S03.exists():
        return texts
    with S03.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            texts.setdefault(row["doc_id"], row.get("normalized_text") or "")
    return texts


def main() -> int:
    already = existing_doc_ids()
    texts = load_texts()
    batches = []
    with MANIFEST.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                batches.append(json.loads(line))

    appended = 0
    error_rows = 0
    missing_batches = 0
    parsed_batches = 0

    with S06.open("a", encoding="utf-8", errors="replace") as out:
        for batch in batches:
            result_path = Path(batch["result_path"])
            if not result_path.exists():
                missing_batches += 1
                continue
            parsed = parse_json_array(result_path.read_text(encoding="utf-8", errors="replace"))
            if parsed is None:
                parsed = []
                batch_error = "malformed local agent output"
            else:
                parsed_batches += 1
                batch_error = None
            by_id = {
                item.get("doc_id"): item
                for item in parsed
                if isinstance(item, dict) and item.get("doc_id")
            }
            for index, doc_id in enumerate(batch["doc_ids"]):
                if doc_id in already:
                    continue
                obj = by_id.get(doc_id)
                score_error = batch_error
                if obj is None:
                    obj = {}
                    score_error = score_error or "missing score for doc_id"
                prompt_text = truncate_words(texts.get(doc_id, ""))
                kw_score, kw_matches = keyword_score_text(texts.get(doc_id, ""))
                obj = sanitize_score(obj, prompt_text)
                obj = apply_keyword_floors(obj, kw_matches)
                if score_error:
                    error_rows += 1
                row = {
                    "doc_id": doc_id,
                    "filename": batch["filenames"][index],
                    "original_path": batch["original_paths"][index],
                    "keyword_score": round(kw_score, 4),
                    "keyword_matches": kw_matches,
                    "score_carefirst": clamp_score(obj.get("score_carefirst")),
                    "score_ai_governance": clamp_score(obj.get("score_ai_governance")),
                    "score_intersection": clamp_score(obj.get("score_intersection")),
                    "score_evidentiary": clamp_score(obj.get("score_evidentiary")),
                    "rationale": str(obj.get("rationale", ""))[:500],
                    "score_error": score_error,
                    "scored_by": SCORED_BY,
                }
                if obj.get("codex_guardrails"):
                    row["codex_guardrails"] = obj["codex_guardrails"]
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                already.add(doc_id)
                appended += 1

    print(
        json.dumps(
            {
                "manifest_batches": len(batches),
                "parsed_batches": parsed_batches,
                "missing_batches": missing_batches,
                "appended_rows": appended,
                "error_rows": error_rows,
                "total_scored_rows": len(already),
                "output": str(S06),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
