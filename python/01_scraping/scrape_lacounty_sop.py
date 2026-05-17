#!/usr/bin/env python3
"""
LA County Board of Supervisors - Statement of Proceedings Scraper

  pip install playwright beautifulsoup4 requests tqdm
  playwright install chromium

Usage:
  python scrape_lacounty_sop.py --doc-type all --date-from 2020-01-01
  python scrape_lacounty_sop.py --doc-type transcripts --date-from 2024-01-01 --max-docs 10
  python scrape_lacounty_sop.py --doc-type all --date-from 2020-01-01 --dry-run
  python scrape_lacounty_sop.py --doc-type all --date-from 2020-01-01 --no-headless

Document type options: all | transcripts | sop | supporting
"""

import argparse
import logging
import re
import time
from datetime import datetime, timedelta
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
OUTPUT_DIR = Path("./lacounty_sop_docs")
DELAY      = 0.4

DOC_TYPE_LABELS = {
    "transcripts": "Transcripts",
    "sop":         "Statement of Proceedings",
    "supporting":  "Supporting Documents",
}


def p(msg):
    print(msg, flush=True)


def parse_date_from_url(url):
    """Extract date from URL stem like 1204786_032426 -> 2026-03-24"""
    stem = Path(urlparse(url).path).stem  # e.g. "1204786_032426"
    parts = stem.split("_")
    if len(parts) >= 2:
        raw = parts[-1].rstrip("C")  # strip trailing C (corrected transcripts)
        # Try MMDDYY (6 digits)
        if len(raw) == 6 and raw.isdigit():
            mm, dd, yy = raw[:2], raw[2:4], raw[4:6]
            year = f"20{yy}"
            try:
                datetime.strptime(f"{year}-{mm}-{dd}", "%Y-%m-%d")
                return f"{year}-{mm}-{dd}"
            except ValueError:
                pass
        # Try MMDDYYYY (8 digits)
        if len(raw) == 8 and raw.isdigit():
            mm, dd, yyyy = raw[:2], raw[2:4], raw[4:8]
            try:
                datetime.strptime(f"{yyyy}-{mm}-{dd}", "%Y-%m-%d")
                return f"{yyyy}-{mm}-{dd}"
            except ValueError:
                pass
    return None


def safe_filename(url, title="", meeting_date=None):
    url_stem = Path(urlparse(url).path).stem
    file_id  = url_stem.split("_")[0]
    # Prefer meeting_date from page structure, fall back to URL-parsed date
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


def set_date_input(page, selector, value):
    """
    Reliably fill a date input by clicking, selecting all, and typing.
    Tries multiple approaches since date pickers can be finicky.
    """
    try:
        el = page.query_selector(selector)
        if not el or not el.is_visible():
            return False
        # Click to focus
        el.click()
        page.wait_for_timeout(300)
        # Select all existing content
        page.keyboard.press("Control+A")
        page.wait_for_timeout(100)
        # Delete it
        page.keyboard.press("Delete")
        page.wait_for_timeout(100)
        # Type the new value character by character
        page.keyboard.type(value, delay=50)
        page.wait_for_timeout(200)
        # Tab out to trigger any change events
        page.keyboard.press("Tab")
        page.wait_for_timeout(300)
        return True
    except Exception:
        return False


