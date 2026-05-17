import json
import re
import csv
from pathlib import Path

# =========================
# CONFIG
# =========================
INPUT_DIR = Path("./extracted_text_supporting")
OUTPUT_DIR = Path("./rank_outputs_v4")
OUTPUT_DIR.mkdir(exist_ok=True)

# This is a threshold, not a forced slice target.
API_MIN_SCORE = 26

# Optional hard cap only after thresholding
MAX_API_FILES = 1200

# =========================
# TERM SETS
# =========================

# Strong / specific tech terms only
TECH_TERMS = [
    "artificial intelligence", "generative ai", "machine learning",
    "algorithmic", "predictive analytics", "predictive risk",
    "risk assessment algorithm", "eligibility algorithm", "matching algorithm",
    "natural language processing", "facial recognition", "biometric",
    "automated decision", "decision support system",
    "surveillance technology", "surveillance system", "surveillance software",
    "electronic monitoring", "gps monitoring", "cctv camera",
    "body worn camera", "body-worn camera", "digital evidence management",
    "liveview",
    "case management system", "coordinated entry system", "hmis system",
    "integrated data system", "electronic health record system",
    "electronic health record", "ehr system", "emr system",
    "data sharing agreement", "data use agreement", "data governance",
    "privacy impact assessment", "interoperability", "real-time data",
    "calsaws", "cws/cms",
    "microsoft azure", "amazon web services", "google cloud platform",
    "oracle cloud", "servicenow", "salesforce platform",
    "m365", "microsoft 365", "saas platform", "cloud-based system",
    "software as a service",
    "technology directive", "td 24-04", "genai governance board",
    "it investment board", "chief information officer",
    "chief privacy officer", "information systems advisory",
    "procurement policy", "technology policy", "ai policy",
    "responsible ai", "ethical ai",
    "risk score", "triage tool", "screening tool", "early warning system",
    "resource matching", "benefits eligibility system",
    "grant management system", "telehealth", "telepsychiatry"
]

# Weak / generic tech terms kept separate
TECH_WEAK = [
    "dashboard", "software", "platform", "system", "api", "cloud", "vendor"
]

VENDORS = [
    "compas", "axon enterprise", "decision lens", "clarity human services",
    "collective medical", "northpointe", "palantir", "dataworks plus",
    "healthvana", "ibm watson", "salesforce", "servicenow",
    "microsoft azure", "google cloud", "oracle cloud", "amazon web services",
    "splunk", "tyler technologies", "accenture", "deloitte",
    "maximus", "qualtrics", "accela", "netsmart", "cerner",
    "strata decision", "epic systems", "esri", "imprivata",
    "zscaler", "cyberark", "unite us", "findhelp",
    "aunt bertha", "servicepoint"
]

# Strong / specific care-first terms only
CARE_FIRST_TERMS = [
    "mental health outreach", "behavioral health technology",
    "mobile crisis unit", "crisis stabilization unit",
    "psychiatric mobile response", "peer support specialist",
    "mental health navigator", "telehealth", "telepsychiatry",
    "988 crisis", "warm line",
    "youth development program", "gang reduction", "gryd",
    "violence prevention program", "restorative justice program",
    "transition age youth", "foster youth", "after school program",
    "homelessness prevention", "eviction prevention",
    "rental assistance program", "housing navigation",
    "housing stability", "rapid rehousing", "coordinated entry",
    "housing for health", "hmis", "housing information management",
    "workforce development program", "job training program",
    "career navigation", "america's job centers", "ajcc",
    "wioa", "reentry employment", "formerly incarcerated",
    "harm reduction program", "naloxone distribution",
    "overdose prevention", "community health worker",
    "doula program", "maternal health program",
    "african american infant", "aaimm",
    "calfresh enrollment", "benefits eligibility technology",
    "ebt system", "wic program",
    "measure j", "care first community investment", "cfci",
    "participatory budgeting", "community governance",
    "cbo capacity", "pay for success",
    "digital divide", "broadband access program",
    "digital literacy program", "distance learning program",
    "early childhood education program",
    "whole person care"
]

