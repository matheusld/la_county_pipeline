import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from hashlib import md5
from html import unescape

from pypdf import PdfReader
from bs4 import BeautifulSoup
import docx

SUPPORTED_EXTS = {".json", ".pdf", ".txt", ".md", ".csv", ".html", ".htm", ".docx"}

KEYWORD_FALLBACK = [
    "measure j", "care first community investment", "cfci", "cfci advisory committee",
    "care first community investment advisory committee", "alternatives to incarceration",
    "ati initiative", "ati", "genai governance board", "technology directive",
    "td 24-04", "chief information officer", "chief privacy officer",
    "it investment board", "technology management council",
    "whole person care", "behavioral health", "mental health", "housing", "homeless",
    "youth development", "family support", "maternal health", "benefits", "reentry",
    "digital equity", "community investment", "prevention", "community-based",
    "artificial intelligence", "generative ai", "machine learning", "algorithmic",
    "predictive analytics", "risk assessment", "coordinated entry", "hmis", "calsaws",
    "cws/cms", "dashboard", "case management system", "eligibility system",
    "data sharing", "data use agreement", "privacy impact", "procurement", "contract",
    "salesforce", "servicenow", "palantir", "compas", "axon", "esri", "cerner",
    "epic", "unite us", "findhelp", "maximus", "qualtrics"
]

PROMPT_SYSTEM = (
    "You are analyzing Los Angeles County documents for academic research. "
    "The research question is: How do LA County's existing care-first community governance structures "
    "(Measure J, CFCI Advisory Committee, ATI Initiative) connect to the county's AI and technology governance apparatus "
    "(GenAI Governance Board, Technology Directive TD 24-04, CIO-led governance, procurement, privacy, and data governance)? "
    "Return factual JSON only. Use only the provided text. Do not guess. Be conservative."
)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "relevance": {"type": "integer", "minimum": 0, "maximum": 3},
        "confidence": {"type": "integer", "minimum": 1, "maximum": 3},
        "doc_type": {"type": "string"},
        "care_first_structures": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "ai_governance_structures": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "care_domains": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "tech_systems_or_vendors": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "main_actors": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "money": {"type": ["string", "null"]},
        "decision_or_event": {"type": ["string", "null"]},
        "connection_type": {"type": "string"},
        "connection_strength": {"type": "integer", "minimum": 0, "maximum": 3},
        "why_it_matters": {"type": "string"},
        "evidence_quotes": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
        "evidence_labels": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
        "needs_second_pass": {"type": "boolean"}
    },
    "required": [
        "relevance", "confidence", "doc_type", "care_first_structures", "ai_governance_structures",
        "care_domains", "tech_systems_or_vendors", "main_actors", "money", "decision_or_event",
        "connection_type", "connection_strength", "why_it_matters", "evidence_quotes", "evidence_labels",
        "needs_second_pass"
    ]
}


def log(msg: str) -> None:
    print(msg, flush=True)


def normalize(text: str) -> str:
    text = (text or "").replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", text).strip()


def parse_semicolon_list(value: str) -> List[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(";") if x.strip()]


def guess_doc_type(name: str) -> str:
    n = name.lower()
    for needle, label in [
        ("board_letter", "board_letter"), ("board letter", "board_letter"), ("motion", "motion"),
        ("mou", "mou"), ("memorandum", "memorandum"), ("agreement", "agreement"),
        ("contract", "contract"), ("ordinance", "ordinance"), ("report", "report"),
        ("agenda", "agenda"), ("correspondence", "correspondence"), ("attachment", "attachment"),
        ("public_comment", "public_comment"), ("public comment", "public_comment"),
    ]:
        if needle in n:
            return label
    return "unknown"


def guess_meeting_date(name: str, text: str = "") -> str:
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", name)
    if m:
        return m.group(1)
    m = re.search(r"\b(20\d{2})[-_ ](\d{2})[-_ ](\d{2})\b", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}\b", text, re.I)
    return m.group(0) if m else ""


def extract_text_from_pdf(path: Path) -> Tuple[str, str]:
    try:
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
        return "\n\n".join(pages), "pypdf"
    except Exception:
        return "", "pypdf_failed"


def extract_text_from_docx(path: Path) -> Tuple[str, str]:
    try:
        d = docx.Document(str(path))
        return "\n".join(p.text for p in d.paragraphs if p.text), "docx"
    except Exception:
        return "", "docx_failed"


def extract_text_from_html(path: Path) -> Tuple[str, str]:
    try:
        html = path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        return unescape(soup.get_text(" ", strip=True)), "html"
    except Exception:
        return "", "html_failed"


