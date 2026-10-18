"""Stage 3: surprise credit in the hunt / selection layer only."""
from colony import surprise_credit as SC
from colony import retire


def _r(**kw):
    r = {"kind": "cong", "unknown": True, "prediction": 0.3, "hunt_value": 1.0, "range": [13, 20000],
         "retested_to": 60000, "retests": 2, "reference": "no reference found (checked: catalog)"}
    r.update(kw)
    return r


def test_credit_factors():
    base = SC.credit(_r(), trivial=False)
    assert 0 < base["credit"] <= 1 and base["unlikely"] == 0.7
    assert SC.credit(_r(prediction=0.9), trivial=False)["credit"] < base["credit"]      # expected -> less
    assert SC.credit(_r(range=[13, 200], retested_to=None, retests=0), trivial=False)["credit"] < base["credit"]
    assert SC.credit(_r(retests=6), trivial=False)["credit"] > base["credit"]          # more re-tests survived


def test_explained_earns_zero():
    assert SC.credit(_r(), trivial=True)["credit"] == 0.0
    assert SC.credit(_r(reference="explained by A000010 (comment)"), trivial=False)["credit"] == 0.0
    assert SC.credit(_r(unknown=False, unknown_reason="known: x"), trivial=False)["credit"] == 0.0
    assert SC.credit(_r(falsified_later=True), trivial=False)["credit"] == 0.0


def test_value_passthrough_for_non_frontier(monkeypatch):
    assert SC.value("authored_sieve_hl_within_g2_w1", 0.004) == 0.004
    monkeypatch.setenv("COLONY_SURPRISE", "bogus")
    assert SC.mode() == "shadow"


def test_sieve_sweep_blocked():
    rows = [{"mutation": f"authored_sieve_hl_within_g{i}_w1", "passed": True} for i in (2, 4, 6)]
    assert retire.sieve_sweep_blocked("authored_sieve_hl_within_g8_w1", rows, k_prior=0.1)
    assert not retire.sieve_sweep_blocked("authored_sieve_hl_within_g8_w1", rows[:2], k_prior=0.1)
    assert not retire.sieve_sweep_blocked("authored_sieve_new_family_g2_w1", rows, k_prior=0.1)
    assert not retire.sieve_sweep_blocked("authored_frontier_cong_x1_w1", rows, k_prior=0.1)
