"""State-vector probe for the Athanor gate on lemma-desk changes (what the gate MEASURES).

The legacy probe looks only at the pass bit of checks present before and after, plus score/0.1.
Every desk keep adds one passing check with the score flat, so its dPhi is always 0 and the gate is
inert. This probe measures the colony's state before and after the change as ten blocks of honest,
normalised quantities; each block is one probe (one step of the trajectory), so a growing catalog
cannot dilute H7 the way the legacy per-check probe does.
Athanor's math is untouched: per probe dPhi = L2 distance between the before/after sub-vectors
divided by a calibrated scale, C = 1/(1+|dPhi|), H7 = share of probes
with C >= the profile threshold (0.75 for the conservative profile) and the profile's verdict rule (Governor.judge) as before.

Blocks (each is computed the same way for the before and the after state):
  checks_basic     pass bit per basic check; absent = 0.5 ("no evidence"), so adding or losing a
                   check moves 0.5 while flipping an existing result moves 1
  checks_catalog   pass bit per catalog (textbook) hard check
  checks_authored  pass bit per colony-authored hard check
  coverage         n_basic/14, n_catalog/28, n_authored/28 (the bench's headroom denominators)
  score            score, basic_comp, hard_comp, n_pass/n_checks
  tier_ok          ok, basic_ok, hard_ok
  runtime          log(bench seconds)                                (wall-clock; calibrated noise)
  structure        Athanor 2.5 AST structural distance to the before source (before = 0)
  novelty_mix      share of enabled hard checks that are textbook building blocks
  oracle_pattern   Oracle pass rate over the last 20 verdicts (before = without this change's
                   verdict, after = with it)
Fitness is NOT a block: the colony only computes fitness once per cycle, after the desk, so an
"after" value does not exist at gate time and copying the before value would fake zero drift.
Per-check numeric margins do not exist either: lemma checks return booleans.

Scales come from colony/trust/athanor_probe_calibration.json, produced by
evals/athanor_probe/calibrate.py on HISTORICAL desk changes (chronological tuning split only;
held-out split reported, never tuned on). Without that file the a-priori UNITS are used.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
CALIBRATION = Path(__file__).resolve().parent / "athanor_probe_calibration.json"
ORACLE_LOG = ROOT / "data" / "commons" / "oracle.jsonl"
PROBES = ("legacy", "state")
ORACLE_WINDOW = 20
BLOCKS = ("checks_basic", "checks_catalog", "checks_authored", "coverage", "score", "tier_ok",
          "runtime", "structure", "novelty_mix", "oracle_pattern")
ABSENT = 0.5  # a check that does not exist on one side: no evidence either way
# A-priori "one unit of change" per block = the largest drift still tolerated as coherent when the
# history shows less: one added check, 1/28 of hard headroom, 0.01 score, half a tier bit (so any
# ok-bit flip is incoherent), a 25% runtime change, 1% of the AST, one Oracle verdict in 20.
UNITS = {"checks_basic": ABSENT, "checks_catalog": ABSENT, "checks_authored": ABSENT, "coverage": 1.0 / 28.0,
         "score": 0.01, "tier_ok": 0.5, "runtime": math.log(1.25), "structure": 0.01,
         "novelty_mix": 0.01, "oracle_pattern": 1.0 / ORACLE_WINDOW}
COHERENT_LIMIT = 1.0 / 0.70 - 1.0   # dPhi at which C = 1/(1+dPhi) hits Athanor's 0.70 line


def coherent_limit(threshold: float = 0.70) -> float:
    """dPhi at which C = 1/(1+dPhi) equals the profile's per-step coherence line (its H7 threshold)."""
    return 1.0 / float(threshold) - 1.0


def probe_mode() -> str:
    m = (os.environ.get("COLONY_ATHANOR_PROBE") or "legacy").strip().lower()
    return m if m in PROBES else "legacy"


def _bb_kind(name: str) -> str | None:
    try:
        from colony.shortlist import building_block_kind
        return building_block_kind(name)
    except Exception:  # noqa: BLE001
        return None if name.startswith("authored_") else "catalog"


