import os
import asyncio
import json
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
import random

BASE = "https://nu.edu.pk"
DEGREE_LIST_PATH = "/Degree-Programs"
OUTPUT_DIR = os.path.join("data", "degree_programs")
OUT_JSON = os.path.join(OUTPUT_DIR, "degree_programs.json")
OUT_MARKDOWN_DIR = os.path.join(OUTPUT_DIR, "degree_programs_raw.md")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

def collect_program_urls_requests():
    url = urljoin(BASE, DEGREE_LIST_PATH)
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print("[requests] Failed to fetch degree listing:", e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    program_links = []
    for a in soup.select("a"):
        href = a.get("href", "")
        if not href:
            continue
        full = urljoin(BASE, href)
        if any(part in full for part in ["/Program/", "/Bachelor/", "/Masters/", "/PhD/", "/Degree/"]):
            program_links.append(full)
    return sorted(set(program_links))

async def collect_program_urls_crawl4ai(crawler, run_config):
    url = urljoin(BASE, DEGREE_LIST_PATH)
    print("[crawl4ai] Fetching degree index:", url)
    result = await crawler.arun(url=url, config=run_config)

    links = set()
    html = getattr(result, "html", None)
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href]"):
            href = a.get("href")
            if not href:
                continue
            full = urljoin(BASE, href)
            if any(part in full for part in ["/Program/", "/Bachelor/", "/Masters/", "/PhD/", "/Degree/"]):
                links.add(full)

    if not links:
        md = getattr(result, "markdown", "")
        for match in re.finditer(r"\((https?://[^)]+)\)", md):
            candidate = match.group(1)
            if any(part in candidate for part in ["/Program/", "/Bachelor/", "/Masters/", "/PhD/", "/Degree/"]):
                links.add(candidate)

    links_list = sorted(links)
    print(f"[crawl4ai] Found {len(links_list)} program links (sample up to 10):", links_list[:10])
    return links_list

# ---------------- PEO/PLO extraction helpers ----------------

def extract_list_from_html(html: str, label_patterns):
    soup = BeautifulSoup(html, "html.parser")
    label_re = re.compile("|".join([re.escape(p) for p in label_patterns]), re.I)

    for header in soup.find_all(re.compile(r"^h[1-6]$")):
        text = header.get_text(" ", strip=True)
        if label_re.search(text):
            sib = header.find_next_sibling()
            while sib and (sib.name is None or sib.name in ("script", "style")):
                sib = sib.next_sibling
            if sib and sib.name in ("ul", "ol"):
                items = [li.get_text(" ", strip=True) for li in sib.find_all("li") if li.get_text(strip=True)]
                if items:
                    return items

            # fallback parse numbered / plain text lists
            current_items = []
            cur = None
            sib = header.next_sibling
            while sib:
                if getattr(sib, "name", "") and re.match(r"h[1-6]", sib.name, re.I):
                    break
                if hasattr(sib, "get_text"):
                    text_block = sib.get_text("\n", strip=True)
                    if text_block:
                        lines = [ln.strip() for ln in text_block.splitlines() if ln.strip()]
                        for ln in lines:
                            m = re.match(r'^(?:\d+[\.\)]\s*|(?:PO|PLO)\s*\d+[:\-]?\s*)(.*)$', ln, re.I)
                            if m:
                                if cur:
                                    current_items.append(cur.strip())
                                cur = m.group(1).strip()
                            else:
                                if cur:
                                    cur += " " + ln
                                else:
                                    cur = ln
                        if cur:
                            current_items.append(cur.strip())
                sib = sib.next_sibling
            if current_items:
                return current_items
    return []

