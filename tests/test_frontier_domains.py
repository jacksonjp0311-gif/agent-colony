"""New domains: every table built two independent ways; gating; honest 'automatic' label."""
from functools import lru_cache

from colony import frontier_conjectures as FC
from colony import frontier_domains as D
from colony import known_check as K


def test_words_two_ways():
    for w in D.WORDS:
        assert D.word(w, 4000) == D.word_by_morphism(w, 4000), w


def _partitions(n, maxp=None):
    maxp = n if maxp is None else maxp
    if n == 0:
        yield ()
        return
    for p in range(min(n, maxp), 0, -1):
        for rest in _partitions(n - p, p):
            yield (p,) + rest


def _plane(n):
    # plane partitions of n: rows are partitions, each row dominated entrywise by the previous one
    @lru_cache(None)
    def count(m, prev):
        if m == 0:
            return 1
        tot = 0
        for k in range(1, m + 1):
            for row in _partitions(k, prev[0] if prev else k):
                if prev and (len(row) > len(prev) or any(r > q for r, q in zip(row, prev))):
                    continue
                tot += count(m - k, row)
        return tot
    return count(n, ())


def test_qseries_brute_force():
    for n in range(0, 16):
        ps = list(_partitions(n))
        assert D.qseries("overpart", 15)[n] == sum(2 ** len(set(p)) for p in ps)
        assert D.qseries("podd", 15)[n] == sum(1 for p in ps if len([x for x in p if x % 2]) == len({x for x in p if x % 2}))
        cnt = lambda m: len(list(_partitions(m)))  # noqa: E731
        assert D.qseries("cubic", 15)[n] == sum(cnt(a) * cnt((n - a) // 2) for a in range(n + 1) if (n - a) % 2 == 0)
    for n in range(0, 11):
        assert D.qseries("pplane", 10)[n] == _plane(n)


def test_gating(monkeypatch):
    monkeypatch.setenv("COLONY_DOMAINS", "shadow")
    assert not set(FC.menu_prims()) & set(D.PRIMS)
    monkeypatch.setenv("COLONY_DOMAINS", "live")
    assert set(D.PRIMS) <= set(FC.menu_prims())


def test_tables_and_automatic_label():
    T = FC.Tables(lim=6000, exp_n=300)
    assert T.t["tm"][:8] == [0, 1, 1, 0, 1, 0, 0, 1]
    assert len(T.t["pplane"]) == 301
    c = {"kind": "cong", "lhs": "S(tm)", "rhs": "", "params": {"m": 2, "r": 0, "q": 4, "s": 0},
         "_le": FC.parse("S(tm)"), "_re": None}
    r = K.check(c, T)
    assert r["explained"] and r["step"] == "automatic"
    c2 = {"kind": "le", "lhs": "tm", "rhs": "tau", "params": {}, "_le": FC.parse("tm"), "_re": FC.parse("tau")}
    assert K.check(c2, T)["step"] != "automatic"


def test_deep_range_words():
    from colony import deep_range as DR
    tb = DR.tables(20000)
    assert tb["tm"][:20001] == D.word_by_morphism("tm", 20000)
