"""Codex-side scoring helpers and guardrails.

These helpers keep the GPT/Codex branch aligned with the rubric in
prompts/scorer_agent.md without changing Claude artifacts. The LLM still assigns
the substantive relevance scores, but this module enforces hard rubric caps that
are easy to verify locally.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


HEAD_WORDS = 400
TAIL_WORDS = 400

CARE_STRICT_TERMS = [
    "care first",
    "care-first",
    "measure j",
    "measure g",
    "cfci",
    "alternatives to incarceration",
    "ati",
    "department of youth development",
    "dyd",
    "youth justice reimagined",
    "ready to rise",
    "office of diversion and reentry",
    "odr",
    "jcod",
    "justice care opportunities",
]

CARE_WEAK_TERMS = [
    "diversion",
    "reentry",
    "restorative justice",
    "community-based",
    "probation youth",
    "probation",
    "mental health",
    "behavioral health",
    "public health",
    "health services",
    "public social services",
    "homeless services",
    "supportive services",
    "child welfare",
    "foster youth",
]

AI_STRICT_TERMS = [
    "artificial intelligence",
    "machine learning",
    "predictive analytics",
    "algorithmic",
    "algorithm",
    "automated decision",
    "pretrial risk",
    "technology directive",
    "td 24-04",
    "technology management council",
    "isd procurement",
    "technology acquisition",
    "genai",
    "generative ai",
    "governance board",
    "chief information officer",
    "cio",
    "ciso",
    "chief information security officer",
    "chief privacy officer",
    "data governance",
    "facial recognition",
    "surveillance",
    "automated eligibility",
    "hmis",
    "coordinated entry",
]

AI_WEAK_TERMS = [
    "technology governance",
    "technology",
    "information technology",
    "it system",
    "it systems",
    "information system",
    "information systems",
    "cybersecurity",
    "cyber",
    "security audit",
    "security audits",
    "privacy controls",
    "vendor oversight",
    "privacy officer",
    "software",
    "database",
    "data system",
    "data systems",
    "data sharing",
    "electronic record",
    "electronic records",
    "telehealth",
    "analytics",
    "automated tool",
    "digital service",
    "platform",
    "portal",
    "software system",
    "case management system",
]

NEGATION_RE = re.compile(r"\b(?:no|not|without|lacks?|none|never)\b[^.!?;:]{0,60}$")
TOKEN_BOUNDARY = r"(?<![a-z0-9]){term}(?![a-z0-9])"

TITLE_NAME_RE = re.compile(
    r"\b(?:Supervisor|Director|Chief|Officer|CEO|CIO|CISO|County Counsel|"
    r"Executive Officer|Chief Probation Officer|Chief Information Officer)\s+"
    r"[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,3}\b"
)
DOLLAR_RE = re.compile(r"\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion))?", re.I)
REFERENCE_RE = re.compile(
    r"\b(?:contract|motion|agenda(?:\s+item)?|item|board letter|file|case|"
    r"capital project|project|specs?)\s*(?:no\.|#|number)?\s*[:.]?\s*"
    r"[A-Z0-9][A-Z0-9_.()/-]{1,}\b",
    re.I,
)
FORMAL_POLICY_RE = re.compile(
    r"\b(?:shall|authorize|authorized|approve|approval|adopt|execute|delegate "
    r"authority|instruct|recommend|recommended)\b",
    re.I,
)
DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},\s+\d{4})\b",
    re.I,
)

CODEX_SCORER_ADDENDUM = """
---

## Codex Reliability Addendum

Score only evidence in the document text. Do not infer relevance from filename,
agenda metadata, keyword scores, or the fact that a document is a Board record.

Public comments, transcripts, board letters, contracts, or RFQs about unrelated
subjects must receive 0 for care-first, AI governance, and intersection unless
the text itself substantively discusses the named care-first apparatus and/or a
specific AI/technology governance apparatus.

