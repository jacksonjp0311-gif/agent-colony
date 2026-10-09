"""Challenger: block-only self-challenge before the Oracle / frontier recheck."""
from __future__ import annotations

import ast
import json
import time

import pytest

import colony.challenger as C

ART = '''
from typing import Callable
import time


def check_odd_sum(n: int) -> bool:
    """1+3+...+(2n-1) = n^2"""
    return sum(2 * i - 1 for i in range(1, n + 1)) == n * n


def check_euler_prime(n: int) -> bool:
    """Seeded FALSE identity: n^2-n+41 is prime (fails at n=41)."""
    m = n * n - n + 41
    return m > 1 and all(m % d for d in range(2, int(m ** 0.5) + 1))


def check_square_again(a: int, b: int) -> bool:
    return (a + b) ** 2 == a * a + 2 * a * b + b * b


def check_guarded(n: int) -> bool:
    if n < 100:
        return True
    return n % 7 == 3


def check_inverse(n: int) -> bool:
    return (1 // n) * n <= n


def check_count(n: int) -> int:
    return n + 1


def check_slow(n: int) -> bool:
    t = time.monotonic()
    while time.monotonic() - t < 0.3:
        pass
    return True


CANDIDATE_LEMMAS: list[tuple[str, Callable[[], bool], bool]] = [
    ("odd_sum", lambda: all(check_odd_sum(n) for n in range(0, 20)), ENABLED_ODD),
    ("euler_prime", lambda: all(check_euler_prime(n) for n in range(0, 12)), ENABLED_EULER),
    ("square_again", lambda: all(check_square_again(a, b) for a in range(-3, 4) for b in range(-3, 4)), True),
    ("const_pad", lambda: all(2 + 2 == 4 for a in range(0, 5)), True),
    ("empty_window", lambda: all(check_odd_sum(n) for n in range(5, 5)), True),
    ("guarded", lambda: all(check_guarded(n) for n in range(1, 30)), True),
    ("inverse", lambda: all(check_inverse(n) for n in range(0, 1)), False),
    ("inverse_tested", lambda: all(check_inverse(n) for n in range(1, 9)), True),
    ("counts", lambda: all(check_count(n) for n in range(0, 5)), True),
    ("slow", lambda: all(check_slow(n) for n in range(0, 50)), True),
]
'''


def art(odd=True, euler=True) -> str:
    return ART.replace("ENABLED_ODD", str(odd)).replace("ENABLED_EULER", str(euler))


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    import colony.exploration_budget as B
    import colony.lessons as L

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
    monkeypatch.setattr(B, "BUDGET_PATH", tmp_path / "exploration_budget.json")
    monkeypatch.setattr(C, "LOG", tmp_path / "self_challenge.jsonl")
    monkeypatch.setattr(C, "SYSTEM", tmp_path / "self_challenger.json")
    return tmp_path


# ---------------------------------------------------------------- break / pass

def test_blocks_seeded_false_identity():
    r = C.challenge_entry(art(), "euler_prime", cycle_id="cyc1", before_src=art(euler=False))
    assert r.blocked and r.reason.startswith("counterexample_")
    n = r.counterexample["inputs"]["n"]
    import math
    m = n * n - n + 41
    assert n >= 12 and any(m % d == 0 for d in range(2, math.isqrt(m) + 1))  # a real composite value
    # reproducible: same cycle → same seed → same counterexample
    r2 = C.challenge_entry(art(), "euler_prime", cycle_id="cyc1", before_src=art(euler=False))
    assert r2.counterexample == r.counterexample and r2.seed == r.seed


def test_passes_true_identity_with_all_probe_families():
    r = C.challenge_entry(art(), "odd_sum", cycle_id="cyc1", before_src=art(odd=False))
    assert not r.blocked, (r.reason, r.counterexample)
    assert r.probes["boundary"] and r.probes["far"] and r.probes["sample"]
    assert r.trivial["g0"] == "nontrivial"
    assert r.ranges_tested["g0"] == {"n": [0, 19]}


def test_triviality_and_edges_are_caught():
    src = art()
    assert C.challenge_entry(src, "square_again").reason == "trivial:component:ring_tautology"
    assert C.challenge_entry(src, "const_pad").reason.startswith("trivial:")
    assert C.challenge_entry(src, "empty_window").reason == "trivial:vacuous_empty_range"
    assert C.challenge_entry(src, "guarded").reason.startswith(("trivial:vacuous_guard", "counterexample_"))
    assert C.challenge_entry(src, "counts").reason == "type_edge_non_bool"
    # the established domain is n>=1 (enabled entry) so n=0 is never probed → no false edge_error
    assert not C.challenge_entry(src, "inverse_tested").blocked
    assert C.challenge_entry(src, "odd_sum", before_src=src).reason == "no_op_submission"
    assert C.challenge_entry(src, "inverse").reason == "not_enabled"


