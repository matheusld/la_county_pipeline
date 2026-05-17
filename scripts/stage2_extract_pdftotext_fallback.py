"""Fast Stage 2 extraction fallback for remaining PDFs.

The requested Codex pipeline began with pdfplumber extraction. On this corpus,
large transcript PDFs made that path unstable and very slow, so this fallback
finishes only records not already present in s02_extracted.jsonl using the local
Poppler pdftotext executable. The output schema remains exactly the Stage 2
schema from prompts/orchestrator_codex.md.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


OUTPUT_FOLDER = Path(r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\gpt")
INVENTORY_PATH = OUTPUT_FOLDER / "s01_inventory.jsonl"
EXTRACTED_PATH = OUTPUT_FOLDER / "s02_extracted.jsonl"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"Skipping malformed JSONL line {line_no} in {path}", file=sys.stderr)
    return records


def extract_pdf(path: str, timeout_s: int = 180) -> tuple[str, str | None]:
    try:
        cp = subprocess.run(
            ["pdftotext", "-layout", path, "-"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout_s,
        )
    except Exception as exc:
        return "", str(exc)
    if cp.returncode != 0:
        return "", cp.stderr.strip() or f"pdftotext exited {cp.returncode}"
    return cp.stdout, None


def extract_one(rec: dict[str, Any]) -> dict[str, Any]:
    raw_text = ""
    error = None
    try:
        if rec["file_type"] == "pdf":
            raw_text, error = extract_pdf(rec["original_path"])
        elif rec["file_type"] == "json":
            with open(rec["original_path"], "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for key in ("text", "normalized_text", "content", "body"):
                    if data.get(key) is not None:
                        raw_text = str(data[key])
                        break
            else:
                raw_text = str(data)
        elif rec["file_type"] == "txt":
            with open(rec["original_path"], "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read()
    except Exception as exc:
        error = str(exc)
        raw_text = ""

    status = "failed" if error else "success"
    return {
        "doc_id": rec["doc_id"],
        "filename": rec["filename"],
        "original_path": rec["original_path"],
        "file_type": rec["file_type"],
        "extraction_status": status,
        "text_length": len(raw_text),
        "raw_text": raw_text,
        "_error": error,
    }


def clone_for_path(base: dict[str, Any], rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": rec["doc_id"],
        "filename": rec["filename"],
        "original_path": rec["original_path"],
        "file_type": rec["file_type"],
        "extraction_status": base.get("extraction_status", "failed"),
        "text_length": base.get("text_length", 0),
        "raw_text": base.get("raw_text", ""),
    }


def write_record(handle, rec: dict[str, Any]) -> None:
    clean = {k: v for k, v in rec.items() if not k.startswith("_")}
    handle.write(json.dumps(clean, ensure_ascii=False) + "\n")
    handle.flush()


def main() -> int:
    workers = int(os.environ.get("PDFTEXT_WORKERS", "12"))
    inventory = load_jsonl(INVENTORY_PATH)
    existing = load_jsonl(EXTRACTED_PATH)

    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    first_by_doc: dict[str, dict[str, Any]] = {}
    for rec in inventory:
        by_doc[rec["doc_id"]].append(rec)
        first_by_doc.setdefault(rec["doc_id"], rec)

    existing_paths = {r["original_path"] for r in existing}
    cache_by_doc: dict[str, dict[str, Any]] = {}
    for rec in existing:
        cache_by_doc.setdefault(rec["doc_id"], rec)

    todo = [
        first_by_doc[doc_id]
        for doc_id in first_by_doc
        if doc_id not in cache_by_doc
    ]

    print(
        json.dumps(
            {
                "inventory_records": len(inventory),
                "existing_records": len(existing),
                "unique_docs_to_extract": len(todo),
                "workers": workers,
            }
        ),
        flush=True,
    )

    start = time.time()
    written = 0
    failures = 0
    with EXTRACTED_PATH.open("a", encoding="utf-8", errors="replace") as out:
        for doc_id, base in list(cache_by_doc.items()):
            for rec in by_doc.get(doc_id, []):
                if rec["original_path"] not in existing_paths:
                    write_record(out, clone_for_path(base, rec))
                    existing_paths.add(rec["original_path"])
                    written += 1

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(extract_one, rec): rec for rec in todo}
            for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
                source_rec = futures[future]
                try:
                    base = future.result()
                except Exception as exc:
                    base = {
                        "doc_id": source_rec["doc_id"],
                        "filename": source_rec["filename"],
                        "original_path": source_rec["original_path"],
                        "file_type": source_rec["file_type"],
                        "extraction_status": "failed",
                        "text_length": 0,
                        "raw_text": "",
                        "_error": str(exc),
                    }
                if base.get("extraction_status") == "failed":
                    failures += 1
                    print(
                        f"EXTRACT_ERROR\t{base['doc_id'][:12]}\t"
                        f"{source_rec['original_path']}\t{base.get('_error')}",
                        file=sys.stderr,
                        flush=True,
                    )
                for rec in by_doc[base["doc_id"]]:
                    if rec["original_path"] not in existing_paths:
                        write_record(out, clone_for_path(base, rec))
                        existing_paths.add(rec["original_path"])
                        written += 1
                if completed % 250 == 0:
                    elapsed = time.time() - start
                    print(
                        f"progress unique_completed={completed} "
                        f"records_written_new={written} failures={failures} "
                        f"elapsed_s={elapsed:.1f}",
                        flush=True,
                    )

    print(
        json.dumps(
            {
                "inventory_records": len(inventory),
                "total_records_written": len(existing_paths),
                "new_records_written": written,
                "unique_failures_new": failures,
                "output": str(EXTRACTED_PATH),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