Use 8-10 scores only when the text makes that dimension a major focus. If a term
appears only in boilerplate, a footer, an unrelated environmental discussion, or
a negated sentence ("no AI governance"), treat it as absent.
"""


def clamp_int(value: Any) -> int:
    try:
        return max(0, min(10, int(value)))
    except Exception:
        return 0


def truncate_words(text: str, head: int = HEAD_WORDS, tail: int = TAIL_WORDS) -> str:
    words = text.split()
    if len(words) <= head + tail:
        return text
    return " ".join(words[:head]) + "\n\n[...TRUNCATED...]\n\n" + " ".join(words[-tail:])


def _term_regex(term: str) -> re.Pattern[str]:
    escaped = re.escape(term.lower()).replace(r"\ ", r"\s+")
    return re.compile(TOKEN_BOUNDARY.format(term=escaped), re.I)


def _term_occurs_unnegated(text_lc: str, term: str) -> bool:
    rx = _term_regex(term)
    for match in rx.finditer(text_lc):
        prefix = text_lc[max(0, match.start() - 80) : match.start()]
        if NEGATION_RE.search(prefix):
            continue
        return True
    return False


def _count_terms(text_lc: str, terms: Iterable[str]) -> int:
    return sum(1 for term in terms if _term_occurs_unnegated(text_lc, term))


def _care_cap(text_lc: str) -> int:
    strict = _count_terms(text_lc, CARE_STRICT_TERMS)
    weak = _count_terms(text_lc, CARE_WEAK_TERMS)
    if strict == 0 and weak == 0:
        return 0
    if strict == 0:
        return 8 if weak >= 2 else 5
    if strict == 1:
        return 8
    return 10


def _ai_cap(text_lc: str) -> int:
    strict = _count_terms(text_lc, AI_STRICT_TERMS)
    weak = _count_terms(text_lc, AI_WEAK_TERMS)
    if strict == 0 and weak == 0:
        return 0
    if strict == 0:
        return 8 if weak >= 2 else 5
    if strict == 1:
        return 8
    return 10


def evidence_score(text: str) -> int:
    """Compute the evidentiary checklist score from explicit text evidence."""
    officials = min(len(set(TITLE_NAME_RE.findall(text))), 3)
    dollars = min(len(set(DOLLAR_RE.findall(text))), 2)
    refs = min(len(set(REFERENCE_RE.findall(text))), 2)
    formal = min(len(set(m.group(0).lower() for m in FORMAL_POLICY_RE.finditer(text))), 2)
    dates = 1 if DATE_RE.search(text) else 0
    return min(10, officials + dollars + refs + formal + dates)


def sanitize_score(score: dict[str, Any], text: str) -> dict[str, Any]:
    """Clamp a model score to locally verifiable rubric constraints."""
    cleaned = dict(score)
    cleaned.pop("codex_guardrails", None)
    text_lc = text.lower()
    adjustments: list[str] = []

    cf = clamp_int(cleaned.get("score_carefirst"))
    ag = clamp_int(cleaned.get("score_ai_governance"))
    ix = clamp_int(cleaned.get("score_intersection"))
    ev = clamp_int(cleaned.get("score_evidentiary"))

    cf_cap = _care_cap(text_lc)
    ag_cap = _ai_cap(text_lc)
    if cf > cf_cap:
        adjustments.append(f"score_carefirst capped at {cf_cap}: no stronger care-first evidence")
        cf = cf_cap
    if ag > ag_cap:
        adjustments.append(
            f"score_ai_governance capped at {ag_cap}: no stronger AI/tech governance evidence"
        )
        ag = ag_cap

    if cf == 0 and ag == 0:
        ix_cap = 0
    elif cf == 0 or ag == 0:
        ix_cap = 2
    else:
        ix_cap = min(10, min(cf, ag) + 2)
    if ix > ix_cap:
        adjustments.append(f"score_intersection capped at {ix_cap}: rubric lower-score constraint")
        ix = ix_cap

    ev_cap = evidence_score(text)
    if ev > ev_cap:
        adjustments.append(f"score_evidentiary capped at {ev_cap}: checklist evidence count")
        ev = ev_cap

    cleaned["score_carefirst"] = cf
    cleaned["score_ai_governance"] = ag
    cleaned["score_intersection"] = ix
    cleaned["score_evidentiary"] = ev
    if adjustments:
        cleaned["codex_guardrails"] = adjustments
    return cleaned


def apply_keyword_floors(score: dict[str, Any], keyword_matches: Iterable[str]) -> dict[str, Any]:
    """Apply low-end rubric floors from corrected keyword evidence.

    The floor is intentionally small: an AI-governance keyword only guarantees an
    incidental 1-2 score, never a substantive governance score.
    """
    cleaned = dict(score)
    matches = set(keyword_matches or [])
    adjustments = list(cleaned.get("codex_guardrails") or [])
    if "ai_governance" in matches and clamp_int(cleaned.get("score_ai_governance")) < 2:
        cleaned["score_ai_governance"] = 2
        adjustments.append("score_ai_governance raised to 2: corrected keyword evidence")
    if adjustments:
        cleaned["codex_guardrails"] = adjustments
    return cleaned


def format_documents_for_prompt(batch: list[dict[str, Any]], text_by_id: dict[str, str]) -> str:
    """Format batch documents without keyword metadata that can bias the scorer."""
    parts = []
    for idx, rec in enumerate(batch, 1):
        doc_id = rec["doc_id"]
        parts.append(
            f"--- DOCUMENT {idx} ---\n"
            f"doc_id: {doc_id}\n"
            f"filename: {rec['filename']}\n\n"
            f"{text_by_id.get(doc_id, '')}\n"
        )
    return "\n".join(parts)


def codex_prompt_template(base_template: str) -> str:
    marker = "## Documents to Score"
    if marker not in base_template:
        return base_template + "\n" + CODEX_SCORER_ADDENDUM
    return base_template.replace(marker, CODEX_SCORER_ADDENDUM.strip() + "\n\n" + marker, 1)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", errors="replace") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
