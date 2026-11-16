"""Item 80: self-build pipeline (blueprints of flow components, trials vs baseline and twin).

Fixture-only: fake desks, tmp state/log paths, no network, no live run state.
"""
from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

import colony.self_build as SB


# --------------------------------------------------------------------------- fakes

def _menu(n=6):
    forms = ["gf", "relation", "property"]
    return [{"id": f"oc_A{100000 + i}_0", "anum": f"A{100000 + i}", "claim": {"form": forms[i % 3]}}
            for i in range(n)]


class FakeOEIS:
    STATE = Path("unused")

    def __init__(self, menu=None, live=True, attempts=None):
        self.menu = _menu() if menu is None else menu
        self.live = live
        self.calls = []
        self.attempts = attempts or []
        self.state = {"targets": {}, "families": {"gf": {"credit": 1.0, "attempts": 1}}}

    def mode(self):
        return "live" if self.live else "shadow"

    def load_menu(self):
        return list(self.menu)

    def _load(self, path, default):
        return self.state

    def choose(self, menu, state, cycle_id, k=4, *, forms=None, beyond_bfile=False):
        pool = [e for e in menu if (forms is None or e["claim"]["form"] in forms)]
        if beyond_bfile:
            pool = [e for e in pool if e["claim"]["form"] != "relation"]
        return pool[:k]

    def load_attempt_log(self):
        return {"attempts": list(self.attempts)}

    def planned_depth(self, e, prior):
        return 100 + int(e["anum"][1:]) % 7

    def run_cycle(self, cycle_id, **kw):
        self.calls.append(kw)
        ids = kw.get("only_ids") or [e["id"] for e in self.menu[: kw.get("k") or 1]]
        return {"chosen": [{"id": i} for i in ids]}


class FakeFrontier:
    def __init__(self):
        self.calls = 0

    def mode(self):
        return "live"

    def run_cycle(self, cycle_id, seed=None):
        self.calls += 1
        return {"counts": {"expressions": 10}}


class FakeNewData:
    INDEX = Path("unused")

    def __init__(self, open_n=0):
        self.open_n = open_n

    def mode(self):
        return "live"

    def _load(self, path, default):
        return {"entries": {str(i): {"status": "matched"} for i in range(self.open_n)}}

    def _done(self, e):
        return False

    def run_cycle(self, cycle_id, budget_s=40.0):
        return {"pushed": [1]}


def _auth(free):
    return types.SimpleNamespace(MAX_AUTHORED_TOTAL=150, authored_count=lambda: 150 - free)


def _ctx(oeis=None, free=0, nd=0, exclude=()):
    return SB.Context("c1", oeis=oeis or FakeOEIS(), frontier=FakeFrontier(), new_data=FakeNewData(nd),
                      authoring=_auth(free), exclude_ids=exclude)


def _row(tp, td, cp, cd, cycles=3):
    return {"paired": True, "cycles_this_run": cycles,
            "treatment": {"oracle_passes": tp, "verified_depth_sum": td},
            "control": {"oracle_passes": cp, "verified_depth_sum": cd}}


NO_EV = {name: {"boost": 1.0} for name in SB.COMPONENTS}


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.setenv("COLONY_SELF_MOD", "on")
    st, log = tmp_path / "self_build.json", tmp_path / "blueprint_log.jsonl"
    monkeypatch.setattr(SB, "STATE_PATH", st)
    monkeypatch.setattr(SB, "LOG_PATH", log)
    monkeypatch.setattr(SB, "IDEAS_PATH", tmp_path / "architecture_ideas.jsonl")
    return st, log


# --------------------------------------------------------------------------- validation

def test_default_blueprint_is_empty_like_control():
    assert SB.DEFAULT_BLUEPRINT["steps"] == []
    assert SB.empty_state()["active"]["steps"] == []


