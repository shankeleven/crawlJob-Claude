# jobCrawl

A small daily job-search tool. It searches the public web through Firecrawl for software engineering jobs matching your profile. It remembers every job it has found in SQLite, so the same posting isn't shown to you twice, and it writes the results to an Excel workbook.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then set FIRECRAWL_API_KEY=fc-... in .env
```

## Usage

```bash
.venv/bin/python main.py          # full daily search
.venv/bin/python main.py --test   # tiny run (2 queries, ≤5 scrapes) to check the API key and setup
```

The output goes to:

- `data/jobs.xlsx`: two sheets.
  - **New Jobs**: jobs first found in this run.
  - **All Jobs**: every job ever found.
  - Both are sorted by score, with clickable URLs, a frozen header and filters.
- `data/jobs.db`: the SQLite database of every job found.
- A summary in the terminal, followed by the new jobs sorted by relevance.

To keep a log of a run: `.venv/bin/python -u main.py > data/last_run.log 2>&1`

## Files

- `profile.yaml`: your profile (roles, experience, languages, technologies, locations, graduation year). Edit it freely; the queries and the scoring are built from it.
- `main.py`: runs the whole pipeline. The run settings are at the top.
- `search.py`: builds the queries, runs the Firecrawl search and pulls the job details from each page.
- `db.py`: the SQLite database (`data/jobs.db`). The cleaned-up URL is the unique key.
- `urls.py`: removes tracking parameters from URLs and labels the source (Greenhouse, Lever, Ashby, Workday, etc.).
- `score.py`: the 0–100 relevance score.
- `freshness.py`: parses posted dates and drops closed or stale postings.
- `excel.py`: writes the "New Jobs" and "All Jobs" sheets.
- `.env`: your Firecrawl API key. It's ignored by git.
- `.venv/`: the installed dependencies, so always run the tool with `.venv/bin/python main.py`.

## How it works

1. **Search.** The tool builds a pool of about 240 queries from your profile, combining role, experience level, language, technology and graduation year. Every query also ends with a location phrase: `India`, `remote India` or `remote global`. These come from `locations` in `profile.yaml`. Each run uses 30 of them, and the set changes every day. Running it more than once on the same day reuses that day's set, so coverage grows over the days. Searches cover the whole web. The only results dropped before scraping are obvious non-postings: blogs, news, docs, Reddit, YouTube, salary pages and LinkedIn, which Firecrawl can't scrape.
2. **Recognising job pages.** Firecrawl reads each page and reports whether it is a single open job posting. It also extracts the title, company, location, posted date, a summary, the requirements and the experience requirements. Missing fields are left blank. Pages that aren't postings are dropped, including listing pages, articles and closed postings.
   **Freshness filter.** A posting is saved only if it's current. Postings that fail the filter go in `non_jobs`, so they aren't scraped again.
   - The page must not say the job is closed, filled, expired or no longer accepting applications.
   - It must have been posted this year, or, if it's older or undated, the page must still show it as open (for example, an Apply button is present).

   Firecrawl returns the posted date exactly as written on the page ("3 days ago", "Sep 20, 2026"), and `freshness.py` works out the actual date. The date is calculated locally rather than by Firecrawl's extraction because the extraction was resolving relative dates to the wrong year.
   **Location filter.** Only jobs matching a location in `profile.yaml` (currently `Remote` and `India`) are saved. The tool checks the location text and the countries Firecrawl extracts, and "Remote" matches only remote jobs open to one of your other locations (India). A remote job counts as open to India if the page lists India, a region that includes it (APAC, Asia), or says "worldwide", "anywhere" or "global". Remote jobs with no region stated are kept. Remote jobs limited to another country are skipped. Jobs with no location are skipped. Rejected pages also go in `non_jobs`, so if you add a location later, run `sqlite3 data/jobs.db "DELETE FROM non_jobs"` to let them be checked again.
3. **Deduplication.** Each URL is cleaned up first: `utm_*`, `ref`, `source`, `gclid`, `hl` and similar parameters are removed. Parameters that identify the job, like `gh_jid`, are kept.
   - If the URL is already in `jobs`, only `last_seen` is updated and the job isn't shown as new.
   - Otherwise it's saved and appears in today's **New Jobs**.
4. **Saving credits.** URLs already in the database are never scraped again. Pages that turned out not to be postings go in a separate `non_jobs` table, so they aren't scraped again either. Failed scrapes aren't recorded, so they're tried again on the next run.
5. **Scoring.** The score is out of 100:

   | Part | Points |
   |---|---|
   | Role | 30 |
   | Experience level | 25 |
   | Languages | 15 |
   | Technologies | 15 |
   | Location | 15 |

   Off-profile titles lose points, for example frontend, mobile, QA/tester, sales and internship roles. So do senior, staff, principal and lead titles, and experience requirements of 3+ years. As a guide, a new-grad distributed-storage role scores about 93, a frontend role 23 and a senior backend role 26. The score is used only for sorting and for the display threshold below.

## Settings (top of `main.py`)

| Setting | Default | Meaning |
|---|---|---|
| `MAX_QUERIES` | 30 | Queries per run, picked from the pool |
| `RESULTS_PER_QUERY` | 30 | Firecrawl search results per query |
| `MAX_SCRAPES` | 200 | Maximum number of unseen pages scraped per run. Each scrape costs credits |
| `RECENCY` | `"qdr:m"` | Only search results from the past month. Set to `None` for any time |
| `MIN_SCORE` | 25 | New jobs scoring below this are saved and appear in "All Jobs", but not in "New Jobs" or the terminal list. Set to 0 to show everything |

## Firecrawl credits and rate limits

- Every page is scraped with Firecrawl's JSON extraction, which costs more credits than a plain scrape. A full run with `MAX_SCRAPES = 200` uses a lot of credits. If your plan is small, lower `MAX_SCRAPES`, for example to 50.
- The tool waits and retries when Firecrawl rate-limits it. On a plan allowing about 10 requests a minute, a full run takes roughly 20–25 minutes.
- When credits run out, scrapes fail with "Insufficient credits". Nothing is lost: those URLs are tried again on the next run.

## Resetting

- To start over completely, delete `data/jobs.db`.
- To only make pages that were rejected as "not a posting" eligible for scraping again, clear the `non_jobs` table:
  `sqlite3 data/jobs.db "DELETE FROM non_jobs"`
