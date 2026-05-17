"""
s04_dedup.py - Near-duplicate detection using MinHash/LSH (Stage S04).

Uses datasketch's MinHash with configurable shingle size and Jaccard threshold.
Documents flagged as near-duplicates are NOT removed from the pipeline.
Instead, the canonical (first-seen) copy proceeds normally and duplicates
are marked with is_duplicate=True and duplicate_of=<canonical doc_id>.

This approach avoids false-negative risk from premature removal while still
letting the human reviewer skip duplicates.

Cost: $0 (no API calls).

Error Sources:
    - Very short documents (<50 chars) produce unreliable MinHash signatures.
      These are excluded from dedup and always pass through as non-duplicates.
    - Documents that are substantively similar but use different vocabulary
      (e.g., a summary vs. the full report) will NOT be caught. MinHash
      detects near-verbatim overlap, not semantic similarity.

Usage:
    from stages.s04_dedup import run_dedup
    records = run_dedup(config, normalized_records, logger)
"""

import json
import os
from datasketch import MinHash, MinHashLSH
from utils.logging_utils import now_iso
from utils.schemas import DedupRecord


def _make_shingles(text: str, k: int = 5) -> set[str]:
    """Create k-word shingles from text."""
    words = text.lower().split()
    if len(words) < k:
        return {" ".join(words)}
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def _make_minhash(shingles: set[str], num_perm: int = 128) -> MinHash:
    """Create a MinHash signature from a set of shingles."""
    m = MinHash(num_perm=num_perm)
    for s in shingles:
        m.update(s.encode("utf-8"))
    return m


def run_dedup(config: dict, normalized: list[dict], logger) -> list[dict]:
    """
    Detect near-duplicate documents using MinHash LSH.

    Args:
        config: Parsed pipeline_config.yaml.
        normalized: List of NormalizedRecord dicts from S03.
        logger: Pipeline logger.

    Returns:
        List of DedupRecord dicts.
        Writes outputs/s04_deduped.jsonl.
    """
    dedup_cfg = config.get("dedup", {})
    num_perm = dedup_cfg.get("num_perm", 128)
    threshold = dedup_cfg.get("threshold", 0.85)
    shingle_size = dedup_cfg.get("shingle_size", 5)

    output_dir = config.get("outputs", {}).get("base_dir", "./outputs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "s04_deduped.jsonl")

    # Build LSH index
    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    minhashes = {}  # doc_id -> MinHash
    doc_order = []  # preserve insertion order for canonical selection

    for rec in normalized:
        text = rec.get("normalized_text", "")
        doc_id = rec["doc_id"]

        if not text or len(text.strip()) < 50:
            # Too short for reliable dedup; skip indexing
            continue

        shingles = _make_shingles(text, shingle_size)
        mh = _make_minhash(shingles, num_perm)
        minhashes[doc_id] = mh
        doc_order.append(doc_id)

    # Insert into LSH and detect duplicates
    duplicates = {}  # duplicate_doc_id -> canonical_doc_id
    similarities = {}  # duplicate_doc_id -> jaccard score

    for doc_id in doc_order:
        mh = minhashes[doc_id]
        # Query before inserting so earlier docs are canonical
        try:
            result = lsh.query(mh)
        except Exception:
            result = []

        if result:
            # This doc is a near-duplicate of the first match
            canonical = result[0]
            duplicates[doc_id] = canonical
            # Compute exact Jaccard for the record
            similarities[doc_id] = mh.jaccard(minhashes[canonical])
        else:
            # Not a duplicate; insert into index
            try:
                lsh.insert(doc_id, mh)
            except ValueError:
                # Already inserted (shouldn't happen, but defensive)
                pass

    # Build output records
    records = []
    for rec in normalized:
        doc_id = rec["doc_id"]
        is_dup = doc_id in duplicates

        record = DedupRecord(
            doc_id=doc_id,
            filename=rec["filename"],
            source_folder=rec["source_folder"],
            original_path=rec["original_path"],
            extraction_status=rec["extraction_status"],
            ocr_status=rec["ocr_status"],
            normalized_length=rec.get("normalized_length", 0),
            is_duplicate=is_dup,
            duplicate_of=duplicates.get(doc_id),
            jaccard_similarity=similarities.get(doc_id),
            dedup_timestamp=now_iso(),
        )
        records.append(record.model_dump())

    dup_count = len(duplicates)
    logger.info(
        f"S04_DEDUP | COMPLETE | "
        f"{len(records)} records processed, {dup_count} near-duplicates found | "
        f"Output: {output_path}"
    )

    with open(output_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    return records