def parse_program_markdown(md: str, html: str = None):
    out = {}
    out["raw_markdown"] = md

    # --- title ---
    title = ""
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("# "):
            title = s.lstrip("# ").strip()
            break
        if s.startswith("## "):
            title = s.lstrip("# ").strip()
            break
    out["title"] = title

    # eligibility
    m = re.search(r"\*\*Those who.*?\.\*\*", md, re.S | re.I)
    if m:
        out["eligibility"] = m.group(0).replace("**", "").strip()
    else:
        m = re.search(r"(?:\*\*Eligibility(?: Criteria)?\:\*\*|### Eligibility(?: Criteria)?:)(.*?)(?:\n\*\*|$)", md, re.S | re.I)
        if m:
            out["eligibility"] = m.group(1).strip()

    def extract_section_by_label(label):
        m = re.search(rf"\*\*{re.escape(label)}\*\*(.*?)(\*\*|$)", md, re.S | re.I)
        if m:
            return m.group(1).strip()
        m = re.search(rf"{label}\s*\n-+\s*\n(.*?)(?:\n\n|$)", md, re.S | re.I)
        if m:
            return m.group(1).strip()
        return ""

    out["vision"] = extract_section_by_label("Program Vision")
    out["mission"] = extract_section_by_label("Program Mission")
    out["career_opportunities"] = extract_section_by_label("Career Opportunities")

    # ---- PEO/PLO ----
    peos = []
    plos = []
    if html:
        peos = extract_list_from_html(html, ["Program Educational Objectives", "PEO", "PEOs"])
        plos = extract_list_from_html(html, ["Program Learning Outcomes", "PLO", "PLOs"])
    if not peos:
        m = re.search(r"Program Educational Objectives.*?\n(.*?)(?=\n#|\Z)", md, re.S | re.I)
        if m:
            peos = [it.strip() for it in re.findall(r"(?:\*|\-|\d+\.)\s*(.+)", m.group(1))]
    if not plos:
        m = re.search(r"Program Learning Outcomes.*?\n(.*?)(?=\n#|\Z)", md, re.S | re.I)
        if m:
            plos = [it.strip() for it in re.findall(r"(?:\*|\-|\d+\.)\s*(.+)", m.group(1))]
    out["peos"] = peos
    out["plos"] = plos

    # ---- Tentative Study Plan (Semesters) ----
    def parse_semesters(markdown: str):
        semesters = {}
        lines = markdown.splitlines()

        sem_header_re = re.compile(r"^#{1,6}\s*Semester\s+(\d+)\b", re.I)
        code_re = re.compile(r"^([A-Za-z]{2,6}\s?\d{3,4}[A-Za-z]?)\s*[-:]?\s*(.*)$")

        current_sem = None
        courses = []

        for raw in lines:
            line = raw.strip()
            if not line:
                continue

            # detect semester headers like "##### Semester 1"
            m = sem_header_re.match(line)
            if m:
                # save previous semester if any
                if current_sem and courses:
                    semesters[f"semester_{current_sem}"] = courses
                current_sem = int(m.group(1))
                courses = []
                continue

            # stop at total row
            if line.lower().startswith("**total"):
                if current_sem and courses:
                    semesters[f"semester_{current_sem}"] = courses
                    courses = []
                continue

            # skip headers/separators
            if "sr. no" in line.lower() or set(line) == {"-"}:
                continue

            # table rows (e.g. "1 | CS1001 Intro to ... | 3+1")
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3 and parts[0].isdigit():
                    idx_num = int(parts[0])
                    name_cell = parts[1]
                    credit_cell = parts[-1]

                    code = ""
                    name = name_cell
                    mcode = code_re.match(name_cell)
                    if mcode:
                        code = mcode.group(1).strip()
                        name = (mcode.group(2) or name_cell).strip()

                    courses.append({
                        "index": idx_num,
                        "code": code,
                        "name": name,
                        "credit_hours": credit_cell,
                    })

        # catch last semester
        if current_sem and courses:
            semesters[f"semester_{current_sem}"] = courses

        return semesters

    semesters = parse_semesters(md)
    if semesters:
        out["semesters"] = semesters

    return out

# ---------------- Main scraping ----------------

def is_server_error_page(md: str) -> bool:
    if not md:
        return False
    text = md.lower()
    return (
        "server error in '/' application" in text or
        'input string was not in a correct format' in text or
        'system.formatexception' in text or
        'views/admissions/programdetails.cshtml' in text
    )

