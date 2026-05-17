# Phase 1 — Document Collection

Scrapes LA County Board of Supervisors records, extracts text from PDFs, ranks the
supporting-document corpus by relevance, and runs batch triage to score every document.

**Source:** `C:\Users\Matheus.Ligeiro\scrap_page`

---

## What This Phase Does

1. Scrapes Board transcripts, SOPs, and supporting PDFs by date range or keyword list
2. Extracts text from PDFs into structured JSON
3. Ranks the large supporting-document corpus using local keyword heuristics (no LLM, free)
4. Builds and submits an OpenAI Batch triage over the ranked shortlist

---

## Prerequisites

```bash
pip install playwright pdfplumber openai pandas openpyxl
playwright install chromium
```

Set your OpenAI API key — copy the placeholder file and fill it in:

```bash
# Mac/Linux
cp .env.example .env

# Windows
copy .env.example .env
```

Open `.env` and replace `your-openai-api-key-here` with your actual key, then load it:

```bash
# Mac/Linux
export $(grep -v '^#' .env | xargs)

# Windows (PowerShell)
foreach ($line in Get-Content .env) { if ($line -notmatch '^#') { $parts = $line -split '=', 2; [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1]) } }
```

Steps 1–4 (scraping and text extraction) need no API key — only the batch triage steps do.

---

## Step-by-Step

### Step 1 — Scrape transcript/SOP documents by date

```bash
python scrape_lacounty_sop.py \
  --doc-type transcripts \
  --start-date 2020-01-01 \
  --end-date 2026-03-31 \
  --output-dir ./lacounty_analysis_docs
```

`--doc-type` accepts: `transcripts`, `sop`, `supporting`, `all`

Uses 14-day search chunks to avoid the page's result limit. Expect 30–90 minutes for
a multi-year range.

---

### Step 2 — Scrape supporting documents by keyword

```bash
python scrape_lacounty_keywords.py \
  --output-dir ./lacounty_keyword_docs \
  --state-file ./lacounty_keyword_scraper_state.json
```

The `--state-file` flag enables resume — re-run the same command after any interruption
and it skips already-completed keywords.

Searches 283 keywords across AI/tech governance, Care First, vendors, departments, and
homelessness topics. Expect 8,000–10,000 PDFs and several hours of runtime.

---

### Step 3 — Extract text from PDFs

```bash
# Transcripts/SOP corpus
python extract_text.py \
  --input-dir ./lacounty_analysis_docs \
  --output-dir ./extracted_text \
  --doc-type transcripts \
  --workers 4

# Supporting-document corpus
python extract_text.py \
  --input-dir ./lacounty_keyword_docs \
  --output-dir ./extracted_text_supporting \
  --doc-type supporting \
  --workers 4
```

Output: one JSON per PDF with fields `filename`, `doc_type`, `meeting_date`, `text`,
`char_count`, `word_count`.

---

### Step 4 — Rank supporting documents (free, no LLM)

```bash
python rank_supporting_docs_v2.py \
  --input-dir ./extracted_text_supporting \
  --output-dir ./rank_outputs_v4
```

Scores documents using local keyword and proximity heuristics — no API calls, no cost.
Output: `ranked_all.csv` (all docs) and `api_shortlist.csv` (shortlist, `api_score >= 26`).
Use `api_shortlist.csv` as input to the batch triage step.

---

### Step 5 — Build OpenAI batch triage requests

```bash
python build_openai_batch_requests_v5.py \
  --shortlist ./api_shortlist.csv \
  --scan-dir ./extracted_text \
  --board-comms-dir ./board_comms \
  --output ./openai_batch_input_v5.jsonl \
  --manifest ./openai_batch_manifest_v5.csv \
  --model gpt-5.4-nano
```

---

### Step 6 — Split the batch (required before submission)

The full JSONL will exceed OpenAI's enqueued-token limit. Always split first:

```bash
python split_openai_batch_jsonl.py \
  --input ./openai_batch_input_v5.jsonl \
  --output-dir ./batch_shards \
  --max-tokens 1800000
```

---

### Step 7 — Submit and monitor shards

```bash
python run_openai_batch_multi.py \
  --shards-dir ./batch_shards \
  --status-dir ./batch_status \
  --output-dir ./batch_outputs \
  --model gpt-5.4-nano
```

Shards complete within 24 hours. The script polls every 60 seconds and prints status.

---

### Step 8 — Parse batch results

```bash
python parse_openai_batch_results_v5.py \
  --input-dir ./batch_outputs \
  --manifest ./openai_batch_manifest_v5.csv \
  --output ./batch_triage_results_v5.csv
```

---

## File Map

| Script | Does |
|--------|------|
| `scrape_lacounty_sop.py` | Download transcripts/SOPs/supporting PDFs by date range |
| `scrape_lacounty_keywords.py` | Keyword-driven PDF acquisition (resumable) |
| `extract_text.py` | PDF → JSON text extraction (parallel workers) |
| `rank_supporting_docs_v2.py` | Local heuristic ranking — no LLM, free |
| `build_openai_batch_requests_v5.py` | Assemble batch JSONL + manifest |
| `split_openai_batch_jsonl.py` | Split JSONL into shards (required before submission) |
| `run_openai_batch_multi.py` | Submit shards + poll until complete |
| `parse_openai_batch_results_v5.py` | Parse merged batch output into CSV |

---

## Known Issues

- **Batch token limits:** `gpt-5.4-nano` org limit is 2M enqueued tokens. Always split
  into shards of ≤ 1.8M tokens. The original 26-shard run completed, but most responses
  were **incomplete** because `max_output_tokens` was too low. Fix: set
  `max_output_tokens` to 2,000–3,000 per request before rebuilding the batch.

- The outputs from this phase feed into `02_batch_pipeline` as source documents.