def collect_pdf_links(doc_type, date_from, date_to, headless=True):
    """
    date_from / date_to should be MM/DD/YYYY strings.
    Returns list of {url, title} dicts.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        raise SystemExit("\nRun: pip install playwright && playwright install chromium\n")

    from bs4 import BeautifulSoup
    links = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page    = browser.new_page()

        p(f"\n  [1/4] Loading search page...")
        page.goto(SOP_URL, wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(1000)

        # ── Checkboxes ────────────────────────────────────────────────────────
        p(f"  [2/4] Setting checkboxes for: {doc_type}")
        want = {
            "Transcripts":              doc_type in ("all", "transcripts"),
            "Statement of Proceedings": doc_type in ("all", "sop"),
            "Supporting Documents":     doc_type in ("all", "supporting"),
        }
        for label_el in page.query_selector_all("label"):
            try:
                text = (label_el.inner_text() or "").strip()
                for label_text, should_check in want.items():
                    if label_text.lower() in text.lower():
                        cb = label_el.query_selector('input[type="checkbox"]')
                        if not cb:
                            # try sibling
                            cb = page.query_selector(f'input[type="checkbox"] + label:has-text("{label_text}")')
                        if cb:
                            checked = cb.is_checked()
                            if should_check and not checked:
                                cb.click()
                                page.wait_for_timeout(200)
                                p(f"        + Checked: {label_text}")
                            elif not should_check and checked:
                                cb.click()
                                page.wait_for_timeout(200)
                                p(f"        - Unchecked: {label_text}")
                        break
            except Exception:
                pass

        # ── Date inputs ───────────────────────────────────────────────────────
        p(f"  [3/4] Setting dates: {date_from} to {date_to}")

        # Target fromDate and toDate directly by name attribute
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

        r_from = page.evaluate(set_date_js, ["fromDate", date_from])
        page.wait_for_timeout(300)
        r_to   = page.evaluate(set_date_js, ["toDate",   date_to])
        page.wait_for_timeout(300)
        p(f"        From = {r_from or '(not set)'}")
        p(f"        To   = {r_to   or '(not set)'}")

                # ── Submit ────────────────────────────────────────────────────────────
        p(f"  [4/4] Submitting search...")
        for sel in ['button:has-text("Search")', 'input[value*="Search"]',
                    'button[type="submit"]', 'input[type="submit"]']:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    break
            except Exception:
                continue

        try:
            page.wait_for_load_state("networkidle", timeout=25_000)
        except PWTimeout:
            pass
        page.wait_for_timeout(1000)

        # Log what count the page shows
        try:
            body_text = page.inner_text("body")
            count_match = re.search(r'Count:\s*(\d+)', body_text)
            entries_match = re.search(r'Showing \d+ to \d+ of (\d+) entries', body_text)
            if count_match:
                p(f"        Page reports Count: {count_match.group(1)}")
            if entries_match:
                p(f"        Page reports {entries_match.group(1)} entries")
        except Exception:
            pass

        # ── Paginate and collect ──────────────────────────────────────────────
        page_num = 1
        while True:
            # Scroll to bottom to trigger any lazy-loaded content
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)

            soup = BeautifulSoup(page.content(), "html.parser")
            new_links = []
            seen_urls = set()

            # Walk the DOM tracking the current meeting date heading
            # The page renders: <date heading> then <links> under it
            current_date = None
            for tag in soup.find_all(True):
                # Detect date headings — they appear as standalone text like "12/19/2023"
                if tag.name in ("h2", "h3", "h4", "strong", "span", "div", "td", "p"):
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
                    })

            if not new_links:
                p(f"        Page {page_num}: no PDFs found — done.")
                break

            links.extend(new_links)

            # Log meeting dates found on this page and running total
            try:
                body = page.inner_text("body")
                entries_match = re.search(r"Showing (\d+) to (\d+) of (\d+) entries", body)
                if entries_match:
                    showing_from = entries_match.group(1)
                    showing_to   = entries_match.group(2)
                    total_entries = entries_match.group(3)
                    p(f"        Page {page_num}: {len(new_links)} PDFs from meeting dates {showing_from}-{showing_to} of {total_entries} | {len(links)} total PDFs")
                else:
                    p(f"        Page {page_num}: {len(new_links)} PDFs | {len(links)} total")
            except Exception:
                p(f"        Page {page_num}: {len(new_links)} PDFs | {len(links)} total")

            # Check for disabled next button (controls meeting-date pagination)
            next_li = page.query_selector("li#SOPSearch_next") or page.query_selector("li.next")
            if not next_li or "disabled" in (next_li.get_attribute("class") or ""):
                p(f"        Last meeting-date page reached.")
                break

            next_a = next_li.query_selector("a")
            if not next_a:
                break
            # Click via JS to avoid detached element issues after re-renders
            page.evaluate("el => el.click()", next_a)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PWTimeout:
                pass
            page.wait_for_timeout(1000)
            page_num += 1

        browser.close()

    seen = set()
    deduped = []
    for d in links:
        if d["url"] not in seen:
            seen.add(d["url"])
            deduped.append(d)
    return deduped


def main():
    today     = datetime.today()
    month_ago = today - timedelta(days=30)

    parser = argparse.ArgumentParser(description="Download LA County SOP PDFs.")
    parser.add_argument("--doc-type", choices=["all", "transcripts", "sop", "supporting"],
                        default="transcripts")
    parser.add_argument("--date-from", default=month_ago.strftime("%Y-%m-%d"))
    parser.add_argument("--date-to",   default=today.strftime("%Y-%m-%d"))
    parser.add_argument("--max-docs",  type=int, default=None)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--no-headless", action="store_true")
    parser.add_argument("--dry-run",     action="store_true")
    args = parser.parse_args()

    def to_form_date(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").strftime("%m/%d/%Y")
        except ValueError:
            return s

    log.info("=== LA County SOP Scraper ===")
    log.info("Doc type  : %s", args.doc_type)
    log.info("Date range: %s -- %s", args.date_from, args.date_to)
    log.info("Max docs  : %s", args.max_docs if args.max_docs else "unlimited")
    log.info("Output    : %s", args.output_dir)

    # Batch by 2-week chunks to stay under the ~300 doc DOM render cap
    from_dt = datetime.strptime(args.date_from, "%Y-%m-%d")
    to_dt   = datetime.strptime(args.date_to,   "%Y-%m-%d")

    batches = []
    cur = from_dt
    while cur <= to_dt:
        batch_start = cur
        batch_end   = min(cur + timedelta(days=13), to_dt)
        batches.append((to_form_date(batch_start.strftime("%Y-%m-%d")),
                        to_form_date(batch_end.strftime("%Y-%m-%d"))))
        cur = batch_end + timedelta(days=1)

    all_docs  = []
    seen_urls = set()

    for i, (bf, bt) in enumerate(batches, 1):
        p(f"\n=== Batch {i}/{len(batches)}: {bf} to {bt} ===")
        batch_docs = collect_pdf_links(
            doc_type=args.doc_type,
            date_from=bf,
            date_to=bt,
            headless=not args.no_headless,
        )
        new_count = 0
        for d in batch_docs:
            if d["url"] not in seen_urls:
                seen_urls.add(d["url"])
                all_docs.append(d)
                new_count += 1
        p(f"  Batch result: {len(batch_docs)} found | {new_count} new | {len(all_docs)} total")

    docs = all_docs
    if args.max_docs:
        docs = docs[:args.max_docs]

    if not docs:
        log.warning("No PDFs found. Try --no-headless to debug the form.")
        return

    p(f"\n>> Found {len(docs)} unique PDF(s) to download.\n")

    if args.dry_run:
        p("-- Dry run: not downloading --")
        for i, d in enumerate(docs, 1):
            p(f"  [{i}] {d['title'] or '(no title)'}")
            p(f"       {d['url']}")
        return

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 lacounty-sop-scraper/2.0"

    ok = fail = skipped = 0
    with tqdm(docs, unit="file", desc="Downloading") as bar:
        for doc in bar:
            fname  = safe_filename(doc["url"], doc.get("title", ""), doc.get("meeting_date"))
            bar.set_postfix_str(fname[:50])
            result = download_pdf(session, doc["url"], out_dir / fname)
            if result == "ok":       ok += 1
            elif result == "skipped": skipped += 1
            else:                    fail += 1
            time.sleep(DELAY)

    p(f"\n>> Done. {ok} downloaded, {skipped} skipped, {fail} failed.")
    p(f"   Saved to: {out_dir.resolve()}")


if __name__ == "__main__":
    main()