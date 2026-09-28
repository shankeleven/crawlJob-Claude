"""URL normalization so the same job with different tracking params dedupes."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query params that only track where a click came from. Anything else is kept,
# because many job sites identify the posting via a query param (e.g. gh_jid, jobId).
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "ref", "refid", "referrer", "source", "src", "gclid", "fbclid", "msclkid",
    "trk", "trackingid", "lipi", "gh_src", "lever-source", "lever-origin",
    "_hsenc", "_hsmi", "mc_cid", "mc_eid", "hl",
}


def canonicalize(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    query.sort()
    return urlunsplit(("https", host, path, urlencode(query), ""))


ATS_SOURCES = {
    "greenhouse.io": "Greenhouse",
    "lever.co": "Lever",
    "ashbyhq.com": "Ashby",
    "myworkdayjobs.com": "Workday",
    "workday.com": "Workday",
    "smartrecruiters.com": "SmartRecruiters",
    "workable.com": "Workable",
    "bamboohr.com": "BambooHR",
    "icims.com": "iCIMS",
    "jobvite.com": "Jobvite",
    "recruitee.com": "Recruitee",
    "teamtailor.com": "Teamtailor",
    "breezy.hr": "Breezy",
    "linkedin.com": "LinkedIn",
    "indeed.com": "Indeed",
    "wellfound.com": "Wellfound",
    "ycombinator.com": "Y Combinator",
}


def source_of(url: str) -> str:
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    for domain, name in ATS_SOURCES.items():
        if host == domain or host.endswith("." + domain):
            return name
    return host
