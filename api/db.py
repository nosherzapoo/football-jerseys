"""Postgres (Supabase) connection layer for serverless.

We keep a single connection at module level. On warm invocations the same
connection is reused; on cold starts a fresh one is created. Supabase's
transaction pooler (port 6543) sits in front, so this stays cheap even with
many parallel functions.
"""
import os
import threading

import psycopg

DATABASE_URL = os.environ.get("DATABASE_URL")

_conn: psycopg.Connection | None = None
_lock = threading.Lock()


def _make_conn() -> psycopg.Connection:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(
        DATABASE_URL,
        autocommit=False,
        # Short statement timeout to keep stuck queries from blocking the
        # serverless function for its full timeout window.
        options="-c statement_timeout=8000",
    )


def conn() -> psycopg.Connection:
    """Return a healthy connection, reconnecting on failure."""
    global _conn
    with _lock:
        if _conn is None or _conn.closed:
            _conn = _make_conn()
            return _conn
        try:
            with _conn.cursor() as cur:
                cur.execute("SELECT 1")
            return _conn
        except Exception:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = _make_conn()
            return _conn


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jerseys (
    id          BIGSERIAL PRIMARY KEY,
    country     TEXT NOT NULL,
    kit_type    TEXT NOT NULL,
    image_path  TEXT NOT NULL,
    rating      DOUBLE PRECISION NOT NULL DEFAULT 1500.0,
    rd          DOUBLE PRECISION NOT NULL DEFAULT 350.0,
    vol         DOUBLE PRECISION NOT NULL DEFAULT 0.06,
    matches     INTEGER NOT NULL DEFAULT 0,
    wins        INTEGER NOT NULL DEFAULT 0,
    UNIQUE (country, kit_type)
);

CREATE TABLE IF NOT EXISTS votes (
    id          BIGSERIAL PRIMARY KEY,
    winner_id   BIGINT NOT NULL REFERENCES jerseys(id),
    loser_id    BIGINT NOT NULL REFERENCES jerseys(id),
    session_id  TEXT NOT NULL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_votes_session_ts ON votes(session_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_votes_pair ON votes(winner_id, loser_id);

CREATE TABLE IF NOT EXISTS pair_tokens (
    token       TEXT PRIMARY KEY,
    jersey_a    BIGINT NOT NULL,
    jersey_b    BIGINT NOT NULL,
    session_id  TEXT NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pair_tokens_expires ON pair_tokens(expires_at);
"""


def init_schema(c: psycopg.Connection) -> None:
    with c.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    c.commit()