def test_identity_trivial_helper():
    p = lambda s: ast.parse(s, mode="eval").body  # noqa: E731
    assert C.identity_trivial(p("a + b == b + a"), {"a", "b"}) == "ring_tautology"
    assert C.identity_trivial(p("x == x"), {"x"}) == "identical_sides"
    assert C.identity_trivial(p("2 + 2 == 4"), {"n"}) == "both_sides_constant"
    assert C.identity_trivial(p("f(n) == n * n"), {"n"}) == ""
    assert C.identity_trivial(p("(n + 1) ** 2 == n * n + 2 * n"), {"n"}) == ""  # false, not trivial


# ---------------------------------------------------------------- cannot approve / budget

def test_challenger_cannot_approve_anything():
    assert C.CAN_APPROVE is False
    r = C.challenge_entry(art(), "odd_sum", before_src=art(odd=False))
    assert r.approved is False and r.to_dict()["approved"] is False
    with pytest.raises(AttributeError):
        r.approved = True  # read-only property: no approve path
    src = open(C.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    fnames = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    risky = {f for f in fnames if any(w in f for w in ("approve", "accept", "authorize", "enable", "score"))}
    assert risky == {"approved"}  # the read-only property, which only ever returns False
    prop = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "approved")
    rets = [n for n in ast.walk(prop) if isinstance(n, ast.Return)]
    assert rets and all(isinstance(r.value, ast.Constant) and r.value.value is False for r in rets)
    # never imports the Oracle gate / authorize paths
    assert "gate_keep" not in src and "colony.authorize" not in src


def test_time_budget_is_respected_and_slow_is_not_a_block():
    t0 = time.monotonic()
    r = C.challenge_entry(art(), "slow", budget_s=0.8)
    assert time.monotonic() - t0 < 2.5
    assert not r.blocked and (r.budget_hit or r.inconclusive)


# ---------------------------------------------------------------- record / lesson / note / metrics

def test_block_writes_self_challenge_lesson_and_receipt_with_note(sandbox):
    r = C.challenge_entry(art(), "euler_prime", cycle_id="cyc9", before_src=art(euler=False))
    why = C.why_believe(r)
    row = C.record(r, why=why)
    assert row["why_believe"]["generated_by"] == "colony.challenger"
    assert row["why_believe"]["free_text_from_feeds"] is False
    assert "check_euler_prime" in row["why_believe"]["components"]
    assert "ranges tested" in row["why_believe"]["text"] and "Challenger BLOCKED" in row["why_believe"]["text"]
    lessons = [json.loads(l) for l in (sandbox / "lessons.jsonl").read_text().splitlines()]
    sc = [e for e in lessons if e.get("type") == "self_challenge"]
    assert sc and sc[-1]["decision"] == "block" and "euler_prime" in sc[-1]["what"]
    from colony.lessons import mutation_cooldown
    assert mutation_cooldown().reason("euler_prime").startswith("self_challenge:")
    # a pass writes a receipt but no lesson
    C.record(C.challenge_entry(art(), "odd_sum", cycle_id="cyc9", before_src=art(odd=False)))
    assert len([json.loads(l) for l in (sandbox / "lessons.jsonl").read_text().splitlines()]) == len(lessons)


def test_metrics_self_reject_and_post_challenger_kill_rate(sandbox):
    rows = [
        {"ts": "2026-10-09T07:00:00Z", "kind": "lemma_mutation", "target": "a", "cycle_id": "c1", "blocked": True,
         "reason": "counterexample_far", "counterexample": {"inputs": {"n": 47}}},
        {"ts": "2026-10-09T07:00:01Z", "kind": "lemma_mutation", "target": "b", "cycle_id": "c1", "blocked": False},
        {"ts": "2026-10-09T07:00:02Z", "kind": "claim", "target": "vandermonde", "cycle_id": "c1", "blocked": False},
        {"ts": "2026-10-09T07:00:03Z", "kind": "claim_component", "target": "x", "cycle_id": "c1", "blocked": True},
    ]
    oracle = [
        {"ts": "2026-10-09T06:00:00Z", "source": "conjecture_desk", "mutation": "old", "cycle_id": "c0", "passed": False},
        {"ts": "2026-10-09T06:00:01Z", "source": "conjecture_desk", "mutation": "old2", "cycle_id": "c0", "passed": True},
        {"ts": "2026-10-09T07:00:05Z", "source": "conjecture_desk", "mutation": "b", "cycle_id": "c1", "passed": True},
        {"ts": "2026-10-09T07:00:06Z", "source": "claim_pipeline", "mutation": "vandermonde", "cycle_id": "c1", "passed": False},
    ]
    m = C.metrics(rows=rows, oracle_rows=oracle, frontier_rows=[])
    assert m["challenged"] == 3 and m["blocked"] == 1 and m["self_reject_rate"] == round(1 / 3, 4)
    assert m["post_challenger_oracle_judged"] == 2 and m["post_challenger_oracle_kill_rate"] == 0.5
    assert m["pre_challenger_oracle_judged"] == 2 and m["pre_challenger_oracle_kill_rate"] == 0.5
    assert m["challenger_catches"][0]["target"] == "a" and m["can_approve"] is False


