"""Item 93: holdout_v3 raises held-out n (24 candidates, 10 paired seeds). Only adds evidence:
no gate, threshold or scoring rule changes; every arm sees the same pool; manifest pinned."""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "evaluation"
sys.path.insert(0, str(EVAL))

import evaluator_v3 as E3  # noqa: E402


def _pool(name):
    return json.loads((EVAL / "pools" / name / "candidates.json").read_text())["candidates"]


def _labels(name):
    return json.loads((EVAL / "pools" / name / "labels.json").read_text())["labels"]


def test_larger_n_and_balanced_design():
    labels = _labels("holdout_v3")
    assert len(labels) == 24 and len(labels) > max(len(_labels("holdout_v1")), len(_labels("holdout_v2")))
    kinds = [v["label"] for v in labels.values()]
    assert kinds.count("sound_useful") == 12 and kinds.count("unsound") == 8 and kinds.count("trivial") == 4
    assert all(v["witness"] for v in labels.values() if v["label"] == "unsound")


def test_independent_evaluator_agrees_with_every_label():
    j = E3.judge_pool("holdout_v3")
    assert set(j) == set(_labels("holdout_v3"))
    assert all(v["agree"] for v in j.values()), {k: v for k, v in j.items() if not v["agree"]}
    assert any(v["found_by"] == "witness" for v in j.values())  # the escape-by-design one


def test_every_candidate_passes_its_own_coded_window():
    """The colony only sees the coded window; unsound ones must look green there."""
    for c in _pool("holdout_v3"):
        g = {"math": math}
        exec(c["helpers_src"], g)  # noqa: S102 — committed pool source, not web code
        exec(c["check_src"], g)  # noqa: S102
        assert g["check_" + c["name"]]() is True, c["name"]


def test_families_and_names_unseen():
    seen_fams = {v["family"] for p in ("dev", "holdout_v1", "holdout_v2") for v in _labels(p).values()}
    v3 = _labels("holdout_v3")
    assert not ({v["family"] for v in v3.values()} & seen_fams)
    lemma_src = (ROOT / "society" / "benchmarks" / "artifacts" / "lemma_impl.py").read_text()
    lemma_names = set(re.findall(r"def check_([a-z0-9_]+)", lemma_src))
    for name, v in v3.items():
        assert name not in lemma_src
        assert v["family"] not in lemma_names


def test_manifest_pins_v3_and_harness_defaults():
    man = (EVAL / "MANIFEST.sha256").read_text()
    for f in ("build_pools_v3.py", "evaluator_v3.py", "pools/holdout_v3/candidates.json", "pools/holdout_v3/labels.json"):
        assert f in man
    sys.path.insert(0, str(ROOT / "scripts"))
    import trust_experiments as T
    assert T.EV("holdout_v3") is E3 and len(T.SEEDS_V3) == 10 and T.SEEDS == [11, 23, 37, 41, 53]
    from colony.trust.gate import manifest_check
    assert manifest_check(ROOT)["ok"]
