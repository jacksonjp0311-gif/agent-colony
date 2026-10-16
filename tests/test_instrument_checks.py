"""Desk-authored checks that call the sieve instrument: same disabled/verify path, real falsifiability."""
import ast

import pytest

from colony import instrument_checks as ic
from colony.authoring import FALLBACK_MARKER, INSERT_MARKER, _lemma_impl, insert_disabled, verify_candidate
from colony.instruments import sieve

pytestmark = pytest.mark.skipif(sieve._helper() is None, reason="C helper unavailable")


def _src():
    src = _lemma_impl().read_text(encoding="utf-8")
    return ic.ensure_bridges(src, INSERT_MARKER if INSERT_MARKER in src else FALLBACK_MARKER)


def test_gap_tuples_admissible_only():
    ts = ic.gap_tuples()
    assert (2,) in ts and (2, 4) in ts and (6, 6, 6) in ts
    assert (2, 2) not in ts  # 0,2,4 covers every class mod 3


@pytest.mark.parametrize("template", ic.TEMPLATES)
def test_templates_verify_disabled(template):
    src = _src()
    c = ic.build(template, (2, 4), 1)
    new = insert_disabled(src, c["name"], c["fn_src"])
    assert f'("{c["name"]}", check_{c["name"]}, False)' in new  # inserted disabled
    r = verify_candidate(new, c["name"], c["verify_fns"])
    assert r["accepted"], r


def test_false_claim_is_rejected(monkeypatch):
    monkeypatch.setattr(ic, "K_SIGMA", 0.001)
    src = _src()
    c = ic.build("hl_within", (2,), 1)
    r = verify_candidate(insert_disabled(src, c["name"], c["fn_src"]), c["name"], c["verify_fns"])
    assert not r["accepted"] and r["reason"] == "does_not_hold_on_new_window"


def test_candidates_rotate_and_advance_windows():
    first = ic.candidates(set(), limit=3)
    assert first and first[0]["name"].endswith("_w1")
    used = {first[0]["name"]}
    nxt = ic.candidates(used, limit=50)
    assert first[0]["name"] not in {c["name"] for c in nxt}
    assert all(ast.parse(c["fn_src"]) for c in nxt)


def test_bridges_respect_cap():
    ns = {}
    exec(ic.BRIDGE_SRC, ns)
    with pytest.raises(sieve.SieveCapExceeded):
        ns["sieve_count"]((2,), 0, 10 ** 12)
