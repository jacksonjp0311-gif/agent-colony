"""Item 104: bounded new-data scheduler (aging, bounded exploration, cost hypothesis, chunks with
safe checkpoints, CPU + wall budgets, strict reuse keys, schedule invariance). Deterministic:
fake clocks and a fake two-method runner; no network, no live state."""
from __future__ import annotations

import json

import pytest

from colony import work_scheduler as W


class Clock:
    def __init__(self):
        self.cpu = 0.0
        self.wall = 0.0


def truth(target, n):
    return (n * n + len(target)) % 1009


def make(costs=None, *, poison=None, wall_extra=None, cliff=None, **kw):
    """costs[target] = (prefix coefficient per hi**1.2, per-unit) seconds."""
    clk = Clock()
    costs = costs or {}

    def runner(job, lo, hi):
        pre, unit = costs.get(job.target, (0.0, 1e-3))
        u = unit * (cliff[1] if cliff and job.target == cliff[0] and hi > cliff[2] else 1)
        c_pre = pre * hi ** W.PREFIX_EXP
        clk.cpu += c_pre + u * (hi - lo)
        clk.wall += c_pre + u * (hi - lo) + (wall_extra or {}).get(job.target, 0.0)
        vals = {n: truth(job.target, n) for n in range(lo, hi)}
        if poison and job.target == poison[0] and lo <= poison[1] < hi:
            return {"verified": False, "why": "method_b_disagrees"}
        return {"verified": True, "values": vals, "parts": {"prefix_s": c_pre}}
    s = W.Scheduler(runner, clock_cpu=lambda: clk.cpu, clock_wall=lambda: clk.wall, **kw)
    return s, clk


def test_mode_default_shadow_off_on_control_and_no_live(monkeypatch):
    monkeypatch.delenv("COLONY_WORK_SCHED", raising=False)
    assert W.mode() == "shadow"
    monkeypatch.setenv("COLONY_WORK_SCHED", "live")
    assert W.mode() == "shadow"          # live is not wired (claims per chunk): never silently on
    monkeypatch.setenv("COLONY_WORK_SCHED", "off")
    assert W.mode() == "off"
    monkeypatch.delenv("COLONY_WORK_SCHED")
    monkeypatch.setenv("COLONY_ARM", "control")
    assert W.mode() == "off"


def test_chunks_resume_and_cover_goal_with_budgets_respected():
    s, _ = make({"a": (0.0, 1e-3)})
    s.admit("t", "a", "m", 0, 5000)
    for c in range(10):
        r = s.run_cycle(1.0, 1.0, cycle=c)
        assert not r["over_cpu"] and not r["over_wall"]
    j = s.jobs[0]
    assert j.status == "done" and j.cursor == 5000
    assert len(s.results.values) == 5000
    assert all(s.results.values[W.reuse_key("t", "a", "m", n)] == truth("a", n) for n in range(5000))
    assert s.cycle_overruns_cpu == 0 and s.cycle_overruns_wall == 0


def test_wall_budget_binds_even_when_cpu_is_free():
    s, _ = make({"io": (0.0, 1e-4)}, wall_extra={"io": 0.3})
    s.admit("t", "io", "m", 0, 100000)
    for c in range(5):
        s.run_cycle(10.0, 1.0, cycle=c)
    # the measured wall cost per chunk is learned: after the first probe no cycle exceeds wall
    assert s.cycle_overruns_wall <= 1
    walls = [r["wall_s"] for r in s.receipts if "wall_s" in r]
    assert walls and max(walls) < 1.0


def test_aging_serves_old_job_despite_cheap_hog():
    s, _ = make({"hog": (0.0, 1e-6), "old": (0.0, 1e-3)}, explore_share=0.0)
    old = s.admit("t", "old", "m", 0, 10 ** 6, value=1.0)
    s.admit("t", "hog", "m", 0, 10 ** 9, value=1000.0)
    old.k_cpu = {"prefix": 0.0, "unit": 1e-3}       # both measured: pure value order would starve "old"
    s.jobs[1].k_cpu = {"prefix": 0.0, "unit": 1e-6}
    s.run_cycle(1.0, 1.0, cycle=0, max_picks=W.AGE_BOUND + 2)
    whys = [(r["job"].split("|")[1], r["why"]) for r in s.receipts if "why" in r]
    assert ("old", "aging") in whys
    assert whys.index(("old", "aging")) <= W.AGE_BOUND


