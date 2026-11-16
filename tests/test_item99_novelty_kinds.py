"""Item 99: family-level novelty bias on the desk order + widened OEIS pool terms."""
from __future__ import annotations

import math
from fractions import Fraction

import colony.hard_tier_families as H
from colony import novelty_kind_bias as B


def _row(m, kind="hard_enable", novel=False):
    return {"mutation": m, "kind": kind, "novel_to_commons": novel}


def test_family_keys():
    assert B.family("stem_rc_discharge") == "stem"
    assert B.family("oeis_a000032_lucas_norm") == "oeis"
    assert B.family("authored_frontier_le_x1_w1") == "authored_frontier"
    assert B.family("authored_sieve_hl_g4") == "authored_sieve"
    assert B.family("zeckendorf_unique") == "catalog"


def test_repeating_family_down_untried_neutral_plus_bonus():
    rows = [_row("stem_a", "stem_enable")] * 6 + [_row(f"oeis_{i}", novel=True) for i in range(6)]
    f = B.factors(["stem_b", "oeis_new", "authored_frontier_x"], rows)
    assert f["stem_b"] == B.MIN_F
    assert f["oeis_new"] > 1.5
    assert f["authored_frontier_x"] == 1.0 + B.UNDER_TRIED_BONUS
    assert all(B.MIN_F <= v <= B.MAX_F for v in f.values())


def test_non_desk_rows_ignored():
    rows = [_row("theme", "claim_theme")] * 50
    assert B.family_stats(rows) == {}


def test_off_on_control_and_kill_switch(monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    assert B.enabled() is False
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.setenv("COLONY_NOVELTY_KIND_BIAS", "off")
    assert B.enabled() is False


def test_order_only_nothing_removed(monkeypatch):
    from colony import exploration_budget as E
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.setenv("COLONY_NOVELTY_KIND_BIAS", "live")
    cands = [("stem_x", "stem_enable", "enable:stem_x"), ("oeis_y", "hard_enable", "enable:oeis_y")]
    monkeypatch.setattr(E, "ensure_distribution", lambda names: {n: 1.0 for n in names})
    monkeypatch.setattr(B, "factors", lambda names, rows=None: {"stem_x": 0.25, "oeis_y": 1.8})
    out = E.pick_mutation_order(list(cands))
    assert sorted(out) == sorted(cands)
    assert [n for n, _k, _s in out if n in ("stem_x", "oeis_y")] == ["oeis_y", "stem_x"]


def _zigzag(n_terms):
    """sec x + tan x Taylor coefficients times n!, by exact series division (independent route)."""
    N = n_terms
    cos = [Fraction((-1) ** (k // 2), math.factorial(k)) if k % 2 == 0 else Fraction(0) for k in range(N)]
    num = [Fraction((-1) ** (k // 2), math.factorial(k)) if k % 2 == 1 else Fraction(0) for k in range(N)]
    num[0] = Fraction(1)
    q = [Fraction(0)] * N
    for k in range(N):  # q = (1 + sin) / cos
        q[k] = (num[k] - sum(q[j] * cos[k - j] for j in range(k))) / cos[0]
    return [int(q[k] * math.factorial(k)) for k in range(N)]


def test_widened_pool_matches_oeis_terms():
    t = H.OEIS_TERMS
    assert [sum(math.comb(n, 2 * k) * math.comb(2 * k, k) for k in range(n // 2 + 1)) for n in range(10)] == t["A002426"]
    assert _zigzag(10) == t["A000111"]
    assert [1] + [sum(math.comb(n - 1, k - 1) * math.factorial(n) // math.factorial(k) for k in range(1, n + 1))
                  for n in range(1, 8)] == t["A000262"]
    assert [math.comb(3 * n, n) // (2 * n + 1) for n in range(8)] == t["A001764"]
    fine = [1]
    for n in range(1, 10):
        fine.append((math.comb(2 * n, n) // (n + 1) - fine[-1]) // 2)
    assert fine == t["A000957"]

    def narayana(n, k):
        return math.comb(n, k) * math.comb(n, k - 1) // n
    assert [1] + [sum(narayana(n, k) * 2 ** (k - 1) for k in range(1, n + 1)) for n in range(1, 9)] == t["A001003"]
    assert [sum(math.comb(n, k) ** 2 * math.comb(n + k, k) ** 2 for k in range(n + 1)) for n in range(6)] == t["A005259"]
    assert [sum(math.comb(n, k) ** 3 for k in range(n + 1)) for n in range(7)] == t["A000172"]
    assert [sum(math.comb(n, k) ** 2 * math.comb(2 * k, k) for k in range(n + 1)) for n in range(7)] == t["A002893"]


def test_pool_widened():
    assert len(H.POOL) >= 16
    for name, _w, fn_src in H.POOL:
        assert f"def check_{name}(" in fn_src