def test_validate_bounds_unknown_heavy_and_macros():
    ok = SB.make_blueprint([{"component": "oeis_extra_pass", "n": 2}])
    assert SB.validate(ok) == (True, "ok")
    assert not SB.validate(SB.make_blueprint([{"component": "rm_rf", "n": 1}]))[0]
    assert not SB.validate(SB.make_blueprint([{"component": "oeis_extra_pass", "n": 9}]))[0]
    two_heavy = SB.make_blueprint([{"component": "frontier_extra_batch", "n": 1}] * 2)
    assert SB.validate(two_heavy)[1] == "too_many_heavy"
    big = SB.make_blueprint([{"component": "oeis_extra_pass", "n": 3}] * 3)
    assert SB.validate(big)[1] == "too_large"
    macros = {"macro_x": {"steps": [{"component": "oeis_extra_pass", "n": 1},
                                    {"component": "oeis_replay_buffer", "n": 1}]}}
    assert SB.validate(SB.make_blueprint([{"component": "macro_x", "n": 1}]), macros) == (True, "ok")
    nested = {"macro_y": {"steps": [{"component": "macro_x", "n": 1}]}, **macros}
    assert not SB.validate(SB.make_blueprint([{"component": "macro_y", "n": 1}]), nested)[0]


def test_consensus_needs_quorum():
    ballots = {"a": ["x", "y", "z", "w"], "b": ["x", "z", "y", "w"], "c": ["w", "y", "x", "z"]}
    assert SB.consensus(ballots, 1, 2) == ["x"]
    assert SB.consensus(ballots, 2, 3) == ["x", "y"] or SB.consensus(ballots, 2, 3)[0] == "x"
    assert SB.consensus({"a": ["x"], "b": ["y"]}, 2, 2) == []


# --------------------------------------------------------------------------- self-test and run

def test_self_test_rejects_dead_steps_and_accepts_live_ones():
    ctx = _ctx(oeis=FakeOEIS(menu=[]), free=0, nd=0)
    for name in SB.COMPONENTS:
        bp = SB.make_blueprint([{"component": name, "n": 1}])
        res = SB.self_test(bp, ctx)
        assert not res["ok"] and res["reason"].startswith("dead_step"), name
    live = _ctx(free=2, nd=3)
    for name in SB.COMPONENTS:
        if name in ("oeis_replay_buffer", "oeis_prediction_error"):
            continue  # need recent gain / planned depths in the attempt log
        assert SB.self_test(SB.make_blueprint([{"component": name, "n": 1}]), live)["ok"], name


def test_shadow_oeis_mode_makes_oeis_steps_dead():
    ctx = _ctx(oeis=FakeOEIS(live=False))
    assert not SB.self_test(SB.make_blueprint([{"component": "oeis_extra_pass", "n": 1}]), ctx)["ok"]


def test_replay_buffer_uses_recent_gain_and_excludes_self_heal_targets():
    menu = _menu(4)
    attempts = [{"id": menu[2]["id"], "extended": 50}, {"id": menu[1]["id"], "extended": 5},
                {"id": menu[0]["id"], "extended": 500}]
    oeis = FakeOEIS(menu=menu, attempts=attempts)
    ctx = _ctx(oeis=oeis, exclude=[menu[0]["id"]])
    out = SB.run_blueprint(SB.make_blueprint([{"component": "oeis_replay_buffer", "n": 2}]), ctx)
    assert out["actions"] == 2
    assert oeis.calls[-1]["only_ids"] == [menu[2]["id"], menu[1]["id"]]


def test_steps_do_not_repeat_targets_within_a_cycle():
    oeis = FakeOEIS(menu=_menu(3))
    ctx = _ctx(oeis=oeis)
    bp = SB.make_blueprint([{"component": "oeis_extra_pass", "n": 2},
                            {"component": "oeis_consensus_vote", "n": 2}])
    SB.run_blueprint(bp, ctx)
    first, second = oeis.calls[0]["only_ids"], oeis.calls[1]["only_ids"]
    assert not set(first) & set(second)


