# LA County Document Scoring Pipeline — Claude Code

**Research question:** What institutional design would bridge LA County's care-first
community governance and its AI/tech governance apparatus?

## Your Role

You are the **orchestration agent** for a document relevance scoring pipeline.
Your model is `claude-opus-4-7`. You spawn scorer sub-agents using `claude-haiku-4-5-20251001`.

## How to Run

The user will give you two paths:
- `INPUT_FOLDER` — folder containing LA County documents (PDFs and/or JSONs)
- `OUTPUT_FOLDER` — where all pipeline outputs should be written

Open `prompts/orchestrator_claude.md` and follow it exactly.

## Key Rules

- **Never score a duplicate.** Deduplicate by SHA-256 hash before any scoring call.
- **Batch 20 documents per sub-agent call.** Spawning one agent per document is wasteful.
- **Truncate documents** to approximately 800 words before sending to scorer agents.
  Head-tail truncation: keep the first 400 words and last 400 words.
- **Scorers are Haiku.** Orchestration logic stays in Opus. Do not use a heavyweight
  model for bulk structured scoring.
- **Write to disk after every batch.** Append scored records to the output JSONL
  as batches complete so the run is resumable if interrupted.
- **Resume on restart.** At startup, load any existing scored doc_ids from
  OUTPUT_FOLDER/s06_scored.jsonl and skip them in subsequent batches.

## Scoring Formula (compute locally — never ask the model for a composite)

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
- Codex equivalent: `AGENTS.md` + `prompts/orchestrator_codex.md`
