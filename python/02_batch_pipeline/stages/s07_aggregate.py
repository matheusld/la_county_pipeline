"""
s07_aggregate.py - Cross-model score aggregation and disagreement detection (Stage S07).

Joins the two independent model scores from S06a (GPT) and S06b (Claude), computes
averaged final scores, detects disagreements, assigns the definitive priority tier,
and routes each document to the shortlist or the low-priority pool.

Aggregation logic:
    - Final dimension scores are the mean of the two models' scores.
    - If one model's scoring failed (score_error set), the other model's scores are
      used directly as the final scores. If both failed, all final scores are 0.0.
    - composite_delta = abs(gpt_composite - claude_composite). Only computed when
      both models produced valid scores; otherwise 0.0.
    - flagged_disagreement = True when composite_delta >= disagreement_threshold
      (default 2.0, configurable in pipeline_config.yaml under aggregate).

Priority routing:
    - priority_review = True if final_tier is 1 or 2.
    - priority_review = True also if flagged_disagreement = True, regardless of tier.
      A document with disagreement could be underscored by the lower model and should
      receive human attention before being deprioritized.
    - Documents with priority_review = False (Tier 3/4, no disagreement) form the
      low-priority pool from which Stage S08 draws a 10% spot-check sample.

Output:
    outputs/s07_aggregated.jsonl — one AggregateRecord per non-duplicate document.

Usage:
    python run_pipeline.py --config config/pipeline_config.yaml --stage s07

    Or directly:
        from stages.s07_aggregate import run_aggregation
        records = run_aggregation(config, gpt_records, claude_records, normalized_records, logger, error_logger)
"""

import json
import os

from utils.logging_utils import now_iso
from utils.schemas import AggregateRecord, PriorityTier
from stages.s06a_score_gpt import _compute_composite, _assign_tier


# ---------------------------------------------------------------------------
# Score merging helpers
# ---------------------------------------------------------------------------

