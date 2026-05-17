"""
s06b_score_claude.py - Score documents with Claude Haiku via Anthropic Batch API (Stage S06b).

Applies the same four-dimension scoring prompt used in Stage S06a (GPT scoring),
ensuring both models evaluate documents on identical criteria. The two independent
scores are later compared in Stage S07 to identify agreement, disagreement, and
uncertain cases.

Using Claude Haiku alongside GPT-5.4-mini:
    - Reduces single-model dependence and associated systematic biases.
    - Documents where models agree strongly provide higher-confidence rankings.
    - Documents where models disagree are flagged for human review regardless
      of tier, because the lower-scoring model may be underfitting relevance.

Anthropic Batch API mechanics:
    - Requests are grouped into chunks (default 100) and submitted as separate
      Message Batch jobs. Anthropic's batch limit is 100K requests per job, but
      smaller chunks reduce memory pressure during result streaming.
    - Results are streamed via client.messages.batches.results(); no file download.
    - Existing results are loaded on startup; already-scored doc_ids are skipped.

Output: outputs/s06_claude_scored.jsonl — one ScoredRecord per document.
        outputs/s06_claude_batch_manifest.jsonl — batch job IDs and metadata.

Usage:
    python run_pipeline.py --config config/pipeline_config.yaml --stage s06b

    Or directly:
        from stages.s06b_score_claude import run_claude_scoring
        records = run_claude_scoring(config, filtered, normalized, cost_tracker, logger, error_logger)
"""

import json
import os
import time

import anthropic

from utils.logging_utils import now_iso
from utils.provenance import get_prompt_template
from utils.schemas import PriorityTier, ScoredRecord

# Re-use the two pure functions from the GPT stage; they have no provider dependency.
from stages.s06a_score_gpt import _truncate_text, _compute_composite, _assign_tier, _load_existing_scored


# ---------------------------------------------------------------------------
# Request preparation
# ---------------------------------------------------------------------------

def _prepare_requests(
    config: dict,
    filtered_records: list[dict],
    normalized_records: list[dict],
    already_scored: set[str],
    output_dir: str,
    logger,
) -> tuple[list[dict], dict[str, str]]:
    """
    Build Anthropic Batch API request dicts and the custom_id → doc_id map.

    Skips duplicates, already-scored documents, and documents with no text.
    Returns: (requests, id_map)
    """
    scoring_cfg = config.get("scoring", {})
    model = scoring_cfg.get("claude_model", "claude-haiku-4-5")
    max_tokens_input = scoring_cfg.get("max_input_tokens", 1200)
    trunc_strategy = scoring_cfg.get("truncation_strategy", "head_tail")
    max_tokens_output = scoring_cfg.get("claude_max_output_tokens", 300)

    template, version, phash = get_prompt_template(config, "scoring_v1")

    text_lookup = {
        r["doc_id"]: (r.get("normalized_text") or "")
        for r in normalized_records
    }

    requests: list[dict] = []
    id_map: dict[str, str] = {}
    skipped_dup = 0
    skipped_empty = 0
    skipped_scored = 0

    for rec in filtered_records:
        doc_id = rec["doc_id"]

        if rec.get("is_duplicate", False):
            skipped_dup += 1
            continue

        if doc_id in already_scored:
            skipped_scored += 1
            continue

        text = text_lookup.get(doc_id, "")
        if not text or len(text.strip()) < 10:
            skipped_empty += 1
            continue

        custom_id = f"claude_{len(requests):06d}"
        id_map[custom_id] = doc_id

        truncated = _truncate_text(text, max_tokens_input, trunc_strategy)
        filled_prompt = template.replace("{text}", truncated)

        # Anthropic Batch API request format
        requests.append({
            "custom_id": custom_id,
            "params": {
                "model": model,
                "max_tokens": max_tokens_output,
                "messages": [{"role": "user", "content": filled_prompt}],
            },
        })

    # Save id map for audit
    id_map_path = os.path.join(output_dir, "s06_claude_id_map.json")
    with open(id_map_path, "w") as f:
        json.dump(id_map, f)

    logger.info(
        f"S06_CLAUDE | Prepared {len(requests)} requests | "
        f"Model: {model} | Prompt: scoring_v1 v{version} hash={phash[:12]} | "
        f"Skipped: {skipped_scored} already-scored, {skipped_dup} duplicates, "
        f"{skipped_empty} empty"
    )

    return requests, id_map


# ---------------------------------------------------------------------------
# Batch submission and polling
# ---------------------------------------------------------------------------

