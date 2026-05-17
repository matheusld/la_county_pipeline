"""Stage 1 — Inventory: walk input folders, compute SHA-256, write JSONL."""
import hashlib
import json
import os
import sys
from collections import Counter

INPUT_FOLDERS = [
    r"C:\Users\Matheus.Ligeiro\scrap_page\lacounty_analysis_docs",
    r"C:\Users\Matheus.Ligeiro\scrap_page\lacounty_keyword_docs",
    r"C:\Users\Matheus.Ligeiro\scrap_page\board_comms",
    r"C:\Users\Matheus.Ligeiro\Claude Code\Policy Research v3\evidence\county-docs",
    r"C:\Users\Matheus.Ligeiro\Claude Code\Policy Research\Batch 2\Public Record Request",
]
OUTPUT_FOLDER = r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\claude"
OUT = os.path.join(OUTPUT_FOLDER, "s01_inventory.jsonl")

ALLOWED_EXTS = {".pdf", ".json", ".txt"}


def hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    records = []
    type_counter = Counter()
    folder_counter = Counter()
    errors = 0

    for folder in INPUT_FOLDERS:
        if not os.path.isdir(folder):
            print(f"[WARN] missing input folder: {folder}", file=sys.stderr)
            continue
        for root, _, files in os.walk(folder):
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext not in ALLOWED_EXTS:
                    continue
                full = os.path.join(root, name)
                try:
                    size = os.path.getsize(full)
                    digest = hash_file(full)
                except Exception as e:
                    errors += 1
                    print(f"[ERR] {full}: {e}", file=sys.stderr)
                    continue
                file_type = ext.lstrip(".")
                rec = {
                    "doc_id": digest,
                    "filename": name,
                    "original_path": full,
                    "file_type": file_type,
                    "file_size_bytes": size,
                }
                records.append(rec)
                type_counter[file_type] += 1
                folder_counter[folder] += 1

    with open(OUT, "w", encoding="utf-8") as fout:
        for r in records:
            fout.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Total files: {len(records)}")
    print(f"By type: {dict(type_counter)}")
    print(f"By folder:")
    for k, v in folder_counter.items():
        print(f"  {v:>5}  {k}")
    print(f"Read errors: {errors}")
    print(f"Wrote: {OUT}")


if __name__ == "__main__":
    main()
