"""Idle fix: frontier queue stays fed (in-flight cap, open-surprise re-tests), sieve sweeps last."""
import json

from colony import frontier_checks as F


def _r(**kw):
    r = {"kind": "cong", "lhs": "sigma[digsum]", "rhs": "", "params": {"m": 3, "r": 0, "q": 3, "s": 2},
         "sig": "abcdef1234", "unknown": True, "prediction": 0.3, "hunt_value": 1.0, "range": [13, 20000],
         "retested_to": 60000, "retests": 2, "statement": "S1", "reference": "no reference found"}
    r.update(kw)
    return r


def test_inflight_cap(monkeypatch):
    monkeypatch.delenv("COLONY_FRONTIER_INFLIGHT", raising=False)
    assert F.inflight_cap() == 1
    monkeypatch.setenv("COLONY_FRONTIER_INFLIGHT", "3")
    assert F.inflight_cap() == 3
    monkeypatch.setenv("COLONY_FRONTIER_INFLIGHT", "99")
    assert F.inflight_cap() == 5


def test_retest_tiers(tmp_path, monkeypatch):
    import colony.oracle as O
    import colony.proof_path as PP
    import colony.surprise_credit as SC
    r = _r()
    w1, w2 = F.check_name(r), F.check_name(r, 2)
    log = tmp_path / "oracle.jsonl"
    log.write_text(json.dumps({"mutation": w1, "passed": True}) + "\n")
    monkeypatch.setattr(O, "ORACLE_LOG", log)
    monkeypatch.setattr(PP, "REPORT", tmp_path / "none.json")
    monkeypatch.setattr(SC, "trivial_any_seed", lambda r: False)
    got = [c["name"] for c in F.retest_candidates({w1}, [r])]
    assert got == [w2]
    assert F.windows(r, 2)[0][0] > F.windows(r, 1)[-1][1]
    assert F.retest_candidates({w1, w2}, [r]) == []                      # w3 waits for w2 to pass
    assert F.retest_candidates({w1}, [dict(r, certificate={"m": 1})]) == []   # proved: no re-test
    log.write_text("")
    assert F.retest_candidates({w1}, [r]) == []                          # w1 not passed yet


def test_retest_windows_stay_inside_bridge_tables():
    """A re-test window past the bridge tables must not read as 'does not hold'."""
    from colony import frontier_checks as F, frontier_conjectures as fc
    r = {"kind": "cong", "lhs": "dbl(gcd(fib,tau))", "rhs": "", "params": {"m": 3, "q": 4, "r": 0, "s": 2}}
    wins = F.windows(r, 2)
    claim = {k: r[k] for k in ("kind", "lhs", "rhs", "params")}
    assert all(fc.holds_on(claim, a, b) > 0 for a, b in wins) or wins == []
    assert all(b <= F.evaluable_hi(r, 10 ** 6) for _a, b in wins)