def test_starvation_counts_only_when_a_younger_job_is_served():
    s, _ = make({"a": (0.0, 1e-3), "b": (0.0, 1e-3)}, explore_share=0.0)
    a = s.admit("t", "a", "m", 0, 10 ** 6, value=1.0)
    b = s.admit("t", "b", "m", 0, 10 ** 6, value=1.0)
    a.k_cpu = b.k_cpu = {"prefix": 0.0, "unit": 1e-3}
    s.run_cycle(1.0, 1.0, cycle=0, max_picks=1)
    # equal value: the oldest goes first and the younger one does not count a starved tick
    assert s.receipts[-1]["job"].split("|")[1] == "a"
    assert b.starved == 0


def test_exploration_is_bounded():
    s, _ = make({f"j{i}": (0.0, 1e-2) for i in range(20)}, explore_share=0.1)
    for i in range(20):
        s.admit("t", f"j{i}", "m", 0, 100)
    s.run_cycle(1.0, 1.0, cycle=0)
    spent = sum(r["cpu_s"] for r in s.receipts if r.get("why") == "explore")
    last = max((r["cpu_s"] for r in s.receipts if r.get("why") == "explore"), default=0)
    assert spent <= 0.1 + last + 1e-9          # at most one pick past the share


def test_crash_between_accept_and_checkpoint_never_double_counts():
    s, _ = make({"a": (0.0, 1e-3)})
    j = s.admit("t", "a", "m", 0, 2000)
    s.crash_after_accept.add((j.id, 0))
    for c in range(6):
        s.run_cycle(1.0, 1.0, cycle=c)
    assert any(r.get("crashed_before_checkpoint") for r in s.receipts)
    assert s.results.duplicates > 0
    assert len(s.results.values) == 2000 and j.status == "done"


def test_method_disagreement_quarantines_and_retracts():
    s, _ = make({"p": (0.0, 1e-3)}, poison=("p", 500))
    s.admit("t", "p", "m", 0, 2000)
    for c in range(4):
        s.run_cycle(1.0, 1.0, cycle=c)
    j = s.jobs[0]
    assert j.status == "quarantined" and j.why == "method_b_disagrees"
    assert not any(k.split("|")[1] == "p" for k in s.results.values)   # nothing kept from it


def test_conflicting_recomputation_is_refused():
    r = W.Results()
    j = W.Job("t", "a", "m", 0, 10, 0)
    assert r.accept(j, {1: 5, 2: 6}) == {"accepted": 2, "duplicate": 0, "conflict": 0}
    assert r.accept(j, {1: 5}) == {"accepted": 0, "duplicate": 1, "conflict": 0}
    assert r.accept(j, {2: 7, 3: 1}) == {"accepted": 0, "duplicate": 0, "conflict": 1}
    assert r.values[W.reuse_key("t", "a", "m", 2)] == 6 and W.reuse_key("t", "a", "m", 3) not in r.values


def test_duplicate_admission_is_one_job():
    s, _ = make()
    a = s.admit("t", "x", "m", 0, 100)
    b = s.admit("t", "x", "m", 0, 300)
    assert a is b and len(s.jobs) == 1 and a.goal == 300
    c = s.admit("t", "x", "other_method", 0, 100)
    assert c is not a                       # strict key: another method tag is another question


def test_schedule_invariance_across_budgets_orders_and_chunk_shares():
    costs = {"a": (1e-7, 1e-4), "b": (0.0, 5e-4), "c": (2e-7, 2e-4)}
    finals = []
    for cpu, order, share in ((1.0, "abc", 0.5), (0.3, "cba", 0.2), (2.0, "bac", 0.9)):
        s, _ = make(costs, chunk_share=share)
        for t in order:
            s.admit("t", t, "m", 0, 3000)
        for c in range(40):
            s.run_cycle(cpu, cpu, cycle=c)
        finals.append(dict(s.results.values))
    common = set(finals[0]) & set(finals[1]) & set(finals[2])
    assert common and all(len({f[k] for f in finals}) == 1 for k in common)
    assert all(f[k] == truth(k.split("|")[1], int(k.split("|")[3])) for f in finals for k in f)


