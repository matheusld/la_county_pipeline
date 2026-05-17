#!/usr/bin/env python3
"""
LA County SOP — Keyword-Based Scraper
Searches the SOP page for each keyword and downloads matching documents.
Results saved to ./lacounty_keyword_docs/

  pip install playwright beautifulsoup4 requests tqdm
  playwright install chromium

Usage:
  python scrape_lacounty_keywords.py
  python scrape_lacounty_keywords.py --date-from 2020-01-01 --date-to 2026-03-28
  python scrape_lacounty_keywords.py --dry-run
  python scrape_lacounty_keywords.py --resume        # skip keywords already searched
"""

import argparse
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SOP_URL    = "https://lacounty.gov/government/board-of-supervisors/statement-of-proceedings/"
OUTPUT_DIR = Path("./lacounty_keyword_docs")
STATE_FILE = Path("./lacounty_keyword_scraper_state.json")
DELAY      = 0.4

DATE_FROM  = "01/01/2020"
DATE_TO    = "03/28/2026"

# ── Keyword list ──────────────────────────────────────────────────────────────
# Each entry is searched exactly as written. Case-insensitive on the server.
KEYWORDS = [
    # Vendors & Products
    "Northpointe", "COMPAS", "Palantir", "Salesforce", "SAS Institute",
    "Axon", "LiveView", "Collective Medical", "Healthvana", "TeleTracking",
    "DataWorks Plus", "Biometrics4All", "Decision Lens", "Accela",
    "Amazon Web Services", "AWS", "Oracle Cloud", "Google Cloud", "GCP",
    "Microsoft Azure", "M365", "IBM Watson", "IBM", "Qualtrics", "Zscaler",
    "CyberArk", "Splunk", "Imprivata", "ESRI", "ServiceNow",
    "Tyler Technologies", "Maximus", "Deloitte", "Accenture",
    "Microsoft Copilot", "Clarity Human Services", "ServicePoint",
    "Unite Us", "Aunt Bertha", "Findhelp", "CHAMP",
    "USC Children's Data Network", "Million Dollar Hoods", "Chapin Hall",

    # AI / Technology Concepts
    "artificial intelligence", "generative AI", "machine learning",
    "predictive analytics", "predictive risk", "risk assessment algorithm",
    "algorithmic", "risk score", "automation", "data analytics",
    "data integration", "data repository", "data warehouse",
    "case management system", "electronic monitoring", "surveillance",
    "biometric", "facial recognition", "natural language processing",
    "decision support", "digital evidence", "body worn camera", "BWC",
    "GPS monitoring", "CCTV", "SaaS", "cloud-based", "API",
    "interoperability", "data sharing", "real-time data", "dashboard",
    "early warning system", "screening tool", "triage tool",
    "matching algorithm", "resource matching", "eligibility algorithm",
    "integrated data", "information system",

    # Directives & Governance
    "TD 24-04", "Technology Directive", "GenAI Governance Board",
    "GenAI Board", "Chief Information Officer", "CIO",
    "Chief Privacy Officer", "ATI-2022-01", "GASB 96",
    "data governance", "algorithmic accountability", "privacy impact",
    "algorithmic impact", "technology policy", "responsible AI",
    "ethical AI", "AI policy", "procurement policy", "HIPAA",
    "data sharing agreement", "data use agreement",
    "memorandum of understanding", "MOU",

    # Care-First Infrastructure
    "Measure J", "Care First Community Investment", "CFCI", "Care First",
    "Alternatives to Incarceration", "ATI Initiative",
    "Youth Justice Reimagined", "Department of Youth Development", "DYD",
    "Ready to Rise", "Jail Depopulation", "Family First Prevention",
    "FFPSA", "JCOD", "Justice Care and Opportunities",
    "Justice Care Opportunities Department", "Re-Imagine LA",
    "Sequential Intercept Model", "SIM",
    "Office of Diversion and Reentry", "ODR", "Whole Person Care",
    "WPC", "diversion", "reentry", "pretrial",

    # Departments & Programs
    "Department of Children and Family Services", "DCFS",
    "Department of Mental Health", "DMH", "Department of Public Health",
    "DPH", "Probation Department", "Department of Health Services", "DHS",
    "Behavioral Health", "WDACS", "DCBA", "ISD",
    "Department of Homeless Services", "Department of Public Social Services",
    "DPSS", "Public Defender", "District Attorney",
    "Office of Child Protection", "Probation Oversight Commission",
    "GRYD", "Gang Reduction and Youth Development",
    "Office of Violence Prevention",

    # Homelessness
    "Homeless Initiative", "LAHSA", "Measure H", "Proposition HHH",
    "HMIS", "Coordinated Entry", "CES", "coordinated entry system",
    "Housing for Health", "encampment", "housing navigation",
    "interim housing", "bridge housing", "permanent supportive housing",
    "recuperative care", "crisis stabilization unit", "sobering center",
    "Restorative Care Village", "LACDA",

    # Specific Systems
    "Family Assessment Form", "CWS/CMS", "child welfare information system",
    "CARES", "CalSAWS", "electronic health record", "EHR", "EMR",
    "crisis stabilization", "988 crisis", "mobile crisis", "MCOT",
    "Psychiatric Mobile Response Team", "PMRT", "ASPIRE",
    "AB 109", "AB 1810", "SB 823", "Realignment",
    "electronic home detention", "grievance management",
    "digital evidence management", "MHSA", "JJCPA", "CalWORKs",
    "CalFresh", "General Relief", "benefits eligibility",
    "Medi-Cal enrollment", "WIOA", "AJCC", "SAPC",
    "ACCESS line", "medication-assisted treatment", "MAT",
    "harm reduction", "naloxone", "overdose prevention",
    "MLK Behavioral Health Center", "LAC+USC", "Olive View",
    "Rancho Los Amigos",

    # Workforce & Economic Inclusion
    "workforce development", "job training", "reentry",
    "formerly incarcerated", "returning residents",
    "community health worker", "CHW", "peer support", "lived experience",
    "pay for success", "performance-based contract", "EITC",
    "African American Infant and Maternal Mortality", "AAIMM", "doula",

    # Accountability & Oversight
    "Office of Inspector General", "OIG", "racial equity",
    "disparate impact", "equity impact", "racial bias", "bias audit",
    "civil rights", "consent decree", "racial equity toolkit", "GARE",
    "data transparency",

    # Key People
    "Peter Loo", "Greg Melendez", "Mirian Avalos", "Lawrence Gann",
    "James Thurmond", "Derek Steele", "Timothy Young", "Fesia Davenport",
    "Diana Zuniga", "Karen Tamis", "Peter Espinoza", "Corrin Buchanan",
    "Hilda Solis", "Holly Mitchell", "Lindsey Horvath", "Janice Hahn",
    "Kathryn Barger", "Sheila Kuehl", "Mark Ridley-Thomas",

    # CBOs & Partners
    "Social Justice Learning Institute", "SJLI", "Urban Peace Institute",
    "Anti-Recidivism Coalition", "ARC", "Homeboy Industries",
    "Youth Justice Coalition", "Community Coalition", "Reform LA Jails",
    "Justice LA", "Liberty Hill Foundation", "California Endowment",
    "Vera Institute", "Dignity and Power Now", "Root and Rebound",
    "All of Us or None", "Chrysalis", "HealthRIGHT 360",
    "Inner City Struggle", "Brotherhood Crusade",
    "Centinela Youth Services",
]