def _submit_and_collect(
    requests: list[dict],
    output_dir: str,
    logger,
    error_logger,
    chunk_size: int = 100,
    poll_interval: int = 120,
) -> list[dict]:
    """
    Split requests into chunks, submit each as an Anthropic Message Batch,
    poll for completion, and stream results into a flat list.

    chunk_size=100 is conservative; Anthropic supports up to 100K per batch.
    Smaller chunks give finer-grained resume granularity if a batch fails.

    Returns: list of raw result dicts, one per request, across all chunks.
    """
    client = anthropic.Anthropic()

    chunks = [requests[i:i + chunk_size] for i in range(0, len(requests), chunk_size)]
    logger.info(
        f"S06_CLAUDE | Submitting {len(chunks)} chunks: {[len(c) for c in chunks]}"
    )

    manifest: list[dict] = []
    all_results: list[dict] = []

    for i, chunk in enumerate(chunks):
        label = f"chunk {i + 1}/{len(chunks)}"

        batch = client.messages.batches.create(requests=chunk)
        manifest.append({
            "chunk_index": i,
            "batch_id": batch.id,
            "request_count": len(chunk),
        })
        logger.info(
            f"S06_CLAUDE | {label} submitted | {len(chunk)} requests | batch_id={batch.id}"
        )

        # Poll until the batch reaches a terminal state
        while True:
            batch = client.messages.batches.retrieve(batch.id)

            if batch.processing_status == "ended":
                counts = batch.request_counts
                logger.info(
                    f"S06_CLAUDE | {label} ended | "
                    f"succeeded={counts.succeeded} errored={counts.errored} "
                    f"expired={counts.expired}"
                )

                # Stream results
                chunk_results: list[dict] = []
                for result in client.messages.batches.results(batch.id):
                    entry: dict = {"custom_id": result.custom_id, "batch_id": batch.id}

                    if result.result.type == "succeeded":
                        text = result.result.message.content[0].text
                        entry["text"] = text
                        entry["input_tokens"] = result.result.message.usage.input_tokens
                        entry["output_tokens"] = result.result.message.usage.output_tokens
                        entry["error"] = None
                    else:
                        entry["text"] = None
                        entry["input_tokens"] = 0
                        entry["output_tokens"] = 0
                        entry["error"] = result.result.type  # "errored" or "expired"
                        error_logger.warning(
                            f"S06_CLAUDE | {label} | "
                            f"custom_id={result.custom_id} status={result.result.type}"
                        )

                    chunk_results.append(entry)

                all_results.extend(chunk_results)
                logger.info(
                    f"S06_CLAUDE | {label} streamed {len(chunk_results)} results | "
                    f"{len(all_results)} total"
                )
                break

            else:
                processing = getattr(batch.request_counts, "processing", "?")
                logger.info(
                    f"S06_CLAUDE | {label} | status={batch.processing_status} "
                    f"({processing} processing) | waiting {poll_interval}s"
                )
                time.sleep(poll_interval)

    # Save manifest and raw results for audit
    manifest_path = os.path.join(output_dir, "s06_claude_batch_manifest.jsonl")
    with open(manifest_path, "w") as f:
        for entry in manifest:
            f.write(json.dumps(entry) + "\n")

    raw_path = os.path.join(output_dir, "s06_claude_batch_results.jsonl")
    with open(raw_path, "w") as f:
        for r in all_results:
            f.write(json.dumps(r) + "\n")

    logger.info(f"S06_CLAUDE | All chunks done | {len(all_results)} total results")
    return all_results


# ---------------------------------------------------------------------------
# Record construction
# ---------------------------------------------------------------------------

