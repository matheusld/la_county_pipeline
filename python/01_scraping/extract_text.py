#!/usr/bin/env python3
"""
Phase 1: Extract text from all Transcript and SOP PDFs.
Saves extracted text to ./extracted_text/ as JSON files.
Uses parallel processing to speed things up.

  pip install pdfplumber
  python extract_text.py
  python extract_text.py --workers 8   # more parallel workers
"""

import argparse
import json
import logging
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def p(msg):
    print(msg, flush=True)


def classify_doc_type(filename: str) -> str:
    name = filename.lower()
    if "transcript" in name:
        return "transcript"
    elif "statement_of_proceedings" in name:
        return "sop"
    return "supporting"


def parse_date_from_filename(filename: str) -> str:
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", filename)
    return m.group(1) if m else ""


def process_one(args):
    """Worker function — runs in a separate process."""
    pdf_path_str, out_path_str = args
    pdf_path = Path(pdf_path_str)
    out_path = Path(out_path_str)

    if out_path.exists():
        return ("skipped", pdf_path.name, 0)

    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        text = "\n".join(text_parts)
    except Exception as exc:
        return ("failed", pdf_path.name, str(exc))

    doc = {
        "filename":     pdf_path.name,
        "doc_type":     classify_doc_type(pdf_path.name),
        "meeting_date": parse_date_from_filename(pdf_path.name),
        "file_size_kb": round(pdf_path.stat().st_size / 1024, 1),
        "text":         text,
        "char_count":   len(text),
        "word_count":   len(text.split()),
    }
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return ("ok", pdf_path.name, doc["word_count"])


def main():
    parser = argparse.ArgumentParser(description="Extract PDF text (parallel)")
    parser.add_argument("--folder",     default="./lacounty_keyword_docs")
    parser.add_argument("--output-dir", default="./extracted_text")
    parser.add_argument("--doc-types",  nargs="+",
                        choices=["transcript", "sop", "supporting"],
                        default=["transcript", "sop"])
    parser.add_argument("--workers",    type=int, default=4,
                        help="Parallel workers (default: 4, try 6-8 on your machine)")
    parser.add_argument("--limit",      type=int, default=None)
    args = parser.parse_args()

    folder     = Path(args.folder)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_pdfs = list(folder.glob("*.pdf"))
    targets  = [f for f in all_pdfs
                if classify_doc_type(f.name) in args.doc_types]
    if args.limit:
        targets = targets[:args.limit]

    p(f"Found {len(targets)} files to process (workers={args.workers})")

    # Build work items
    work = [
        (str(f), str(output_dir / (f.stem + ".json")))
        for f in targets
    ]

    ok = fail = skipped = total_words = 0
    done = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_one, item): item for item in work}
        for future in as_completed(futures):
            done += 1
            status, name, extra = future.result()
            if status == "ok":
                ok += 1
                total_words += extra
                p(f"  [{done}/{len(work)}] OK       {name} ({extra:,} words)")
            elif status == "skipped":
                skipped += 1
                p(f"  [{done}/{len(work)}] SKIP     {name}")
            else:
                fail += 1
                p(f"  [{done}/{len(work)}] FAILED   {name}: {extra}")

    p(f"\nDone. {ok} extracted, {skipped} skipped, {fail} failed.")
    p(f"Total words : {total_words:,}")
    p(f"Est. tokens : {total_words * 1.3:,.0f}")
    p(f"Output      : {output_dir.resolve()}")


if __name__ == "__main__":
    main()