def _split_checks(checks: dict[str, Any]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {"basic": {}, "catalog": {}, "authored": {}}
    for k, v in (checks or {}).items():
        k = str(k)
        if k.startswith("basic:"):
            out["basic"][k] = float(bool(v))
        else:
            name = k[5:] if k.startswith("hard:") else k
            out["authored" if name.startswith("authored_") else "catalog"][k] = float(bool(v))
    return out


def _f(x: Any, default: float = 0.0) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


def oracle_windows(mutation: str, rows: list[dict[str, Any]] | None = None,
                   window: int = ORACLE_WINDOW) -> tuple[list[bool], list[bool]]:
    """(before, after) pass windows: after includes this change's own (latest) verdict if logged."""
    if rows is None:
        rows = []
        try:
            with ORACLE_LOG.open(encoding="utf-8") as fh:
                tail = fh.readlines()[-(window + 5):]
            for line in tail:
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass
        except OSError:
            rows = []
    passes = [bool(r.get("passed")) for r in rows]
    if rows and mutation and rows[-1].get("mutation") == mutation:
        return passes[:-1][-window:], passes[-window:]
    return passes[-window:], passes[-window:]


def _rate(xs: list[bool]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def state_blocks(before: dict[str, Any] | None, after: dict[str, Any] | None, *, src: str = "",
                 new_src: str = "", oracle: tuple[list[bool], list[bool]] | None = None,
                 structural: float | None = None) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """Aligned before/after sub-vectors for every block."""
    b, a = before or {}, after or {}
    sb, sa = _split_checks(b.get("checks") or {}), _split_checks(a.get("checks") or {})
    cur: dict[str, list[float]] = {}
    new: dict[str, list[float]] = {}
    for fam in ("basic", "catalog", "authored"):
        keys = sorted(set(sb[fam]) | set(sa[fam]))
        cur[f"checks_{fam}"] = [sb[fam].get(k, ABSENT) for k in keys]
        new[f"checks_{fam}"] = [sa[fam].get(k, ABSENT) for k in keys]

    def cov(s):  # counts in units of the bench's own headroom denominators (14 basic, 28 hard)
        return [len(s["basic"]) / 14.0, len(s["catalog"]) / 28.0, len(s["authored"]) / 28.0]

    def score(x, s):
        n_basic = len(s["basic"])
        n_hard = len(s["catalog"]) + len(s["authored"])
        hard_pass = sum(s["catalog"].values()) + sum(s["authored"].values())
        n = n_basic + n_hard
        return [_f(x.get("score")), min(1.0, n_basic / 14.0), min(1.0, hard_pass / 28.0) if n_hard else 0.0,
                (sum(s["basic"].values()) + hard_pass) / n if n else 0.0]

    def mix(s):
        on = [k[5:] for k, v in {**s["catalog"], **s["authored"]}.items() if v]
        return [sum(1 for n in on if _bb_kind(n)) / len(on) if on else 0.0]

    cur["coverage"], new["coverage"] = cov(sb), cov(sa)
    cur["score"], new["score"] = score(b, sb), score(a, sa)
    cur["tier_ok"] = [float(bool(b.get(k))) for k in ("ok", "basic_ok", "hard_ok")]
    new["tier_ok"] = [float(bool(a.get(k))) for k in ("ok", "basic_ok", "hard_ok")]
    cur["runtime"] = [math.log(max(_f(b.get("seconds"), 1e-3), 1e-3))]
    new["runtime"] = [math.log(max(_f(a.get("seconds"), 1e-3), 1e-3))]
    if structural is None:
        try:
            from colony.athanor_coherence import structural_distance
            structural = structural_distance(src, new_src) if (src or new_src) else 0.0
        except Exception:  # noqa: BLE001
            structural = 0.0
    cur["structure"], new["structure"] = [0.0], [float(structural)]
    cur["novelty_mix"], new["novelty_mix"] = mix(sb), mix(sa)
    ob, oa = oracle if oracle is not None else ([], [])
    cur["oracle_pattern"], new["oracle_pattern"] = [_rate(ob)], [_rate(oa)]
    return cur, new


STEPS = BLOCKS  # the probe set: one probe per block


def step_unit(step: str) -> float:
    return UNITS[step]


def block_drift(cur: dict[str, list[float]], new: dict[str, list[float]]) -> dict[str, float]:
    """Raw L2 distance per block (Athanor dPhi before scaling)."""
    return {k: math.sqrt(sum((y - x) ** 2 for x, y in zip(cur[k], new[k]))) for k in BLOCKS}


def load_calibration(path: Path | str | None = None) -> dict[str, Any]:
    try:
        cal = json.loads(Path(path or CALIBRATION).read_text(encoding="utf-8"))
        if all(float(cal["scales"][k]) > 0 for k in STEPS):
            return cal
    except Exception:  # noqa: BLE001
        pass
    return {"version": 0, "source": "a-priori units (no calibration file)",
            "scales": scales_from([], 0.0, tol=0.7, threshold=0.75)}


FLOAT_GUARD = 1.0 + 1e-6  # keeps a change sitting exactly on the C = 0.70 line on the coherent side


def scales_from(drifts: list[dict[str, float]], q: float, tol: float = 1.0,
                threshold: float = 0.70) -> dict[str, float]:
    """Calibration rule: scale_b = max(unit_b, q-quantile of block-b drift over the set) / (limit * tol),
    so a change at the set's q-quantile sits exactly on the profile's coherence line
    (C = threshold) at the live tolerance ``tol`` (the profile's adaptive floor)."""
    lim = coherent_limit(threshold)
    out = {}
    for k in STEPS:
        xs = sorted(float(d[k]) for d in drifts)
        qv = xs[min(len(xs) - 1, max(0, math.ceil(q * len(xs)) - 1))] if xs else 0.0
        out[k] = max(step_unit(k), qv) * FLOAT_GUARD / (lim * float(tol))
    return out


def state_probe(before: dict[str, Any] | None, after: dict[str, Any] | None, *, src: str = "",
                new_src: str = "", mutation: str = "", oracle: tuple[list[bool], list[bool]] | None = None,
                calibration: dict[str, Any] | None = None, structural: float | None = None) -> dict[str, Any]:
    """(current, candidate) probe vectors for Governor.judge (one coordinate per block, already
    divided by its scale) plus the raw per-block drift for the log."""
    cal = calibration or load_calibration()
    if oracle is None:
        oracle = oracle_windows(mutation)
    cur, new = state_blocks(before, after, src=src, new_src=new_src, oracle=oracle, structural=structural)
    raw = block_drift(cur, new)
    scaled = {k: raw[k] / float(cal["scales"][k]) for k in STEPS}
    return {"current": [0.0] * len(STEPS), "candidate": [scaled[k] for k in STEPS], "raw": raw,
            "scaled": scaled, "l2_raw": math.sqrt(sum(v * v for v in raw.values())),
            "calibration_version": cal.get("version")}
