"""
s06a_score_gpt.py - Score documents with GPT-5.4-mini via OpenAI Batch API (Stage S06a).

Applies a standardized four-dimension scoring prompt independently, producing
relevance scores that are later compared against Claude's scores in Stage S07.
Using two models independently — rather than one — reduces dependence on any
single model's tendencies and surfaces documents where models disagree.

Scoring dimensions (0–10 each, defined in config scoring_v1 prompt):
    score_carefirst       — care-first governance relevance
    score_ai_governance   — AI/tech governance relevance
    score_intersection    — explicit connection between the two systems
    score_evidentiary     — concrete evidence quality for citation

Composite formula (computed locally, model output never trusted):
    composite = (carefirst × 0.25) + (ai_gov × 0.25) + (intersection × 0.35)
              + (evidentiary × 0.15)

Batch API mechanics:
    - Requests are split into chunks (default 500) to stay within org token limits.
    - Each chunk is uploaded, submitted, and polled independently.
    - Existing results are loaded on startup; already-scored doc_ids are skipped.
      This makes the stage safe to re-run after partial failures.

Output: outputs/s06_gpt_scored.jsonl — one ScoredRecord per document.
        outputs/s06_gpt_batch_input.jsonl — full batch input for audit.
        outputs/s06_gpt_id_map.json — custom_id → doc_id mapping.

Usage:
    python run_pipeline.py --config config/pipeline_config.yaml --stage s06a

    Or directly:
        from stages.s06a_score_gpt import run_gpt_scoring
        records = run_gpt_scoring(config, filtered, normalized, cost_tracker, logger, error_logger)
"""

import json
import os
import time

from openai import OpenAI

from utils.logging_utils import now_iso
from utils.provenance import get_prompt_template
from utils.schemas import PriorityTier, ScoredRecord


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _truncate_text(text: str, max_tokens: int, strategy: str = "head_tail") -> str:
    """
    Truncate text to approximately max_tokens using word-count estimation.

    "head_tail" preserves both opening context and closing content, which
    is important for documents where conclusions appear at the end.
    """
    words = text.split()
    est_tokens = int(len(words) / 0.75)  # conservative: 0.75 words per token

    if est_tokens <= max_tokens:
        return text

    max_words = int(max_tokens * 0.75)

    if strategy == "head_tail":
        half = max_words // 2
        head = " ".join(words[:half])
        tail = " ".join(words[-half:])
        return f"{head}\n\n[...TRUNCATED...]\n\n{tail}"

    return " ".join(words[:max_words])


def _compute_composite(
    carefirst: float,
    ai_governance: float,
    intersection: float,
    evidentiary: float,
) -> float:
    """
    Weighted composite formula. Intersection receives the highest weight because
    documents bridging both governance systems are the primary research target.
    """
    return (
        carefirst     * 0.25
        + ai_governance * 0.25
        + intersection  * 0.35
        + evidentiary   * 0.15
    )


def _assign_tier(composite: float, carefirst: float, ai_governance: float) -> PriorityTier:
    """
    Assign a priority tier from the composite and dimension scores.

    Tier 1 requires not just a high composite but also substantive content on
    at least one of the two primary dimensions (carefirst or ai_governance >= 5),
    preventing a document that scores high on evidentiary and intersection alone
    from reaching Tier 1.
    """
    if composite >= 6.0 and (carefirst >= 5.0 or ai_governance >= 5.0):
        return PriorityTier.TIER_1
    if composite >= 3.5:
        return PriorityTier.TIER_2
    if composite >= 1.0:
        return PriorityTier.TIER_3
    return PriorityTier.TIER_4


