import json
import math

from colony import hunt_shadow as H
from evals.hunt import calibrate_k as C


def test_k_loaded_from_calibration_file(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"K_PRIOR": 0.25}))
    assert H.load_k_prior(p) == 0.25


def test_k_falls_back_to_default(tmp_path):
    assert H.load_k_prior(tmp_path / "missing.json") == H.K_PRIOR_DEFAULT
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"K_PRIOR": -1}))
    assert H.load_k_prior(bad) == H.K_PRIOR_DEFAULT


def test_repo_calibration_matches_module():
    cal = json.loads(H.CALIBRATION.read_text())
    assert math.isclose(H.K_PRIOR, float(cal["K_PRIOR"]))
    assert cal["split"] and cal["held_out"]["logloss_per_event"]


def test_fit_recovers_rate_and_is_interior():
    # family members with s prior keeps; 1 surprise in 20 at s=1 -> K ~ 1/19
    ev = [("f", 1, 0, i == 0, "t") for i in range(20)]
    f = C.fit(ev)
    assert not f["at_grid_edge"]
    assert 0.03 < f["K"] < 0.09


def test_first_members_do_not_inform_k():
    ev = [("f", 0, 0, True, "t")] * 5 + [("g", 2, 0, False, "t")] * 5 + [("g", 2, 0, True, "t")]
    assert C.loglik(ev, 1.0) == C.loglik([e for e in ev if e[1] > 0], 1.0)
