"""
run_pipeline.py - CLI entrypoint for the dual-model document scoring pipeline.

Every stage reads its inputs from the previous stage's JSONL output on disk.
You can run the full pipeline or any single stage. Stages are idempotent: re-running
a stage overwrites its output (except S06a/S06b, which append and skip already-scored
doc_ids to avoid re-billing).

Pipeline flow:
    S01 → S02 → S03 → S04 → S05 → S06a (GPT)    ─┐
                                   S06b (Claude) ─┤ → S07 → S08 → S09
    (free, fast)                   (paid, async, hours)
                                                  (free, fast)

Usage:
    # Full pipeline — runs S01 through S09
    python run_pipeline.py --stage all

    # Any single stage (loads inputs from disk automatically)
    python run_pipeline.py --stage s01
    python run_pipeline.py --stage s06a
    python run_pipeline.py --stage s06b
    python run_pipeline.py --stage s07
    python run_pipeline.py --stage s08
    python run_pipeline.py --stage s09

    # Custom config path
    python run_pipeline.py --config config/pipeline_config.yaml --stage all

Notes:
    - S06_GPT and S06_CLAUDE are the only stages that cost money. Both submit to
      batch APIs and block until complete (poll every 2 minutes by default).
    - S06_GPT and S06_CLAUDE can be run in any order — each reads S05 output and
      writes its own JSONL. S07 requires both to be done.
    - If either S06 stage is interrupted, re-run it. It skips already-scored doc_ids.
    - S01–S05, S07–S09 are free and typically complete in seconds to minutes.
"""

import argparse
import json
import os
import sys

import yaml

from utils.logging_utils import get_pipeline_logger, get_error_logger
from utils.cost_tracker import CostTracker

from stages.s01_discover import run_discovery
from stages.s02_extract import run_extraction
from stages.s03_normalize import run_normalization
from stages.s04_dedup import run_dedup
from stages.s05_keyword_filter import run_keyword_filter
from stages.s06a_score_gpt import run_gpt_scoring
from stages.s06b_score_claude import run_claude_scoring
from stages.s07_aggregate import run_aggregation
from stages.s08_spotcheck import run_spotcheck
from stages.s09_shortlist import run_shortlist


