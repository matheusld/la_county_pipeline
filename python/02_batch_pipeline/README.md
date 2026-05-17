# Phase 2 — Dual-Model Scoring & Tiering Pipeline

Processes ~9,000 LA County Board of Supervisors documents through seven stages,
scoring each document independently with two LLMs, comparing the scores to detect
disagreements, and producing a ranked shortlist for qualitative analysis.

**Source:** `C:\Users\Matheus.Ligeiro\triage_documents`
**Research question:** What institutional design would bridge LA County's care-first
community governance and its AI/tech governance apparatus?

---

## Why Two Models?

Both GPT-5.4-mini (OpenAI) and Claude Haiku (Anthropic) score every document
independently using the same prompt. Then:

- Documents where **both models score high** → included in shortlist with high confidence
- Documents where **models disagree** (|composite difference| >= 2.0) → flagged and
  included regardless of their average score, because the lower-scoring model may be
  underfitting relevance
- Documents where **both models score low** → low-priority pool; 10% is spot-checked
  by a human to estimate the false-negative rate

This reduces dependence on any single model's systematic biases and surfaces
borderline cases that a single-model pipeline would silently discard.

---

## Pipeline Overview

Stages S01–S05 are free and deterministic. S06a and S06b cost money. S07–S09 are free.

| Stage | What it does | Cost | Output |
|-------|-------------|------|--------|
| S01 Discover | File walk + SHA-256 hash | $0 | `s01_inventory.jsonl` |
| S02 Extract | pdfplumber + pytesseract OCR | $0 | `s02_extracted.jsonl` |
| S03 Normalize | Unicode cleanup + truncation | $0 | `s03_normalized.jsonl` |
| S04 Dedup | MinHash LSH (Jaccard 0.85) | $0 | `s04_deduped.jsonl` |
| S05 Keyword Filter | Domain keyword scoring | $0 | `s05_filtered.jsonl` |
| S06a Score (GPT) | Score with GPT-5.4-mini (OpenAI Batch API) | ~$1.50 / 9k docs | `s06_gpt_scored.jsonl` |
| S06b Score (Claude) | Score with Claude Haiku (Anthropic Batch API) | ~$1.00 / 9k docs | `s06_claude_scored.jsonl` |
| S07 Aggregate | Join scores, flag disagreements, assign final tier | $0 | `s07_aggregated.jsonl` |
| S08 Spot-check | Random 10% sample of low-priority docs | $0 | `s08_spotcheck.csv` |
| S09 Shortlist | Final ranked shortlist (~167 docs) | $0 | `s09_shortlist.csv` |

---

## Prerequisites

```bash
pip install pdfplumber pytesseract datasketch openai anthropic pyyaml pydantic pandas
```

`tesseract-ocr` system package (OCR fallback for image-only PDFs):

```bash
# Windows — installer at https://github.com/UB-Mannheim/tesseract/wiki
# Ubuntu/Debian
sudo apt install tesseract-ocr
```

Copy the placeholder and fill in your keys:

```bash
# Windows
copy .env.example .env

# Mac/Linux
cp .env.example .env
```

Open `.env` and replace the placeholder values, then load:

```bash
# Windows (PowerShell)
foreach ($line in Get-Content .env) { if ($line -notmatch '^#') { $parts = $line -split '=', 2; [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1]) } }

# Mac/Linux
export $(grep -v '^#' .env | xargs)
```

Only S06a and S06b need keys. S01–S05 and S07–S09 run without them.

---

## Configuration

All parameters live in `config/pipeline_config.yaml`. Set these before your first run:

```yaml
sources:
  extracted_text_supporting:
    path: ./data/extracted_text_supporting   # from Phase 1
  board_comms:
    path: ./data/board_comms                 # PDF folder

outputs:
  base_dir: ./outputs

scoring:
  gpt_model: gpt-5.4-mini
  claude_model: claude-haiku-4-5

aggregate:
  disagreement_threshold: 2.0   # composite delta that triggers flagging

shortlist:
  target_size: 167              # final shortlist length
```

Keyword domains are in `config/keywords.yaml`.

---

## Step-by-Step

### Step 1 — Point config at your source folders

Open `config/pipeline_config.yaml`, set `sources` paths to the directories from Phase 1
(or any folders containing PDFs/JSONs to triage).

### Step 2 — Run the free preprocessing stages

```bash
python run_pipeline.py --stage s01
python run_pipeline.py --stage s02
python run_pipeline.py --stage s03
python run_pipeline.py --stage s04
python run_pipeline.py --stage s05
```

Or in one command (stops before paying anything):

```bash
python run_pipeline.py --stage all --config config/pipeline_config.yaml
# (will run S01–S09 but you can stop after S05 manually if you want to check first)
```

Check `outputs/s05_filtered.jsonl` before spending money — verify document counts
and keyword scores look reasonable.

### Step 3 — Score with both models (costs ~$2.50 per 9,000 docs)

Run both scoring stages. They can run in either order; each is independent.

