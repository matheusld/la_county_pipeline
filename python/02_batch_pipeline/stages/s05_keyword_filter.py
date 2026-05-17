"""
s05_keyword_filter.py - Deterministic keyword/regex filtering (Stage S05).

Applies keyword lists and regex patterns from config/keywords.yaml to
every document. Matching adds a positive score; non-matching documents
are NOT discarded. This stage only adds signal for downstream classification
and escalation decisions.

Cost: $0 (no API calls).

Design Rationale:
    Keyword filtering is the cheapest possible relevance signal. By making
    it additive-only (never discarding), we avoid the false-negative risk
    of documents that are relevant but use unexpected terminology. The
    classification model (S06) serves as the safety net for keyword misses.

Error Sources:
    - Overly broad regex patterns (e.g., "\\bAI\\b") may match false positives
      like "AI" in proper nouns or abbreviations. This is acceptable at triage
      because false positives waste reviewer time but don't lose documents.
    - Keyword lists may be incomplete for emerging terminology.

Usage:
    from stages.s05_keyword_filter import run_keyword_filter
    records = run_keyword_filter(config, dedup_records, normalized_records, logger)
"""

import json
import os
import re
import yaml
from utils.logging_utils import now_iso
from utils.schemas import FilteredRecord


def _load_keywords(keywords_path: str) -> tuple[dict[str, list[str]], list[str]]:
    """
    Load keyword domains and regex patterns from keywords.yaml.

    Returns: (domain_keywords, regex_patterns)
        domain_keywords: {"ai_governance": ["artificial intelligence", ...], ...}
        regex_patterns: ["\\bAI\\b", ...]
    """
    with open(keywords_path, "r") as f:
        kw_config = yaml.safe_load(f)

    domain_keywords = {}
    for key, val in kw_config.items():
        if key == "regex_patterns":
            continue
        if isinstance(val, dict) and "keywords" in val:
            domain_keywords[key] = [k.lower() for k in val["keywords"]]

    regex_patterns = kw_config.get("regex_patterns", [])
    return domain_keywords, regex_patterns


def _match_document(
    text: str,
    domain_keywords: dict[str, list[str]],
    regex_patterns: list[str],
) -> tuple[list[str], list[str], float]:
    """
    Check a document against all keyword domains and regex patterns.

    Returns: (matched_domains, matched_terms, score)
    """
    text_lower = text.lower()
    matched_domains = set()
    matched_terms = []

    # Keyword matching
    for domain, keywords in domain_keywords.items():
        for kw in keywords:
            if kw in text_lower:
                matched_domains.add(domain)
                matched_terms.append(kw)

    # Regex matching
    for pattern in regex_patterns:
        try:
            if re.search(pattern, text, re.IGNORECASE):
                matched_domains.add("regex_match")
                matched_terms.append(pattern)
        except re.error:
            pass  # malformed pattern; skip

    # Score: 0.3 per domain matched (configurable)
    score = len(matched_domains) * 0.3

    return sorted(matched_domains), matched_terms, score


def run_keyword_filter(
    config: dict,
    dedup_records: list[dict],
    normalized_records: list[dict],
    logger,
) -> list[dict]:
    """
    Apply keyword and regex filtering to all documents.

    Args:
        config: Parsed pipeline_config.yaml.
        dedup_records: List of DedupRecord dicts from S04.
        normalized_records: List of NormalizedRecord dicts from S03
            (needed for full text access).
        logger: Pipeline logger.

    Returns:
        List of FilteredRecord dicts.
        Writes outputs/s05_filtered.jsonl.
    """
    kw_cfg = config.get("keyword_filter", {})
    keywords_path = kw_cfg.get("keywords_file", "./config/keywords.yaml")

    output_dir = config.get("outputs", {}).get("base_dir", "./outputs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "s05_filtered.jsonl")

    domain_keywords, regex_patterns = _load_keywords(keywords_path)

    # Build lookup from doc_id -> normalized_text
    text_lookup = {
        r["doc_id"]: r.get("normalized_text", "")
        for r in normalized_records
    }

    records = []
    match_count = 0

    for dedup in dedup_records:
        doc_id = dedup["doc_id"]
        text = text_lookup.get(doc_id, "")

        if text:
            matched_domains, matched_terms, score = _match_document(
                text, domain_keywords, regex_patterns
            )
        else:
            matched_domains, matched_terms, score = [], [], 0.0

        if matched_domains:
            match_count += 1

        record = FilteredRecord(
            doc_id=doc_id,
            filename=dedup["filename"],
            source_folder=dedup["source_folder"],
            original_path=dedup["original_path"],
            extraction_status=dedup["extraction_status"],
            normalized_length=dedup.get("normalized_length", 0),
            is_duplicate=dedup.get("is_duplicate", False),
            keyword_matches=matched_domains,
            keyword_terms_matched=matched_terms,
            keyword_score=score,
            filter_timestamp=now_iso(),
        )
        records.append(record.model_dump())

    with open(output_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    logger.info(
        f"S05_KEYWORD_FILTER | COMPLETE | "
        f"{match_count}/{len(records)} documents matched keywords | "
        f"Output: {output_path}"
    )

    return records
