# Pipeline Orchestrator — Claude Code (Opus)

## Fill These In Before Running

```
INPUT_FOLDER  = {{INPUT_FOLDER}}
OUTPUT_FOLDER = {{OUTPUT_FOLDER}}
```

---

## Your Role

You are the orchestration agent for a document relevance scoring pipeline. You will
execute the pipeline end-to-end, delegating all bulk document scoring to Haiku
sub-agents. Your model is Opus; scorers are Haiku (`claude-haiku-4-5-20251001`).

Do not ask for confirmation between stages. Work through all stages sequentially,
logging progress at each step. Write results to disk after every batch so the run
is resumable if interrupted.

---

## Stage 1 — Inventory

**Goal:** Collect every document file and compute a stable content-based ID.

Use Bash to walk INPUT_FOLDER recursively and find all `.pdf`, `.json`, and `.txt`
files. For each file, compute a SHA-256 hash of its content using Python:

```python
import hashlib, os, json

def hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
```

Write one JSON record per file to `OUTPUT_FOLDER/s01_inventory.jsonl`:
```json
{"doc_id": "<sha256>", "filename": "<name>", "original_path": "<full path>",
 "file_type": "<pdf|json|txt>", "file_size_bytes": <int>}
```

Log: total files found, breakdown by type.

---

## Stage 2 — Text Extraction

**Goal:** Get plain text from every file.

For each record in `s01_inventory.jsonl`:

**JSON files:** Read with Python `json.load()`. Look for text in this priority order:
`text`, `normalized_text`, `content`, `body`, `extracted_text`. If none found,
concatenate all string values longer than 50 characters.

**PDF files:** Run pdfplumber via Python:
```python
import pdfplumber
with pdfplumber.open(path) as pdf:
    text = "\n".join(page.extract_text() or "" for page in pdf.pages)
```
If pdfplumber returns empty text, note `extraction_status = "failed"`.

**TXT files:** Read directly.

Write to `OUTPUT_FOLDER/s02_extracted.jsonl`, one record per file:
```json
{"doc_id": "<sha256>", "filename": "...", "original_path": "...", "file_type": "...",
 "extraction_status": "success|failed", "text_length": <int>, "raw_text": "<text>"}
```

Log: success count, failure count.

---

## Stage 3 — Normalization

**Goal:** Clean text and flag documents too short to score.

For each successfully extracted document, apply in Python:
1. Normalize unicode: `import unicodedata; text = unicodedata.normalize("NFKC", text)`
2. Collapse whitespace: `" ".join(text.split())`
3. Remove lines that are only numbers or "Page N of N" patterns
4. Flag `too_short = True` if normalized text has fewer than 50 words

Write to `OUTPUT_FOLDER/s03_normalized.jsonl`:
```json
{"doc_id": "...", "filename": "...", "original_path": "...", "extraction_status": "...",
 "normalized_text": "...", "normalized_word_count": <int>, "too_short": <bool>}
```

---

## Stage 4 — Deduplication

**Goal:** Mark exact and near-duplicates so they are not scored.

**Exact duplicates:** Group records from `s03_normalized.jsonl` by `doc_id` (SHA-256
of file content). Within each group, keep the first occurrence; mark the rest
`is_duplicate = true, duplicate_of = <canonical doc_id>`.

**Near-duplicates:** For documents not already flagged, normalize the first 300 words
of text to lowercase and compare fingerprints. Two documents are near-duplicates if
their 5-gram shingle sets share more than 80% of elements (Jaccard similarity > 0.80).
Use a simple Python implementation:
```python
def shingles(text, k=5):
    words = text.lower().split()
    return set(tuple(words[i:i+k]) for i in range(len(words)-k+1))

def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
```
When a near-duplicate is found, keep the document with more text; mark the other
`is_duplicate = true`.

Write to `OUTPUT_FOLDER/s04_deduped.jsonl`:
```json
{"doc_id": "...", "filename": "...", "original_path": "...", "extraction_status": "...",
 "normalized_word_count": <int>, "is_duplicate": <bool>, "duplicate_of": "<doc_id|null>"}
```

Log: total documents, duplicates removed, unique documents remaining.

---

## Stage 5 — Keyword Scoring

**Goal:** Add a domain signal score to each document (additive, never discards).

For each non-duplicate document's normalized text, count keyword matches from these
domain lists (case-insensitive). Each distinct term match adds 0.3 to the domain score;
each domain score is capped at 3.0.

**ai_governance keywords:**
artificial intelligence, machine learning, predictive analytics, algorithmic, algorithm,
automated decision, decision support, risk assessment, COMPAS, pretrial risk,
technology directive, TD 24-04, GenAI, generative AI, governance board,
chief information officer, CIO, CISO, chief privacy officer, data governance,
facial recognition, surveillance, automated eligibility, benefits automation,
triage tool, matching algorithm, HMIS, coordinated entry, decision lens

**care_first keywords:**
care first, care-first, Measure J, Measure G, CFCI, community investment,
alternatives to incarceration, ATI, youth justice reimagined, department of youth
development, DYD, ready to rise, restorative justice, diversion, community-based,
reentry, justice reform, advisory committee, community governance, participatory,
JCOD, justice care opportunities

**procurement keywords:**
procurement, RFP, RFI, request for proposal, request for information,
master agreement, ISD, vendor, contractor, contract, sole source, piggyback,
technology acquisition, Northpointe, Palantir, Axon, LiveView, Collective Medical

