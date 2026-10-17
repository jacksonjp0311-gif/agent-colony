"""Instrument checks reach the Oracle; rotation; no slot burn; cycle-suffix dedupe; external_mind guard."""
import ast
import json
from pathlib import Path

import pytest

from colony import instrument_checks as ic
from colony.instruments import sieve

needs_c = pytest.mark.skipif(sieve._helper() is None, reason="C helper unavailable")


# 1. unenabled instrument checks become desk variants; proven only if bridge + self-test
def _fn(src):
    return ast.parse(src).body[0]


def test_instrument_links_require_bridge_and_self_test(monkeypatch):
    fn = _fn("def check_authored_sieve_x():\n    return sieve_count((2,), 1, 9) > 0\n")
    art_ok = ic.BRIDGE_SRC
    monkeypatch.setattr(ic, "self_test", lambda force=False: {"ok": True})
    links = ic.instrument_links(fn, art_ok)
    assert links and all(l["proven"] for l in links)
    assert links[0]["source"] == "colony/instruments/sieve.py"
    assert not any(l["proven"] for l in ic.instrument_links(fn, "no bridge here"))
    monkeypatch.setattr(ic, "self_test", lambda force=False: {"ok": False})
    assert not any(l["proven"] for l in ic.instrument_links(fn, art_ok))


def test_non_instrument_fn_gets_no_links():
    assert ic.instrument_links(_fn("def check_x():\n    return 1 == 1\n"), ic.BRIDGE_SRC) == []


def test_self_test_matches_independent_reference():
    r = ic.self_test(force=True)
    assert r["ok"], r
    assert ic._brute_pattern((2,), 3, 1000) == 35  # twin pairs (p, p+2) with p < 1000


def test_unenabled_variants_include_disabled_instrument_checks(tmp_path, monkeypatch):
    from colony import lessons
    art = tmp_path / "lemma_impl.py"
    art.write_text(ic.BRIDGE_SRC + (
        "\n\ndef check_authored_sieve_two_counter_g2_w9() -> bool:\n"
        "    return sieve_count((2,), 3, 100) == sieve_count((2,), 3, 100, backend='python')\n\n"
        "HARD_TIER_LEMMAS = [\n"
        "    (\"authored_sieve_two_counter_g2_w9\", check_authored_sieve_two_counter_g2_w9, False),\n]\n"
    ), encoding="utf-8")
    monkeypatch.setattr(lessons, "BENCH_ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(lessons, "mutation_cooldown", lambda **k: type("C", (), {"allows": lambda s, n: True})())
    monkeypatch.setattr(ic, "self_test", lambda force=False: {"ok": True})
    names = [v["name"] for v in lessons.unenabled_chain_variants()]
    assert "authored_sieve_two_counter_g2_w9" in names
    monkeypatch.setattr(ic, "self_test", lambda force=False: {"ok": False})
    assert "authored_sieve_two_counter_g2_w9" not in [v["name"] for v in lessons.unenabled_chain_variants()]


# 2. rotate to a new gap pattern before a new window of an old one
def test_candidates_rotate_patterns_before_windows():
    used = {f"{ic.PREFIX}{t}_g2_w1" for t in ic.TEMPLATES}
    nxt = ic.candidates(used, limit=3)
    assert nxt and all("_g2_" not in c["name"] for c in nxt)
    assert all(c["name"].endswith("_w1") for c in nxt)


# 3. no new instrument check while one is pending the Oracle
def _art(flag):
    return ("HARD_TIER_LEMMAS = [\n"
            f"    (\"{ic.PREFIX}hl_within_g2_w1\", check_a, {flag}),\n]\n")


def test_pending_tracks_disabled_without_verdict(tmp_path, monkeypatch):
    from colony import oracle
    log = tmp_path / "oracle.jsonl"
    monkeypatch.setattr(oracle, "ORACLE_LOG", log)
    assert ic.pending(_art("False")) == [f"{ic.PREFIX}hl_within_g2_w1"]
    assert ic.pending(_art("True")) == []
    log.write_text(json.dumps({"mutation": f"{ic.PREFIX}hl_within_g2_w1", "passed": False}) + "\n")
    assert ic.pending(_art("False")) == []  # judged (killed) -> no longer blocks authoring


def test_authoring_skips_instrument_candidates_while_pending(monkeypatch):
    from colony import authoring
    called = []
    monkeypatch.setattr(ic, "pending", lambda src: ["x"])
    monkeypatch.setattr(ic, "candidates", lambda *a, **k: called.append(1) or [])
    authoring.author_checks(write=False, max_new=1)
    assert called == []


# 5. (cycle N) suffix normalized for cooldown / dedupe
def test_cycle_suffix_normalized():
    from colony.lessons import strip_cycle_suffix, theme_key
    t = "Feed accepted/strong RSI findings into skill_router + genome bias"
    assert strip_cycle_suffix(f"{t} (cycle 340)") == t
    assert strip_cycle_suffix(f"{t} (cycle 3) (cycle 4)") == t
    assert theme_key("`lemma_x` (cycle 9)") == theme_key("`lemma_x`")
    assert theme_key("Some free title (cycle 12)") == theme_key("Some free title")


# 4. growth.py no longer imports a missing name
def test_growth_does_not_import_missing_propose():
    src = Path("colony/emergence/growth.py").read_text(encoding="utf-8")
    assert "from colony.external_mind import propose" not in src
    import colony.external_mind as em
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module == "colony.external_mind":
            for a in node.names:
                assert hasattr(em, a.name), a.name