def extract_text_from_textlike(path: Path) -> Tuple[str, str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore"), path.suffix.lower().lstrip(".") or "text"
    except Exception:
        return "", f"{path.suffix.lower()}_failed"


def normalize_mixed_file_to_json(path: Path, cache_dir: Path) -> Optional[Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = md5(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    out_path = cache_dir / f"{path.stem}_{key}.json"
    if out_path.exists():
        return out_path

    ext = path.suffix.lower()
    text = ""
    extraction_method = ""

    if ext == ".json":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "text" in raw:
                raw.setdefault("filename", path.name)
                raw.setdefault("doc_type", guess_doc_type(path.name))
                if not raw.get("meeting_date"):
                    raw["meeting_date"] = guess_meeting_date(path.name, str(raw.get("text", ""))[:5000])
                raw.setdefault("char_count", len(str(raw.get("text", ""))))
                raw.setdefault("source_format", "json")
                raw.setdefault("original_path", str(path))
                out_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
                return out_path
            text = json.dumps(raw, ensure_ascii=False)
            extraction_method = "json_stringified"
        except Exception:
            return None
    elif ext == ".pdf":
        text, extraction_method = extract_text_from_pdf(path)
    elif ext == ".docx":
        text, extraction_method = extract_text_from_docx(path)
    elif ext in {".html", ".htm"}:
        text, extraction_method = extract_text_from_html(path)
    elif ext in {".txt", ".md", ".csv"}:
        text, extraction_method = extract_text_from_textlike(path)
    else:
        return None

    text = normalize(text)
    doc = {
        "filename": path.name,
        "meeting_date": guess_meeting_date(path.name, text[:5000]),
        "doc_type": guess_doc_type(path.name),
        "text": text,
        "char_count": len(text),
        "source_format": ext.lstrip("."),
        "extraction_method": extraction_method,
        "original_path": str(path),
    }
    out_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return out_path


def find_windows(text: str, terms: List[str], radius: int = 500) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    text_lc = text.lower()
    seen = set()
    for term in terms:
        term_lc = term.lower().strip()
        if not term_lc or term_lc in seen:
            continue
        seen.add(term_lc)
        idx = text_lc.find(term_lc)
        if idx == -1:
            continue
        start = max(0, idx - radius)
        end = min(len(text), idx + len(term) + radius)
        out.append((f"TERM:{term[:60]}", text[start:end]))
        if len(out) >= 18:
            break
    return out


def dedupe_chunks(chunks: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    seen = set()
    out = []
    for label, chunk in chunks:
        clean = normalize(chunk)
        key = clean[:240]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append((label, clean))
    return out


def compress_document(doc: Dict, row: Dict, max_chars: int) -> str:
    text = normalize(doc.get("text", ""))
    if not text:
        return ""

    if max_chars <= 0:
        compact = text
    else:
        candidate_terms = []
        for col in ["top_hits", "vendors_found", "money_hits", "negative_hits"]:
            candidate_terms.extend(parse_semicolon_list(row.get(col, "")))
        candidate_terms.extend(KEYWORD_FALLBACK)

        chunks: List[Tuple[str, str]] = [("HEAD", text[:7000])]
        if len(text) > 12000:
            mid_start = max(0, len(text) // 2 - 1800)
            chunks.append(("MIDDLE", text[mid_start: mid_start + 3600]))
        if len(text) > 9000:
            chunks.append(("TAIL", text[-2600:]))
        chunks.extend(find_windows(text, candidate_terms, radius=540))
        chunks = dedupe_chunks(chunks)
        compact = "\n\n---\n\n".join(f"[{idx}:{label}] {chunk}" for idx, (label, chunk) in enumerate(chunks, start=1))
        if len(compact) > max_chars:
            compact = compact[:max_chars]

    prefix = (
        f"FILENAME: {doc.get('filename','')}\n"
        f"MEETING_DATE: {doc.get('meeting_date','')}\n"
        f"DOC_TYPE: {doc.get('doc_type','')}\n"
        f"SOURCE_BUCKET: {row.get('source_bucket','')}\n"
        f"SOURCE_FORMAT: {doc.get('source_format','')}\n"
        f"EXTRACTION_METHOD: {doc.get('extraction_method','existing_json')}\n"
        f"PREVIOUS_SIGNALS: api_score={row.get('api_score','')} | care_score={row.get('care_score','')} | tech_score={row.get('tech_score','')} | top_hits={row.get('top_hits','')} | money_hits={row.get('money_hits','')}\n\n"
        f"DOCUMENT_EXCERPTS:\n"
    )
    return prefix + compact


def build_user_prompt(compact_doc: str) -> str:
    return (
        "Analyze this Los Angeles County document for the research question: "
        "How do care-first community governance structures connect to AI and technology governance?\n\n"
        "Pay special attention to:\n"
        "- Measure J, CFCI, CFCI Advisory Committee, ATI Initiative, participatory budgeting, community governance, lived experience, community-based organizations\n"
        "- GenAI Governance Board, TD 24-04, CIO-led governance, IT Investment Board, procurement, privacy, data governance, vendor approvals\n"
        "- Any actual bridge between the two worlds: shared actors, procurement in care-first domains, governance gaps, oversight gaps, implementation in care-first services, or absence of connection.\n\n"
        "Return valid JSON matching the schema.\n"
        "Rules:\n"
        "- Use only the provided text.\n"
        "- relevance: 0 not relevant, 1 weak/indirect, 2 relevant, 3 highly relevant.\n"
        "- connection_strength: 0 none, 1 weak mention, 2 meaningful connection, 3 direct institutional link.\n"
        "- connection_type should be one short phrase such as 'direct institutional link', 'shared domain but no formal link', 'procurement in care-first service area', 'AI governance only', 'care-first only', 'implementation detail', or 'unclear'.\n"
        "- evidence_quotes: up to 2 short exact quotes, each under 25 words.\n"
        "- evidence_labels: matching excerpt labels.\n"
        "- why_it_matters: one sentence, max 45 words.\n"
        "- needs_second_pass should be true only if this document is useful for a serious timeline, governance map, or thesis argument.\n\n"
        f"{compact_doc}"
    )


def load_csv_rows(path: Path) -> List[Dict]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def rows_from_shortlist(path: Path) -> List[Dict]:
    rows = load_csv_rows(path)
    out = []
    for row in rows:
        row = dict(row)
        row["source_bucket"] = row.get("source_bucket") or "api_shortlist"
        out.append(row)
    return out


def rows_from_extra_dirs(extra_dirs: List[Path], cache_dir: Path, extra_limit: int) -> List[Dict]:
    out: List[Dict] = []
    seen = set()
    for extra_dir in extra_dirs:
        if not extra_dir.exists():
            log(f"[warn] Extra dir not found: {extra_dir}")
            continue
        files = [p for p in sorted(extra_dir.rglob("*")) if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]
        log(f"[scan] {extra_dir} -> {len(files):,} supported files discovered")
        converted = 0
        for idx, path in enumerate(files, start=1):
            if extra_limit and len(out) >= extra_limit:
                log(f"[limit] Reached extra-limit={extra_limit}")
                return out
            norm_path = normalize_mixed_file_to_json(path, cache_dir / extra_dir.name)
            if not norm_path:
                continue
            key = str(norm_path.resolve())
            if key in seen:
                continue
            seen.add(key)
            try:
                doc = json.loads(norm_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            out.append({
                "filename": doc.get("filename", path.name),
                "meeting_date": doc.get("meeting_date", ""),
                "path": str(norm_path),
                "api_score": "",
                "care_score": "",
                "tech_score": "",
                "top_hits": "",
                "money_hits": "",
                "vendors_found": "",
                "negative_hits": "",
                "source_bucket": extra_dir.name,
            })
            converted += 1
            if idx % 50 == 0:
                log(f"[extra] {extra_dir.name}: inspected {idx:,}/{len(files):,}, added {converted:,}")
        log(f"[done] {extra_dir.name}: added {converted:,} normalized files")
    return out


def resolve_doc_path(row: Dict, docs_dir: Path, cache_dir: Path) -> Optional[Path]:
    raw_path = row.get("path", "").strip()
    candidates = []
    if raw_path:
        candidates.append(Path(raw_path))
    filename = row.get("filename", "")
    if filename:
        candidates.append(docs_dir / filename)
        candidates.append(docs_dir / Path(filename).name)
    for c in candidates:
        if c.exists():
            if c.suffix.lower() == ".json":
                return c
            if c.suffix.lower() in SUPPORTED_EXTS:
                return normalize_mixed_file_to_json(c, cache_dir / "shortlist_converted")
    return None


def dedupe_rows(rows: List[Dict], docs_dir: Path) -> List[Dict]:
    out = []
    seen = set()
    for row in rows:
        raw_path = row.get("path", "").strip()
        doc_path = Path(raw_path) if raw_path else docs_dir / row.get("filename", "")
        key = str(doc_path.resolve()) if doc_path.exists() else row.get("filename", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def estimate_tokens_from_chars(chars: int, chars_per_token: float = 4.0) -> int:
    return int(chars / chars_per_token)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shortlist-csv", required=True)
    ap.add_argument("--docs-dir", default="./extracted_text_supporting")
    ap.add_argument("--extra-doc-dirs", nargs="*", default=[])
    ap.add_argument("--extra-limit", type=int, default=0, help="0 means no cap")
    ap.add_argument("--normalized-cache-dir", default="./normalized_json_cache")
    ap.add_argument("--output-jsonl", default="./openai_batch_input.jsonl")
    ap.add_argument("--output-manifest", default="./openai_batch_manifest.csv")
    ap.add_argument("--model", default="gpt-5.4-nano")
    ap.add_argument("--max-docs", type=int, default=0)
    ap.add_argument("--max-doc-chars", type=int, default=0, help="0 means full text")
    ap.add_argument("--max-output-tokens", type=int, default=220)
    args = ap.parse_args()

    shortlist_csv = Path(args.shortlist_csv)
    docs_dir = Path(args.docs_dir)
    extra_dirs = [Path(p) for p in args.extra_doc_dirs]
    cache_dir = Path(args.normalized_cache_dir)
    output_jsonl = Path(args.output_jsonl)
    output_manifest = Path(args.output_manifest)

    log("[start] Loading shortlist rows")
    rows = rows_from_shortlist(shortlist_csv)
    log(f"[info] shortlist rows loaded: {len(rows):,}")

    if extra_dirs:
        log("[start] Collecting extra docs")
        rows.extend(rows_from_extra_dirs(extra_dirs, cache_dir, args.extra_limit))

    pre_dedupe = len(rows)
    rows = dedupe_rows(rows, docs_dir)
    log(f"[info] rows after dedupe: {len(rows):,} (removed {pre_dedupe - len(rows):,})")
    if args.max_docs and args.max_docs > 0:
        rows = rows[:args.max_docs]
        log(f"[info] max-docs applied: {len(rows):,}")

    manifest_rows = []
    written = 0
    skipped = 0
    total_payload_chars = 0
    t0 = time.time()

    with open(output_jsonl, "w", encoding="utf-8") as out:
        for i, row in enumerate(rows, start=1):
            doc_path = resolve_doc_path(row, docs_dir, cache_dir)
            if not doc_path or not doc_path.exists():
                skipped += 1
                continue
            try:
                doc = json.loads(doc_path.read_text(encoding="utf-8"))
            except Exception:
                skipped += 1
                continue
            compact_doc = compress_document(doc, row, max_chars=args.max_doc_chars)
            if not compact_doc:
                skipped += 1
                continue

            custom_id = f"doc-{i:05d}"
            request = {
                "custom_id": custom_id,
                "method": "POST",
                "url": "/v1/responses",
                "body": {
                    "model": args.model,
                    "input": [
                        {"role": "system", "content": [{"type": "input_text", "text": PROMPT_SYSTEM}]},
                        {"role": "user", "content": [{"type": "input_text", "text": build_user_prompt(compact_doc)}]}
                    ],
                    "max_output_tokens": args.max_output_tokens,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "la_county_governance_triage",
                            "schema": SCHEMA
                        }
                    }
                }
            }
            out.write(json.dumps(request, ensure_ascii=False) + "\n")
            total_payload_chars += len(compact_doc)
            manifest_rows.append({
                "custom_id": custom_id,
                "filename": doc.get("filename", row.get("filename", "")),
                "meeting_date": doc.get("meeting_date", row.get("meeting_date", "")),
                "path": str(doc_path),
                "original_path": doc.get("original_path", str(doc_path)),
                "source_bucket": row.get("source_bucket", ""),
                "source_format": doc.get("source_format", "json"),
                "extraction_method": doc.get("extraction_method", "existing_json"),
                "char_count": doc.get("char_count", ""),
                "api_score": row.get("api_score", ""),
                "care_score": row.get("care_score", ""),
                "tech_score": row.get("tech_score", ""),
                "top_hits": row.get("top_hits", ""),
                "money_hits": row.get("money_hits", ""),
                "vendors_found": row.get("vendors_found", "")
            })
            written += 1
            if i % 50 == 0 or i == len(rows):
                elapsed = max(time.time() - t0, 0.001)
                rate = written / elapsed
                log(f"[build] processed {i:,}/{len(rows):,} rows | wrote {written:,} | skipped {skipped:,} | {rate:.1f} docs/sec")

    with open(output_manifest, "w", newline="", encoding="utf-8-sig") as f:
        fieldnames = list(manifest_rows[0].keys()) if manifest_rows else ["custom_id"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        if manifest_rows:
            writer.writerows(manifest_rows)

    estimated_input_tokens = estimate_tokens_from_chars(total_payload_chars)
    log(f"[done] Wrote {written:,} batch requests to {output_jsonl}")
    log(f"[done] Wrote manifest to {output_manifest}")
    log(f"[done] Skipped {skipped:,} rows/files with no usable text")
    log(f"[done] Approx payload chars: {total_payload_chars:,} | approx input tokens: {estimated_input_tokens:,}")
    log(f"[done] Normalized cache: {cache_dir.resolve()}")
    log("[next] Upload JSONL with purpose=batch, then create a batch for /v1/responses.")


if __name__ == "__main__":
    main()