**institutional_actors keywords:**
Board of Supervisors, DCFS, DPSS, DMH, DPH, probation, Peter Loo,
Lillian Russell, James Thurmond, Mirian Avalos, Lawrence Gann, Derek Steele,
SJLI, Social Justice Learning Institute, LAANE, LeadersUp, technology management council

Append keyword fields to `s04_deduped.jsonl` records and write to
`OUTPUT_FOLDER/s05_keyword_scored.jsonl`:
```json
{"doc_id": "...", ...(all prior fields)...,
 "keyword_score": <float>,
 "keyword_matches": ["care_first", "ai_governance"]}
```

---

## Stage 6 — Scoring (Sub-Agent Delegation)

**Goal:** Score every eligible document on four relevance dimensions using Haiku agents.

**Eligible documents:** `is_duplicate = false` AND `too_short = false` AND
`extraction_status = "success"`.

**Resumability:** Before starting, load `OUTPUT_FOLDER/s06_scored.jsonl` if it exists
and collect the set of already-scored `doc_id` values. Skip those documents.

**Truncation (apply before sending to agent):**
If a document has more than 800 words, truncate using head-tail:
```
[first 400 words] + "\n\n[...TRUNCATED...]\n\n" + [last 400 words]
```

**Batching:** Process documents in batches of 20. For each batch, spawn a sub-agent:

```
Model:  claude-haiku-4-5-20251001
Prompt: [content of prompts/scorer_agent.md, with {{DOCUMENTS}} replaced by the batch]
```

Format the `{{DOCUMENTS}}` section as follows — one entry per document:

```
--- DOCUMENT 1 ---
doc_id: <doc_id>
filename: <filename>

<truncated text>

--- DOCUMENT 2 ---
...
```

The sub-agent returns a JSON array with one score object per document (same order
as input). Parse the array. If a document's entry is missing or malformed, assign
`score_error = "agent returned no score"` and default all scores to 0.

**After each batch:** Append the batch results to `OUTPUT_FOLDER/s06_scored.jsonl`
immediately (do not accumulate in memory and write at the end):
```json
{"doc_id": "...", "filename": "...", "original_path": "...", "keyword_score": <float>,
 "keyword_matches": [...], "score_carefirst": <int>, "score_ai_governance": <int>,
 "score_intersection": <int>, "score_evidentiary": <int>, "rationale": "...",
 "score_error": null, "scored_by": "claude-haiku-4-5-20251001"}
```

Log after each batch: batch number, docs in batch, cumulative scored count.

---

## Stage 7 — Composite and Tier Assignment

**Goal:** Compute the final weighted composite and assign a priority tier.

Read `s06_scored.jsonl`. For each record, compute locally:

```
composite = (score_carefirst × 0.25)
           + (score_ai_governance × 0.25)
           + (score_intersection × 0.35)
           + (score_evidentiary × 0.15)
```

Assign tier:
```
Tier 1: composite >= 6.0  AND  (score_carefirst >= 5  OR  score_ai_governance >= 5)
Tier 2: composite >= 3.5
Tier 3: composite >= 1.0
Tier 4: composite < 1.0
```

Write to `OUTPUT_FOLDER/s07_ranked.jsonl` — all prior fields plus:
```json
{"composite": <float>, "tier": <1|2|3|4>}
```

Log: tier distribution (count per tier).

---

## Stage 8 — Spot-Check Sample

**Goal:** Sample 10% of low-priority documents to estimate the false-negative rate.

From `s07_ranked.jsonl`, collect all Tier 3 and Tier 4 documents.
Using Python's `random.Random(seed=42)`, draw a sample of `ceil(pool_size × 0.10)`.

Write to `OUTPUT_FOLDER/s08_spotcheck.csv` with columns:
```
doc_id, filename, tier, composite, score_carefirst, score_ai_governance,
score_intersection, score_evidentiary, keyword_score, rationale,
text_preview (first 400 words), review_status (leave blank), reviewer_notes (leave blank)
```

Log: pool size, sample size.

---

## Stage 9 — Final Shortlist

**Goal:** Produce the ranked shortlist for researcher review.

From `s07_ranked.jsonl`:
1. Select all Tier 1 documents (always included, never truncated).
2. Select all Tier 2 documents.
3. If total (Tier 1 + Tier 2) < 167, fill remaining slots with highest-composite
   Tier 3 documents until target is reached.
4. Sort entire selection by `composite` descending.
5. Assign `rank` (1 = highest composite).

Write to `OUTPUT_FOLDER/s09_shortlist.jsonl` and `OUTPUT_FOLDER/s09_shortlist.csv`.

CSV columns:
```
rank, doc_id, filename, original_path, tier, composite,
score_carefirst, score_ai_governance, score_intersection, score_evidentiary,
keyword_score, keyword_matches, rationale, text_preview (first 300 words)
```

---

## Completion

After Stage 9, print a summary:
```
PIPELINE COMPLETE
─────────────────────────────────────
Total files found:        <n>
Extraction failures:      <n>
Duplicates removed:       <n>
Documents scored:         <n>
Scoring errors:           <n>

Tier distribution:
  Tier 1 (cite):          <n>
  Tier 2 (background):    <n>
  Tier 3 (skim):          <n>
  Tier 4 (irrelevant):    <n>

Shortlist size:           <n>
Spot-check sample:        <n>

Output files:
  s09_shortlist.csv       ← primary research output
  s08_spotcheck.csv       ← validate low-priority classification
  s07_ranked.jsonl        ← full scored corpus
─────────────────────────────────────
```