def _merge_scores(g: dict | None, c: dict | None) -> dict:
    """
    Merge GPT and Claude ScoredRecord dicts into a single set of final scores.

    Strategy when one model failed (score_error is not None):
        Use the other model's scores directly — a one-model result beats 0.0.
    Strategy when both are valid:
        Simple arithmetic mean of each dimension.
    Strategy when both failed:
        All final scores are 0.0 and the tier defaults to TIER_4.

    Returns a dict with keys:
        final_cf, final_ag, final_ix, final_ev, final_composite, final_tier,
        gpt_composite, claude_composite, composite_delta
    """
    g_ok = g is not None and not g.get("score_error")
    c_ok = c is not None and not c.get("score_error")

    if g_ok and c_ok:
        gcf = g["score_carefirst"]
        gag = g["score_ai_governance"]
        gix = g["score_intersection"]
        gev = g["score_evidentiary"]
        ccf = c["score_carefirst"]
        cag = c["score_ai_governance"]
        cix = c["score_intersection"]
        cev = c["score_evidentiary"]

        final_cf = (gcf + ccf) / 2.0
        final_ag = (gag + cag) / 2.0
        final_ix = (gix + cix) / 2.0
        final_ev = (gev + cev) / 2.0

        gpt_composite  = g["composite"]
        claude_composite = c["composite"]
        composite_delta  = abs(gpt_composite - claude_composite)

    elif g_ok:
        final_cf = g["score_carefirst"]
        final_ag = g["score_ai_governance"]
        final_ix = g["score_intersection"]
        final_ev = g["score_evidentiary"]

        gpt_composite    = g["composite"]
        claude_composite = None
        composite_delta  = 0.0

    elif c_ok:
        final_cf = c["score_carefirst"]
        final_ag = c["score_ai_governance"]
        final_ix = c["score_intersection"]
        final_ev = c["score_evidentiary"]

        gpt_composite    = None
        claude_composite = c["composite"]
        composite_delta  = 0.0

    else:
        final_cf = final_ag = final_ix = final_ev = 0.0
        gpt_composite    = None
        claude_composite = None
        composite_delta  = 0.0

    final_composite = _compute_composite(final_cf, final_ag, final_ix, final_ev)
    final_tier      = _assign_tier(final_composite, final_cf, final_ag)

    return {
        "final_cf":        final_cf,
        "final_ag":        final_ag,
        "final_ix":        final_ix,
        "final_ev":        final_ev,
        "final_composite": final_composite,
        "final_tier":      final_tier,
        "gpt_composite":   gpt_composite,
        "claude_composite": claude_composite,
        "composite_delta": composite_delta,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_aggregation(
    config: dict,
    gpt_records: list[dict],
    claude_records: list[dict],
    normalized_records: list[dict],
    logger,
    error_logger,
) -> list[dict]:
    """
    Aggregate GPT and Claude per-model scores into a single ranked output.

    Args:
        config:             Parsed pipeline_config.yaml.
        gpt_records:        ScoredRecord dicts from s06_gpt_scored.jsonl.
        claude_records:     ScoredRecord dicts from s06_claude_scored.jsonl.
        normalized_records: NormalizedRecord dicts from s03_normalized.jsonl
                            (used for text_preview only).
        logger:             Pipeline logger.
        error_logger:       Error logger.

    Returns:
        List of AggregateRecord dicts written to s07_aggregated.jsonl.
    """
    agg_cfg = config.get("aggregate", {})
    disagreement_threshold = float(agg_cfg.get("disagreement_threshold", 2.0))
    preview_length         = int(agg_cfg.get("text_preview_length", 500))
    output_dir             = config.get("outputs", {}).get("base_dir", "./outputs")
    output_path            = os.path.join(output_dir, "s07_aggregated.jsonl")
    os.makedirs(output_dir, exist_ok=True)

    # Build lookups
    gpt_by_id        = {r["doc_id"]: r for r in gpt_records}
    claude_by_id     = {r["doc_id"]: r for r in claude_records}
    normalized_by_id = {r["doc_id"]: r.get("normalized_text", "") or ""
                        for r in normalized_records}

    all_doc_ids = sorted(set(gpt_by_id) | set(claude_by_id))

    records:       list[dict] = []
    only_gpt       = 0
    only_claude    = 0
    both_scored    = 0
    both_failed    = 0
    disagreements  = 0
    priority_count = 0

    for doc_id in all_doc_ids:
        g = gpt_by_id.get(doc_id)
        c = claude_by_id.get(doc_id)

        # Warn if a doc_id appears in only one file
        if g is None:
            error_logger.warning(
                f"S07 | doc_id={doc_id[:12]} not found in GPT scores; "
                f"using Claude scores only"
            )
            only_claude += 1
        elif c is None:
            error_logger.warning(
                f"S07 | doc_id={doc_id[:12]} not found in Claude scores; "
                f"using GPT scores only"
            )
            only_gpt += 1
        elif g.get("score_error") and c.get("score_error"):
            error_logger.warning(
                f"S07 | doc_id={doc_id[:12]} both models errored; "
                f"final scores will be 0.0"
            )
            both_failed += 1
        else:
            both_scored += 1

        merged = _merge_scores(g, c)

        flagged = (
            merged["composite_delta"] >= disagreement_threshold
            and merged["gpt_composite"] is not None
            and merged["claude_composite"] is not None
        )
        if flagged:
            disagreements += 1

        final_tier_value = merged["final_tier"]
        priority_review  = (
            final_tier_value in (PriorityTier.TIER_1, PriorityTier.TIER_2)
            or flagged
        )
        if priority_review:
            priority_count += 1

        # Base record fields come from whichever scored file is available
        base = g or c

        text   = normalized_by_id.get(doc_id, "")
        preview = text[:preview_length] if text else ""

        record = AggregateRecord(
            doc_id          = doc_id,
            filename        = base["filename"],
            source_folder   = base["source_folder"],
            original_path   = base["original_path"],
            extraction_status = base["extraction_status"],
            normalized_length = base.get("normalized_length", 0),
            is_duplicate    = base.get("is_duplicate", False),
            keyword_score   = base.get("keyword_score", 0.0),
            keyword_matches = base.get("keyword_matches", []),

            gpt_score_carefirst    = g.get("score_carefirst")    if g and not g.get("score_error") else None,
            gpt_score_ai_governance= g.get("score_ai_governance") if g and not g.get("score_error") else None,
            gpt_score_intersection = g.get("score_intersection")  if g and not g.get("score_error") else None,
            gpt_score_evidentiary  = g.get("score_evidentiary")   if g and not g.get("score_error") else None,
            gpt_composite   = merged["gpt_composite"],
            gpt_tier        = PriorityTier(g["tier"]) if g and not g.get("score_error") and g.get("tier") is not None else None,
            gpt_rationale   = g.get("rationale") if g else None,
            gpt_model_version = g.get("model_version", "") if g else "",
            gpt_prompt_hash  = g.get("prompt_hash", "")   if g else "",
            gpt_score_error  = g.get("score_error") if g else "not scored by GPT",

            claude_score_carefirst    = c.get("score_carefirst")    if c and not c.get("score_error") else None,
            claude_score_ai_governance= c.get("score_ai_governance") if c and not c.get("score_error") else None,
            claude_score_intersection = c.get("score_intersection")  if c and not c.get("score_error") else None,
            claude_score_evidentiary  = c.get("score_evidentiary")   if c and not c.get("score_error") else None,
            claude_composite  = merged["claude_composite"],
            claude_tier       = PriorityTier(c["tier"]) if c and not c.get("score_error") and c.get("tier") is not None else None,
            claude_rationale  = c.get("rationale") if c else None,
            claude_model_version = c.get("model_version", "") if c else "",
            claude_prompt_hash   = c.get("prompt_hash", "")   if c else "",
            claude_score_error   = c.get("score_error") if c else "not scored by Claude",

            final_score_carefirst    = round(merged["final_cf"], 4),
            final_score_ai_governance= round(merged["final_ag"], 4),
            final_score_intersection = round(merged["final_ix"], 4),
            final_score_evidentiary  = round(merged["final_ev"], 4),
            final_composite = round(merged["final_composite"], 4),
            final_tier      = final_tier_value,

            composite_delta      = round(merged["composite_delta"], 4),
            flagged_disagreement = flagged,
            priority_review      = priority_review,
            text_preview         = preview,
            aggregation_timestamp= now_iso(),
        )
        records.append(record.model_dump())

    with open(output_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    logger.info(
        f"S07 | COMPLETE | {len(records)} documents aggregated | "
        f"both scored: {both_scored}, GPT only: {only_gpt}, "
        f"Claude only: {only_claude}, both failed: {both_failed} | "
        f"Disagreements flagged: {disagreements} "
        f"(threshold={disagreement_threshold}) | "
        f"Priority review: {priority_count} | "
        f"Output: {output_path}"
    )

    return records
