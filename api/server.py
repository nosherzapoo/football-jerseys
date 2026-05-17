"""FastAPI app, Vercel-friendly (Postgres + no in-memory state)."""
import random
import secrets
import time
import uuid

from fastapi import Cookie, FastAPI, HTTPException, Response
from pydantic import BaseModel

from . import db, glicko2

# --- Anti-spam limits ---
MIN_VOTE_INTERVAL_SEC = 0.4
MAX_VOTES_PER_DAY = 300
PAIR_TOKEN_TTL_SEC = 600

app = FastAPI(title="World Cup 2026 Jersey Ranker")


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
def _get_or_set_session(sid: str | None, response: Response) -> str:
    if sid:
        return sid
    new_sid = uuid.uuid4().hex
    response.set_cookie(
        "sid",
        new_sid,
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return new_sid


def _rate_limit_check(c, sid: str) -> None:
    with c.cursor() as cur:
        cur.execute(
            "SELECT EXTRACT(EPOCH FROM (NOW() - MAX(ts))) AS dt, "
            "       COUNT(*) FILTER (WHERE ts > NOW() - INTERVAL '1 day') AS day_count "
            "FROM votes WHERE session_id = %s",
            (sid,),
        )
        dt, day_count = cur.fetchone()
    if dt is not None and dt < MIN_VOTE_INTERVAL_SEC:
        raise HTTPException(429, "Slow down — wait a moment between votes.")
    if day_count and day_count >= MAX_VOTES_PER_DAY:
        raise HTTPException(429, "Daily vote limit reached. Come back tomorrow.")


# ---------------------------------------------------------------------------
# Pair selection
# ---------------------------------------------------------------------------
def _pick_pair(c, sid: str) -> tuple[dict, dict]:
    with c.cursor() as cur:
        cur.execute(
            "SELECT id, country, kit_type, image_path, image_alt, rating, rd, matches "
            "FROM jerseys"
        )
        cols = [d.name for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

        # Pairs this session has already voted on (avoid repeats)
        cur.execute(
            "SELECT winner_id, loser_id FROM votes "
            "WHERE session_id = %s ORDER BY ts DESC LIMIT 60",
            (sid,),
        )
        recent_set = {tuple(sorted(r)) for r in cur.fetchall()}

    if len(rows) < 2:
        raise HTTPException(500, "Not enough jerseys seeded.")

    def pair_key(a, b):
        return tuple(sorted((a["id"], b["id"])))

    cold = [r for r in rows if r["matches"] < 5]
    if cold and random.random() < 0.5:
        a = random.choice(cold)
        others = [r for r in rows if r["id"] != a["id"]]
        sample = random.sample(others, min(20, len(others)))
        sample.sort(
            key=lambda j: (
                pair_key(a, j) in recent_set,
                abs(j["rating"] - a["rating"]) - (60 if j["matches"] < 5 else 0),
            )
        )
        return a, sample[0]

    best = None
    best_score = -1.0
    for _ in range(40):
        a, b = random.sample(rows, 2)
        rating_gap = max(abs(a["rating"] - b["rating"]), 40.0)
        score = (a["rd"] + b["rd"]) / rating_gap
        if pair_key(a, b) in recent_set:
            score *= 0.1
        if score > best_score:
            best_score = score
            best = (a, b)
    return best


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.get("/api/pair")
def api_pair(response: Response, sid: str | None = Cookie(default=None)):
    sid = _get_or_set_session(sid, response)
    c = db.conn()

    a, b = _pick_pair(c, sid)
    if random.random() < 0.5:
        a, b = b, a

    token = secrets.token_urlsafe(16)
    with c.cursor() as cur:
        # Opportunistic cleanup: drop expired tokens on ~2% of issuances.
        if random.random() < 0.02:
            cur.execute("DELETE FROM pair_tokens WHERE expires_at < NOW()")
        cur.execute(
            "INSERT INTO pair_tokens (token, jersey_a, jersey_b, session_id, expires_at) "
            "VALUES (%s, %s, %s, %s, NOW() + make_interval(secs => %s))",
            (token, a["id"], b["id"], sid, PAIR_TOKEN_TTL_SEC),
        )
    c.commit()

    def shape(j):
        # Show a random half each time, so users see both crops over multiple
        # matchups instead of only the tagged "better" one.
        options = [j["image_path"]]
        if j.get("image_alt"):
            options.append(j["image_alt"])
        chosen = random.choice(options)
        return {
            "id": j["id"],
            "country": j["country"],
            "kit_type": j["kit_type"],
            "image": "/" + chosen.lstrip("/"),
        }

    return {"token": token, "left": shape(a), "right": shape(b)}


class VoteIn(BaseModel):
    token: str
    winner: str  # 'left' or 'right'


@app.post("/api/vote")
def api_vote(payload: VoteIn, response: Response, sid: str | None = Cookie(default=None)):
    sid = _get_or_set_session(sid, response)
    if payload.winner not in ("left", "right"):
        raise HTTPException(400, "Invalid winner.")

    c = db.conn()
    try:
        with c.cursor() as cur:
            # Atomic consume: this both validates and prevents replay.
            cur.execute(
                "DELETE FROM pair_tokens "
                "WHERE token = %s AND session_id = %s AND expires_at > NOW() "
                "RETURNING jersey_a, jersey_b",
                (payload.token, sid),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(400, "Pair expired or already voted. Refresh for a new one.")
            a_id, b_id = row

            _rate_limit_check(c, sid)

            winner_id, loser_id = (a_id, b_id) if payload.winner == "left" else (b_id, a_id)

            # Row-level lock so concurrent votes on the same kit serialise correctly.
            cur.execute(
                "SELECT id, rating, rd, vol FROM jerseys "
                "WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
                ([winner_id, loser_id],),
            )
            kits = {r[0]: r for r in cur.fetchall()}
            w = kits[winner_id]
            l = kits[loser_id]

            w_r, w_rd, w_v = w[1], w[2], w[3]
            l_r, l_rd, l_v = l[1], l[2], l[3]

            new_w = glicko2.update(w_r, w_rd, w_v, l_r, l_rd, 1.0)
            new_l = glicko2.update(l_r, l_rd, l_v, w_r, w_rd, 0.0)

            cur.execute(
                "UPDATE jerseys SET rating=%s, rd=%s, vol=%s, matches=matches+1, wins=wins+1 "
                "WHERE id=%s",
                (new_w[0], new_w[1], new_w[2], winner_id),
            )
            cur.execute(
                "UPDATE jerseys SET rating=%s, rd=%s, vol=%s, matches=matches+1 "
                "WHERE id=%s",
                (new_l[0], new_l[1], new_l[2], loser_id),
            )
            cur.execute(
                "INSERT INTO votes (winner_id, loser_id, session_id) VALUES (%s, %s, %s)",
                (winner_id, loser_id, sid),
            )
        c.commit()
    except HTTPException:
        c.rollback()
        raise
    except Exception:
        c.rollback()
        raise

    return {"ok": True}


@app.get("/api/leaderboard")
def api_leaderboard(sort: str = "wilson"):
    c = db.conn()
    with c.cursor() as cur:
        cur.execute(
            "SELECT id, country, kit_type, image_path, rating, rd, matches, wins FROM jerseys"
        )
        cols = [d.name for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    for r in rows:
        r["score"] = r["rating"] - 2.0 * r["rd"]
        r["win_pct"] = (r["wins"] / r["matches"]) if r["matches"] else 0.0
        r["image"] = "/" + r["image_path"].lstrip("/")

    key = "score" if sort == "wilson" else "rating"
    rows.sort(key=lambda r: r[key], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return {"jerseys": rows}


@app.get("/api/stats")
def api_stats():
    c = db.conn()
    with c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM votes")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM jerseys")
        n = cur.fetchone()[0]
    return {"total_votes": total, "jerseys": n}