def test_frontier_batch_only_with_free_slot_under_unchanged_cap():
    ctx = _ctx(free=0)
    out = SB.run_blueprint(SB.make_blueprint([{"component": "frontier_extra_batch", "n": 1}]), ctx)
    assert out["actions"] == 0 and "150" in out["ran"][0]["skipped"]
    ctx2 = _ctx(free=1)
    out2 = SB.run_blueprint(SB.make_blueprint([{"component": "frontier_extra_batch", "n": 1}]), ctx2)
    assert out2["actions"] == 1 and ctx2.frontier.calls == 1


def test_budget_stops_later_steps():
    ctx = _ctx()
    bp = SB.make_blueprint([{"component": "oeis_extra_pass", "n": 1}, {"component": "oeis_extra_pass", "n": 2}])
    out = SB.run_blueprint(bp, ctx, budget_s=0.0)
    assert all(r.get("skipped") == "cycle_budget" for r in out["ran"])


# --------------------------------------------------------------------------- generator

def test_candidates_are_deterministic_and_skip_tried():
    st = SB.empty_state()
    a = SB.candidates(st, NO_EV)
    b = SB.candidates(st, NO_EV)
    assert [c["id"] for c in a] == [c["id"] for c in b]
    st["tried"][a[0]["signature"]] = {"outcome": "reverted", "steps": a[0]["steps"]}
    assert a[0]["id"] not in {c["id"] for c in SB.candidates(st, NO_EV)}


def test_architecture_ideas_raise_component_weight(tmp_path):
    ideas = tmp_path / "ideas.jsonl"
    ideas.write_text("".join(json.dumps({"event": "architecture_idea", "idea": "swarm_topology",
                                         "arxiv_id": f"2611.{i:05d}"}) + "\n" for i in range(4)))
    ev = SB.evidence(ideas=SB.load_ideas(ideas), cards=[], lessons=[])
    assert ev["oeis_consensus_vote"]["n_papers"] == 4
    top = SB.candidates(SB.empty_state(), ev)[0]
    assert top["steps"][0]["component"] == "oeis_consensus_vote"
    # absent item-79 file is simply no evidence
    assert SB.load_ideas(tmp_path / "missing.jsonl") == []


def test_mutation_operators_cover_resize_remove_swap_crossover_macro():
    st = SB.empty_state()
    st["active"] = SB.make_blueprint([{"component": "oeis_extra_pass", "n": 1},
                                      {"component": "oeis_replay_buffer", "n": 1}])
    st["tried"]["k"] = {"outcome": "kept", "steps": [{"component": "new_data_extra_push", "n": 1}]}
    st["macros"]["macro_ab"] = {"steps": [{"component": "oeis_form_router", "n": 1},
                                          {"component": "oeis_beyond_bfile", "n": 1}]}
    ops = {c["operator"] for c in SB.candidates(st, NO_EV)}
    assert {"add", "resize", "remove", "swap", "crossover", "use_macro"} <= ops


def test_propose_returns_first_candidate_passing_self_test():
    ctx = _ctx(oeis=FakeOEIS(menu=[]), free=1, nd=0)
    bp, rejected = SB.propose(SB.empty_state(), ctx, NO_EV)
    assert bp is not None and bp["steps"] == [{"component": "frontier_extra_batch", "n": 1}]
    assert all(r["reason"].startswith("dead_step") for r in rejected)
    ctx2 = _ctx(oeis=FakeOEIS(menu=[]), free=0, nd=1)
    bp2, rejected2 = SB.propose(SB.empty_state(), ctx2, NO_EV)
    assert bp2["steps"] == [{"component": "new_data_extra_push", "n": 1}]
    assert rejected2 and all(r["reason"].startswith("dead_step") for r in rejected2)


# --------------------------------------------------------------------------- scoring

def test_decide_needs_strictly_better_than_baseline_and_twin():
    assert SB.decide((0, 5), (0, 1))["keep"]
    assert not SB.decide((0, 1), (0, 1))["keep"]           # tie with baseline
    assert not SB.decide((0, 0), (0, -3))["keep"]          # better than baseline, not twin
    assert not SB.decide((-1, 900), (-2, 0))["keep"]       # control gained more passes
    assert SB.decide((1, -10), (0, 50))["keep"]            # passes outrank depth
    assert SB.decide(None, (0, 0))["reason"] == "no_paired_window"


