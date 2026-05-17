# LA County Document Collection & Triage Pipeline

**UC Berkeley Goldman School of Public Policy — MPP Capstone, Spring 2026**

Two-phase pipeline for collecting LA County Board of Supervisors documents and
scoring them for research relevance using two independent LLMs.

**Client:** Derek Steele, Executive Director, Social Justice Learning Institute (SJLI)
**Research question:** What institutional design would bridge LA County's care-first
community governance and its AI/tech governance apparatus?

---

## Two Phases

| | [01_scraping](01_scraping/) | [02_batch_pipeline](02_batch_pipeline/) |
|--|--|--|
| **What it does** | Scrapes + extracts documents | Scores + ranks documents |
| **Interface** | Command line | Command line |
| **LLM** | OpenAI (optional batch triage step) | GPT-5.4-mini + Claude Haiku (dual-model) |
| **Cost** | ~$0 (scraping is free; triage step optional) | ~$2.50 for 9,000 docs |

---

## Full Pipeline (in order)

```
Phase 1 — Collect
  ↓  scrape_lacounty_sop.py              Download transcripts/SOPs by date range
  ↓  scrape_lacounty_keywords.py         Download supporting docs via keyword list (resumable)
  ↓  extract_text.py                     PDF → JSON (parallel workers)
  ↓  rank_supporting_docs_v2.py          Keyword heuristic ranking — free, no LLM
  ↓  build_openai_batch_requests_v5.py   Assemble batch triage requests (optional)
  ↓  split_openai_batch_jsonl.py         Split into shards (token limit workaround)
  ↓  run_openai_batch_multi.py           Submit + poll until complete
  ↓  parse_openai_batch_results_v5.py    Parse results into CSV

Phase 2 — Score & Rank
  ↓  S01 Discover        Walk folders, SHA-256 hash every file
  ↓  S02 Extract         pdfplumber + pytesseract OCR fallback
  ↓  S03 Normalize       Unicode cleanup, truncation
  ↓  S04 Dedup           MinHash LSH near-duplicate detection
  ↓  S05 Keyword Filter  Domain scoring (additive — never discards)
  ↓  S06_GPT   Score     GPT-5.4-mini via OpenAI Batch API
  ↓  S06_CLAUDE Score    Claude Haiku via Anthropic Batch API
  ↓  S07 Aggregate       Join scores, detect disagreements, assign final tier
  ↓  S08 Spot-check      Random 10% sample of low-priority docs for validation
  ↓  S09 Shortlist       Final ranked list of ~167 documents for human review
```

---

## Why Two Models?

Both models score every document independently on the same four dimensions. Then:

- Documents where **both models agree and score high** → high-confidence shortlist inclusion
- Documents where **models disagree** (composite score gap ≥ 2.0) → always included in
  shortlist, because the lower-scoring model may be wrong
- Documents where **both models score low** → low-priority pool; 10% is spot-checked
  to estimate the false-negative rate

This reduces dependence on any single model's systematic biases.

---

## Directory Structure

```
python/
├── README.md                              ← You are here
│
├── 01_scraping/
│   ├── README.md                          ← Step-by-step guide
│   ├── scrape_lacounty_sop.py             Scrape by date / doc type
│   ├── scrape_lacounty_keywords.py        Scrape by keyword list (resumable)
│   ├── extract_text.py                    PDF → JSON
│   ├── rank_supporting_docs_v2.py         Heuristic ranking (free)
│   ├── build_openai_batch_requests_v5.py  Build batch JSONL + manifest
│   ├── split_openai_batch_jsonl.py        Split for token limits
│   ├── run_openai_batch_multi.py          Submit + poll shards
│   └── parse_openai_batch_results_v5.py   Parse results
│
└── 02_batch_pipeline/
    ├── README.md                          ← Step-by-step guide
    ├── requirements.txt                   pip install -r requirements.txt
    ├── run_pipeline.py                    Run any stage or all stages
    ├── jsonl_to_xlsx_v2.py                Export any pipeline JSONL to Excel
    ├── stages/
    │   ├── s01_discover.py                File discovery + SHA-256 hashing
    │   ├── s02_extract.py                 PDF/JSON text extraction
    │   ├── s03_normalize.py               Unicode cleanup + truncation
    │   ├── s04_dedup.py                   MinHash LSH near-duplicate detection
    │   ├── s05_keyword_filter.py          Domain keyword scoring
    │   ├── s06a_score_gpt.py              GPT-5.4-mini scoring (OpenAI Batch API)
    │   ├── s06b_score_claude.py           Claude Haiku scoring (Anthropic Batch API)
    │   ├── s07_aggregate.py               Cross-model aggregation + disagreement detection
    │   ├── s08_spotcheck.py               Random 10% spot-check sample
    │   └── s09_shortlist.py               Final ranked shortlist (~167 docs)
    ├── utils/
    │   ├── schemas.py                     Pydantic models — living data dictionary
    │   ├── cost_tracker.py                Token and cost accounting
    │   ├── logging_utils.py               Pipeline and error loggers
    │   └── provenance.py                  Prompt SHA-256 versioning
    └── config/
        ├── pipeline_config.yaml           All parameters + embedded prompts
        └── keywords.yaml                  Keyword domain lists
```

---

## Which Phase to Start With

**If you already have the documents** (extracted JSON from Phase 1, or any folder of
PDFs/JSONs): go straight to `02_batch_pipeline`. Point `config/pipeline_config.yaml`
at your source folders and run `python run_pipeline.py --stage all`.

**If you need to collect documents first**: start with `01_scraping`. The extracted
JSON files it produces are the direct input to Phase 2.

---

## API Keys

Phase 2 uses both OpenAI (S06_GPT) and Anthropic (S06_CLAUDE).

```bash
# Windows
copy python\02_batch_pipeline\.env.example python\02_batch_pipeline\.env

# Mac/Linux
cp python/02_batch_pipeline/.env.example python/02_batch_pipeline/.env
```

Open `.env`, replace the placeholders, then load:

```bash
# Mac/Linux
export $(grep -v '^#' .env | xargs)

# Windows (PowerShell)
foreach ($line in Get-Content .env) {
  if ($line -notmatch '^#') {
    $parts = $line -split '=', 2
    [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1])
  }
}
```

Only S06_GPT and S06_CLAUDE need keys. All other stages run without them.
