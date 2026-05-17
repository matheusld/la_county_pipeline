# LA County Document Scoring Pipeline — Codex

**Research question:** What institutional design would bridge LA County's care-first
community governance and its AI/tech governance apparatus?

## Your Role

You are the **orchestration agent** for a document relevance scoring pipeline.
Use `gpt-4o` (or the most capable available model) for orchestration decisions.
Use `gpt-4o-mini` for bulk document scoring sub-tasks.

## How to Run

The user will give you two paths:
- `INPUT_FOLDER` — folder containing LA County documents (PDFs and/or JSONs)
- `OUTPUT_FOLDER` — where all pipeline outputs should be written

Open `prompts/orchestrator_codex.md` and follow it exactly.

## Key Rules

- **Never score a duplicate.** Deduplicate by SHA-256 hash before any scoring call.
- **Batch 20 documents per scoring sub-task.** One request per document wastes cost.
- **Truncate documents** to approximately 800 words before scoring.
  Head-tail: keep first 400 words and last 400 words, join with `\n\n[...TRUNCATED...]\n\n`.
- **Write to disk after every batch.** Append to OUTPUT_FOLDER/s04_scored.jsonl
  continuously so the run is resumable.
- **Resume on restart.** Check OUTPUT_FOLDER/s04_scored.jsonl at startup and
  skip doc_ids already present.

## Scoring Formula (compute locally)

```
composite = (score_carefirst × 0.25) + (score_ai_governance × 0.25)
           + (score_intersection × 0.35) + (score_evidentiary × 0.15)
```

## Priority Tiers

```
Tier 1: composite >= 6.0  AND  (score_carefirst >= 5  OR  score_ai_governance >= 5)
Tier 2: composite >= 3.5
Tier 3: composite >= 1.0
Tier 4: composite < 1.0
```

## Reference

- Full Python implementation: `python/02_batch_pipeline/`
- Scoring prompt: `prompts/scorer_agent.md`
- Claude Code equivalent: `CLAUDE.md` + `prompts/orchestrator_claude.md`
