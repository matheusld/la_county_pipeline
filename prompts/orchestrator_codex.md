# Pipeline Orchestrator — Codex

## Fill These In Before Running

```
INPUT_FOLDER  = {{INPUT_FOLDER}}
OUTPUT_FOLDER = {{OUTPUT_FOLDER}}
```

---

## Your Role

You are the orchestration agent for a document relevance scoring pipeline. Execute
all stages sequentially. Use `gpt-4o-mini` (or the fastest available cost-effective
model) for all bulk document scoring sub-tasks. Use your own model (gpt-4o or
equivalent) only for orchestration decisions and aggregation logic.

Do not ask for confirmation between stages. Write results to disk after every batch.

---

## Stage 1 — Inventory

Walk INPUT_FOLDER recursively. Find all `.pdf`, `.json`, `.txt` files.
For each file, compute SHA-256 using Python `hashlib`. This hash is the `doc_id`.

Write to `OUTPUT_FOLDER/s01_inventory.jsonl`:
```json
{"doc_id": "<sha256>", "filename": "...", "original_path": "...",
 "file_type": "<pdf|json|txt>", "file_size_bytes": <int>}
```

---

## Stage 2 — Text Extraction

**JSON files:** Extract from `text`, `normalized_text`, `content`, or `body` key.
**PDF files:** Use `pdfplumber`: `"\n".join(page.extract_text() or "" for page in pdf.pages)`
**TXT files:** Read directly.

Write to `OUTPUT_FOLDER/s02_extracted.jsonl`:
```json
{"doc_id": "...", "filename": "...", "original_path": "...", "file_type": "...",
 "extraction_status": "success|failed", "text_length": <int>, "raw_text": "..."}
```

---

## Stage 3 — Normalization

For each extracted document:
1. `unicodedata.normalize("NFKC", text)`
2. Collapse whitespace: `" ".join(text.split())`
3. Remove lines matching `^\d+$` or `^Page \d+ of \d+$`
4. Flag `too_short = True` if fewer than 50 words remain

Write to `OUTPUT_FOLDER/s03_normalized.jsonl`.

---

## Stage 4 — Deduplication

**Exact dedup:** Group by `doc_id` (SHA-256). Keep first; mark others
`is_duplicate = true`.

**Near-dedup (5-gram Jaccard > 0.80):**
```python
def shingles(text, k=5):
    words = text.lower().split()
    return set(tuple(words[i:i+k]) for i in range(len(words)-k+1))

def jaccard(a, b):
    return len(a & b) / len(a | b) if (a or b) else 0.0
```
Compare all non-duplicate pairs (process in sorted order to reduce comparisons).
Flag lower-word-count document as duplicate when Jaccard > 0.80.

Write to `OUTPUT_FOLDER/s04_deduped.jsonl`.

---

## Stage 5 — Keyword Scoring

For each non-duplicate document, count case-insensitive matches across these domains:

**ai_governance:** artificial intelligence, machine learning, predictive analytics,
algorithmic, algorithm, automated decision, risk assessment, COMPAS, pretrial risk,
technology directive, TD 24-04, GenAI, generative AI, governance board, CIO, CISO,
chief privacy officer, data governance, facial recognition, surveillance,
automated eligibility, HMIS, coordinated entry

**care_first:** care first, care-first, Measure J, Measure G, CFCI, community
investment, alternatives to incarceration, ATI, youth justice reimagined, DYD,
ready to rise, restorative justice, diversion, community-based, reentry,
justice reform, community governance, participatory, JCOD

**procurement:** procurement, RFP, RFI, request for proposal, ISD, vendor,
contractor, contract, sole source, technology acquisition, Palantir, Axon, Northpointe

**institutional_actors:** Board of Supervisors, DCFS, DPSS, DMH, DPH, probation,
Peter Loo, Lillian Russell, James Thurmond, Mirian Avalos, Lawrence Gann,
technology management council, SJLI