# Weak / generic care terms kept separate
CARE_WEAK = [
    "public health", "mental health", "behavioral health",
    "housing", "homeless", "reentry", "youth", "prevention",
    "family support", "community-based", "supportive services"
]

ACTION_TERMS = [
    "approve and authorize", "approve and instruct",
    "it is recommended that the board",
    "sole source contract", "sole source agreement",
    "not to exceed", "maximum contract amount",
    "annual maximum obligation", "authorize the director to execute",
    "authorize the chair to sign", "execute an amendment",
    "increase the contract maximum", "extend the term",
    "fiscal impact", "appropriation adjustment", "4-votes",
    "memorandum of understanding", "statement of work", "scope of work",
    "procurement", "contract award"
]

DOC_TYPE_HINTS = {
    "board_letter": 10,
    "board letter": 10,
    "motion": 8,
    "sole_source": 10,
    "sole source": 10,
    "amendment": 6,
    "directive": 10,
    "ordinance": 8,
    "mou": 6,
    "memorandum_of_understanding": 6,
    "report": 4,
    "budget": 4,
    "attachment": 1,
    "public_comment": -30,
    "publiccomment": -30,
    "correspondence": -20,
    "public comment": -30,
}

HIGH_VALUE_ACTORS = [
    "chief executive office",
    "department of public health",
    "department of health services",
    "department of mental health",
    "department of children and family services",
    "department of youth development",
    "internal services department",
    "information systems advisory",
    "it investment board",
    "justice care and opportunities department",
    "office of inspector general",
    "chief information officer",
    "chief privacy officer",
    "first 5 la", "probation", "los angeles homelessness services authority",
    "public social services", "dcfs", "dph", "dhs", "dmh", "dyd",
    "measure j", "care first community investment"
]

NEGATIVE_TERMS = [
    "museum", "performing arts", "arts commission", "beach", "marina",
    "harbor", "flood control", "road construction", "sidewalk", "sewer",
    "watershed", "park improvements", "landfill", "golf course",
    "assessor parcel", "property tax", "fire suppression system",
    "janitorial", "custodial", "landscaping", "elevator maintenance",
    "as-needed maintenance", "tree trimming", "roof replacement",
    "library services", "animal care", "veterinary", "airport", "runway",
    "public works construction", "lease-leaseback", "concession agreement"
]

MONEY_RE = re.compile(
    r"\$[\d,]+(?:\.\d+)?(?:\s*million|\s*billion)?|"
    r"\b\d[\d,]*(?:\.\d+)?\s*(?:million|billion)\b",
    re.IGNORECASE
)

# =========================
# HELPERS
# =========================
def normalize(text: str) -> str:
    text = (text or "").replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", text).strip()

def unique_hits(text_lc: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term in text_lc]

def doc_type_score(filename: str, text_lc: str):
    fname_lc = filename.lower()
    head = text_lc[:2500]
    bonus = 0
    hits = []
    for hint, score in DOC_TYPE_HINTS.items():
        if hint in fname_lc or (score > 0 and hint in head):
            bonus += score
            hits.append(hint)
    return bonus, hits

def money_score(text: str):
    matches = MONEY_RE.findall(text)
    if not matches:
        return 0, []
    # reward presence, not density
    return min(10, 4 + len(matches)), matches[:8]

def proximity_score(text_lc: str, group_a: list[str], group_b: list[str], window: int = 1000) -> int:
    positions_a = []
    positions_b = []

    for term in group_a:
        start = 0
        while True:
            idx = text_lc.find(term, start)
            if idx == -1:
                break
            positions_a.append(idx)
            start = idx + len(term)

    for term in group_b:
        start = 0
        while True:
            idx = text_lc.find(term, start)
            if idx == -1:
                break
            positions_b.append(idx)
            start = idx + len(term)

    if not positions_a or not positions_b:
        return 0

    positions_b.sort()
    hits = 0
    j = 0
    for a in sorted(positions_a):
        while j < len(positions_b) and positions_b[j] < a - window:
            j += 1
        k = j
        while k < len(positions_b) and positions_b[k] <= a + window:
            hits += 1
            break

    return min(8, hits * 2)

