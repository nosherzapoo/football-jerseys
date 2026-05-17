"""Glicko-2 rating system.

Reference: http://www.glicko.net/glicko/glicko2.pdf

We apply updates per-match (single-game rating period). This is a common
simplification for live/online settings — slightly noisier than batched periods
but lets the leaderboard react immediately to each vote.
"""
import math

TAU = 0.5
EPSILON = 1e-6
SCALE = 173.7178

DEFAULT_RATING = 1500.0
DEFAULT_RD = 350.0
DEFAULT_VOL = 0.06


def _g(phi):
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _E(mu, mu_j, phi_j):
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def update(rating, rd, vol, opp_rating, opp_rd, score):
    """Update one player's rating after a single match.

    score: 1.0 = win, 0.5 = draw, 0.0 = loss.
    Returns (new_rating, new_rd, new_vol).
    """
    mu = (rating - 1500.0) / SCALE
    phi = rd / SCALE
    opp_mu = (opp_rating - 1500.0) / SCALE
    opp_phi = opp_rd / SCALE

    g_j = _g(opp_phi)
    E_j = _E(mu, opp_mu, opp_phi)

    v = 1.0 / (g_j * g_j * E_j * (1.0 - E_j))
    delta = v * g_j * (score - E_j)

    a = math.log(vol * vol)

    def f(x):
        ex = math.exp(x)
        num = ex * (delta * delta - phi * phi - v - ex)
        den = 2.0 * (phi * phi + v + ex) ** 2
        return num / den - (x - a) / (TAU * TAU)

    A = a
    if delta * delta > phi * phi + v:
        B = math.log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a - k * TAU) < 0:
            k += 1
        B = a - k * TAU

    fa, fb = f(A), f(B)
    while abs(B - A) > EPSILON:
        C = A + (A - B) * fa / (fb - fa)
        fc = f(C)
        if fc * fb <= 0:
            A, fa = B, fb
        else:
            fa = fa / 2.0
        B, fb = C, fc

    new_vol = math.exp(A / 2.0)

    phi_star = math.sqrt(phi * phi + new_vol * new_vol)
    new_phi = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    new_mu = mu + new_phi * new_phi * g_j * (score - E_j)

    return new_mu * SCALE + 1500.0, new_phi * SCALE, new_vol
