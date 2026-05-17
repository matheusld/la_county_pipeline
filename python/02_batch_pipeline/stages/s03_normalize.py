"""
s03_normalize.py - Text normalization and cleanup (Stage S03).

Applies deterministic text cleaning:
    - Unicode normalization (NFKD)
    - Whitespace collapsing
    - Header/footer stripping via configurable regex patterns
    - Truncation of excessively long documents with logging

Cost: $0 (no API calls).

Error Sources:
    - Encoding issues in extracted text (handled by errors="replace" upstream).
    - Over-aggressive regex stripping could remove relevant content. The
      strip_patterns in config should be reviewed for each corpus.
    - Truncation loses content. The truncation_point is logged so downstream
      analysis can assess whether truncated documents need full-text review.

Usage:
    from stages.s03_normalize import run_normalization
    records = run_normalization(config, extracted_records, logger)
"""

import json
import os
import re
import unicodedata
from utils.logging_utils import now_iso
from utils.schemas import NormalizedRecord


def _normalize_text(text: str, config: dict) -> tuple[str, bool, int | None]:
    """
    Clean and normalize a text string.

    Returns: (normalized_text, was_truncated, truncation_point)
    """
    norm_cfg = config.get("normalization", {})

    # Unicode normalization
    if norm_cfg.get("unicode_normalize", True):
        text = unicodedata.normalize("NFKD", text)

    # Strip matching lines
    strip_patterns = norm_cfg.get("strip_patterns", [])
    if strip_patterns:
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            skip = False
            for pattern in strip_patterns:
                if re.match(pattern, stripped):
                    skip = True
                    break
            if not skip:
                cleaned_lines.append(line)
        text = "\n".join(cleaned_lines)

    # Collapse whitespace
    if norm_cfg.get("collapse_whitespace", True):
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

    # Truncation
    max_len = norm_cfg.get("max_text_length", 50000)
    was_truncated = False
    truncation_point = None
    if len(text) > max_len:
        was_truncated = True
        truncation_point = max_len
        text = text[:max_len]

    return text, was_truncated, truncation_point


def run_normalization(config: dict, extracted: list[dict], logger) -> list[dict]:
    """
    Normalize text for all extracted records.

    Args:
        config: Parsed pipeline_config.yaml.
        extracted: List of ExtractedRecord dicts from S02.
        logger: Pipeline logger.

    Returns:
        List of NormalizedRecord dicts.
        Writes outputs/s03_normalized.jsonl.
    """
    output_dir = config.get("outputs", {}).get("base_dir", "./outputs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "s03_normalized.jsonl")

    records = []
    truncated_count = 0

    for ext in extracted:
        raw_text = ext.get("raw_text")
        normalized_text = None
        normalized_length = 0
        was_truncated = False
        truncation_point = None

        if raw_text and len(raw_text.strip()) > 0:
            normalized_text, was_truncated, truncation_point = _normalize_text(
                raw_text, config
            )
            normalized_length = len(normalized_text)
            if was_truncated:
                truncated_count += 1

        record = NormalizedRecord(
            doc_id=ext["doc_id"],
            filename=ext["filename"],
            source_folder=ext["source_folder"],
            original_path=ext["original_path"],
            file_type=ext["file_type"],
            file_size_bytes=ext["file_size_bytes"],
            extraction_method=ext["extraction_method"],
            extraction_status=ext["extraction_status"],
            ocr_status=ext["ocr_status"],
            text_length=ext["text_length"],
            page_count=ext.get("page_count"),
            normalized_text=normalized_text,
            normalized_length=normalized_length,
            was_truncated=was_truncated,
            truncation_point=truncation_point,
            normalization_timestamp=now_iso(),
        )
        records.append(record.model_dump())

    # Write output (text excluded from JSONL to save disk; store separately if needed)
    with open(output_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    logger.info(
        f"S03_NORMALIZE | COMPLETE | "
        f"{len(records)} records normalized, {truncated_count} truncated | "
        f"Output: {output_path}"
    )

    return records
