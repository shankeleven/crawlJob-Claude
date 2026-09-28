"""Decide whether a posting is current: posted this year, or older but still open."""
import re
import warnings
from datetime import date, timedelta

import pandas as pd

CLOSED = re.compile(
    r"no longer (accepting|available|open)|(job|position|posting|role|vacancy) (has|is) "
    r"(been )?(closed|filled|expired)|this job (has )?expired|applications? (are |is )?(now )?closed",
    re.I,
)
RELATIVE = re.compile(r"(\d+)\+?\s*(hour|day|week|month|year)s?\s+ago", re.I)
UNIT_DAYS = {"hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}


def parse_posted_date(text: str, today: date) -> date | None:
    """Turn the date as written on the page ('3 days ago', 'Sep 20, 2026') into a date."""
    t = (text or "").strip().lower()
    if not t:
        return None
    if "today" in t or "just posted" in t or "hour" in t and "ago" in t:
        return today
    if "yesterday" in t:
        return today - timedelta(days=1)
    m = RELATIVE.search(t)
    if m:
        return today - timedelta(days=int(m.group(1)) * UNIT_DAYS[m.group(2).lower()])
    t = re.sub(r"^(posted|published|date posted|posted on)[:\s]*", "", t)
    with warnings.catch_warnings():  # pandas warns when it can't infer a format
        warnings.simplefilter("ignore")
        d = pd.to_datetime(t, errors="coerce")
    return None if pd.isna(d) or d.date() > today else d.date()


def is_current(data: dict, posted: date | None, today: date) -> bool:
    """Keep jobs posted this year; keep older or undated jobs only if the page shows they're still open."""
    if CLOSED.search(data.get("markdown") or ""):
        return False
    if posted and posted.year >= today.year:
        return True
    return data.get("is_accepting_applications") is True