def _load_existing_scored(output_path: str) -> set[str]:
    """Return the set of doc_ids already present in the output file."""
    scored = set()
    if not os.path.exists(output_path):
        return scored
    with open(output_path, "r") as f:
        for line in f:
            if line.strip():
                try:
                    scored.add(json.loads(line)["doc_id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return scored


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
    Build OpenAI Batch API request dicts and the custom_id → doc_id map.

    Skips documents that are already scored (idempotency) or have no
    usable text (extraction failures).

    Returns: (requests, id_map)
    """
    scoring_cfg = config.get("scoring", {})
    model = scoring_cfg.get("gpt_model", "gpt-5.4-mini")
    max_tokens = scoring_cfg.get("max_input_tokens", 1200)
    trunc_strategy = scoring_cfg.get("truncation_strategy", "head_tail")
    temperature = scoring_cfg.get("temperature", 0.0)
    max_tokens_output = scoring_cfg.get("gpt_max_output_tokens", 300)

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

        custom_id = f"gpt_{len(requests):06d}"
        id_map[custom_id] = doc_id

        truncated = _truncate_text(text, max_tokens, trunc_strategy)
        filled_prompt = template.replace("{text}", truncated)

        requests.append({
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": model,
                "temperature": temperature,
                "max_completion_tokens": max_tokens_output,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": filled_prompt}],
            },
        })

    # Write audit artifacts
    id_map_path = os.path.join(output_dir, "s06_gpt_id_map.json")
    with open(id_map_path, "w") as f:
        json.dump(id_map, f)

    batch_input_path = os.path.join(output_dir, "s06_gpt_batch_input.jsonl")
    with open(batch_input_path, "w") as f:
        for req in requests:
            f.write(json.dumps(req) + "\n")

    logger.info(
        f"S06_GPT | Prepared {len(requests)} requests | "
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
    chunk_size: int = 500,
    poll_interval: int = 120,
) -> list[dict]:
    """
    Split requests into chunks, submit each as an OpenAI batch job, poll for
    completion, and collect all results into a flat list.

    chunk_size=500 keeps batches well under the 2M enqueued-token org limit
    for gpt-5.4-mini (~500 docs × 1,400 tokens ≈ 700K tokens per chunk).

    Returns: list of raw result dicts from all completed batches.
    """
    client = OpenAI()

    chunks = [requests[i:i + chunk_size] for i in range(0, len(requests), chunk_size)]
    logger.info(
        f"S06_GPT | Submitting {len(chunks)} chunks: {[len(c) for c in chunks]}"
    )

    all_results: list[dict] = []

    for i, chunk in enumerate(chunks):
        label = f"chunk {i + 1}/{len(chunks)}"

        chunk_path = os.path.join(output_dir, f"s06_gpt_chunk_{i}.jsonl")
        with open(chunk_path, "w") as f:
            for req in chunk:
                f.write(json.dumps(req) + "\n")

        with open(chunk_path, "rb") as f:
            file_obj = client.files.create(file=f, purpose="batch")

        batch = client.batches.create(
            input_file_id=file_obj.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
            metadata={"pipeline": "la-county-doc-triage", "stage": "s06_gpt", "chunk": str(i)},
        )
        logger.info(f"S06_GPT | {label} submitted | {len(chunk)} requests | batch_id={batch.id}")

        while True:
            status = client.batches.retrieve(batch.id)

            if status.status == "completed":
                if not status.output_file_id:
                    error_logger.error(
                        f"S06_GPT | {label} completed with no output file | "
                        f"{len(chunk)} requests will be unscored"
                    )
                    break

                content = client.files.content(status.output_file_id)
                chunk_results = []
                for line in content.text.strip().split("\n"):
                    if line.strip():
                        try:
                            chunk_results.append(json.loads(line))
                        except json.JSONDecodeError:
                            error_logger.warning(
                                f"S06_GPT | {label} | Malformed result line: {line[:120]}"
                            )

                all_results.extend(chunk_results)
                logger.info(
                    f"S06_GPT | {label} done | "
                    f"{len(chunk_results)} results | {len(all_results)} total"
                )
                break

            elif status.status in ("failed", "expired", "cancelled"):
                error_msg = str(status.errors) if status.errors else "unknown error"
                error_logger.error(
                    f"S06_GPT | {label} {status.status} | "
                    f"batch_id={batch.id} | {error_msg} | "
                    f"{len(chunk)} requests will be unscored"
                )
                break

            else:
                completed = getattr(status.request_counts, "completed", "?")
                total = getattr(status.request_counts, "total", "?")
                logger.info(
                    f"S06_GPT | {label} | status={status.status} "
                    f"({completed}/{total}) | waiting {poll_interval}s"
                )
                time.sleep(poll_interval)

    # Save merged raw results for audit
    raw_path = os.path.join(output_dir, "s06_gpt_batch_results.jsonl")
    with open(raw_path, "w") as f:
        for r in all_results:
            f.write(json.dumps(r) + "\n")

    logger.info(f"S06_GPT | All chunks done | {len(all_results)} total results")
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
    Parse batch API results, compute composites locally, and write ScoredRecord
    JSONL. Merges any previously-scored records (idempotency).
    """
    scoring_cfg = config.get("scoring", {})
    model = scoring_cfg.get("gpt_model", "gpt-5.4-mini")
    model_version = scoring_cfg.get("gpt_model_version", model)
    _, prompt_version, prompt_hash = get_prompt_template(config, "scoring_v1")

    # Index batch results by doc_id
    result_lookup: dict[str, dict] = {}
    total_input_tokens = 0
    total_output_tokens = 0

    for res in batch_results:
        custom_id = res.get("custom_id", "")
        doc_id = id_map.get(custom_id, custom_id)
        response = res.get("response", {})
        body = response.get("body", {})
        usage = body.get("usage", {})
        choices = body.get("choices", [])

        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        total_input_tokens += in_tok
        total_output_tokens += out_tok

        parsed = None
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                error_logger.warning(
                    f"S06_GPT | doc_id={doc_id[:12]} | JSON parse failed: {content[:200]}"
                )

        result_lookup.setdefault(doc_id, {
            "parsed": parsed,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "request_id": response.get("request_id", ""),
            "batch_id": res.get("batch_id", ""),
        })

    if total_input_tokens > 0:
        cost_tracker.log_batch(
            model=model,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            doc_count=len(batch_results),
            stage="s06_score_gpt",
        )

    # Build records for newly scored documents
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
            error_msg = "No valid score returned (API error or JSON parse failure)"
            error_logger.warning(f"S06_GPT | doc_id={doc_id[:12]} | {error_msg}")

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
            api_request_id=res["request_id"] if res else None,
            batch_id=res["batch_id"] if res else None,
            score_error=error_msg,
        )
        new_records.append(record.model_dump())

    # Append to (or create) the output file — preserves existing scored records
    with open(existing_output_path, "a") as f:
        for rec in new_records:
            f.write(json.dumps(rec) + "\n")

    error_count = sum(1 for r in new_records if r.get("score_error"))
    logger.info(
        f"S06_GPT | COMPLETE | "
        f"{len(new_records)} new records written, {len(already_scored)} previously scored | "
        f"{error_count} scoring errors | "
        f"Output: {existing_output_path}"
    )

    cost_tracker.summary()
    return new_records


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_gpt_scoring(
    config: dict,
    filtered_records: list[dict],
    normalized_records: list[dict],
    cost_tracker,
    logger,
    error_logger,
    chunk_size: int = 500,
    poll_interval: int = 120,
) -> list[dict]:
    """
    Score all non-duplicate documents with GPT-5.4-mini via the Batch API.

    Idempotent: if outputs/s06_gpt_scored.jsonl already contains results
    for some doc_ids, those are skipped and not re-billed.

    Args:
        config:           Parsed pipeline_config.yaml.
        filtered_records: FilteredRecord dicts from Stage S05.
        normalized_records: NormalizedRecord dicts from Stage S03.
        cost_tracker:     CostTracker instance.
        logger:           Pipeline logger.
        error_logger:     Error logger.
        chunk_size:       Max requests per batch chunk (default 500).
        poll_interval:    Seconds between batch status checks (default 120).

    Returns:
        List of ScoredRecord dicts (new records only; use load_jsonl for full set).
    """
    output_dir = config.get("outputs", {}).get("base_dir", "./outputs")
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, "s06_gpt_scored.jsonl")
    already_scored = _load_existing_scored(output_path)

    if already_scored:
        logger.info(f"S06_GPT | Resuming: {len(already_scored)} doc_ids already scored")

    requests, id_map = _prepare_requests(
        config, filtered_records, normalized_records,
        already_scored, output_dir, logger,
    )

    if not requests:
        logger.info("S06_GPT | No new documents to score")
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
