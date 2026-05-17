"""Stage 6 collect — read batch_*_result.json files written by sub-agents,
parse into ScoredRecord rows, and append new ones to s06_scored.jsonl.

Idempotent: skips doc_ids already present in s06_scored.jsonl.
"""
import json
import os

OUTPUT_FOLDER = r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\claude"
SCRATCH = os.path.join(OUTPUT_FOLDER, "scratch")
MANIFEST = os.path.join(SCRATCH, "batches.jsonl")
S06 = os.path.join(OUTPUT_FOLDER, "s06_scored.jsonl")

DEFAULT_SCORE = {"score_carefirst": 0, "score_ai_governance": 0,
                 "score_intersection": 0, "score_evidentiary": 0,
                 "rationale": ""}


def parse_agent_json(text: str):
    """Pull a JSON array out of agent output. Tolerates fences and prose."""
    if not text:
        return None
    s = text.strip()
    # Strip fences
    if s.startswith("```"):
        # remove leading fence line
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1:]
        # remove trailing fence
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    # Find first '[' and last ']'
    a = s.find("[")
    b = s.rfind("]")
    if a == -1 or b == -1 or b < a:
        return None
    candidate = s[a:b + 1]
    try:
        arr = json.loads(candidate)
        return arr if isinstance(arr, list) else None
    except json.JSONDecodeError:
        return None


def main():
    already = set()
    if os.path.exists(S06):
        with open(S06, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    already.add(json.loads(line)["doc_id"])
                except Exception:
                    pass

    if not os.path.exists(MANIFEST):
        print("No batch manifest found.")
        return

    batches = []
    with open(MANIFEST, "r", encoding="utf-8") as f:
        for line in f:
            batches.append(json.loads(line))

    new_rows = 0
    err_rows = 0
    missing_batches = 0

    with open(S06, "a", encoding="utf-8") as fout:
        for b in batches:
            rp = b["result_path"]
            if not os.path.exists(rp):
                missing_batches += 1
                continue
            with open(rp, "r", encoding="utf-8") as f:
                raw = f.read()
            arr = parse_agent_json(raw)

            doc_ids = b["doc_ids"]
            filenames = b["filenames"]
            paths = b["original_paths"]
            kscores = b["keyword_scores"]
            kmatches = b["keyword_matches"]

            # Build doc_id -> score map from agent output
            by_id = {}
            if isinstance(arr, list):
                for o in arr:
                    if isinstance(o, dict) and "doc_id" in o:
                        by_id[o["doc_id"]] = o

            # Fallback: if agent returned the same count but with wrong/typo'd doc_ids,
            # match positionally. Trust position only when length matches input exactly.
            position_map = {}
            if isinstance(arr, list) and len(arr) == len(doc_ids):
                position_map = {doc_ids[i]: arr[i] for i in range(len(arr)) if isinstance(arr[i], dict)}

            for i, did in enumerate(doc_ids):
                if did in already:
                    continue
                obj = by_id.get(did)
                err = None
                if not obj:
                    obj = position_map.get(did)
                    if obj:
                        err = "matched by position (doc_id mismatch)"
                if not obj:
                    obj = DEFAULT_SCORE
                    err = "agent returned no score"
                try:
                    cf = int(obj.get("score_carefirst", 0))
                    ag = int(obj.get("score_ai_governance", 0))
                    ix = int(obj.get("score_intersection", 0))
                    ev = int(obj.get("score_evidentiary", 0))
                except Exception:
                    cf = ag = ix = ev = 0
                    err = err or "score parse error"
                if err:
                    err_rows += 1
                row = {
                    "doc_id": did,
                    "filename": filenames[i],
                    "original_path": paths[i],
                    "keyword_score": kscores[i],
                    "keyword_matches": kmatches[i],
                    "score_carefirst": cf,
                    "score_ai_governance": ag,
                    "score_intersection": ix,
                    "score_evidentiary": ev,
                    "rationale": obj.get("rationale", "") if isinstance(obj, dict) else "",
                    "score_error": err,
                    "scored_by": "claude-haiku-4-5-20251001",
                }
                fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                already.add(did)
                new_rows += 1

    print(f"Appended {new_rows} rows ({err_rows} with score_error). "
          f"Missing batches: {missing_batches}.")


if __name__ == "__main__":
    main()
