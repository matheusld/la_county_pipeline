"""
s09_shortlist.py - Final shortlist production (Stage S09).

Selects documents for full human review and produces the pipeline's primary
research output: a ranked shortlist of the most relevant documents.

Inclusion criteria (applied in this order):
    1. All Tier 1 documents (composite >= 6.0, with strong care-first or AI governance
       dimension) are always included.
    2. All Tier 2 documents (composite >= 3.5) are always included.
    3. All disagreement-flagged documents (flagged_disagreement=True) are always
       included regardless of tier, because model disagreement indicates the lower
       score may be wrong and warrants a human look.
    4. The combined set is deduplicated (a Tier 1 doc with a disagreement flag
       appears once) and sorted by final_composite descending.
    5. If the total exceeds the target_size configured in pipeline_config.yaml
       (default 167), the list is truncated. Tier 1 documents are never truncated;
       the cut falls within the lowest-ranked Tier 2 documents.

The 167-document target reflects practical limits of qualitative analysis within a
research semester. Adjust target_size in config for different research scales.

Output:
    outputs/s09_shortlist.jsonl — ShortlistRecord per selected document, ranked.
    outputs/s09_shortlist.csv  — Same data as a spreadsheet for researcher use.

Usage:
    python run_pipeline.py --config config/pipeline_config.yaml --stage s09

    Or directly:
        from stages.s09_shortlist import run_shortlist
        records = run_shortlist(config, aggregate_records, logger)
"""

import csv
import json
import os

from utils.logging_utils import now_iso
from utils.schemas import PriorityTier, ShortlistRecord


def run_shortlist(
    config: dict,
    aggregate_records: list[dict],
    logger,
) -> list[dict]:
    """
    Produce the final shortlist from the aggregated scores.

    Args:
        config:            Parsed pipeline_config.yaml.
        aggregate_records: AggregateRecord dicts from s07_aggregated.jsonl.
        logger:            Pipeline logger.

    Returns:
        List of ShortlistRecord dicts written to s09_shortlist.jsonl.
    """
    shortlist_cfg = config.get("shortlist", {})
    target_size   = int(shortlist_cfg.get("target_size", 167))
    preview_length = int(shortlist_cfg.get("text_preview_length", 500))
    output_dir    = config.get("outputs", {}).get("base_dir", "./outputs")
    output_jsonl  = os.path.join(output_dir, "s09_shortlist.jsonl")
    output_csv    = os.path.join(output_dir, "s09_shortlist.csv")
    os.makedirs(output_dir, exist_ok=True)

    tier1_docs       = []
    tier2_docs       = []
    disagreement_docs = []

    for rec in aggregate_records:
        if rec.get("is_duplicate", False):
            continue

        tier = rec.get("final_tier")
        flagged = rec.get("flagged_disagreement", False)

        if tier == PriorityTier.TIER_1.value:
            tier1_docs.append(rec)
        elif tier == PriorityTier.TIER_2.value:
            tier2_docs.append(rec)
        elif flagged:
            # Tier 3/4 with disagreement: include under 'disagreement' reason
            disagreement_docs.append(rec)

    # Deduplicate: disagreement docs already captured in tier1/tier2 if applicable
    tier1_ids = {r["doc_id"] for r in tier1_docs}
    tier2_ids = {r["doc_id"] for r in tier2_docs}
    disagreement_only = [
        r for r in disagreement_docs
        if r["doc_id"] not in tier1_ids and r["doc_id"] not in tier2_ids
    ]

    # Sort each group by final_composite descending
    def by_composite(r: dict) -> float:
        return r.get("final_composite", 0.0)

    tier1_docs       = sorted(tier1_docs,       key=by_composite, reverse=True)
    tier2_docs       = sorted(tier2_docs,       key=by_composite, reverse=True)
    disagreement_only = sorted(disagreement_only, key=by_composite, reverse=True)

    # Tier 1 is always fully included — truncation only affects Tier 2 and disagreement docs
    tier1_n = len(tier1_docs)
    remaining_budget = max(0, target_size - tier1_n)

    # Fill the budget with Tier 2 first, then disagreement-only
    tier2_selected       = tier2_docs[:remaining_budget]
    remaining_budget    -= len(tier2_selected)
    disagreement_selected = disagreement_only[:remaining_budget]

    selected = (
        [(r, "tier_1")       for r in tier1_docs]
        + [(r, "tier_2")     for r in tier2_selected]
        + [(r, "disagreement") for r in disagreement_selected]
    )

    # Final sort across all included docs by composite descending, then assign ranks
    selected.sort(key=lambda x: x[0].get("final_composite", 0.0), reverse=True)

    shortlist: list[dict] = []
    timestamp = now_iso()

    for rank, (rec, reason) in enumerate(selected, start=1):
        preview = (rec.get("text_preview") or "")[:preview_length]

        entry = ShortlistRecord(
            rank            = rank,
            doc_id          = rec["doc_id"],
            filename        = rec["filename"],
            source_folder   = rec["source_folder"],
            original_path   = rec["original_path"],
            extraction_status = rec["extraction_status"],
            normalized_length = rec.get("normalized_length", 0),
            keyword_score   = rec.get("keyword_score", 0.0),
            keyword_matches = rec.get("keyword_matches", []),

            final_composite          = rec["final_composite"],
            final_tier               = PriorityTier(rec["final_tier"]),
            final_score_carefirst    = rec["final_score_carefirst"],
            final_score_ai_governance= rec["final_score_ai_governance"],
            final_score_intersection = rec["final_score_intersection"],
            final_score_evidentiary  = rec["final_score_evidentiary"],

            gpt_composite    = rec.get("gpt_composite"),
            claude_composite = rec.get("claude_composite"),
            composite_delta  = rec.get("composite_delta", 0.0),
            flagged_disagreement = rec.get("flagged_disagreement", False),

            inclusion_reason = reason,
            gpt_rationale    = rec.get("gpt_rationale"),
            claude_rationale = rec.get("claude_rationale"),
            text_preview     = preview,

            shortlist_timestamp = timestamp,
        )
        shortlist.append(entry.model_dump())

    # Write JSONL
    with open(output_jsonl, "w") as f:
        for rec in shortlist:
            f.write(json.dumps(rec) + "\n")

    # Write CSV
    csv_fields = [
        "rank", "doc_id", "filename", "source_folder",
        "final_tier", "final_composite",
        "final_score_carefirst", "final_score_ai_governance",
        "final_score_intersection", "final_score_evidentiary",
        "gpt_composite", "claude_composite", "composite_delta",
        "flagged_disagreement", "inclusion_reason",
        "keyword_score", "keyword_matches",
        "gpt_rationale", "claude_rationale",
        "text_preview", "original_path",
    ]
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(shortlist)

    tier2_truncated = len(tier2_docs) - len(tier2_selected)
    disagreement_truncated = len(disagreement_only) - len(disagreement_selected)

    logger.info(
        f"S09 | COMPLETE | "
        f"Shortlist: {len(shortlist)} documents (target {target_size}) | "
        f"Tier 1: {tier1_n}, Tier 2: {len(tier2_selected)}, "
        f"Disagreement-only: {len(disagreement_selected)} | "
        f"Truncated: {tier2_truncated} Tier 2, "
        f"{disagreement_truncated} disagreement-only docs beyond target | "
        f"JSONL: {output_jsonl} | CSV: {output_csv}"
    )

    return shortlist