Each match: +0.3 to domain score (capped at 3.0 per domain).
`keyword_score` = sum of domain scores. `keyword_matches` = list of matched domains.

Write to `OUTPUT_FOLDER/s05_keyword_scored.jsonl`.

---

## Stage 6 — Scoring

**Eligible:** `is_duplicate = false` AND `too_short = false` AND `extraction_status = "success"`.

**Resumability:** Load existing `doc_id` values from `OUTPUT_FOLDER/s06_scored.jsonl`
if it exists. Skip those documents.

**Truncation:** If more than 800 words, keep first 400 + last 400:
```python
words = text.split()
if len(words) > 800:
    text = " ".join(words[:400]) + "\n\n[...TRUNCATED...]\n\n" + " ".join(words[-400:])
```

**Batching:** Score 20 documents per call using `gpt-4o-mini` (or equivalent).

For each batch, send this prompt to the scoring model:

---
*[Paste the full content of `prompts/scorer_agent.md` here, replacing `{{DOCUMENTS}}`
with the batch formatted as shown below]*

---

Format each document in the batch as:
```
--- DOCUMENT 1 ---
doc_id: <doc_id>
filename: <filename>

<truncated text>
```

The model returns a JSON array. Parse it. On malformed output, assign `score_error`
and default all scores to 0.

Append each batch immediately to `OUTPUT_FOLDER/s06_scored.jsonl`:
```json
{"doc_id": "...", "filename": "...", "original_path": "...", "keyword_score": <float>,
 "keyword_matches": [...], "score_carefirst": <int>, "score_ai_governance": <int>,
 "score_intersection": <int>, "score_evidentiary": <int>, "rationale": "...",
 "score_error": null, "scored_by": "gpt-4o-mini"}
```

---

## Stage 7 — Composite and Tier Assignment

Compute locally from `s06_scored.jsonl`:

```
composite = (score_carefirst × 0.25) + (score_ai_governance × 0.25)
           + (score_intersection × 0.35) + (score_evidentiary × 0.15)

Tier 1: composite >= 6.0  AND  (score_carefirst >= 5  OR  score_ai_governance >= 5)
Tier 2: composite >= 3.5
Tier 3: composite >= 1.0
Tier 4: composite < 1.0
```

Write to `OUTPUT_FOLDER/s07_ranked.jsonl`.

---

## Stage 8 — Spot-Check Sample

From `s07_ranked.jsonl`, collect all Tier 3 and Tier 4 documents.
Draw `ceil(pool × 0.10)` using `random.Random(42)`.

Write to `OUTPUT_FOLDER/s08_spotcheck.csv` with columns:
```
doc_id, filename, tier, composite, score_carefirst, score_ai_governance,
score_intersection, score_evidentiary, keyword_score, rationale,
text_preview (first 400 words), review_status, reviewer_notes
```

---

## Stage 9 — Final Shortlist

From `s07_ranked.jsonl`:
1. All Tier 1 (always included)
2. All Tier 2
3. Fill to 167 with highest Tier 3 docs if needed
4. Sort by `composite` descending, assign `rank`

Write to `OUTPUT_FOLDER/s09_shortlist.jsonl` and `OUTPUT_FOLDER/s09_shortlist.csv`.

CSV columns:
```
rank, doc_id, filename, original_path, tier, composite,
score_carefirst, score_ai_governance, score_intersection, score_evidentiary,
keyword_score, keyword_matches, rationale, text_preview (first 300 words)
```

---

## Completion Summary

```
PIPELINE COMPLETE
─────────────────────────────────────
Total files found:        <n>
Extraction failures:      <n>
Duplicates removed:       <n>
Documents scored:         <n>

Tier 1 (cite):            <n>
Tier 2 (background):      <n>
Tier 3 (skim):            <n>
Tier 4 (irrelevant):      <n>

Shortlist:                <n> documents → s09_shortlist.csv
Spot-check:               <n> documents → s08_spotcheck.csv
─────────────────────────────────────
```
