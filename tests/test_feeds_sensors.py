"""Outward feeds + inward sensors: offline fixtures, fail-soft, dedupe, bounds, wiring."""
from __future__ import annotations

import ast
import json

import pytest

import colony.feeds as F
import colony.sensors as S

ATOM = """<?xml version='1.0'?><feed>
<entry><id>http://arxiv.org/abs/2610.00001v1</id><published>2026-10-06T00:00:00Z</published>
<title>On <b>Catalan</b>   identities</title><summary>We prove things &amp; more.</summary></entry>
<entry><id>http://arxiv.org/abs/2610.00002v2</id><published>2026-10-06T00:00:00Z</published>
<title>__import__('os').system('echo pwned')</title><summary>x</summary></entry>
</feed>"""

CATALAN = [1, 1, 2, 5, 14, 42, 132, 429, 1430, 4862, 16796, 58786, 208012, 742900, 2674440,
           9694845, 35357670, 129644790, 477638700, 1767263190]
FIB = [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181]


def _oeis_body(number, terms, name="Seq"):
    return json.dumps([{"number": number, "data": ",".join(str(t) for t in terms), "name": name}])


def _fake_http(url, **kw):
    if "arxiv.org" in url:
        return True, ATOM
    if "oeis.org" in url:
        q = url.split("q=")[1].split("&")[0].replace("%2C", ",")
        if q.startswith("1,2,5,14"):
            return True, _oeis_body(108, CATALAN, 'Catalan "); import os #')
        if q.startswith("1,1,2,3,5"):
            return True, _oeis_body(45, FIB, "Fibonacci numbers")
        return True, "[]"
    if "crossref.org" in url:
        return True, json.dumps({"message": {"items": [
            {"DOI": "10.1/abc", "title": ["A square sum identity"], "container-title": ["J"]},
            {"DOI": "10.1/xyz", "title": ["Unrelated cooking"], "container-title": ["K"]}]}})
    if "w/api.php" in url:
        return True, json.dumps({"query": {"search": [{"title": "Odds"}, {"title": "Sum of odds"}]}})
    if "rest_v1/page/summary" in url:
        return True, json.dumps({"extract": "<i>Sum</i> of the first n odd numbers is n^2.",
                                 "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/X"}}})
    if "api.github.com" in url:
        return True, json.dumps({"workflow_runs": [
            {"id": 1, "name": "Colony evolve", "status": "completed", "conclusion": "success"},
            {"id": 2, "name": "Colony evolve", "status": "completed", "conclusion": "failure"}]})
    return False, "unknown"


@pytest.fixture()
def feeds_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "FEEDS_JSONL", tmp_path / "feeds.jsonl")
    monkeypatch.setattr(F, "FEEDS_STATE", tmp_path / "feeds_state.json")
    monkeypatch.setattr(S, "SENSORS_JSON", tmp_path / "sensors.json")
    monkeypatch.setattr(F, "_http_get", _fake_http)
    return tmp_path


def test_parse_arxiv_cleans_and_routes():
    items = F.parse_arxiv(ATOM, "math.CO")
    assert [i["id"] for i in items] == ["arxiv:2610.00001", "arxiv:2610.00002"]
    assert items[0]["title"] == "On Catalan identities" and items[0]["text"] == "We prove things & more."
    assert items[0]["channel"] == "math" and items[0]["provenance"]["untrusted"] is True
    assert F.arxiv_channel("cs.MA") == "rsi" and F.arxiv_channel("cs.LG") == "science"
    assert F.arxiv_channel("math.NT") == "math"


def test_oeis_heldout_alignment_and_int_only():
    gen = F.generator_by_name("catalan")
    q = F.generator_terms(gen, 1, F.QUERY_TERMS)
    assert q == CATALAN[1:9]
    hit = F.parse_oeis(_oeis_body(108, CATALAN), q, 1, gen)
    assert hit["oeis_id"] == "A000108" and hit["heldout_start"] == 9 and hit["terms"] == CATALAN[9:]
    # non-matching data → nothing; non-integer junk truncates the term list (too short → None)
    assert F.parse_oeis(_oeis_body(7, [9, 9, 9]), q, 1, gen) is None
    bad = '[{"number": 108, "data": "' + ",".join(map(str, CATALAN[:12])) + ',1e9,__import__", "name": "x"}]'
    assert F.parse_oeis(bad, q, 1, gen) is None