def test_snapshot_restore_resumes_cursor_and_results():
    s, clk = make({"a": (0.0, 1e-3)})
    s.admit("t", "a", "m", 0, 3000)
    s.run_cycle(0.5, 0.5, cycle=0)
    cur = s.jobs[0].cursor
    assert 0 < cur < 3000
    snap = json.loads(json.dumps(s.snapshot()))
    s2 = W.Scheduler.restore(snap, s.runner, clock_cpu=lambda: clk.cpu, clock_wall=lambda: clk.wall)
    assert s2.jobs[0].cursor == cur and len(s2.results.values) == cur
    for c in range(1, 10):
        s2.run_cycle(0.5, 0.5, cycle=c)
    assert s2.jobs[0].status == "done" and len(s2.results.values) == 3000


def test_over_budget_job_is_parked_visibly_and_reopens():
    s, _ = make({"big": (0.0, 1.0)})        # 1 s per unit: min chunk 8 s
    s.admit("t", "big", "m", 0, 100)
    s.run_cycle(1.0, 1.0, cycle=0)          # probe runs (cost unknown): counted overrun
    s.run_cycle(1.0, 1.0, cycle=1)
    assert s.jobs[0].status == "over_budget"
    assert any(r.get("event") == "parked_over_budget" for r in s.receipts)
    s.run_cycle(100.0, 100.0, cycle=2)      # a bigger budget: it fits again
    assert any(r.get("event") == "reopened" for r in s.receipts)


def test_cost_hypothesis_needs_evidence_before_driving_plans():
    m = W.CostModel()
    j = W.Job("t", "a", "m", 0, 10, 0)
    assert m.predict(j, 0, 8)[2] == "none"
    m.observe(j, 0, 8, 0.008, 0.008)
    assert m.predict(j, 8, 16)[2] == "conservative_max"
    assert not m.smoothed_accepted("t")
    m.err_smooth["t"] = [0.1] * W.HYP_MIN_SAMPLES
    m.err_job["t"] = [0.5] * W.HYP_MIN_SAMPLES
    assert m.smoothed_accepted("t") and m.predict(j, 8, 16)[2] == "smoothed"
    assert m.report()["t"]["smoothed_accepted"] is True


def test_receipts_are_append_only_and_separate(tmp_path):
    p = tmp_path / "work_receipts.jsonl"
    assert W.append_receipts([{"a": 1}], p) == 1
    assert W.append_receipts([{"b": 2}], p) == 1
    assert [json.loads(x) for x in p.read_text().splitlines()] == [{"a": 1}, {"b": 2}]
    assert W.RECEIPTS.name == "work_receipts.jsonl" and "claims" not in str(W.RECEIPTS)


def test_shadow_view_is_read_only_counts():
    idx = {"entries": {"A1": {"anum": "A1", "status": "matched", "done_for_sha": "x"},
                       "A2": {"anum": "A2", "status": "matched", "intractable": "big"},
                       "A3": {"anum": "A3", "status": "matched"}},
           "sparse": {"A4": {"status": "matched", "claimed": True}}}
    before = json.dumps(idx, sort_keys=True)
    v = W.shadow_view(idx)
    assert v["eligible"] == 1 and v["intractable"] == ["A2"] and v["done"] == 1 and v["sparse_eligible"] == 0
    assert json.dumps(idx, sort_keys=True) == before


@pytest.mark.parametrize("bad", [MemoryError, ValueError])
def test_runner_failure_quarantines_without_accepting(bad):
    def runner(job, lo, hi):
        raise bad()
    s = W.Scheduler(runner)
    s.admit("t", "x", "m", 0, 100)
    s.run_cycle(1.0, 1.0)
    assert s.jobs[0].status == "quarantined" and not s.results.values