def extract_snippet(text: str, terms: list[str], window: int = 250) -> str:
    text = normalize(text)
    lc = text.lower()
    for term in terms:
        idx = lc.find(term.lower())
        if idx != -1:
            s = max(0, idx - window)
            e = min(len(text), idx + len(term) + window)
            return text[s:e]
    return text[:500]

# =========================
# SCORE
# =========================
def score_doc(d: dict, path: Path) -> dict:
    text = normalize(d.get("text", ""))
    text_lc = text.lower()
    filename = d.get("filename", path.name)
    chars = int(d.get("char_count", len(text)))
    date = d.get("meeting_date", "")
    doc_type = str(d.get("doc_type", "") or "")

    tech_hits = unique_hits(text_lc, TECH_TERMS)
    tech_weak_hits = unique_hits(text_lc, TECH_WEAK)
    vendor_hits = unique_hits(text_lc, VENDORS)
    care_hits = unique_hits(text_lc, CARE_FIRST_TERMS)
    care_weak_hits = unique_hits(text_lc, CARE_WEAK)
    action_hits = unique_hits(text_lc, ACTION_TERMS)
    actor_hits = unique_hits(text_lc, HIGH_VALUE_ACTORS)
    neg_hits = unique_hits(text_lc, NEGATIVE_TERMS)

    tech_n = len(tech_hits)
    tech_weak_n = len(tech_weak_hits)
    vendor_n = len(vendor_hits)
    care_n = len(care_hits)
    care_weak_n = len(care_weak_hits)
    action_n = len(action_hits)
    actor_n = len(actor_hits)
    neg_n = len(neg_hits)

    doc_bonus, doc_hits = doc_type_score(filename, text_lc)
    money_pts, mon_hits = money_score(text)

    # lower caps, unique hits only
    tech_score = min(18, tech_n * 3 + vendor_n * 4 + min(4, tech_weak_n))
    care_score = min(18, care_n * 3 + min(4, care_weak_n))
    action_score = min(12, action_n * 2)
    actor_score = min(10, actor_n * 2)

    impl_score = 0
    for term in [
        "scope of work", "statement of work", "deliverables",
        "implementation plan", "evaluation criteria",
        "performance metrics", "timeline", "milestones"
    ]:
        if term in text_lc:
            impl_score += 2
    impl_score = min(8, impl_score)

    care_tech_prox = proximity_score(text_lc, CARE_FIRST_TERMS + CARE_WEAK, TECH_TERMS + VENDORS)
    care_action_prox = proximity_score(text_lc, CARE_FIRST_TERMS + CARE_WEAK, ACTION_TERMS)
    tech_actor_prox = proximity_score(text_lc, TECH_TERMS + VENDORS, HIGH_VALUE_ACTORS)

    # tighter gate
    gate_score = 0
    if care_n >= 1 and (tech_n >= 1 or vendor_n >= 1):
        gate_score += 18
    if (tech_n >= 1 or vendor_n >= 1) and (action_n >= 1 or actor_n >= 1):
        gate_score += 12
    if care_tech_prox >= 4:
        gate_score += 8

    negative_penalty = min(24, neg_n * 6)

    filename_lc = filename.lower()
    if "public comment" in filename_lc or "public_comment" in filename_lc:
        negative_penalty += 40

    size_score = 0
    if chars < 2500:
        size_score = -6
    elif chars > 300000:
        size_score = 1

    topic_relevance = tech_score + care_score + care_tech_prox + care_action_prox
    document_importance = action_score + money_pts + actor_score + doc_bonus + impl_score + tech_actor_prox
    overall_score = topic_relevance + document_importance + gate_score + size_score - negative_penalty

    # dedicated shortlist score
    api_score = (
        gate_score
        + care_tech_prox
        + care_action_prox
        + tech_actor_prox
        + min(14, tech_score)
        + min(14, care_score)
        + min(8, money_pts)
        + min(6, impl_score)
        - negative_penalty
    )

    # hard rules for weak false positives
    strong_project_overlap = (
        (care_n >= 1 and (tech_n >= 1 or vendor_n >= 1))
        or ((tech_n >= 1 or vendor_n >= 1) and (action_n >= 1 or actor_n >= 1))
    )

    top_hits = []
    for grp in [vendor_hits, tech_hits, care_hits, action_hits, actor_hits]:
        for item in grp[:4]:
            if item not in top_hits:
                top_hits.append(item)

    snippet = extract_snippet(
        text,
        vendor_hits + care_hits + tech_hits + action_hits + actor_hits
    )

    return {
        "filename": filename,
        "meeting_date": date,
        "doc_type": doc_type,
        "char_count": chars,
        "tech_score": tech_score,
        "care_score": care_score,
        "action_score": action_score,
        "money_score": money_pts,
        "actor_score": actor_score,
        "impl_score": impl_score,
        "doc_bonus": doc_bonus,
        "care_tech_prox": care_tech_prox,
        "care_action_prox": care_action_prox,
        "tech_actor_prox": tech_actor_prox,
        "gate_score": gate_score,
        "negative_penalty": negative_penalty,
        "topic_relevance": topic_relevance,
        "document_importance": document_importance,
        "overall_score": overall_score,
        "api_score": api_score,
        "strong_project_overlap": int(strong_project_overlap),
        "vendors_found": "; ".join(vendor_hits[:8]),
        "negative_hits": "; ".join(neg_hits[:8]),
        "top_hits": "; ".join(top_hits[:12]),
        "money_hits": "; ".join(mon_hits[:6]),
        "snippet": snippet,
        "path": str(path),
    }