def test_metrics_stay_out_of_aggregate_fitness():
    import inspect
    from colony import fitness
    src = inspect.getsource(fitness.compute_fitness)
    assert "self_reject" not in src and "challenger" not in src


# ---------------------------------------------------------------- desk integration

def _desk(monkeypatch, sandbox, src_text, name):
    import colony.conjecture_desk as D
    import colony.exploration_budget as B
    import colony.lessons as L

    impl = sandbox / "lemma_impl.py"
    impl.write_text(src_text)
    monkeypatch.setattr(D, "LEMMA_IMPL", impl)
    monkeypatch.setattr(D, "KINEMATICS_IMPL", sandbox / "kin.py")
    monkeypatch.setattr(D, "BACKUP_DIR", sandbox / "b1")
    monkeypatch.setattr(D, "STEM_BACKUP_DIR", sandbox / "b2")
    monkeypatch.setattr(D, "_load_paper_themes", lambda limit=12: [])
    monkeypatch.setattr(D, "propose_from_themes", lambda *a, **k: [])
    scores = iter([{"score": 0.8, "ok": True, "n_hard_pass": 1}, {"score": 0.9, "ok": True, "n_hard_pass": 2}])
    monkeypatch.setattr(D, "run_lemma_bench", lambda: next(scores))
    monkeypatch.setattr(D, "all_snippets", lambda: [(name, "hard_enable", f"enable:{name}")])
    monkeypatch.setattr(D, "recent_revert_counts", lambda limit=30: {})
    monkeypatch.setattr(D, "_append_history", lambda r: None)
    monkeypatch.setattr(D, "_write_witness", lambda rs: None)
    monkeypatch.setattr(D, "_record_desk_bookkeeping", lambda **k: {})
    monkeypatch.setattr(L, "variant_mutation_snippets", lambda: [])
    monkeypatch.setattr(B, "pick_mutation_order", lambda c: list(c))
    import colony.authoring as A
    monkeypatch.setattr(A, "guide_authoring_active", lambda: False)
    return D, impl


def test_desk_withholds_broken_mutation_from_oracle(sandbox, monkeypatch):
    import colony.novelty_gate as NG
    import colony.oracle as O
    monkeypatch.setattr(O, "gate_keep", lambda **k: pytest.fail("Oracle must not see a self-rejected mutation"))
    monkeypatch.setattr(NG, "evaluate", lambda **k: pytest.fail("no judgment to gate"))
    D, impl = _desk(monkeypatch, sandbox, art(euler=False), "euler_prime")
    r = D.improve_once(cycle_id="cycD")
    assert r.decision == "revert" and r.self_rejected and "SELF-REJECT" in r.note
    assert r.why_believe and "Challenger BLOCKED" in r.why_believe["text"]
    assert "(\"euler_prime\", lambda: all(check_euler_prime(n) for n in range(0, 12)), False)" in impl.read_text()
    rows = [json.loads(l) for l in (sandbox / "self_challenge.jsonl").read_text().splitlines()]
    assert rows[-1]["blocked"] and rows[-1]["target"] == "euler_prime" and rows[-1]["kind"] == "lemma_mutation"


def test_desk_true_mutation_reaches_oracle_with_note(sandbox, monkeypatch):
    import colony.novelty_gate as NG
    import colony.oracle as O

    seen = {}

    class V:
        passed = True
        fitness_credit = True
        kills: list = []

    def gate(**k):
        seen.update(k)
        return "keep", V()

    monkeypatch.setattr(O, "gate_keep", gate)
    monkeypatch.setattr(NG, "evaluate", lambda **k: {"novel_to_commons": True, "kills": []})
    D, _impl = _desk(monkeypatch, sandbox, art(odd=False), "odd_sum")
    r = D.improve_once(cycle_id="cycT")
    assert seen.get("mutation") == "odd_sum" and r.decision == "keep" and not r.self_rejected
    assert r.why_believe["components"] == ["check_odd_sum"] and "not broken" in r.why_believe["text"]