async def fetch_with_retries(crawler, url: str, run_config, attempts: int = 4):
    for i in range(attempts):
        result = await crawler.arun(url=url, config=run_config)
        md = getattr(result, 'markdown', '') or ''
        if getattr(result, 'success', False) and not is_server_error_page(md):
            return result
        # backoff with jitter before retrying
        delay = (2 ** i) + random.uniform(0, 0.8)
        print(f"  [retry] {url} attempt {i+1}/{attempts} failed (server error or not success). Sleeping {delay:.1f}s...")
        await asyncio.sleep(delay)
    return result

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    program_links = collect_program_urls_requests()
    print(f"[requests] Found {len(program_links)} program links (requests).")

    # Updated config per Crawl4AI docs
    browser_config = BrowserConfig()
    run_config = CrawlerRunConfig(
        screenshot=False,
        remove_overlay_elements=True,
        excluded_tags=["header", "footer", "nav", "script", "style"],
        cache_mode="bypass",
        word_count_threshold=20,
        verbose=True,
    )

    results = []
    raw_snapshots = []

    async with AsyncWebCrawler(config=browser_config) as crawler:
        if len(program_links) < 5:
            program_links = await collect_program_urls_crawl4ai(crawler, run_config)

        if not program_links:
            print("ERROR: No program links found. Exiting.")
            return

        program_links = sorted({urljoin(BASE, link) for link in program_links})
        print(f"[final] Scraping {len(program_links)} program pages in parallel...")

        async def fetch_one(link: str):
            # initial attempt via arun_many-equivalent single call with retries
            res = await fetch_with_retries(crawler, link, run_config)
            return link, res

        tasks = [fetch_one(link) for link in program_links]
        crawl_results = await asyncio.gather(*tasks)

        for idx, (link, result) in enumerate(crawl_results, 1):
            try:
                if not getattr(result, 'success', False):
                    print(f"  [error] scraping {link}: {getattr(result, 'error_message', 'Unknown error')}")
                    continue
                md = getattr(result, 'markdown', '') or ''
                html = getattr(result, "html", None)
                parsed = parse_program_markdown(md, html=html)
                parsed["url"] = link
                # include final_url if crawl4ai returns it and it differs
                final_url = getattr(result, 'url', None) or getattr(result, 'page_url', None) or getattr(result, 'final_url', None)
                if final_url and str(final_url) != link:
                    parsed["final_url"] = str(final_url)
                parsed["last_scraped"] = datetime.utcnow().isoformat() + "Z"
                results.append(parsed)

                snapshot = {
                    "url": link,
                    "title": parsed.get("title", ""),
                    "timestamp": parsed.get("last_scraped"),
                    "raw_markdown_head": (parsed.get("raw_markdown") or "")[:4000]
                }
                raw_snapshots.append(snapshot)
            except Exception as e:
                print(f"  [error] parsing {link}: {e}")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    with open(OUT_MARKDOWN_DIR, "w", encoding="utf-8") as f:
        for s in raw_snapshots:
            f.write(f"# {s['title']} — {s['url']}\n")
            f.write(f"Scraped: {s['timestamp']}\n\n")
            f.write(s["raw_markdown_head"])
            f.write("\n\n---\n\n")

    print(f"Done — {len(results)} programs saved to {OUT_JSON} (snapshots -> {OUT_MARKDOWN_DIR})")

if __name__ == "__main__":
    asyncio.run(main())

def repair_saved_json(file_path: str = OUT_JSON):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("[repair] failed to load:", e)
        return
    updated = 0
    for rec in data:
        md = (rec.get("raw_markdown") or "").strip()
        if not md:
            continue
        parsed = parse_program_markdown(md)
        sem = parsed.get("semesters") or {}
        if sem:
            if rec.get("semesters") != sem:
                rec["semesters"] = sem
                updated += 1
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[repair] semesters updated for {updated} programs in {file_path}")
    except Exception as e:
        print("[repair] failed to write:", e)
