"""Stage 6 — score eligible documents with OpenAI, 20 documents per call.

Matches prompts/orchestrator_codex.md:
- loads existing s06_scored.jsonl and skips already scored doc_ids;
- truncates normalized text to first 400 + last 400 words;
- sends batches of 20 documents using prompts/scorer_agent.md;
- appends to s06_scored.jsonl after every batch.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from openai import OpenAI


ROOT = Path(r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison")
sys.path.insert(0, str(ROOT))

from scripts.codex_scoring_guardrails import (  # noqa: E402
    apply_keyword_floors,
    codex_prompt_template,
    format_documents_for_prompt,
    sanitize_score,
    truncate_words,
)
from scripts.stage5_keyword import keyword_score_text  # noqa: E402

OUTPUT_FOLDER = ROOT / "gpt"
S03 = OUTPUT_FOLDER / "s03_normalized.jsonl"
S05 = OUTPUT_FOLDER / "s05_keyword_scored.jsonl"
S06 = OUTPUT_FOLDER / "s06_scored.jsonl"
SCORER_PROMPT = ROOT / "prompts" / "scorer_agent.md"
BATCH_SIZE = 20
MODEL = os.environ.get("OPENAI_SCORING_MODEL", "gpt-4o-mini")


def load_existing() -> set[str]:
    scored: set[str] = set()
    if not S06.exists():
        return scored
    with S06.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                scored.add(json.loads(line)["doc_id"])
            except Exception:
                pass
    return scored


def extract_json_array(text: str) -> list[dict[str, Any]] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def default_score(doc_id: str, error: str) -> dict[str, Any]:
    return {
        "doc_id": doc_id,
        "score_carefirst": 0,
        "score_ai_governance": 0,
        "score_intersection": 0,
        "score_evidentiary": 0,
        "rationale": "",
        "score_error": error,
    }


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set; cannot run Stage 6 scoring.")
        return 2

    already = load_existing()
    eligible: list[dict[str, Any]] = []
    with S05.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r["doc_id"] in already:
                continue
            if r.get("is_duplicate"):
                continue
            if r.get("too_short"):
                continue
            if r.get("extraction_status") != "success":
                continue
            eligible.append(r)

    needed = {r["doc_id"] for r in eligible}
    full_text_by_id: dict[str, str] = {}
    prompt_text_by_id: dict[str, str] = {}
    with S03.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            doc_id = r["doc_id"]
            if doc_id in needed and doc_id not in full_text_by_id:
                full_text = r.get("normalized_text") or ""
                full_text_by_id[doc_id] = full_text
                prompt_text_by_id[doc_id] = truncate_words(full_text)

    template = codex_prompt_template(SCORER_PROMPT.read_text(encoding="utf-8"))
    client = OpenAI()
    print(
        json.dumps(
            {
                "already_scored": len(already),
                "eligible_to_score": len(eligible),
                "batches": (len(eligible) + BATCH_SIZE - 1) // BATCH_SIZE,
                "model": MODEL,
            }
        ),
        flush=True,
    )

    with S06.open("a", encoding="utf-8", errors="replace") as out:
        for batch_start in range(0, len(eligible), BATCH_SIZE):
            batch = eligible[batch_start : batch_start + BATCH_SIZE]
            prompt = template.replace("{{DOCUMENTS}}", format_documents_for_prompt(batch, prompt_text_by_id))
            score_error = None
            parsed: list[dict[str, Any]] | None = None
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    temperature=0,
                    messages=[{"role": "user", "content": prompt}],
                )
                content = response.choices[0].message.content or ""
                parsed = extract_json_array(content)
                if parsed is None:
                    score_error = "malformed model output"
            except Exception as exc:
                score_error = str(exc)

            by_id: dict[str, dict[str, Any]] = {}
            if parsed is not None:
                for obj in parsed:
                    if isinstance(obj, dict) and obj.get("doc_id"):
                        by_id[obj["doc_id"]] = obj

            for rec in batch:
                doc_id = rec["doc_id"]
                obj = by_id.get(doc_id) if score_error is None else None
                if obj is None:
                    obj = default_score(doc_id, score_error or "missing score for doc_id")
                kw_score, kw_matches = keyword_score_text(full_text_by_id.get(doc_id, ""))
                obj = sanitize_score(obj, prompt_text_by_id.get(doc_id, ""))
                obj = apply_keyword_floors(obj, kw_matches)
                row = {
                    "doc_id": doc_id,
                    "filename": rec["filename"],
                    "original_path": rec["original_path"],
                    "keyword_score": round(kw_score, 4),
                    "keyword_matches": kw_matches,
                    "score_carefirst": obj.get("score_carefirst", 0),
                    "score_ai_governance": obj.get("score_ai_governance", 0),
                    "score_intersection": obj.get("score_intersection", 0),
                    "score_evidentiary": obj.get("score_evidentiary", 0),
                    "rationale": str(obj.get("rationale", ""))[:500],
                    "score_error": obj.get("score_error"),
                    "scored_by": MODEL,
                }
                if obj.get("codex_guardrails"):
                    row["codex_guardrails"] = obj["codex_guardrails"]
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            done = min(batch_start + BATCH_SIZE, len(eligible))
            print(f"scored {done}/{len(eligible)}", flush=True)
            time.sleep(0.1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