def p(msg):
    print(msg, flush=True)


def safe_filename(url, title="", meeting_date=None):
    url_stem = Path(urlparse(url).path).stem
    file_id  = url_stem.split("_")[0]
    date_str = meeting_date or parse_date_from_url(url)
    if title:
        slug = re.sub(r"[^\w\s\-]", "", title.strip())
        slug = re.sub(r"\s+", "_", slug)[:80]
        if date_str:
            return f"{date_str}_{slug}_{file_id}.pdf"
        return f"{slug}_{file_id}.pdf"
    if date_str:
        return f"{date_str}_{url_stem}.pdf"
    return f"{url_stem}.pdf"


def parse_date_from_url(url):
    stem  = Path(urlparse(url).path).stem
    parts = stem.split("_")
    if len(parts) >= 2:
        raw = parts[-1].rstrip("C")
        if len(raw) == 6 and raw.isdigit():
            mm, dd, yy = raw[:2], raw[2:4], raw[4:6]
            year = f"20{yy}"
            try:
                datetime.strptime(f"{year}-{mm}-{dd}", "%Y-%m-%d")
                return f"{year}-{mm}-{dd}"
            except ValueError:
                pass
        if len(raw) == 8 and raw.isdigit():
            mm, dd, yyyy = raw[:2], raw[2:4], raw[4:8]
            try:
                datetime.strptime(f"{yyyy}-{mm}-{dd}", "%Y-%m-%d")
                return f"{yyyy}-{mm}-{dd}"
            except ValueError:
                pass
    return None


