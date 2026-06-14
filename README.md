# LA County Document Scoring Pipeline

A reproducible pipeline for processing, scoring, and ranking roughly 9,000 LA County public documents to identify a targeted shortlist for qualitative policy analysis.

The project supports three execution paths: interactive agentic workflows with Claude Code or Codex, and a lower-cost Python batch pipeline using OpenAI and Anthropic APIs. Each path produces comparable staged outputs, from inventory and text extraction through scoring, ranking, spot-checking, and final shortlist generation.

---

## Three Ways to Run

| | [Claude Code](#claude-code-agentic) | [Codex](#codex-agentic) | [Python](#python-batch-api) |
|--|--|--|--|
| **Models** | Opus orchestrates, Haiku scores | GPT-4o orchestrates, GPT-4o-mini scores | GPT-5.4-mini + Claude Haiku (dual) |
| **Cost** | ~$15-20 (agentic, standard pricing) | ~$10-15 (agentic) | ~$2.50 (batch API discount) |
| **Turnaround** | ~1 hour interactive | ~1 hour interactive | ~24 hours (async) |
| **Best for** | Quick, interactive, no setup | OpenAI users | Reproducible research, cost-sensitive |

---

## Claude Code (agentic)

**How `CLAUDE.md` and `prompts/orchestrator_claude.md` relate:**

- **`CLAUDE.md`** - project context that Claude Code reads automatically when you open
  this folder. It sets model assignments, scoring rules, and batching constraints.
  **You do not paste it anywhere.** It loads silently in the background.

- **`prompts/orchestrator_claude.md`** - the actual task prompt. This is what you send
  to Claude Code to start the pipeline.

**Steps:**

1. Open Claude Code in this directory (`claude` in terminal, or open the app and point
   it here). `CLAUDE.md` loads automatically.
2. Open [`prompts/orchestrator_claude.md`](prompts/orchestrator_claude.md).
3. At the top, replace the two placeholders:
   ```
   INPUT_FOLDER  = /path/to/your/documents
   OUTPUT_FOLDER = /path/to/write/outputs
   ```
4. Paste the entire prompt as your first message to Claude Code and press Enter.
5. Claude Code (Opus) will execute all nine stages, spawning Haiku sub-agents for
   batch scoring. Progress is printed after each batch. You can stop and resume at
   any point - already-scored documents are skipped on restart.

**Output:** `OUTPUT_FOLDER/s09_shortlist.csv` - the primary research output.

---

## Codex (agentic)

Same flow, different models:

1. Open Codex in this directory. `AGENTS.md` loads automatically.
2. Open [`prompts/orchestrator_codex.md`](prompts/orchestrator_codex.md).
3. Replace `{{INPUT_FOLDER}}` and `{{OUTPUT_FOLDER}}`.
4. Paste the prompt as your first message to Codex.

---

## Python (batch API)

The Python pipeline produces the same outputs using the OpenAI and Anthropic batch
APIs (50% discount, ~24-hour turnaround). It also scores with two models independently
and flags disagreements for human review.

See [`python/README.md`](python/README.md) for setup and usage.

Quick start:
```bash
cd python/02_batch_pipeline
pip install -r requirements.txt
cp .env.example .env          # fill in your API keys
python run_pipeline.py --stage all
```

---

## Output Files (all three approaches produce the same names)

```
OUTPUT_FOLDER/
├── s01_inventory.jsonl         file discovery
├── s02_extracted.jsonl         raw text per document
├── s03_normalized.jsonl        cleaned text
├── s04_deduped.jsonl           near-duplicate flags
├── s05_keyword_scored.jsonl    domain keyword scores
├── s06_scored.jsonl            LLM dimension scores   ← agentic pipelines
├── s06_gpt_scored.jsonl        GPT scores             ← Python pipeline
├── s06_claude_scored.jsonl     Claude scores          ← Python pipeline
├── s07_ranked.jsonl            composite + tier per document
├── s08_spotcheck.csv           10% sample for human validation
└── s09_shortlist.csv           final ranked shortlist (~167 docs) ← primary output
```

---

## Scoring at a Glance

Four dimensions (0-10 each), scored independently per document:

| Dimension | What it measures |
|-----------|-----------------|
| `score_carefirst` | Relevance to care-first governance (Measure J, ATI, DYD, etc.) |
| `score_ai_governance` | Relevance to AI/tech governance (TD 24-04, ISD procurement, etc.) |
| `score_intersection` | Explicit connection between the two governance systems |
| `score_evidentiary` | Concrete evidence quality for academic citation |

```
composite = carefirst×0.25 + ai_governance×0.25 + intersection×0.35 + evidentiary×0.15

Tier 1: composite >= 6.0  AND  (carefirst >= 5  OR  ai_governance >= 5)
Tier 2: composite >= 3.5
Tier 3: composite >= 1.0
Tier 4: composite < 1.0   (low-priority pool, 10% spot-checked)
```

See [`python/METHODS_APPENDIX.md`](python/METHODS_APPENDIX.md) for a plain-English
explanation of the full methodology.
