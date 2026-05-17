"""
s08_spotcheck.py - Random 10% spot-check of low-priority documents (Stage S08).

Draws a reproducible random sample from the low-priority pool — documents where
priority_review=False (Tier 3 or Tier 4, no disagreement flag). The spot-check
estimates the pipeline's false-negative rate: how often a low-priority classification
is wrong and the document should have been escalated.

Sampling design:
    - Pool: all AggregateRecords where priority_review=False and is_duplicate=False.
    - Sample size: ceil(pool_size * sample_rate), default sample_rate=0.10.
    - Randomness is seeded (random_seed in config) so the sample is reproducible.
    - The sample is stratified: half from Tier 3, half from Tier 4 (proportional
      if either tier has fewer documents than the proportional target).

Output:
    outputs/s08_spotcheck.jsonl — SpotCheckRecord per sampled document.
    outputs/s08_spotcheck.csv  — Flat spreadsheet for human review, including text
                                 preview and both model rationales.

Human review workflow:
    1. Open s08_spotcheck.csv and review each row.
    2. For each row, set `review_status` to one of:
           confirmed_low  — pipeline was right, document is low priority
           escalate       — pipeline was wrong, document should be reviewed
           uncertain      — cannot determine from preview alone
    3. Optionally add `reviewer_id` and `reviewer_notes`.
    4. Save the completed CSV. Stage S09 does not depend on this file, but the
       spot-check results should be reported in the research methods appendix.

Usage:
    python run_pipeline.py --config config/pipeline_config.yaml --stage s08

    Or directly:
        from stages.s08_spotcheck import run_spotcheck
        records = run_spotcheck(config, aggregate_records, logger)
"""

import csv
import json
import math
import os
import random

from utils.logging_utils import now_iso
from utils.schemas import PriorityTier, ReviewStatus, SpotCheckRecord


def run_spotcheck(
    config: dict,
    aggregate_records: list[dict],
    logger,
) -> list[dict]:
    """
    Sample the low-priority pool for human spot-check review.

    Args:
        config:            Parsed pipeline_config.yaml.
        aggregate_records: AggregateRecord dicts from s07_aggregated.jsonl.
        logger:            Pipeline logger.

    Returns:
        List of SpotCheckRecord dicts written to s08_spotcheck.jsonl.
    """
    spotcheck_cfg = config.get("spotcheck", {})
    sample_rate   = float(spotcheck_cfg.get("sample_rate", 0.10))
    random_seed   = int(spotcheck_cfg.get("random_seed", 42))
    preview_length = int(spotcheck_cfg.get("text_preview_length", 500))
    output_dir    = config.get("outputs", {}).get("base_dir", "./outputs")
    output_jsonl  = os.path.join(output_dir, "s08_spotcheck.jsonl")
    output_csv    = os.path.join(output_dir, "s08_spotcheck.csv")
    os.makedirs(output_dir, exist_ok=True)

    # Build the low-priority pool (eligible for sampling)
    pool = [
        r for r in aggregate_records
        if not r.get("is_duplicate", False)
        and not r.get("priority_review", True)
    ]
    pool_size = len(pool)

    if pool_size == 0:
        logger.info("S08 | No low-priority documents to sample — spot-check skipped")
        return []

    target_n = math.ceil(pool_size * sample_rate)

    # Stratified by tier: proportional split, Tier 3 first
    tier3 = [r for r in pool if r.get("final_tier") == PriorityTier.TIER_3.value]
    tier4 = [r for r in pool if r.get("final_tier") == PriorityTier.TIER_4.value]

    tier3_n = min(
        math.ceil(target_n * (len(tier3) / pool_size)) if pool_size else 0,
        len(tier3),
    )
    tier4_n = min(target_n - tier3_n, len(tier4))

    rng = random.Random(random_seed)
    sampled_tier3 = rng.sample(tier3, tier3_n)
    sampled_tier4 = rng.sample(tier4, tier4_n)
    sampled = sampled_tier3 + sampled_tier4
    rng.shuffle(sampled)  # interleave tiers so reviewers see variety

    spot_records: list[dict] = []

    for idx, rec in enumerate(sampled, start=1):
        preview = (rec.get("text_preview") or "")[:preview_length]

        spot = SpotCheckRecord(
            doc_id          = rec["doc_id"],
            filename        = rec["filename"],
            source_folder   = rec["source_folder"],
            original_path   = rec["original_path"],
            extraction_status = rec["extraction_status"],
            normalized_length = rec.get("normalized_length", 0),
            keyword_score   = rec.get("keyword_score", 0.0),
            keyword_matches = rec.get("keyword_matches", []),

            final_composite = rec["final_composite"],
            final_tier      = PriorityTier(rec["final_tier"]),
            gpt_composite   = rec.get("gpt_composite"),
            claude_composite= rec.get("claude_composite"),
            gpt_rationale   = rec.get("gpt_rationale"),
            claude_rationale= rec.get("claude_rationale"),

            sample_index    = idx,
            sample_pool_size= pool_size,
            sample_rate     = sample_rate,
            random_seed     = random_seed,
            text_preview    = preview,

            review_status   = ReviewStatus.NOT_REVIEWED,
        )
        spot_records.append(spot.model_dump())

    # Write JSONL
    with open(output_jsonl, "w") as f:
        for rec in spot_records:
            f.write(json.dumps(rec) + "\n")

    # Write CSV for human review
    csv_fields = [
        "sample_index", "doc_id", "filename", "source_folder",
        "final_tier", "final_composite", "gpt_composite", "claude_composite",
        "keyword_score", "keyword_matches",
        "gpt_rationale", "claude_rationale",
        "text_preview",
        "review_status", "reviewer_id", "reviewer_notes",
    ]
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(spot_records)

    logger.info(
        f"S08 | COMPLETE | "
        f"Pool: {pool_size} low-priority docs "
        f"(Tier 3: {len(tier3)}, Tier 4: {len(tier4)}) | "
        f"Sample: {len(spot_records)} docs ({sample_rate:.0%}, seed={random_seed}) | "
        f"JSONL: {output_jsonl} | CSV: {output_csv}"
    )

    return spot_records