def _build_scored_records(
    config: dict,
    batch_results: list[dict],
    id_map: dict[str, str],
    filtered_records: list[dict],
    already_scored: set[str],
    existing_output_path: str,
    cost_tracker,
    logger,
    error_logger,
) -> list[dict]:
    """
    Parse Anthropic batch results, compute composites locally, and write
    ScoredRecord JSONL. Merges with any previously-scored records.
    """
    scoring_cfg = config.get("scoring", {})
    model = scoring_cfg.get("claude_model", "claude-haiku-4-5")
    model_version = scoring_cfg.get("claude_model_version", model)
    _, prompt_version, prompt_hash = get_prompt_template(config, "scoring_v1")

    # Index results by doc_id
    result_lookup: dict[str, dict] = {}
    total_input_tokens = 0
    total_output_tokens = 0

    for res in batch_results:
        custom_id = res.get("custom_id", "")
        doc_id = id_map.get(custom_id, custom_id)
        in_tok = res.get("input_tokens", 0)
        out_tok = res.get("output_tokens", 0)
        total_input_tokens += in_tok
        total_output_tokens += out_tok

        parsed = None
        if res.get("text"):
            try:
                parsed = json.loads(res["text"])
            except json.JSONDecodeError:
                error_logger.warning(
                    f"S06_CLAUDE | doc_id={doc_id[:12]} | "
                    f"JSON parse failed: {res['text'][:200]}"
                )

        result_lookup.setdefault(doc_id, {
            "parsed": parsed,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "error": res.get("error"),
            "batch_id": res.get("batch_id", ""),
        })

    if total_input_tokens > 0:
        cost_tracker.log_batch(
            model=model,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            doc_count=len(batch_results),
            stage="s06_score_claude",
        )

    new_records: list[dict] = []

    for filt in filtered_records:
        doc_id = filt["doc_id"]

        if filt.get("is_duplicate", False) or doc_id in already_scored:
            continue

        res = result_lookup.get(doc_id)
        p = res.get("parsed") if res else None
        error_msg = None

        if p:
            cf  = float(p.get("score_carefirst",    0.0))
            ag  = float(p.get("score_ai_governance", 0.0))
            ix  = float(p.get("score_intersection",  0.0))
            ev  = float(p.get("score_evidentiary",   0.0))
            rationale = p.get("rationale", "")
        else:
            cf = ag = ix = ev = 0.0
            rationale = ""
            error_msg = (
                res["error"] if res and res.get("error")
                else "No valid score returned (API error or JSON parse failure)"
            )
            error_logger.warning(f"S06_CLAUDE | doc_id={doc_id[:12]} | {error_msg}")

        composite = _compute_composite(cf, ag, ix, ev)
        tier = _assign_tier(composite, cf, ag)

        record = ScoredRecord(
            doc_id=doc_id,
            filename=filt["filename"],
            source_folder=filt["source_folder"],
            original_path=filt["original_path"],
            extraction_status=filt["extraction_status"],
            normalized_length=filt.get("normalized_length", 0),
            is_duplicate=False,
            keyword_score=filt.get("keyword_score", 0.0),
            keyword_matches=filt.get("keyword_matches", []),
            score_carefirst=cf,
            score_ai_governance=ag,
            score_intersection=ix,
            score_evidentiary=ev,
            composite=composite,
            tier=tier,
            rationale=rationale,
            model_used=model,
            model_version=model_version,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
            input_tokens=res["input_tokens"] if res else 0,
            output_tokens=res["output_tokens"] if res else 0,
            scoring_timestamp=now_iso(),
            api_request_id=None,  # Anthropic batch does not expose per-request IDs
            batch_id=res["batch_id"] if res else None,
            score_error=error_msg,
        )
        new_records.append(record.model_dump())

    with open(existing_output_path, "a") as f:
        for rec in new_records:
            f.write(json.dumps(rec) + "\n")

    error_count = sum(1 for r in new_records if r.get("score_error"))
    logger.info(
        f"S06_CLAUDE | COMPLETE | "
        f"{len(new_records)} new records written, {len(already_scored)} previously scored | "
        f"{error_count} scoring errors | "
        f"Output: {existing_output_path}"
    )

    cost_tracker.summary()
    return new_records


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_claude_scoring(
    config: dict,
    filtered_records: list[dict],
    normalized_records: list[dict],
    cost_tracker,
    logger,
    error_logger,
    chunk_size: int = 100,
    poll_interval: int = 120,
) -> list[dict]:
    """
    Score all non-duplicate documents with Claude Haiku via the Anthropic Batch API.

    Idempotent: if outputs/s06_claude_scored.jsonl already contains results
    for some doc_ids, those are skipped and not re-billed.

    Args:
        config:             Parsed pipeline_config.yaml.
        filtered_records:   FilteredRecord dicts from Stage S05.
        normalized_records: NormalizedRecord dicts from Stage S03.
        cost_tracker:       CostTracker instance.
        logger:             Pipeline logger.
        error_logger:       Error logger.
        chunk_size:         Max requests per Anthropic batch chunk (default 100).
        poll_interval:      Seconds between batch status checks (default 120).

    Returns:
        List of ScoredRecord dicts (new records only; use load_jsonl for full set).
    """
    output_dir = config.get("outputs", {}).get("base_dir", "./outputs")
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, "s06_claude_scored.jsonl")
    already_scored = _load_existing_scored(output_path)

    if already_scored:
        logger.info(f"S06_CLAUDE | Resuming: {len(already_scored)} doc_ids already scored")

    requests, id_map = _prepare_requests(
        config, filtered_records, normalized_records,
        already_scored, output_dir, logger,
    )

    if not requests:
        logger.info("S06_CLAUDE | No new documents to score")
        return []

    batch_results = _submit_and_collect(
        requests, output_dir, logger, error_logger,
        chunk_size=chunk_size, poll_interval=poll_interval,
    )

    return _build_scored_records(
        config, batch_results, id_map, filtered_records,
        already_scored, output_path,
        cost_tracker, logger, error_logger,
    )
