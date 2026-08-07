"""
SQLite storage: film-funding opportunities, users, sessions, magic-link tokens,
and a per-user record of what has already been emailed (so digests don't repeat).
"""

import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint   TEXT UNIQUE NOT NULL,
    url           TEXT NOT NULL,
    title         TEXT NOT NULL,
    summary       TEXT,
    org           TEXT,                 -- funding body, if known
    source        TEXT NOT NULL,
    country       TEXT,                 -- region key (india, usa, uk, ...)
    published     TEXT,
    deadline      TEXT,                 -- YYYY-MM-DD when known
    discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
    score         INTEGER DEFAULT 0,
    est_value_inr INTEGER DEFAULT 0,
    fit_note      TEXT,                 -- one-line LLM/keyword reason
    kind          TEXT                  -- grant | fund | fellowship | open_call
);
CREATE INDEX IF NOT EXISTS idx_opp_deadline ON opportunities(deadline);
CREATE INDEX IF NOT EXISTS idx_opp_disc ON opportunities(discovered_at DESC);
CREATE INDEX IF NOT EXISTS idx_opp_score ON opportunities(score DESC);

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT UNIQUE NOT NULL,
    name        TEXT,
    regions     TEXT,                   -- optional CSV region filter; empty = all
    digest_on   INTEGER DEFAULT 1,      -- receive daily digest
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    last_login  TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    email      TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_tokens (
    token      TEXT PRIMARY KEY,
    email      TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL,
    used       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sent_digest (
    email   TEXT NOT NULL,
    opp_id  INTEGER NOT NULL,
    sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (email, opp_id)
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db(path: str) -> sqlite3.Connection:
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


# ---------------------------------------------------------------- opportunities
def opp_exists(conn, fingerprint: str) -> bool:
    return conn.execute("SELECT 1 FROM opportunities WHERE fingerprint=?",
                        (fingerprint,)).fetchone() is not None


def insert_opp(conn, o: dict) -> int:
    cur = conn.execute(
        """INSERT OR IGNORE INTO opportunities
           (fingerprint,url,title,summary,org,source,country,published,deadline,
            score,est_value_inr,fit_note,kind)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (o["fingerprint"], o["url"], o["title"], o.get("summary", ""), o.get("org", ""),
         o["source"], o.get("country", ""), o.get("published", ""), o.get("deadline", ""),
         o.get("score", 0), o.get("est_value_inr", 0), o.get("fit_note", ""),
         o.get("kind", "grant")))
    conn.commit()
    return cur.lastrowid


def set_deadline(conn, opp_id: int, deadline: str):
    conn.execute("UPDATE opportunities SET deadline=COALESCE(NULLIF(deadline,''),?) WHERE id=?",
                 (deadline, opp_id))
    conn.commit()


# Deadline bucket SQL fragments. Default view hides closed calls.
HAS_DL = "COALESCE(deadline,'')!=''"
DLD = "substr(deadline,1,10)"
DL_BUCKETS = {
    "": f"NOT ({HAS_DL} AND {DLD} < date('now'))",          # live: hide closed
    "open": f"{HAS_DL} AND {DLD} >= date('now')",
    "d7": f"{HAS_DL} AND {DLD} BETWEEN date('now') AND date('now','+7 day')",
    "d30": f"{HAS_DL} AND {DLD} BETWEEN date('now') AND date('now','+30 day')",
    "undated": "COALESCE(deadline,'')=''",
    "closed": f"{HAS_DL} AND {DLD} < date('now')",
    "all": "1=1",
}


def feed(conn, dl: str = "", region: str = "", limit: int = 200) -> list:
    where = [DL_BUCKETS.get(dl, DL_BUCKETS[""])]
    params = []
    if region:
        where.append("country=?")
        params.append(region)
    order = ("substr(deadline,1,10) ASC, score DESC" if dl in ("open", "d7", "d30")
             else "(CASE WHEN COALESCE(deadline,'')!='' AND substr(deadline,1,10)>=date('now') "
                  "THEN 0 ELSE 1 END), score DESC, discovered_at DESC")
    params.append(limit)
    return conn.execute(
        f"SELECT * FROM opportunities WHERE {' AND '.join(where)} "
        f"ORDER BY {order} LIMIT ?", params).fetchall()


def bucket_counts(conn) -> dict:
    return {k: conn.execute(f"SELECT COUNT(*) FROM opportunities WHERE {expr}").fetchone()[0]
            for k, expr in DL_BUCKETS.items()}


def get_opp(conn, opp_id: int):
    return conn.execute("SELECT * FROM opportunities WHERE id=?", (opp_id,)).fetchone()


# ---------------------------------------------------------------- users
def upsert_user(conn, email: str, name: str = "") -> int:
    email = email.strip().lower()
    conn.execute(
        "INSERT INTO users (email,name) VALUES (?,?) ON CONFLICT(email) DO NOTHING",
        (email, name))
    conn.commit()
    return conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]


def get_user(conn, email: str):
    return conn.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()


def all_users(conn, digest_only: bool = False) -> list:
    q = "SELECT * FROM users"
    if digest_only:
        q += " WHERE digest_on=1"
    return conn.execute(q).fetchall()


def touch_login(conn, email: str):
    conn.execute("UPDATE users SET last_login=? WHERE email=?", (now(), email.strip().lower()))
    conn.commit()


def set_prefs(conn, email: str, regions: str = None, digest_on: int = None):
    if regions is not None:
        conn.execute("UPDATE users SET regions=? WHERE email=?", (regions, email.strip().lower()))
    if digest_on is not None:
        conn.execute("UPDATE users SET digest_on=? WHERE email=?", (digest_on, email.strip().lower()))
    conn.commit()


# ---------------------------------------------------------------- digest bookkeeping
def unsent_for(conn, email: str, dl_bucket: str = "open", limit: int = 15) -> list:
    expr = DL_BUCKETS.get(dl_bucket, DL_BUCKETS["open"])
    return conn.execute(
        f"""SELECT * FROM opportunities o
            WHERE {expr}
              AND NOT EXISTS (SELECT 1 FROM sent_digest s
                              WHERE s.email=? AND s.opp_id=o.id)
            ORDER BY (CASE WHEN COALESCE(deadline,'')!='' THEN substr(deadline,1,10)
                           ELSE '9999' END) ASC, score DESC
            LIMIT ?""", (email.strip().lower(), limit)).fetchall()


def mark_sent(conn, email: str, opp_ids: list):
    email = email.strip().lower()
    conn.executemany("INSERT OR IGNORE INTO sent_digest (email,opp_id) VALUES (?,?)",
                     [(email, i) for i in opp_ids])
    conn.commit()