def test_gain_is_treatment_minus_control_over_window():
    rows = [_row(10, 100, 10, 50), _row(10, 120, 10, 60), _row(11, 130, 10, 60)]
    assert SB.gain(rows, 0, 2) == (1.0, 20.0)
    assert SB.window_rows(rows) == 2
    assert SB.gain(rows, 1, 5) is None


# --------------------------------------------------------------------------- lifecycle

def _run(n, board, ctx, heal=None):
    out = None
    for i in range(n):
        out = SB.run_cycle(f"c{i}", ctx=ctx, board=board, heal=heal or {}, ev=NO_EV)
    return out


def test_control_arm_is_a_no_op(paths, monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    assert SB.run_cycle("c", ctx=_ctx(free=1), board={}, heal={}, ev=NO_EV)["skipped"]
    assert not paths[0].exists() and not paths[1].exists()


def test_no_trial_while_self_heal_trial_open(paths):
    out = SB.run_cycle("c", ctx=_ctx(free=1), board={"history": []}, heal={"trial": {"knob": "x"}}, ev=NO_EV)
    assert out["opened"] is None and out["last_skip"]["reason"] == "self_heal_trial_open"


def test_trial_kept_when_strictly_better_then_active_and_logged(paths):
    st_path, log = paths
    rows = [_row(5, 100, 5, 100), _row(5, 101, 5, 100), _row(5, 102, 5, 100)]  # baseline gain (0, 2)
    board = {"history": list(rows)}
    ctx = _ctx(oeis=FakeOEIS(menu=[]), free=1)
    out = SB.run_cycle("c0", ctx=ctx, board=board, heal={}, ev=NO_EV)
    assert out["opened"]["baseline_gain"] == [0.0, 2.0]
    assert SB.blocks_self_heal(SB.load_state())
    board["history"] += [_row(6, 110, 5, 100), _row(7, 120, 5, 100)]
    for i in range(1, SB.WINDOW_CYCLES + 1):
        out = SB.run_cycle(f"c{i}", ctx=ctx, board=board, heal={}, ev=NO_EV)
        if out["closed"]:
            break
    assert out["closed"]["outcome"] == "kept"
    st = SB.load_state()
    assert st["active"]["steps"] == [{"component": "frontier_extra_batch", "n": 1}]
    assert st["kept_count"] == 1 and st["component_stats"]["frontier_extra_batch"]["kept"] == 1
    events = [json.loads(x)["event"] for x in log.read_text().splitlines()]
    assert events[:2] == ["blueprint_trial_open", "blueprint_trial_close"]
    rows_logged = [json.loads(x) for x in log.read_text().splitlines()]
    assert all(r["authorized"] is False and r["human_signoff_required"] is False for r in rows_logged)
    assert rows_logged[1]["parent"] == "bp_default"


def test_trial_reverted_when_not_better(paths):
    rows = [_row(5, 100, 5, 100)] * 3
    board = {"history": list(rows)}
    ctx = _ctx(oeis=FakeOEIS(menu=[]), free=1)
    SB.run_cycle("c0", ctx=ctx, board=board, heal={}, ev=NO_EV)
    board["history"] += [_row(5, 100, 5, 100)] * 2
    out = _run(SB.WINDOW_CYCLES, board, ctx)
    st = SB.load_state()
    assert st["active"]["id"] == "bp_default" and st["reverted_count"] == 1
    assert any(v["outcome"] == "reverted" for v in st["tried"].values())
    assert out is not None


def test_trial_inconclusive_without_paired_rows(paths):
    board = {"history": [_row(5, 100, 5, 100)]}
    ctx = _ctx(oeis=FakeOEIS(menu=[]), free=1)
    SB.run_cycle("c0", ctx=ctx, board=board, heal={}, ev=NO_EV)
    _run(SB.INCONCLUSIVE_CYCLES, board, ctx)
    st = SB.load_state()
    assert st["inconclusive_count"] == 1 and st["active"]["id"] == "bp_default"


def test_kept_multi_step_blueprint_becomes_macro(paths):
    st = SB.empty_state()
    bp = SB.make_blueprint([{"component": "oeis_extra_pass", "n": 1}, {"component": "new_data_extra_push", "n": 1}])
    bp["added"] = bp["steps"]
    st["trial"] = {"blueprint": bp, "opened_cycle_index": 0, "open_row": 0, "window_rows": 1,
                   "baseline_gain": [0, 0]}
    st["cycle_index"] = SB.WINDOW_CYCLES
    board = {"history": [_row(1, 1, 1, 1), _row(1, 9, 1, 1)]}
    row = SB._close(st, board, "cX", write=False, log_path=None)
    assert row["outcome"] == "kept" and len(st["macros"]) == 1
    (name, macro), = st["macros"].items()
    assert macro["steps"] == bp["steps"]


def test_log_is_append_only(paths):
    _, log = paths
    SB.append_log({"event": "a"})
    first = log.read_text()
    SB.append_log({"event": "b"})
    assert log.read_text().startswith(first)


def test_dry_run_does_not_write(paths, monkeypatch):
    st_path, log = paths
    out = SB.run_cycle("c", ctx=_ctx(free=1), board={}, heal={}, ev=NO_EV, write=False, execute=False)
    assert out["proposal"] is not None and out["opened"] is not None
    assert not st_path.exists() and not log.exists()


def test_society_runs_self_build_stage_and_self_heal_waits():
    import inspect
    import colony.society as S
    import colony.self_heal as SH
    assert '"self_build"' in inspect.getsource(S.Society.run_cycle)
    assert "self_build_trial_open" in inspect.getsource(SH.run_cycle)


def test_self_heal_skips_proposal_while_blueprint_trial_open(monkeypatch):
    import colony.self_heal as SH
    monkeypatch.setattr(SB, "blocks_self_heal", lambda state=None: True)
    called = []
    monkeypatch.setattr(SH, "propose_trial", lambda *a, **k: called.append(1))
    out = SH.run_cycle("c1", metrics={}, stall_state={}, findings=[])
    assert not called
    assert (out.get("trial_skip") or {}).get("reason") == "self_build_trial_open"


# --------------------------------------------------------------------------- item-79 idea blocks

def _ideas_file(tmp_path, counts):
    f = tmp_path / "architecture_ideas.jsonl"
    rows = []
    for idea, n in counts.items():
        rows += [json.dumps({"event": "architecture_idea", "idea": idea,
                             "arxiv_id": f"{idea}.{i}"}) + "\n" for i in range(n)]
    f.write_text("".join(rows))
    return f


TOP_IDEAS = {"swarm_topology": 13, "self_model_calibration": 4, "specialist_routing": 4,
             "novelty_archive": 3, "prediction_error_routing": 2}


def test_every_top_idea_has_a_building_block():
    covered = {i for spec in SB.COMPONENTS.values() for i in spec["ideas"]}
    assert set(TOP_IDEAS) <= covered


def test_first_blueprints_are_seeded_from_top_ranked_ideas(tmp_path):
    ev = SB.evidence(ideas=SB.load_ideas(_ideas_file(tmp_path, TOP_IDEAS)), cards=[], lessons=[])
    order = [c["steps"][0]["component"] for c in SB.candidates(SB.empty_state(), ev) if c["steps"][0]["n"] == 1]
    assert order[0] == "oeis_consensus_vote"                       # swarm_topology, 13 papers
    assert order[1] == "oeis_swarm_improvers"   # item 85: same 13 papers, new-component prior 0.95
    assert set(order[2:4]) == {"oeis_calibrated_vote", "oeis_form_router"}  # 4 papers each
    assert order.index("oeis_novelty_archive") < order.index("oeis_extra_pass")
    assert order.index("oeis_prediction_error") < order.index("oeis_extra_pass")
    # with a live pool the swarm block is the first trial proposed
    bp, _ = SB.propose(SB.empty_state(), _ctx(), ev)
    assert bp["steps"] == [{"component": "oeis_consensus_vote", "n": 1}]


def test_novelty_prediction_error_and_calibrated_blocks_pick_targets():
    menu = _menu(6)
    attempts = [{"id": menu[0]["id"], "form": "gf", "planned": 100, "verified_depth": 40},
                {"id": menu[3]["id"], "form": "gf", "planned": 100, "verified_depth": 99},
                {"id": menu[1]["id"], "form": "relation", "planned": 50, "verified_depth": 50},
                {"id": menu[4]["id"], "form": "relation", "planned": 50, "verified_depth": 60}]
    ctx = _ctx(oeis=FakeOEIS(menu=menu, attempts=attempts))
    # property form never attempted -> novelty archive goes there first
    assert SB._pick_novelty(ctx, 1) == [menu[2]["id"]]
    assert SB._pick_prediction_error(ctx, 2) == [menu[0]["id"], menu[4]["id"]]
    # relation predictions came true 2/2, gf 0/2 -> calibrated vote prefers relation targets
    top = SB._pick_calibrated(ctx, 2)
    assert all(e["claim"]["form"] == "relation" for e in menu if e["id"] in top)


def test_flat_baseline_does_not_block_opening_and_twin_decides(paths):
    board = {"history": [_row(5, 100, 5, 100)] * 3}   # flat: no signal in the baseline window
    ctx = _ctx(oeis=FakeOEIS(menu=[]), free=1)
    out = SB.run_cycle("c0", ctx=ctx, board=board, heal={}, ev=NO_EV)
    assert out["opened"] is not None and out["opened"]["baseline_gain"] == [0.0, 0.0]
    board["history"] += [_row(5, 104, 5, 100), _row(5, 108, 5, 100)]
    _run(SB.WINDOW_CYCLES, board, ctx)
    assert SB.load_state()["kept_count"] == 1


def test_item85_swarm_improvers_vote_over_one_shared_pool():
    """Item 85 (top-ranked idea swarm_topology): the improver flows each rank the one shared
    pool and a Borda vote with a quorum picks; it is an ordinary blueprint component, so it is
    only ever kept through the trial machinery (strictly better than baseline and twin)."""
    menu = _menu(6)
    attempts = [{"id": menu[0]["id"], "form": "gf", "planned": 100, "verified_depth": 40},
                {"id": menu[3]["id"], "form": "gf", "planned": 100, "verified_depth": 99},
                {"id": menu[1]["id"], "form": "relation", "planned": 50, "verified_depth": 50},
                {"id": menu[4]["id"], "form": "relation", "planned": 50, "verified_depth": 60}]
    ctx = _ctx(oeis=FakeOEIS(menu=menu, attempts=attempts))
    ballots = SB.improver_ballots(ctx)
    assert {"novelty", "prediction_error", "calibrated", "consensus"} <= set(ballots)
    pool_ids = {e["id"] for e in menu}
    assert all(set(b) <= pool_ids for b in ballots.values())  # one shared pool
    picks = SB._pick_swarm(ctx, 2)
    assert 1 <= len(picks) <= 2 and set(picks) <= pool_ids
    assert picks == SB._pick_swarm(ctx, 2)  # deterministic
    assert SB._plan_oeis(ctx, "oeis_swarm_improvers", 2) == len(picks)
    spec = SB.COMPONENTS["oeis_swarm_improvers"]
    assert "swarm_topology" in spec["ideas"] and spec["max_n"] == 3 and not spec["heavy"]
    ok, _ = SB.validate(SB.make_blueprint([{"component": "oeis_swarm_improvers", "n": 1}]))
    assert ok
    empty = _ctx(oeis=FakeOEIS(menu=[]))
    assert SB.improver_ballots(empty) == {} and SB._pick_swarm(empty, 2) == []
