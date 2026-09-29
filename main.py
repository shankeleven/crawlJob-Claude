"""Daily job search: python main.py   (or: python main.py --test for a tiny run)"""
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from firecrawl import Firecrawl

import db
from excel import write_workbook
from freshness import is_current, parse_posted_date
from score import location_matches, score_job, tags
from search import generate_queries, scrape_many, search_all
from urls import canonicalize, source_of

# ---- Settings (edit as you like) ------------------------------------------------
MAX_QUERIES = 30         # queries per run (picked from a larger pool, rotating daily)
RESULTS_PER_QUERY = 30   # Firecrawl search results per query
MAX_SCRAPES = 200        # max unknown pages scraped per run (each costs Firecrawl credits)
RECENCY = "qdr:m"        # only search results from the past month; None for any time
MIN_SCORE = 25           # new jobs below this are stored but not shown in "New Jobs"
# ---------------------------------------------------------------------------------

ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "jobs.db"
XLSX_PATH = ROOT / "data" / "jobs.xlsx"

JOBBY_URL = re.compile(r"job|career|position|opening|vacanc|greenhouse|lever\.co|ashbyhq|workday|apply", re.I)


def main() -> None:
    test = "--test" in sys.argv
    max_queries, max_scrapes = (2, 5) if test else (MAX_QUERIES, MAX_SCRAPES)

    load_dotenv(ROOT / ".env")
    key = os.getenv("FIRECRAWL_API_KEY")
    if not key:
        sys.exit("FIRECRAWL_API_KEY is not set. Copy .env.example to .env and add your key.")
    fc = Firecrawl(api_key=key)

    profile = yaml.safe_load((ROOT / "profile.yaml").read_text())
    (ROOT / "data").mkdir(exist_ok=True)
    conn = db.connect(str(DB_PATH))
    now = datetime.now().isoformat(timespec="seconds")

    queries = generate_queries(profile, max_queries, seed=date.today().isoformat())
    print(f"Searching with {len(queries)} queries...")
    total_results, candidates = search_all(fc, queries, RESULTS_PER_QUERY, RECENCY)

    known = 0
    to_scrape = []
    for canon, r in candidates.items():
        if db.is_known_job(conn, canon):
            db.touch(conn, canon, now)
            known += 1
        elif not db.is_non_job(conn, canon):
            to_scrape.append(r["url"])
    # Scrape the most job-looking URLs first when we have to cap.
    to_scrape.sort(key=lambda u: not JOBBY_URL.search(u))
    skipped = max(0, len(to_scrape) - max_scrapes)
    to_scrape = to_scrape[:max_scrapes]

    print(f"\nScraping {len(to_scrape)} unseen pages...")
    new_jobs, failed, not_jobs, stale, wrong_location = [], 0, 0, 0, 0
    for url, data in scrape_many(fc, to_scrape):
        if data is None:
            failed += 1  # not recorded, so it is retried next run
            continue
        if not data.get("is_single_job_posting"):
            db.add_non_job(conn, canonicalize(url), now)
            not_jobs += 1
            continue
        posted = parse_posted_date(data.get("posted_date_text"), date.today())
        if not is_current(data, posted, date.today()):
            db.add_non_job(conn, canonicalize(url), now)  # closed/stale; don't re-scrape
            stale += 1
            continue
        if not location_matches(data, profile):
            db.add_non_job(conn, canonicalize(url), now)  # outside profile locations
            wrong_location += 1
            continue
        final_url = data.get("final_url") or url
        canon = canonicalize(final_url)
        job = {
            "url": final_url,
            "canonical_url": canon,
            "title": data.get("title") or "",
            "company": data.get("company") or "",
            "location": data.get("location") or ("Remote" if data.get("is_remote") else ""),
            "posted_date": posted.isoformat() if posted else (data.get("posted_date_text") or ""),
            "description": data.get("description") or "",
            "requirements": json.dumps(data.get("requirements") or []),
            "experience": data.get("experience_requirements") or "",
            "source": source_of(final_url),
            "score": score_job(data, profile),
        }
        if canonicalize(url) != canon:  # redirected; remember the search URL too
            db.add_non_job(conn, canonicalize(url), now)
        if db.insert_job(conn, job, now):
            job["tags"] = tags(data, profile)
            job["first_seen"] = job["last_seen"] = now
            new_jobs.append(job)
        else:
            known += 1
    conn.commit()

    shown = sorted((j for j in new_jobs if j["score"] >= MIN_SCORE), key=lambda j: -j["score"])
    all_rows = [dict(r) for r in conn.execute("SELECT * FROM jobs")]
    write_workbook(str(XLSX_PATH), shown, all_rows)

    print("\nJob search complete.\n")
    print(f"Search queries: {len(queries)}")
    print(f"Search results: {total_results:,}  ({len(candidates):,} unique candidate URLs)")
    print(f"Job pages inspected: {len(to_scrape)}"
          f"  (not postings: {not_jobs}, closed/stale: {stale}, wrong location: {wrong_location}, failed: {failed}"
          + (f", over cap: {skipped}" if skipped else "") + ")")
    print(f"\nPreviously known: {known}")
    print(f"New jobs: {len(new_jobs)}"
          + (f"  ({len(new_jobs) - len(shown)} below score {MIN_SCORE} hidden)" if len(shown) < len(new_jobs) else ""))
    print(f"\nExcel updated:\n{XLSX_PATH.relative_to(ROOT)}\n")
    for i, j in enumerate(shown, 1):
        print(f"{i}. {j['title']} — {j['company'] or '?'}")
        if j["tags"] or j["location"]:
            print("   " + " · ".join(j["tags"] or [j["location"]]))
        print(f"   Score: {j['score']}")
        print(f"   {j['url']}\n")


if __name__ == "__main__":
    main()
