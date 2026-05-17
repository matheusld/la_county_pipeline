# Agentic Pipeline Prompts

Two ways to run the scoring pipeline — one using Claude Code, one using Codex.
Both replicate the same logic: dedup → keyword score → LLM score → rank → shortlist.

---

## Claude Code (Opus + Haiku sub-agents)

**How it works:**
- Opus orchestrates all stages and makes all decisions
- Haiku sub-agents score documents in batches of 20 (cheapest model, structured task)
- The orchestrator spawns each batch as a sub-agent, collects JSON scores, writes to disk

**To run:**
1. Open Claude Code in this directory
2. Open `orchestrator_claude.md`
3. Replace `{{INPUT_FOLDER}}` and `{{OUTPUT_FOLDER}}` with your actual paths
4. Paste the prompt into Claude Code

The `CLAUDE.md` file at the repo root is read automatically by Claude Code and
pre-configures the scoring formula, tier thresholds, and batching rules.

---

## Codex

**How it works:**
- Uses `gpt-4o` (or current equivalent) for orchestration
- Uses `gpt-4o-mini` for batch scoring sub-tasks
- Same pipeline stages, same output file names, same scoring dimensions

**To run:**
1. Open Codex in this directory
2. Open `orchestrator_codex.md`
3. Replace `{{INPUT_FOLDER}}` and `{{OUTPUT_FOLDER}}` with your actual paths
4. Paste the prompt into Codex

The `AGENTS.md` file at the repo root is read automatically by Codex.

---

## Shared Scorer Prompt

`scorer_agent.md` contains the four-dimension scoring criteria used by both pipelines.
The orchestrators embed this prompt when spawning batch scoring tasks. The same prompt
is also used by the Python pipeline (`python/02_batch_pipeline/`) — it corresponds to
`scoring_v1` in `config/pipeline_config.yaml`.

---

## Output Files (both pipelines produce the same names)

```
OUTPUT_FOLDER/
├── s01_inventory.jsonl         file discovery
├── s02_extracted.jsonl         raw text per document
├── s03_normalized.jsonl        cleaned text
├── s04_deduped.jsonl           near-duplicate flags
├── s05_keyword_scored.jsonl    domain keyword scores
├── s06_scored.jsonl            LLM dimension scores (resumable)
├── s07_ranked.jsonl            composite + tier per document
├── s08_spotcheck.csv           10% sample of low-priority docs for human validation
└── s09_shortlist.csv           final ranked shortlist (~167 docs) ← primary output
```

---

## Cost Notes

**Claude Code** (Haiku scoring, 9,000 docs, 20 docs/batch):
- ~450 Haiku agent calls × ~20K tokens each ≈ 9M input tokens
- At Haiku standard pricing (~$0.80/1M input, ~$4/1M output): roughly $15–20
- Faster and more interactive than the batch API, but ~10× more expensive per token

**Codex** (gpt-4o-mini scoring):
- Similar token volume at gpt-4o-mini pricing: roughly $10–15

The Python batch pipeline (`python/02_batch_pipeline/`) costs ~$2.50 for the same
corpus using the 50% batch API discount and smaller output tokens. Use it when cost
is a constraint and a 24-hour turnaround is acceptable.
