"""colony.reference_check (Stage 2): a surprise only if no reference explains it."""
from __future__ import annotations

import json
import random

import pytest

from colony import frontier_conjectures as FC
from colony import reference_check as R


@pytest.fixture(scope="module")
def T():
    return FC.Tables(lim=3000, exp_n=700)


class FakeNet:
    def __init__(self, files):
        self.files, self.n = files, 0

    def get(self, url, name):
        return self.files.get(name)


def _claim(kind, lhs, rhs, **params):
    return {"kind": kind, "params": params, "lhs": lhs, "rhs": rhs, "_le": FC.parse(lhs),
            "_re": FC.parse(rhs) if rhs else None, "oeis_anums": []}


def test_mode_default_and_fact_validation(T, monkeypatch):
    monkeypatch.delenv("COLONY_REFCHECK", raising=False)
    assert R.mode() == "shadow"
    phi = T.t["phi"][1:600]
    assert R.validate(R.CATALOG["phi"][0], phi)
    assert not R.validate({"kind": "residue", "m": 3, "dom": 1, "ref": "x"}, phi)   # phi mod 3 is not simple
    assert not R.validate({"kind": "bound_n", "dom": 1, "ref": "x"}, T.t["sigma"][1:600])


def test_parse_oeis_text():
    f = R.parse_facts("A000010", [("comment", "a(n) is even for n > 2."), ("formula", "a(n) <= n.")])
    kinds = {(x["kind"], x.get("m"), x["dom"]) for x in f}
    assert ("residue", 2, 3) in kinds and ("bound_n", None, 1) in kinds
    assert all(x["ref"].startswith("A000010 (") for x in f)


def test_explained_by_reference_and_not(T):
    net = FakeNet({"A000010.json": json.dumps([{"comment": ["a(n) is even for n > 2."], "formula": []}])})
    c = _claim("cong", "S((phi*rad))", "", m=2, r=1, q=1, s=0)
    r = R.check(c, T, net)
    assert r["explained"] and any("even" in x for x in r["refs"])
    # a congruence that no stated fact implies (pi has no parity fact): not explained
    c2 = _claim("cong", "S((pi*pi))", "", m=2, r=1, q=2, s=0)
    r2 = R.check(c2, T, net)
    assert not r2["explained"] and r2["label"].startswith("no reference found (checked:")


def test_false_claim_never_explained(T):
    """The null keeps only stated facts, so a claim that fails on the real tables cannot pass."""
    c = _claim("cong", "phi", "", m=4, r=0, q=1, s=0)
    assert R.explained_by(c, T, {"phi": R.CATALOG["phi"]}) is False
