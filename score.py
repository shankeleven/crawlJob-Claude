"""Simple 0-100 keyword relevance score. Only used for sorting."""
import re

EUROPE = {
    "europe", "eu", "emea", "united kingdom", "uk", "england", "scotland", "ireland",
    "germany", "france", "netherlands", "belgium", "luxembourg", "switzerland", "austria",
    "spain", "portugal", "italy", "poland", "czech republic", "czechia", "slovakia",
    "hungary", "romania", "bulgaria", "greece", "croatia", "slovenia", "serbia",
    "sweden", "norway", "denmark", "finland", "iceland", "estonia", "latvia", "lithuania",
    "ukraine", "cyprus", "malta",
}
LOCATION_ALIASES = {
    "united states": {"united states", "usa", "us", "united states of america", "u.s."},
    "india": {"india"},
}

# Title words that make a "Software Engineer" posting clearly off-profile.
OFF_ROLE = re.compile(
    r"\b(front[- ]?end|ios|android|mobile|ui|ux|designer|web developer|sales|marketing|"
    r"recruit\w*|data scientist|data analyst|product manager|qa|test engineer|tester|support|"
    r"solutions? engineer|salesforce|sap|mechanical|electrical|civil|hardware|intern(ship)?)\b",
    re.I,
)
SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|manager|director|head|architect|iii|iv)\b", re.I)
SENIOR_YEARS = re.compile(r"\b([3-9]|1\d)\s*\+?\s*(years|yrs)", re.I)
JUNIOR_HINTS = [
    "new grad", "new graduate", "graduate", "entry level", "entry-level", "junior",
    "early career", "university", "0-2 years", "0-1 years", "1-2 years", "recent grad",
]


def _has(term: str, text: str) -> bool:
    if term == "Go":  # avoid matching the English word "go"
        return bool(re.search(r"\bGo\b(?!\s+(to|back|ahead|home|further|through|live|for|on|in|with)\b)", text)) \
            or "golang" in text.lower()
    return re.search(r"(?<!\w)" + re.escape(term.lower()) + r"(?!\w)", text.lower()) is not None


def _role_keyword(role: str) -> str:
    # "Distributed Systems Engineer" -> "distributed systems"; "Software Engineer" -> "software"
    return re.sub(r"\s*engineer\s*$", "", role, flags=re.I).lower()


def score_job(job: dict, profile: dict) -> int:
    title = job.get("title") or ""
    exp_text = job.get("experience_requirements") or ""
    body = " ".join([
        title, job.get("description") or "", " ".join(job.get("requirements") or []),
        exp_text, job.get("markdown") or "",
    ])
    score = 0

    # Role (30): title match counts most; description mention counts a little.
    roles = [_role_keyword(r) for r in profile["roles"]]
    if re.search(r"engineer|developer", title, re.I) and any(_has(r, title) for r in roles):
        score += 30
    elif any(_has(r, title) for r in roles) or any(_has(r + " engineer", body) for r in roles):
        score += 15
    if OFF_ROLE.search(title):
        score -= 30

    # Experience (25)
    junior_text = (title + " " + exp_text).lower()
    year = str(profile.get("graduation_year") or "")
    if any(h in junior_text for h in JUNIOR_HINTS + [e.lower() for e in profile["experience"]]) \
            or (year and year in title):
        score += 25
    elif SENIOR.search(title) or SENIOR_YEARS.search(exp_text):
        score -= 35
    elif any(h in body.lower() for h in JUNIOR_HINTS):
        score += 15
    else:
        score += 8  # unspecified seniority

    # Languages (15) and technologies (15)
    score += min(15, 8 * sum(_has(l, body) for l in profile["languages"]))
    score += min(15, 4 * sum(_has(t, body) for t in profile["technologies"]))

    # Location (15)
    if location_matches(job, profile):
        score += 15

    return max(0, min(100, score))


def location_matches(job: dict, profile: dict) -> list[str]:
    loc = (job.get("location") or "").lower()
    countries = {c.lower().strip() for c in job.get("countries") or []}
    hits = []
    for want in profile["locations"]:
        w = want.lower()
        if w == "remote":
            ok = bool(job.get("is_remote")) or "remote" in loc
        elif w == "europe":
            ok = bool(countries & EUROPE) or any(_has(e, loc) for e in EUROPE)
        else:
            aliases = LOCATION_ALIASES.get(w, {w})
            ok = bool(countries & aliases) or any(_has(a, loc) for a in aliases)
        if ok:
            hits.append(want)
    return hits


def tags(job: dict, profile: dict) -> list[str]:
    """Matched profile keywords, for the terminal summary."""
    body = " ".join([job.get("title") or "", job.get("description") or "",
                     " ".join(job.get("requirements") or []), job.get("markdown") or ""])
    found = [l for l in profile["languages"] if _has(l, body)]
    found += [t for t in profile["technologies"] if _has(t, body)][:3]
    return found + location_matches(job, profile)
