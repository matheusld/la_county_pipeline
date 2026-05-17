"""Stage 2 — Text Extraction.

PDF: pypdfium2 first (fast), pdfplumber fallback if pypdfium2 returns empty.
JSON/TXT as before. Resumable; parallelized with multiprocessing.
"""
import json
import logging
import multiprocessing as mp
import os
import sys
import warnings

warnings.filterwarnings("ignore")
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfplumber").setLevel(logging.ERROR)

OUTPUT_FOLDER = r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\claude"
INVENTORY = os.path.join(OUTPUT_FOLDER, "s01_inventory.jsonl")
OUT = os.path.join(OUTPUT_FOLDER, "s02_extracted.jsonl")

JSON_TEXT_KEYS = ["text", "normalized_text", "content", "body", "extracted_text"]


def extract_pdf_pdfium(path):
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(path)
        try:
            parts = []
            for i in range(len(pdf)):
                try:
                    page = pdf[i]
                    tp = page.get_textpage()
                    txt = tp.get_text_range() or ""
                    parts.append(txt)
                    tp.close()
                    page.close()
                except Exception:
                    parts.append("")
            return "\n".join(parts)
        finally:
            pdf.close()
    except Exception as e:
        return f"__EXTRACTION_ERROR__:{type(e).__name__}:{e}"


def extract_pdf_pdfplumber(path):
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:
                    parts.append("")
        return "\n".join(parts)
    except Exception as e:
        return f"__EXTRACTION_ERROR__:{type(e).__name__}:{e}"


def extract_pdf(path):
    """Use pypdfium2 first; fall back to pdfplumber if result is empty."""
    text = extract_pdf_pdfium(path)
    if isinstance(text, str) and text and not text.startswith("__EXTRACTION_ERROR__"):
        if text.strip():
            return text
    # Fallback
    return extract_pdf_pdfplumber(path)


def extract_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return f"__EXTRACTION_ERROR__:{type(e).__name__}:{e}"

    if isinstance(data, dict):
        for key in JSON_TEXT_KEYS:
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v
        chunks = []
        def walk(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)
            elif isinstance(obj, str) and len(obj) > 50:
                chunks.append(obj)
        walk(data)
        return "\n".join(chunks)
    if isinstance(data, list):
        chunks = []
        for item in data:
            if isinstance(item, str) and len(item) > 50:
                chunks.append(item)
            elif isinstance(item, dict):
                for key in JSON_TEXT_KEYS:
                    v = item.get(key)
                    if isinstance(v, str) and v.strip():
                        chunks.append(v)
                        break
        return "\n".join(chunks)
    return ""


def extract_txt(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"__EXTRACTION_ERROR__:{type(e).__name__}:{e}"


def extract_one(rec):
    path = rec["original_path"]
    ftype = rec["file_type"]
    if ftype == "pdf":
        text = extract_pdf(path)
    elif ftype == "json":
        text = extract_json(path)
    elif ftype == "txt":
        text = extract_txt(path)
    else:
        text = ""

    if isinstance(text, str) and text.startswith("__EXTRACTION_ERROR__"):
        return {
            "doc_id": rec["doc_id"],
            "filename": rec["filename"],
            "original_path": path,
            "file_type": ftype,
            "extraction_status": "failed",
            "text_length": 0,
            "raw_text": "",
            "extraction_error": text[len("__EXTRACTION_ERROR__:"):],
        }

    text = text or ""
    return {
        "doc_id": rec["doc_id"],
        "filename": rec["filename"],
        "original_path": path,
        "file_type": ftype,
        "extraction_status": "success" if text.strip() else "failed",
        "text_length": len(text),
        "raw_text": text,
    }


def main():
    seen = set()
    todo = []
    with open(INVENTORY, "r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["doc_id"] in seen:
                continue
            seen.add(r["doc_id"])
            todo.append(r)
    print(f"Unique doc_ids to extract: {len(todo)}", flush=True)

    already = set()
    if os.path.exists(OUT):
        with open(OUT, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    already.add(json.loads(line)["doc_id"])
                except Exception:
                    pass
        print(f"Resuming. Already extracted: {len(already)}", flush=True)
    todo = [r for r in todo if r["doc_id"] not in already]
    print(f"Remaining to extract: {len(todo)}", flush=True)

    if not todo:
        print("Nothing to do.", flush=True)
        return

    workers = max(1, min(12, (os.cpu_count() or 4)))
    print(f"Using {workers} workers", flush=True)

    successes = 0
    failures = 0
    written = 0

    with open(OUT, "a", encoding="utf-8") as fout:
        with mp.Pool(workers) as pool:
            for i, result in enumerate(pool.imap_unordered(extract_one, todo, chunksize=4), 1):
                fout.write(json.dumps(result, ensure_ascii=False) + "\n")
                fout.flush()
                written += 1
                if result["extraction_status"] == "success":
                    successes += 1
                else:
                    failures += 1
                if i % 200 == 0 or i == len(todo):
                    print(f"[{i}/{len(todo)}] success={successes} failed={failures}", flush=True)

    print(f"DONE: written={written} success={successes} failed={failures}", flush=True)


if __name__ == "__main__":
    main()
