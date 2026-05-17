"""Stage 5 — Keyword scoring (single combined regex per domain).

For speed, all terms in a domain are joined into one alternation regex with \\b
boundaries on the outside, so each domain costs ONE pass through the text per
document instead of N. Terms are sorted longest-first so multi-word phrases
match before their single-word substrings.

Iterates s04_deduped.jsonl and s03_normalized.jsonl in lockstep (same row order).
"""
import json
import os
import re
import sys

OUTPUT_FOLDER = r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\claude"
DEDUP = os.path.join(OUTPUT_FOLDER, "s04_deduped.jsonl")
NORM = os.path.join(OUTPUT_FOLDER, "s03_normalized.jsonl")
OUT = os.path.join(OUTPUT_FOLDER, "s05_keyword_scored.jsonl")

DOMAINS = {
    "ai_governance": [
        "artificial intelligence", "machine learning", "predictive analytics",
        "algorithmic", "algorithm", "automated decision", "decision support",
        "risk assessment", "COMPAS", "pretrial risk", "technology directive",
        "TD 24-04", "GenAI", "generative AI", "governance board",
        "chief information officer", "CIO", "CISO", "chief privacy officer",
        "data governance", "facial recognition", "surveillance",
        "automated eligibility", "benefits automation", "triage tool",
        "matching algorithm", "HMIS", "coordinated entry", "decision lens",
    ],
    "care_first": [
        "care first", "care-first", "Measure J", "Measure G", "CFCI",
        "community investment", "alternatives to incarceration", "ATI",
        "youth justice reimagined", "department of youth development", "DYD",
        "ready to rise", "restorative justice", "diversion", "community-based",
        "reentry", "justice reform", "advisory committee", "community governance",
        "participatory", "JCOD", "justice care opportunities",
    ],
    "procurement": [
        "procurement", "RFP", "RFI", "request for proposal", "request for information",
        "master agreement", "ISD", "vendor", "contractor", "contract", "sole source",
        "piggyback", "technology acquisition", "Northpointe", "Palantir", "Axon",
        "LiveView", "Collective Medical",
    ],
    "institutional_actors": [
        "Board of Supervisors", "DCFS", "DPSS", "DMH", "DPH", "probation",
        "Peter Loo", "Lillian Russell", "James Thurmond", "Mirian Avalos",
        "Lawrence Gann", "Derek Steele", "SJLI", "Social Justice Learning Institute",
        "LAANE", "LeadersUp", "technology management council",
    ],
}


def build_combined(terms):
    # Sort longest-first so multi-word phrases win, lowercase, escape, alternate.
    parts = sorted({t.lower() for t in terms}, key=lambda s: -len(s))
    pattern = r"\b(?:" + "|".join(re.escape(t) for t in parts) + r")\b"
    return re.compile(pattern), parts


DOMAIN_REGEX = {d: build_combined(terms) for d, terms in DOMAINS.items()}


def keyword_score_text(text: str):
    if not text:
        return 0.0, []
    text_lc = text.lower()
    matched_domains = []
    total = 0.0
    for domain, (rx, parts) in DOMAIN_REGEX.items():
        # Single pass: find every distinct match, count distinct surface forms.
        found = set(rx.findall(text_lc))
        domain_score = min(len(found) * 0.3, 3.0)
        if domain_score > 0:
            matched_domains.append(domain)
        total += domain_score
    return total, matched_domains


def main():
    n = 0
    n_scored = 0
    with open(NORM, "r", encoding="utf-8") as fnorm, \
         open(DEDUP, "r", encoding="utf-8") as fdedup, \
         open(OUT, "w", encoding="utf-8") as fout:
        for nline, dline in zip(fnorm, fdedup):
            nrec = json.loads(nline)
            drec = json.loads(dline)
            if nrec["doc_id"] != drec["doc_id"]:
                raise RuntimeError(
                    f"Order mismatch at row {n}: norm={nrec['doc_id']} dedup={drec['doc_id']}"
                )
            n += 1
            if drec.get("is_duplicate") or drec.get("too_short") or drec.get("extraction_status") != "success":
                kw_score = 0.0
                kw_matches = []
            else:
                kw_score, kw_matches = keyword_score_text(nrec.get("normalized_text") or "")
                n_scored += 1
            drec["keyword_score"] = round(kw_score, 4)
            drec["keyword_matches"] = kw_matches
            fout.write(json.dumps(drec, ensure_ascii=False) + "\n")
            if n % 1000 == 0:
                print(f"  processed {n}", flush=True)
    print(f"Total rows: {n}, keyword-scored: {n_scored}")
    print(f"Wrote: {OUT}")


if __name__ == "__main__":
    main()