def test_fetch_all_fail_soft_on_network_error(feeds_tmp, monkeypatch):
    monkeypatch.setattr(F, "_http_get", lambda url, **kw: (False, "URLError: down"))
    out = F.fetch_all(force=True)
    assert all(v.get("new", 0) == 0 for v in out["sources"].values())
    assert out["sources"]["arxiv"]["ok"] is False
    st = F.load_state()
    assert st["health"]["arxiv"]["fail"] == 1 and "down" in st["last_error"]["arxiv"]

    def boom(url, **kw):
        raise RuntimeError("socket exploded")
    monkeypatch.setattr(F, "_http_get", boom)
    out2 = F.fetch_all(force=True)  # must not raise
    assert out2["sources"]["oeis"]["ok"] is False


def test_fetch_dedupes_bounds_and_ttl(feeds_tmp, monkeypatch):
    out = F.fetch_all(force=True)
    src = out["sources"]
    assert src["arxiv"]["new"] >= 2 and src["oeis"]["new"] == 2 and src["crossref"]["new"] == 1
    assert src["ci_health"]["ok"] and F.load_state()["ci_health"]["success_rate"] == 0.5
    rows = F.load_items()
    assert len({r["id"] for r in rows}) == len(rows)
    assert all(len(r["text"]) <= F.MAX_TEXT and len(r["title"]) <= 200 for r in rows)
    assert not any(r["id"] == "crossref:10.1/xyz" for r in rows)  # relevance guard
    again = F.fetch_all(force=True)
    assert all(v.get("new", 0) == 0 for v in again["sources"].values())
    ttl = F.fetch_all()  # within TTL: skipped, no network needed
    assert ttl["sources"]["arxiv"]["skipped"] == "ttl"
    # file stays bounded
    monkeypatch.setattr(F, "MAX_FILE_ROWS", 3)
    monkeypatch.setattr(F, "KEEP_ROWS", 2)
    F._append([F._item("arxiv", f"9999.{i:05d}", "paper", "t", "x", "u", "math", "e", "q") for i in range(3)])
    assert len(F.load_items()) == 2


def test_sequence_items_reject_tampered_rows(feeds_tmp):
    good = {"id": "oeis:A000045:fibonacci", "kind": "sequence", "oeis_id": "A000045", "generator": "fibonacci",
            "heldout_start": 9, "terms": FIB[9:]}
    rows = [good, {**good, "oeis_id": "A45; rm"}, {**good, "terms": [True] * 8},
            {**good, "terms": ["34"] * 8}, {**good, "terms": [10 ** 80] * 8}]
    F.FEEDS_JSONL.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert F.sequence_items() == [good]


def test_seek_theme_prefers_related_paper_and_skips_summaries(feeds_tmp):
    rows = [F._item("wikipedia", "catalan number", "summary", "Catalan number", "catalan", "u0", "history", "e", "q"),
            F._item("arxiv", "2610.1", "paper", "Graph minors", "minors", "u1", "math", "e", "q"),
            F._item("crossref", "10.1/c", "paper", "An identity relating Catalan numbers", "x", "u2", "science", "e", "q")]
    F._append(rows)
    for cyc in ("a", "b", "c", "d"):
        assert F.pick_seek_theme(cyc, target="authored_oeis_a000108__catalan_bounded")["id"] == "crossref:10.1/c"
    assert all(F.pick_seek_theme(c)["kind"] == "paper" for c in ("a", "b", "c", "d"))
    assert F._target_tokens("authored_oeis_a000108__catalan_bounded_w1") == {"catalan"}


def test_channel_note_routes_pointer(feeds_tmp):
    F.fetch_all(force=True)
    note, payload = F.channel_note("math", "c1")
    assert "Feed[" in note and "pointer, not a claim" in note and payload["feed_url"].startswith("https://")
    assert F.channel_note("cosmos", "c1") is None


# ---------------------------------------------------------------- sensors

def _fit(agg, nov=0.0):
    return {"aggregate": agg, "novelty": nov, "kill_rate": 0.9, "lesson_uptake": 0.95}


def test_stall_trends_streaks_and_drift():
    flat = [_fit(0.82 + 0.0005 * (i % 2)) for i in range(6)]
    assert S.stall(flat)["stalled"] is True
    assert S.stall([_fit(0.8), _fit(0.9)] * 3)["stalled"] is False
    assert S.stall(flat[:3])["reason"] == "insufficient_history"
    tr = S.trends([_fit(0.80 + 0.01 * i) for i in range(5)])
    assert tr["aggregate"]["slope"] == pytest.approx(0.01) and tr["aggregate"]["last"] == 0.84
    ls = S.lemma_streaks([{"mutation": "a", "decision": "keep"}, {"mutation": "b", "decision": "revert"},
                          {"mutation": "b", "decision": "revert"}, {"mutation": "a", "decision": "revert"}])
    assert ls["by_mutation"]["b"]["streak"] == 2 and ls["revert_streaks"] == ["b"]
    rows = [{"benches": [{"bench": "x", "seconds": 1.0}]}] * 10 + [{"benches": [{"bench": "x", "seconds": 3.0}]}] * 5
    assert S.bench_timing(rows)["x"]["drift"] is True


