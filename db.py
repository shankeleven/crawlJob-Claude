"""SQLite persistence. canonical_url is the dedup key."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL UNIQUE,
    title TEXT,
    company TEXT,
    location TEXT,
    posted_date TEXT,
    description TEXT,
    requirements TEXT,
    experience TEXT,
    source TEXT,
    score INTEGER,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
-- Pages that turned out not to be job postings, so we don't pay to scrape them again.
CREATE TABLE IF NOT EXISTS non_jobs (
    canonical_url TEXT PRIMARY KEY,
    first_seen TEXT NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def is_known_job(conn, canonical_url: str) -> bool:
    return conn.execute("SELECT 1 FROM jobs WHERE canonical_url = ?", (canonical_url,)).fetchone() is not None


def is_non_job(conn, canonical_url: str) -> bool:
    return conn.execute("SELECT 1 FROM non_jobs WHERE canonical_url = ?", (canonical_url,)).fetchone() is not None


def touch(conn, canonical_url: str, now: str) -> None:
    conn.execute("UPDATE jobs SET last_seen = ? WHERE canonical_url = ?", (now, canonical_url))


def add_non_job(conn, canonical_url: str, now: str) -> None:
    conn.execute("INSERT OR IGNORE INTO non_jobs VALUES (?, ?)", (canonical_url, now))


def insert_job(conn, job: dict, now: str) -> bool:
    """Insert a new job. Returns False if canonical_url already existed (then only last_seen is bumped)."""
    cur = conn.execute(
        """INSERT OR IGNORE INTO jobs (url, canonical_url, title, company, location, posted_date,
               description, requirements, experience, source, score, first_seen, last_seen)
           VALUES (:url, :canonical_url, :title, :company, :location, :posted_date,
               :description, :requirements, :experience, :source, :score, :now, :now)""",
        {**job, "now": now},
    )
    if cur.rowcount == 0:
        touch(conn, job["canonical_url"], now)
        return False
    return True
