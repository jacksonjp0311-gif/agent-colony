"""Report-only semantic bridge: claim vs parameters, mutants must be rejected, verdicts untouched."""
import ast
import json

from colony import instrument_checks as ic
from colony.trust import semantic_bridge as sb


def _fn(src):
    return ast.parse(src).body[0]


def _built(template, gaps, w=1):
    c = ic.build(template, gaps, w)
    return c["name"], _fn(c["fn_src"])


def test_built_sieve_checks_bridge_ok_all_templates():
    for t in ic.TEMPLATES:
        for g in [(2,), (2, 4), (6, 6)]:
            if ic.build(t, g, 1) is None:
                continue
            name, fn = _built(t, g)
            r = sb.assess(name, fn)
            assert r["status"] == "ok", r
            assert r["mutants_tested"] >= 2 and r["mutants_not_rejected"] == []


def test_gap_mismatch_would_reject():
    name, _ = _built("hl_within", (2,))
    src = ic.build("hl_within", (4,), 1)["fn_src"].replace("check_authored_sieve_hl_within_g4_w1", f"check_{name}")
    src = src.replace("pattern (4,)", "pattern (2,)")  # docstring claims twins, code counts gap 4
    r = sb.assess(name, _fn(src))
    assert r["status"] == "would_reject" and any("gaps_used" in m for m in r["mismatches"])


def test_wrong_window_and_class_would_reject():
    name, fn = _built("residue_bal", (2,))
    src = ast.unparse(fn).replace("4, 3)", "4, 1)")  # both classes 1 -> not the admissible pair
    assert sb.assess(name, _fn(src))["status"] == "would_reject"
    name, fn = _built("two_counter", (2,), 2)
    src = ast.unparse(fn).replace("20000000", "30000000", 1)
    assert sb.assess(name, _fn(src))["status"] == "would_reject"


def test_compose_component_mismatch():
    good = _fn('def check_authored_a_lemma__b_lemma_w1():\n    """d"""\n'
               '    return all(check_a_lemma(n) for n in range(3)) and all(check_b_lemma(n) for n in range(3))\n')
    assert sb.assess("authored_a_lemma__b_lemma_w1", good)["status"] == "ok"
    bad = _fn('def check_authored_a_lemma__b_lemma_w1():\n    """d"""\n'
              '    return all(check_a_lemma(n) for n in range(3)) and all(check_c_lemma(n) for n in range(3))\n')
    r = sb.assess("authored_a_lemma__b_lemma_w1", bad)
    assert r["status"] == "would_reject"


def test_unknown_family_unbridged():
    assert sb.assess("authored_oeis_a000045__cassini", _fn("def check_x():\n    return True\n"))["status"] == "unbridged"


def test_report_logs_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "STATE", tmp_path / "sb.json")
    monkeypatch.setattr(sb, "assess", lambda name: {"mutation": name, "status": "would_reject", "mismatches": ["x"]})
    row = sb.report(mutation="authored_sieve_hl_within_g2_w1", kind="hard_enable", oracle_passed=True)
    st = json.loads((tmp_path / "sb.json").read_text())
    assert row["mode"] == "report_only" and st["totals"]["would_reject_on_oracle_pass"] == 1
    monkeypatch.setattr(sb, "assess", lambda name: 1 / 0)
    assert sb.report(mutation="authored_x_w1", kind="hard_enable", oracle_passed=True) is None


def test_flag_off(monkeypatch, tmp_path):
    monkeypatch.setattr(sb, "STATE", tmp_path / "sb.json")
    monkeypatch.setenv("COLONY_SEMANTIC_BRIDGE", "0")
    assert sb.report(mutation="authored_sieve_hl_within_g2_w1", kind="hard_enable", oracle_passed=True) is None
    assert not (tmp_path / "sb.json").exists()


def test_oracle_verdict_unchanged_by_bridge(monkeypatch):
    """The Oracle hook is report-only: a would_reject result cannot flip a verdict."""
    src = open("colony/oracle.py", encoding="utf-8").read()
    hook = src[src.index("REPORT-ONLY: semantic bridge"):][:400]
    assert "verdict.passed =" not in hook and "kills" not in hook and "return verdict" in hook
