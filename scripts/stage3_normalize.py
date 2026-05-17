"""Stage 3 — Normalize text per orchestrator spec.

1. NFKC unicode normalization
2. Collapse whitespace via " ".join(text.split())
3. Remove lines that are only digits or 'Page N of N' patterns
4. Flag too_short = True if < 50 words
"""
import json
import os
import re
import unicodedata

OUTPUT_FOLDER = r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\claude"
INP = os.path.join(OUTPUT_FOLDER, "s02_extracted.jsonl")
OUT = os.path.join(OUTPUT_FOLDER, "s03_normalized.jsonl")

DIGIT_LINE_RE = re.compile(r"^\s*\d+\s*$")
PAGE_RE = re.compile(r"^\s*page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE)
MAX_CHARS = 1_000_000  # head-tail cap; downstream truncates to 800 words anyway


def normalize(text: str) -> str:
    if not text:
        return ""
    # Pre-cap raw text head+tail to keep memory bounded (some PDFs extract 40MB+).
    if len(text) > MAX_CHARS:
        half = MAX_CHARS // 2
        text = text[:half] + "\n\n[...PRE_TRUNCATED...]\n\n" + text[-half:]
    text = unicodedata.normalize("NFKC", text)
    # Drop digit-only and "Page N of N" lines BEFORE whitespace collapse
    cleaned = []
    for line in text.split("\n"):
        if DIGIT_LINE_RE.match(line):
            continue
        if PAGE_RE.match(line):
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)
    # Collapse all whitespace
    text = " ".join(text.split())
    return text


def main():
    n_total = 0
    n_short = 0
    n_failed = 0
    with open(INP, "r", encoding="utf-8") as fin, open(OUT, "w", encoding="utf-8") as fout:
        for line in fin:
            r = json.loads(line)
            n_total += 1
            if r.get("extraction_status") != "success":
                n_failed += 1
                rec = {
                    "doc_id": r["doc_id"],
                    "filename": r["filename"],
                    "original_path": r["original_path"],
                    "file_type": r.get("file_type"),
                    "extraction_status": r["extraction_status"],
                    "normalized_text": "",
                    "normalized_word_count": 0,
                    "too_short": True,
                }
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                continue
            text = normalize(r.get("raw_text") or "")
            wc = len(text.split())
            too_short = wc < 50
            if too_short:
                n_short += 1
            rec = {
                "doc_id": r["doc_id"],
                "filename": r["filename"],
                "original_path": r["original_path"],
                "file_type": r.get("file_type"),
                "extraction_status": r["extraction_status"],
                "normalized_text": text,
                "normalized_word_count": wc,
                "too_short": too_short,
            }
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Normalized: total={n_total} extraction_failed={n_failed} too_short={n_short}")
    print(f"Wrote: {OUT}")


if __name__ == "__main__":
    main()
