"""Item 109: TxGraffiti-style ratio / convex-hull bound generators with triviality pre-filters and lemmas."""
from colony import txgraffiti as T


def _invs():
    return {"n": lambda n: n, "2n+1": lambda n: 2 * n + 1, "n^2": lambda n: n * n, "n^2+n": lambda n: n * n + n,
            "Fib": T.builtin_invariants()["Fibonacci(n)"]}


def test_generates_checked_bounds_with_touch_numbers():
    r = T.generate(_invs(), [], 10.0, n0=1, n_train=20, n_test=60)
    st = r["stats"]
    assert st["passed"] > 0 and st["touch_filtered"] > 0
    for lem in r["lemmas"]:
        assert lem["touch"] >= (T.TOUCH_MIN_HULL if lem["generator"] == "hull" else T.TOUCH_MIN)
        assert lem["status"] == "checked_not_proved" and lem["range"] == [1, 60]


def test_affine_trivial_pairs_filtered():
    r = T.generate({"n": lambda n: n, "n+3": lambda n: n + 3}, [], 5.0, n0=1, n_train=20, n_test=40)
    assert r["lemmas"] == [] and r["stats"]["trivial"] >= 2


def test_held_out_rejects_bounds_that_fail_later():
    # n^2 <= c*n with c = max on n<=20 fails after the training range
    r = T.generate({"n": lambda n: n, "n^2": lambda n: n * n}, [], 5.0, n0=1, n_train=20, n_test=40)
    assert not any(l["statement"].startswith("n^2 <=") and l["source"] == "n" for l in r["lemmas"])


def test_stored_lemmas_are_cited_or_imply():
    first = T.generate(_invs(), [], 10.0, n0=1, n_train=20, n_test=60)["lemmas"]
    second = T.generate(_invs(), first, 10.0, n0=1, n_train=20, n_test=60)
    ids = {l["id"] for l in first}
    assert second["stats"]["implied"] + second["stats"]["dalmatian"] > 0
    assert not ({l["id"] for l in second["lemmas"]} & ids)
    assert all(set(l["cites"]) <= ids | {x["id"] for x in second["lemmas"]} for l in second["lemmas"])


def test_simplicity_filter():
    r = T.generate(_invs(), [], 10.0, n0=1, n_train=20, n_test=60)
    for l in r["lemmas"]:
        for s in (l["m"], l["q"]):
            for part in s.lstrip("-").split("/"):
                assert int(part) <= T.MAX_HEIGHT


def test_off_on_control(monkeypatch):
    from colony import arm
    monkeypatch.setattr(arm, "is_control", lambda: True)
    assert T.enabled() is False
    assert T.turn("c1", menu=[]) is None



def test_run_cycle_hook_is_live_desk_only():
    """The generator is wired once per full live desk pass and reported (static check; a full
    run_cycle needs network-free fixtures that the item-105/106 tests already cover)."""
    from colony import oeis_conjectures as OC
    src = open(OC.__file__, encoding="utf-8").read()
    assert 'if only_ids is None and m == "live":\n        try:   # item 109' in src
    assert "TG.turn(cycle_id, menu)" in src and '"lemmas": None if not lemmas' in src


def test_converse_restatements_are_not_stored_twice():
    from fractions import Fraction
    invs = {"a": lambda n: 2 * n + 1 + (n % 2), "b": lambda n: n + (n % 2)}
    res = T.generate(invs, [], budget_s=5.0)
    seen = set()
    for r in res["lemmas"]:
        m, q = Fraction(r["m"]), Fraction(r["q"])
        key = (r["target"], r["source"], r["rel"], m, q)
        flip = ">=" if r["rel"] == "<=" else "<="
        assert (r["source"], r["target"], flip, 1 / m, -q / m) not in seen if m > 0 else True
        seen.add(key)
