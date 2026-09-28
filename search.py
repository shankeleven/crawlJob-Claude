"""Query generation, Firecrawl search, and job-page extraction."""
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor

from urls import canonicalize

# Search engines match "Go" poorly; use the common alias in queries only.
QUERY_ALIASES = {"Go": "Golang", "New Graduate": "new grad"}


def with_retry(fn, *args, **kwargs):
    """Call a Firecrawl method, waiting out rate limits (plans allow only N requests/min)."""
    for attempt in range(8):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if "rate limit" not in str(e).lower() or attempt == 7:
                raise
            m = re.search(r"retry after (\d+)s", str(e))
            time.sleep((int(m.group(1)) if m else 15) + 2)


def generate_queries(profile: dict, max_queries: int, seed: str) -> list[str]:
    """Build a broad pool of queries from the profile, then pick a daily subset.

    The shuffle is seeded by date, so each day covers a different slice of the pool
    and repeated runs on the same day use the same queries.
    """
    a = lambda s: QUERY_ALIASES.get(s, s)
    roles = profile["roles"]
    exp = profile["experience"]
    year = profile.get("graduation_year")

    pool = set()
    for r in roles:
        for e in exp:
            pool.add(f'"{r}" {a(e)}')
        for lang in profile["languages"]:
            pool.add(f'"{r}" {a(lang)} job')
        for loc in profile["locations"]:
            pool.add(f'"{r}" new grad {loc}')
    for tech in profile["technologies"]:
        pool.add(f'software engineer {tech} entry level job')
    if year:
        for r in roles:
            pool.add(f'"{r}" new grad {year}')

    pool = sorted(pool)
    random.Random(seed).shuffle(pool)
    return pool[:max_queries]


# Hosts/paths that essentially never contain a single job posting.
SKIP_HOSTS = (
    "youtube.com", "reddit.com", "medium.com", "wikipedia.org", "quora.com",
    "twitter.com", "x.com", "facebook.com", "instagram.com", "github.com",
    "stackoverflow.com", "dev.to", "substack.com", "levels.fyi", "glassdoor.com",
    "ambitionbox.com", "tiktok.com",
    "linkedin.com",  # Firecrawl does not support scraping LinkedIn
)
SKIP_PATH = re.compile(
    r"/(blog|blogs|news|article|articles|docs|documentation|press|events|podcast|"
    r"salary|salaries|interview|interviews|in|people|profile|about|guide|guides)(/|$)",
    re.I,
)


def looks_like_job_url(url: str) -> bool:
    host = re.sub(r"^www\.", "", url.split("/")[2].lower()) if "://" in url else ""
    if any(host == h or host.endswith("." + h) for h in SKIP_HOSTS):
        return False
    path = url.split(host, 1)[-1]
    return not SKIP_PATH.search(path)


def search_all(fc, queries: list[str], limit: int, tbs: str | None) -> tuple[int, dict[str, dict]]:
    """Run every query; return (raw result count, unique candidate results keyed by canonical URL)."""
    results: dict[str, dict] = {}
    total = 0
    for i, q in enumerate(queries, 1):
        try:
            data = with_retry(fc.search, q, limit=limit, tbs=tbs)
        except Exception as e:
            print(f"  [{i}/{len(queries)}] search failed: {q!r}: {e}")
            continue
        web = data.web or []
        total += len(web)
        print(f"  [{i}/{len(queries)}] {len(web):3d} results  {q}")
        for r in web:
            url = getattr(r, "url", None)
            if not url or not looks_like_job_url(url):
                continue
            results.setdefault(canonicalize(url), {
                "url": url, "title": getattr(r, "title", "") or "",
            })
    return total, results


JOB_SCHEMA = {
    "type": "object",
    "properties": {
        "is_single_job_posting": {
            "type": "boolean",
            "description": "True only if this page is ONE specific, currently open job posting. "
                           "False for job listing/search pages, articles, blogs, company pages, closed postings.",
        },
        "title": {"type": "string"},
        "company": {"type": "string"},
        "location": {"type": "string", "description": "Location as written on the posting."},
        "countries": {"type": "array", "items": {"type": "string"},
                      "description": "Countries the job can be done from, full English names."},
        "is_remote": {"type": "boolean"},
        "posted_date": {"type": "string", "description": "YYYY-MM-DD if available, else empty."},
        "description": {"type": "string", "description": "2-4 sentence summary of the role."},
        "requirements": {"type": "array", "items": {"type": "string"}},
        "experience_requirements": {"type": "string",
                                    "description": "Required experience/seniority, e.g. 'new grad', '0-2 years', '5+ years'."},
    },
    "required": ["is_single_job_posting", "title"],
}


def scrape_job(fc, url: str) -> dict | None:
    """Scrape one page. Returns extracted fields + page text, or None on failure."""
    try:
        doc = with_retry(
            fc.scrape,
            url,
            formats=["markdown", {"type": "json", "schema": JOB_SCHEMA}],
            only_main_content=True,
            timeout=60000,
        )
    except Exception as e:
        print(f"    scrape failed: {url}: {str(e)[:120]}")
        return None
    data = doc.json or {}
    if not isinstance(data, dict):
        return None
    final_url = getattr(doc.metadata, "url", None) or getattr(doc.metadata, "source_url", None) or url
    data["final_url"] = final_url
    data["markdown"] = (doc.markdown or "")[:20000]
    return data


def scrape_many(fc, urls: list[str], workers: int = 3) -> list[tuple[str, dict | None]]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(zip(urls, pool.map(lambda u: scrape_job(fc, u), urls)))