```bash
# GPT scoring (~$1.50 for 9k docs via OpenAI Batch API)
python run_pipeline.py --stage s06a

# Claude scoring (~$1.00 for 9k docs via Anthropic Batch API)
python run_pipeline.py --stage s06b
```

Each stage submits documents in chunks and polls until all batches complete
(up to 24 hours per batch window, typically under 2 hours). Re-running is safe:
already-scored doc_ids are skipped.

### Step 4 — Aggregate, spot-check, and generate shortlist

```bash
python run_pipeline.py --stage s07   # joins scores, flags disagreements
python run_pipeline.py --stage s08   # 10% spot-check CSV for human review
python run_pipeline.py --stage s09   # final ranked shortlist
```

### Step 5 — Review the outputs

- **`outputs/s09_shortlist.csv`** — the primary research output: ~167 documents ranked
  by averaged composite score, annotated with both models' composites and rationales.
- **`outputs/s08_spotcheck.csv`** — 10% spot-check of low-priority documents. Open this
  in Excel, fill in the `review_status` column (`confirmed_low` / `escalate` /
  `uncertain`), and report results in your methods appendix.
- **`outputs/s07_aggregated.jsonl`** — full record for every document: all dimension
  scores from both models, disagreement flags, final tier, text preview.

---

## Run All Stages at Once

```bash
python run_pipeline.py --stage all
```

This runs S01 through S09. Both scoring stages block until their batch jobs complete,
so the full pipeline can take several hours if processing thousands of documents.

---

## Output Files

```
outputs/
├── s01_inventory.jsonl          file discovery — one record per file
├── s02_extracted.jsonl          extracted text per document
├── s03_normalized.jsonl         cleaned text
├── s04_deduped.jsonl            near-duplicate flags (flagged, not removed)
├── s05_filtered.jsonl           keyword domain scores
├── s06_gpt_scored.jsonl         GPT-5.4-mini dimension scores per document
├── s06_claude_scored.jsonl      Claude Haiku dimension scores per document
├── s07_aggregated.jsonl         merged scores, disagreement flags, final tier
├── s08_spotcheck.jsonl          low-priority spot-check sample (JSONL)
├── s08_spotcheck.csv            low-priority spot-check sample (for review)
├── s09_shortlist.jsonl          final ranked shortlist (JSONL)
├── s09_shortlist.csv            final ranked shortlist (for researcher)
└── cost_log.jsonl               per-stage token and cost accounting
```

---

## Key Fields Per Document (s07_aggregated.jsonl)

| Field | Meaning |
|-------|---------|
| `doc_id` | SHA-256 of file content — stable dedup key |
| `gpt_composite` | GPT weighted composite (locally computed) |
| `claude_composite` | Claude weighted composite (locally computed) |
| `composite_delta` | \|gpt − claude\| — disagreement magnitude |
| `flagged_disagreement` | True if delta >= 2.0 (configurable) |
| `final_composite` | Average composite across both models |
| `final_tier` | 1 (cite) / 2 (background) / 3 (skim) / 4 (irrelevant) |
| `priority_review` | True if Tier 1/2 or flagged — included in shortlist |

Full Pydantic field definitions are in `utils/schemas.py`.

---

## Scoring Dimensions

All four dimensions are scored 0–10 by each model using the `scoring_v1` prompt
defined in `config/pipeline_config.yaml`:

| Dimension | What it measures |
|-----------|-----------------|
| `score_carefirst` | Care-first governance relevance (Measure J, CFCI, ODR, DYD…) |
| `score_ai_governance` | AI/tech governance relevance (TD 24-04, GenAI Board, ISD…) |
| `score_intersection` | Explicit connection between the two governance systems |
| `score_evidentiary` | Concrete evidence quality: named actors, dollar amounts, contract IDs |

**Composite formula** (applied locally, model output never trusted):
```
composite = carefirst×0.25 + ai_governance×0.25 + intersection×0.35 + evidentiary×0.15
```

**Tier thresholds** (applied to the averaged final composite):
```
Tier 1 — composite >= 6.0 AND (carefirst >= 5 OR ai_governance >= 5)
Tier 2 — composite >= 3.5
Tier 3 — composite >= 1.0
Tier 4 — composite < 1.0
```

---

## Cost Check

```bash
python -c "
import json
total = sum(r['cost_usd'] for r in (json.loads(l) for l in open('outputs/cost_log.jsonl')))
print(f'Total spent: \${total:.4f}')
"
```

---

## Known Issues

- **Batch timeouts:** If an OpenAI or Anthropic batch job expires before completing,
  re-run the affected stage. Already-scored doc_ids are skipped automatically.
- **One model fails:** If one scoring stage completely fails, S07 will warn about
  missing doc_ids and fall back to using the available model's scores. The shortlist
  will still be produced but `composite_delta` and `flagged_disagreement` will be
  meaningless for those documents.
- **Prompt hash:** `COMPUTED_AT_RUNTIME` in the config is a placeholder; the actual
  SHA-256 is computed at run time by `utils/provenance.py` and stored in each scored record.