def download_pdf(session, url, dest):
    if dest.exists():
        return "skipped"
    try:
        r = session.get(url, timeout=60)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return "ok"
    except Exception as exc:
        log.warning("  FAILED %s -- %s", url, exc)
        return "failed"


def search_keyword(page, keyword, date_from, date_to, PWTimeout):
    """Run a single keyword search and return list of {url, title, meeting_date, keyword}."""
    from bs4 import BeautifulSoup

    links = []

    # Fill keyword search box
    try:
        el = page.query_selector('input[name="query"], input[id="searchQueryText"]')
        if el:
            el.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            page.keyboard.type(keyword, delay=30)
            page.wait_for_timeout(200)
    except Exception:
        pass

    # Set date range via JS
    set_date_js = """(args) => {
        const [name, value] = args;
        const el = document.querySelector('input[name="' + name + '"]');
        if (!el) return null;
        const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, value);
        el.dispatchEvent(new Event('input',  { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur',   { bubbles: true }));
        return el.value;
    }"""
    page.evaluate(set_date_js, ["fromDate", date_from])
    page.wait_for_timeout(200)
    page.evaluate(set_date_js, ["toDate", date_to])
    page.wait_for_timeout(200)

    # Submit
    for sel in ['button:has-text("Search")', 'input[type="submit"]', 'button[type="submit"]']:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                break
        except Exception:
            continue

    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except PWTimeout:
        pass
    page.wait_for_timeout(800)

    # Check count
    try:
        body = page.inner_text("body")
        count_m = re.search(r"Count:\s*(\d+)", body)
        count = int(count_m.group(1)) if count_m else 0
    except Exception:
        count = 0

    if count == 0:
        return []

    # Scroll and collect across pages
    page_num = 1
    while True:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(600)

        soup = BeautifulSoup(page.content(), "html.parser")
        new_links = []
        seen_urls = set()
        current_date = None

        for tag in soup.find_all(True):
            if tag.name in ("h2","h3","h4","strong","span","div","td","p"):
                text = tag.get_text(strip=True)
                m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", text)
                if m:
                    mo, dy, yr = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
                    current_date = f"{yr}-{mo}-{dy}"

            if tag.name != "a":
                continue
            href = tag.get("href", "")
            if href.lower().startswith("mailto:"):
                mx = re.search(r'body=(https?://[^\s&]+\.pdf)', href, re.IGNORECASE)
                if mx:
                    href = mx.group(1)
                else:
                    continue
            if not href.lower().endswith(".pdf"):
                continue
            if not href.startswith("http"):
                href = f"https://lacounty.gov{href}"
            if "file.lacounty.gov" not in href:
                continue
            if href not in seen_urls:
                seen_urls.add(href)
                new_links.append({
                    "url": href,
                    "title": tag.get_text(strip=True),
                    "meeting_date": current_date,
                    "keyword": keyword,
                })

        links.extend(new_links)

        # Next page
        next_li = page.query_selector("li#SOPSearch_next") or page.query_selector("li.next")
        if not next_li or "disabled" in (next_li.get_attribute("class") or ""):
            break
        next_a = next_li.query_selector("a")
        if not next_a:
            break
        page.evaluate("el => el.click()", next_a)
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except PWTimeout:
            pass
        page.wait_for_timeout(800)
        page_num += 1

    return links