# =========================
# RUN
# =========================
FIELDNAMES = [
    "filename", "meeting_date", "doc_type", "char_count",
    "tech_score", "care_score", "action_score", "money_score",
    "actor_score", "impl_score", "doc_bonus",
    "care_tech_prox", "care_action_prox", "tech_actor_prox",
    "gate_score", "negative_penalty",
    "topic_relevance", "document_importance",
    "overall_score", "api_score", "strong_project_overlap",
    "vendors_found", "negative_hits", "top_hits", "money_hits",
    "snippet", "path"
]

def write_csv(fpath: Path, data: list[dict]):
    with open(fpath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(data)

print("Scoring documents...")
rows = []
failed = 0

for path in INPUT_DIR.glob("*.json"):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        rows.append(score_doc(d, path))
    except Exception:
        failed += 1

rows_overall = sorted(rows, key=lambda x: x["overall_score"], reverse=True)
rows_api = sorted(rows, key=lambda x: x["api_score"], reverse=True)

api_shortlist = [
    r for r in rows_api
    if r["api_score"] >= API_MIN_SCORE
    and r["strong_project_overlap"] == 1
    and r["negative_penalty"] <= 18
][:MAX_API_FILES]

vendor_hits = [r for r in rows_api if r["vendors_found"]][:MAX_API_FILES]
care_hits = [r for r in rows_api if r["care_score"] >= 8][:MAX_API_FILES]

write_csv(OUTPUT_DIR / "ranked_all.csv", rows_overall)
write_csv(OUTPUT_DIR / "api_shortlist.csv", api_shortlist)
write_csv(OUTPUT_DIR / "vendor_hits_ranked.csv", vendor_hits)
write_csv(OUTPUT_DIR / "care_hits_ranked.csv", care_hits)

print(f"Scored         : {len(rows):,}")
print(f"Failed         : {failed}")
print(f"API shortlist  : {len(api_shortlist):,}")
print(f"Vendor hits    : {len(vendor_hits):,}")
print(f"Care hits      : {len(care_hits):,}")
print(f"Output         : {OUTPUT_DIR.resolve()}")

print("\nTop 25 API shortlist:")
for i, r in enumerate(api_shortlist[:25], 1):
    print(
        f"{i:>2}. api={r['api_score']:>3} | "
        f"care={r['care_score']:>2} tech={r['tech_score']:>2} "
        f"gate={r['gate_score']:>2} neg={r['negative_penalty']:>2} "
        f"overlap={r['strong_project_overlap']} | "
        f"{r['meeting_date']} | {r['filename'][:90]}"
    )