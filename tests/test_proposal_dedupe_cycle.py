"""One proposal per fingerprint per cycle (no '(cycle N)' twin of the same seek target)."""
from types import SimpleNamespace

from colony.emergence.growth_steps_evolve import dedupe_specs_this_cycle
from colony.emergence.growth import GrowthResult
from colony.fitness import proposal_fingerprint


def test_fingerprint_ignores_cycle_suffix():
    a = proposal_fingerprint("Chain `x_y` citing P", "seek_enable:x_y")
    assert a == proposal_fingerprint("Chain `x_y` citing P (cycle 383)", "seek_enable:x_y")
    assert a != proposal_fingerprint("Chain `x_y` citing P", "seek_enable:other")


def test_second_path_same_fingerprint_dropped():
    g = SimpleNamespace()
    first = dedupe_specs_this_cycle(g, [{"title": "Chain `x_y` citing P", "action": "seek_enable:x_y"},
                                        {"title": "Chain `x_y` citing P", "action": "seek_enable:x_y"},
                                        {"title": "Other", "action": "mandate:z"}])
    assert [s["title"] for s in first] == ["Chain `x_y` citing P", "Other"]
    # later path in the same cycle (with the "(cycle N)" suffix) is dropped
    assert dedupe_specs_this_cycle(g, [{"title": "Chain `x_y` citing P (cycle 9)", "action": "seek_enable:x_y"}]) == []


def test_new_cycle_object_starts_clean():
    g1, g2 = SimpleNamespace(), SimpleNamespace()
    spec = [{"title": "T", "action": "a"}]
    assert dedupe_specs_this_cycle(g1, spec) and dedupe_specs_this_cycle(g2, spec)


def test_growth_result_accepts_fps():
    g = GrowthResult.__new__(GrowthResult)
    dedupe_specs_this_cycle(g, [{"title": "T", "action": "a"}])
    assert dedupe_specs_this_cycle(g, [{"title": "T", "action": "a"}]) == []