def collect_all_keywords(keywords, date_from, date_to, headless, resume_state):
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        raise SystemExit("\nRun: pip install playwright && playwright install chromium\n")

    all_links = {}   # url -> doc dict (deduped globally)
    keyword_log = resume_state.get("completed_keywords", {})

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page    = browser.new_page()

        total = len(keywords)
        for i, keyword in enumerate(keywords, 1):
            if keyword in keyword_log:
                p(f"[{i}/{total}] SKIP (already done): {keyword}  ({keyword_log[keyword]} docs)")
                continue

            p(f"\n[{i}/{total}] Searching: '{keyword}'")

            # Reload page for each keyword to reset state cleanly
            page.goto(SOP_URL, wait_until="networkidle", timeout=30_000)
            page.wait_for_timeout(800)

            # Ensure all checkboxes are checked
            want = {
                "Transcripts":              True,
                "Statement of Proceedings": True,
                "Supporting Documents":     True,
            }
            for label_el in page.query_selector_all("label"):
                try:
                    text = (label_el.inner_text() or "").strip()
                    for label_text, should_check in want.items():
                        if label_text.lower() in text.lower():
                            cb = label_el.query_selector('input[type="checkbox"]')
                            if cb:
                                if should_check and not cb.is_checked():
                                    cb.click()
                                    page.wait_for_timeout(150)
                            break
                except Exception:
                    pass

            found = search_keyword(page, keyword, date_from, date_to, PWTimeout)

            new_count = 0
            for doc in found:
                if doc["url"] not in all_links:
                    all_links[doc["url"]] = doc
                    new_count += 1

            keyword_log[keyword] = len(found)
            p(f"         Found {len(found)} docs ({new_count} new) | {len(all_links)} unique total")

            # Save state after each keyword so we can resume
            save_state({"completed_keywords": keyword_log,
                        "collected_urls": list(all_links.keys())})

            time.sleep(DELAY)

        browser.close()

    return list(all_links.values())


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def main():
    parser = argparse.ArgumentParser(description="Keyword-based LA County SOP scraper")
    parser.add_argument("--date-from",   default="2020-01-01")
    parser.add_argument("--date-to",     default=datetime.today().strftime("%Y-%m-%d"))
    parser.add_argument("--output-dir",  default=str(OUTPUT_DIR))
    parser.add_argument("--no-headless", action="store_true")
    parser.add_argument("--dry-run",     action="store_true")
    parser.add_argument("--resume",      action="store_true",
                        help="Skip keywords already completed in a previous run")
    parser.add_argument("--keywords",    nargs="+",
                        help="Override keyword list with specific terms")
    args = parser.parse_args()

    def to_form_date(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").strftime("%m/%d/%Y")
        except ValueError:
            return s

    date_from = to_form_date(args.date_from)
    date_to   = to_form_date(args.date_to)
    keywords  = args.keywords or KEYWORDS

    resume_state = load_state() if args.resume else {}

    log.info("=== LA County SOP Keyword Scraper ===")
    log.info("Keywords  : %d", len(keywords))
    log.info("Date range: %s -- %s", date_from, date_to)
    log.info("Output    : %s", args.output_dir)
    if args.resume:
        done = len(resume_state.get("completed_keywords", {}))
        log.info("Resuming  : %d keywords already completed", done)

    docs = collect_all_keywords(
        keywords=keywords,
        date_from=date_from,
        date_to=date_to,
        headless=not args.no_headless,
        resume_state=resume_state,
    )

    p(f"\n>> Found {len(docs)} unique PDF(s) across all keywords.\n")

    if args.dry_run:
        p("-- Dry run: not downloading --")
        # Group by keyword for readability
        from collections import defaultdict
        by_kw = defaultdict(list)
        for d in docs:
            by_kw[d["keyword"]].append(d)
        for kw, items in by_kw.items():
            p(f"\n  [{kw}] — {len(items)} docs")
            for d in items[:3]:
                p(f"    {d['title'] or '(no title)'}")
                p(f"    {d['url']}")
            if len(items) > 3:
                p(f"    ... and {len(items)-3} more")
        return

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Also save a manifest CSV
    manifest_path = out_dir / "_manifest.csv"
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write("filename,keyword,meeting_date,title,url\n")
        for doc in docs:
            fname = safe_filename(doc["url"], doc.get("title",""), doc.get("meeting_date"))
            row = f'"{fname}","{doc.get("keyword","")}","{doc.get("meeting_date","")}","{doc.get("title","").replace(chr(34), chr(39))}","{doc["url"]}"\n'
            f.write(row)
    p(f"Manifest saved: {manifest_path}")

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 lacounty-keyword-scraper/1.0"

    ok = fail = skipped = 0
    with tqdm(docs, unit="file", desc="Downloading") as bar:
        for doc in bar:
            fname  = safe_filename(doc["url"], doc.get("title",""), doc.get("meeting_date"))
            bar.set_postfix_str(fname[:50])
            result = download_pdf(session, doc["url"], out_dir / fname)
            if result == "ok":        ok += 1
            elif result == "skipped": skipped += 1
            else:                     fail += 1
            time.sleep(DELAY)

    p(f"\n>> Done. {ok} downloaded, {skipped} skipped, {fail} failed.")
    p(f"   Saved to: {out_dir.resolve()}")
    p(f"   Manifest: {manifest_path.resolve()}")


if __name__ == "__main__":
    main()
