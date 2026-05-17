"""Stage 6 prep — Build per-batch prompt files and a manifest.

Each batch has up to 20 eligible docs. Eligible: extraction_status=success,
is_duplicate=false, too_short=false, and not already scored in s06_scored.jsonl.

Truncation: head-tail 400+400 words.

Outputs:
  claude/scratch/batches.jsonl — manifest, one row per batch
  claude/scratch/batch_NNNN_prompt.txt — full scorer prompt for the batch
"""
import json
import os
from pathlib import Path

OUTPUT_FOLDER = r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\claude"
SCRATCH = os.path.join(OUTPUT_FOLDER, "scratch")
S05 = os.path.join(OUTPUT_FOLDER, "s05_keyword_scored.jsonl")
S03 = os.path.join(OUTPUT_FOLDER, "s03_normalized.jsonl")
S06 = os.path.join(OUTPUT_FOLDER, "s06_scored.jsonl")
PROMPT_TEMPLATE = r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\prompts\scorer_agent.md"

BATCH_SIZE = 20
HEAD = 400
TAIL = 400


def head_tail(text: str, head: int = HEAD, tail: int = TAIL) -> str:
    words = text.split()
    if len(words) <= head + tail:
        return text
    return " ".join(words[:head]) + "\n\n[...TRUNCATED...]\n\n" + " ".join(words[-tail:])


def main():
    os.makedirs(SCRATCH, exist_ok=True)

    # Resume — read already-scored doc_ids
    already = set()
    if os.path.exists(S06):
        with open(S06, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    already.add(json.loads(line)["doc_id"])
                except Exception:
                    pass

    # Load normalized text by doc_id
    text_by_id = {}
    with open(S03, "r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            text_by_id.setdefault(r["doc_id"], r.get("normalized_text") or "")

    # Eligible docs from s05
    eligible = []
    seen = set()
    with open(S05, "r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            doc_id = r["doc_id"]
            if doc_id in seen:
                continue
            seen.add(doc_id)
            if r.get("is_duplicate"): continue
            if r.get("too_short"): continue
            if r.get("extraction_status") != "success": continue
            if doc_id in already: continue
            eligible.append(r)

    eligible.sort(key=lambda r: r["doc_id"])

    with open(PROMPT_TEMPLATE, "r", encoding="utf-8") as f:
        template = f.read()

    manifest = []
    n_batches = (len(eligible) + BATCH_SIZE - 1) // BATCH_SIZE

    for bi in range(n_batches):
        chunk = eligible[bi * BATCH_SIZE:(bi + 1) * BATCH_SIZE]
        parts = []
        for j, r in enumerate(chunk, 1):
            txt = head_tail(text_by_id.get(r["doc_id"], ""))
            parts.append(
                f"--- DOCUMENT {j} ---\n"
                f"doc_id: {r['doc_id']}\n"
                f"filename: {r['filename']}\n"
                f"keyword_score: {r.get('keyword_score', 0.0)}\n\n"
                f"{txt}\n"
            )
        documents = "\n".join(parts)
        prompt = template.replace("{{DOCUMENTS}}", documents)

        prompt_path = os.path.join(SCRATCH, f"batch_{bi:04d}_prompt.txt")
        result_path = os.path.join(SCRATCH, f"batch_{bi:04d}_result.json")
        with open(prompt_path, "w", encoding="utf-8") as fp:
            fp.write(prompt)

        manifest.append({
            "batch_id": bi,
            "n_docs": len(chunk),
            "doc_ids": [r["doc_id"] for r in chunk],
            "filenames": [r["filename"] for r in chunk],
            "original_paths": [r["original_path"] for r in chunk],
            "keyword_scores": [r.get("keyword_score", 0.0) for r in chunk],
            "keyword_matches": [r.get("keyword_matches", []) for r in chunk],
            "prompt_path": prompt_path,
            "result_path": result_path,
        })

    manifest_path = os.path.join(SCRATCH, "batches.jsonl")
    with open(manifest_path, "w", encoding="utf-8") as f:
        for row in manifest:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Eligible docs: {len(eligible)}")
    print(f"Already scored (skipped): {len(already)}")
    print(f"Batches: {n_batches}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
