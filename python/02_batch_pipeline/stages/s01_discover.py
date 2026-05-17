"""
s01_discover.py - File discovery and inventory (Stage S01).

Walks each source directory, computes a content hash for every file,
and writes an inventory record. This is the foundation of the audit trail:
every document gets a stable doc_id (SHA-256 of content) that follows it
through every subsequent stage.

Cost: $0 (no API calls).

Error Sources:
    - Unreadable files (permissions, corruption) are logged and skipped.
    - Symlinks are not followed to avoid cycles.
    - Hidden files (starting with .) are skipped.

Usage:
    from stages.s01_discover import run_discovery
    records = run_discovery(config, logger, error_logger)
"""

import os
import json
from utils.provenance import hash_file
from utils.logging_utils import now_iso
from utils.schemas import InventoryRecord


def run_discovery(config: dict, logger, error_logger) -> list[dict]:
    """
    Walk all source directories and produce an inventory of every file.

    Args:
        config: Parsed pipeline_config.yaml.
        logger: Pipeline logger.
        error_logger: Error logger.

    Returns:
        List of InventoryRecord dicts, one per file.
        Also writes outputs/s01_inventory.jsonl.
    """
    sources = config.get("sources", {})
    output_dir = config.get("outputs", {}).get("base_dir", "./outputs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "s01_inventory.jsonl")

    records = []
    total_files = 0
    skipped = 0

    for source_name, source_cfg in sources.items():
        source_path = source_cfg["path"]
        expected_type = source_cfg["file_type"]

        if not os.path.isdir(source_path):
            error_logger.error(
                f"S01_DISCOVER | source={source_name} | "
                f"Directory not found: {source_path}"
            )
            continue

        folder_count = 0
        for root, dirs, files in os.walk(source_path, followlinks=False):
            for fname in files:
                # Skip hidden files
                if fname.startswith("."):
                    continue

                fpath = os.path.join(root, fname)

                # Check extension matches expected type
                ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                if ext != expected_type:
                    logger.debug(
                        f"S01_DISCOVER | Skipping non-{expected_type} file: {fpath}"
                    )
                    skipped += 1
                    continue

                try:
                    doc_id = hash_file(fpath)
                    file_size = os.path.getsize(fpath)
                except Exception as e:
                    error_logger.error(
                        f"S01_DISCOVER | file={fpath} | "
                        f"Cannot read file: {e}"
                    )
                    skipped += 1
                    continue

                record = InventoryRecord(
                    doc_id=doc_id,
                    filename=fname,
                    source_folder=source_name,
                    original_path=fpath,
                    file_type=ext,
                    file_size_bytes=file_size,
                    discovery_timestamp=now_iso(),
                )
                records.append(record.model_dump())
                folder_count += 1

        total_files += folder_count
        logger.info(
            f"S01_DISCOVER | source={source_name} | "
            f"Found {folder_count} {expected_type} files"
        )

    # Write output
    with open(output_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    logger.info(
        f"S01_DISCOVER | COMPLETE | "
        f"Total: {total_files} files inventoried, {skipped} skipped | "
        f"Output: {output_path}"
    )

    return records