def test_sensors_refresh_fail_soft_and_signals(feeds_tmp, monkeypatch, tmp_path):
    monkeypatch.setattr(S, "FITNESS_HISTORY", tmp_path / "nope.jsonl")
    monkeypatch.setattr(S, "CONJECTURE_HISTORY", tmp_path / "nope2.jsonl")
    monkeypatch.setattr(S, "BENCH_HISTORY", tmp_path / "nope3.jsonl")
    snap = S.refresh("c0")
    assert snap["stall"]["stalled"] is False and S.SENSORS_JSON.exists()
    F.fetch_all(force=True)
    (tmp_path / "fit.jsonl").write_text("\n".join(json.dumps(_fit(0.82)) for _ in range(6)) + "\n")
    monkeypatch.setattr(S, "FITNESS_HISTORY", tmp_path / "fit.jsonl")
    snap = S.refresh("c1")
    sig = " ".join(snap["signals"])
    assert "stall" in sig and "OEIS sequence" in sig and "ci_health" in sig
    assert S.latest()["cycle_id"] == "c1"


# ---------------------------------------------------------------- wiring

def test_seek_uses_feed_theme_with_cite_and_sensor_order(feeds_tmp, monkeypatch, tmp_path):
    import colony.lessons as L
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "ledger.json")
    L.write_human_guide(what="avoid process spam; seek", author="James Jackson", mutation="seek",
                        catalog_hint={"avoid": ["process_spam"]}, tags=["human_guide", "seek"])
    F.fetch_all(force=True)
    pick = L.seek_proposal_from_guides(cycle_id="cyc1")
    assert pick is not None
    title, hyp, action = pick
    theme = F.pick_seek_theme("cyc1", target=action.split(":", 1)[1])
    assert theme["kind"] == "paper" and theme["title"][:40] in title
    assert "Feed cite:" in hyp and theme["url"] in hyp and "not evidence of truth" in hyp
    first = L.theme_key(action.split(":", 1)[1])
    S.SENSORS_JSON.write_text(json.dumps({"lemma_streaks": {"revert_streaks": [first]}}))
    pick2 = L.seek_proposal_from_guides(cycle_id="cyc1")
    assert pick2 is not None and L.theme_key(pick2[2].split(":", 1)[1]) != first


def test_authoring_turns_oeis_feed_into_verified_disabled_check(feeds_tmp, tmp_path, monkeypatch):
    from tests.test_authoring import _guide, _repo
    import colony.authoring as A
    extra_fns = '''
def fibonacci(n: int) -> int:
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def check_cassini_identity(n: int) -> bool:
    return fibonacci(n + 1) * fibonacci(n - 1) - fibonacci(n) ** 2 == (-1) ** n

'''
    path = _repo(tmp_path, monkeypatch, extra_fns=extra_fns,
                 extra_entries='    ("cassini", lambda: all(check_cassini_identity(n) for n in range(1, 10)), True),\n',
                 latest={"basic:a_lemma": True, "hard:b_lemma": True, "hard:cassini": True})
    _guide()
    F.fetch_all(force=True, sources=["oeis"])
    rows = A.author_checks(cycle_id="c1")
    assert rows and rows[0]["source"] == "oeis" and rows[0]["name"] == "authored_oeis_a000045__cassini"
    assert "oeis:A000045" in rows[0]["evidence"]
    src = path.read_text()
    ast.parse(src)
    assert '("authored_oeis_a000045__cassini", check_authored_oeis_a000045__cassini, False),' in src
    assert "import os" not in src and "Fibonacci numbers" not in src  # fetched text never in code
    # tampered expected values: verification rejects, desk falls back to composing lemmas
    rows_file = [json.loads(x) for x in F.FEEDS_JSONL.read_text().splitlines()]
    for r in rows_file:
        if r.get("kind") == "sequence":
            r["terms"] = [t + 1 for t in r["terms"]]
            r["oeis_id"] = "A999999"
    F.FEEDS_JSONL.write_text("\n".join(json.dumps(r) for r in rows_file) + "\n")
    rows2 = A.author_checks(cycle_id="c2")
    assert rows2 and rows2[0]["source"] == "compose"
    les = [json.loads(x) for x in (tmp_path / "lessons.jsonl").read_text().splitlines()]
    rej = [e for e in les if e.get("type") == "authoring_reject"]
    assert any("a999999" in e["mutation"] and "does_not_hold" in e["what"] for e in rej)


def test_feeds_cli_offline_exit_zero(feeds_tmp, capsys):
    from colony.cli import main
    assert main(["feeds", "--offline"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "cache" in out and "signals" in out