def load_config(config_path: str) -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        print(f"ERROR: expected input file not found: {path}", file=sys.stderr)
        sys.exit(1)
    records = []
    with open(path, "r") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def main():
    parser = argparse.ArgumentParser(description="Dual-model document scoring pipeline")
    parser.add_argument("--config", default="config/pipeline_config.yaml",
                        help="Path to pipeline_config.yaml")
    parser.add_argument(
        "--stage", default="all",
        choices=[
            "all",
            "s01", "s02", "s03", "s04", "s05",
            "s06a", "s06b",
            "s07", "s08", "s09",
        ],
        help="Stage to run. 'all' runs the full pipeline S01–S09.",
    )
    args = parser.parse_args()

    config     = load_config(args.config)
    log_dir    = config.get("outputs", {}).get("log_dir", "./logs")
    output_dir = config.get("outputs", {}).get("base_dir", "./outputs")

    logger        = get_pipeline_logger(log_dir)
    error_logger  = get_error_logger(log_dir)
    cost_tracker  = CostTracker(config, output_dir)

    stage = args.stage

    # -------------------------------------------------------------------------
    # S01: File Discovery
    # -------------------------------------------------------------------------
    if stage in ("all", "s01"):
        logger.info("=" * 60)
        logger.info("STAGE S01: File Discovery")
        inventory = run_discovery(config, logger, error_logger)
        if stage == "s01":
            return

    # -------------------------------------------------------------------------
    # S02: Text Extraction
    # -------------------------------------------------------------------------
    if stage in ("all", "s02"):
        logger.info("=" * 60)
        logger.info("STAGE S02: Text Extraction")
        if stage == "s02":
            inventory = load_jsonl(f"{output_dir}/s01_inventory.jsonl")
        extracted = run_extraction(config, inventory, logger, error_logger)
        if stage == "s02":
            return

    # -------------------------------------------------------------------------
    # S03: Normalization
    # -------------------------------------------------------------------------
    if stage in ("all", "s03"):
        logger.info("=" * 60)
        logger.info("STAGE S03: Normalization")
        if stage == "s03":
            extracted = load_jsonl(f"{output_dir}/s02_extracted.jsonl")
        normalized = run_normalization(config, extracted, logger)
        if stage == "s03":
            return

    # -------------------------------------------------------------------------
    # S04: Deduplication
    # -------------------------------------------------------------------------
    if stage in ("all", "s04"):
        logger.info("=" * 60)
        logger.info("STAGE S04: Deduplication")
        if stage == "s04":
            normalized = load_jsonl(f"{output_dir}/s03_normalized.jsonl")
        deduped = run_dedup(config, normalized, logger)
        if stage == "s04":
            return

    # -------------------------------------------------------------------------
    # S05: Keyword Filtering
    # -------------------------------------------------------------------------
    if stage in ("all", "s05"):
        logger.info("=" * 60)
        logger.info("STAGE S05: Keyword Filtering")
        if stage == "s05":
            deduped    = load_jsonl(f"{output_dir}/s04_deduped.jsonl")
            normalized = load_jsonl(f"{output_dir}/s03_normalized.jsonl")
        filtered = run_keyword_filter(config, deduped, normalized, logger)
        if stage == "s05":
            return

    # -------------------------------------------------------------------------
    # S06a: Score with GPT-5.4-mini via OpenAI Batch API
    # Costs money. Blocks until all batches complete (up to 24 hours per batch).
    # Safe to re-run: skips already-scored doc_ids.
    # -------------------------------------------------------------------------
    if stage in ("all", "s06a"):
        logger.info("=" * 60)
        logger.info("STAGE S06a: Scoring with GPT-5.4-mini (OpenAI Batch API)")
        if stage == "s06a":
            filtered   = load_jsonl(f"{output_dir}/s05_filtered.jsonl")
            normalized = load_jsonl(f"{output_dir}/s03_normalized.jsonl")
        run_gpt_scoring(
            config, filtered, normalized, cost_tracker, logger, error_logger
        )
        if stage == "s06a":
            return

    # -------------------------------------------------------------------------
    # S06b: Score with Claude Haiku via Anthropic Batch API
    # Costs money. Blocks until all batches complete.
    # Safe to re-run: skips already-scored doc_ids.
    # -------------------------------------------------------------------------
    if stage in ("all", "s06b"):
        logger.info("=" * 60)
        logger.info("STAGE S06b: Scoring with Claude Haiku (Anthropic Batch API)")
        if stage == "s06b":
            filtered   = load_jsonl(f"{output_dir}/s05_filtered.jsonl")
            normalized = load_jsonl(f"{output_dir}/s03_normalized.jsonl")
        run_claude_scoring(
            config, filtered, normalized, cost_tracker, logger, error_logger
        )
        if stage == "s06b":
            return

    # -------------------------------------------------------------------------
    # S07: Cross-model Aggregation + Disagreement Detection
    # -------------------------------------------------------------------------
    if stage in ("all", "s07"):
        logger.info("=" * 60)
        logger.info("STAGE S07: Cross-model Aggregation")
        if stage == "s07":
            normalized = load_jsonl(f"{output_dir}/s03_normalized.jsonl")
        gpt_scored    = load_jsonl(f"{output_dir}/s06_gpt_scored.jsonl")
        claude_scored = load_jsonl(f"{output_dir}/s06_claude_scored.jsonl")
        aggregated = run_aggregation(
            config, gpt_scored, claude_scored, normalized, logger, error_logger
        )
        if stage == "s07":
            return

    # -------------------------------------------------------------------------
    # S08: 10% Spot-check of Low-Priority Documents
    # -------------------------------------------------------------------------
    if stage in ("all", "s08"):
        logger.info("=" * 60)
        logger.info("STAGE S08: Low-Priority Spot-Check")
        if stage == "s08":
            aggregated = load_jsonl(f"{output_dir}/s07_aggregated.jsonl")
        run_spotcheck(config, aggregated, logger)
        if stage == "s08":
            return

    # -------------------------------------------------------------------------
    # S09: Final Shortlist
    # -------------------------------------------------------------------------
    if stage in ("all", "s09"):
        logger.info("=" * 60)
        logger.info("STAGE S09: Final Shortlist")
        if stage == "s09":
            aggregated = load_jsonl(f"{output_dir}/s07_aggregated.jsonl")
        run_shortlist(config, aggregated, logger)
        if stage == "s09":
            return

    if stage == "all":
        logger.info("=" * 60)
        logger.info("PIPELINE COMPLETE (S01–S09)")
        logger.info(f"Primary output:  {output_dir}/s09_shortlist.csv")
        logger.info(f"Spot-check:      {output_dir}/s08_spotcheck.csv")
        logger.info(f"Full scores:     {output_dir}/s07_aggregated.jsonl")
        cost_tracker.summary()


if __name__ == "__main__":
    main()
