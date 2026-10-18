"""Stage 3 — reward surprise, not passing (James 2026-10-18 11:06 AM ET). COLONY_SURPRISE=live|shadow|off.

Hunt / selection layer ONLY: it changes the hunt value the colony uses to ORDER candidates and to
size the keep REWARD in its exploration distribution (colony.hunt). It never touches fitness, P,
the Oracle, the 0.70 bar, desk keep/revert, the charter, TributeKeeper, Ceiling or Athanor.

Credit of a kept frontier conjecture (registry entry r of colony.frontier_conjectures):
    credit = family * unlikely * effort * (0 if explained)
  family   = hunt value K/(s+K) (s = earlier surprises of the same family; existing rule)
  unlikely = 1 - p, p = the colony's OWN pre-registered survival prediction recorded before the test
  effort   = falsification effort survived, log-scaled to [0, 1]:
             0.75 * log10(1 + held-out span) / log10(1 + SPAN_REF)
             + 0.25 * log2(1 + re-tests) / log2(1 + RETEST_REF)       (each part capped at 1)
  explained = the triviality filter flags it NOW (frontier_checks.still_new is False), or it is a
             known result / loose / OEIS-known (unknown = False), or the reference check explains it.
Any other authored check (sieve sweep, new data, compose) keeps its existing hunt value K/(s+K)
(a sweep of a family that already passed many times stays ~0).
shadow (code default): credits are computed and reported (society/systems/surprise_credit.json,
with the ranking check of past keeps); live: colony.hunt uses them.
"""
from __future__ import annotations

import ast
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "society" / "systems" / "surprise_credit.json"
DESK_HISTORY = ROOT / "society" / "benchmarks" / "conjecture_history.jsonl"
MODES = ("live", "shadow", "off")
SPAN_REF = 60000
RETEST_REF = 8
W_SPAN, W_RETEST = 0.75, 0.25
PREFIX = "authored_frontier_"


def mode() -> str:
    m = os.environ.get("COLONY_SURPRISE", "shadow").strip().lower()
    return m if m in MODES else "shadow"


def live() -> bool:
    return mode() == "live"


def effort(r: dict[str, Any]) -> float:
    lo, hi = (list(r.get("range") or [0, 0]) + [0, 0])[:2]
    hi = max(int(hi or 0), int(r.get("retested_to") or 0))
    span = max(0, hi - int(lo or 0))
    retests = int(r.get("retests") or (1 if r.get("retested_to") else 0))
    a = min(1.0, math.log10(1 + span) / math.log10(1 + SPAN_REF))
    b = min(1.0, math.log2(1 + retests) / math.log2(1 + RETEST_REF))
    return round(W_SPAN * a + W_RETEST * b, 4)


SEEDS = ("", ":1", ":2", ":3")


def trivial_any_seed(r: dict[str, Any]) -> bool | None:
    """The triviality filter's randomized rules (idle_part, shuffle-null, ...) depend on the seed;
    a claim counts as filter-explained when ANY of a few fixed seeds flags it."""
    try:
        from colony.frontier_checks import still_new
        sig = str(r.get("sig") or "x")
        return any(not still_new(dict(r, sig=sig + sd)) for sd in SEEDS)
    except Exception:  # noqa: BLE001
        return None


def explained(r: dict[str, Any], *, trivial: bool | None = None) -> str:
    """Why the claim earns zero ('' when it is not explained)."""
    if r.get("falsified_later"):
        return "falsified on re-test"
    ref = str(r.get("reference") or "")
    if ref.startswith("explained by"):
        return ref[:120]
    if not r.get("unknown"):
        return str(r.get("unknown_reason") or "not a surprise")[:120]
    if trivial is None:
        trivial = trivial_any_seed(r)
    if trivial:
        return "the current triviality filter explains it"
    return ""


def credit(r: dict[str, Any], *, trivial: bool | None = None) -> dict[str, Any]:
    p = r.get("prediction")
    p = 0.5 if p is None else float(p)
    fam = float(r.get("hunt_value") if r.get("hunt_value") is not None else 1.0)
    why = explained(r, trivial=trivial)
    unlikely, eff = round(1.0 - p, 4), effort(r)
    val = 0.0 if why else round(max(0.0, min(1.0, fam if fam > 0 else 1.0)) * unlikely * eff, 4)
    return {"credit": val, "unlikely": unlikely, "effort": eff, "family": round(fam, 4), "explained": why}


def _registry_by_name(state: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    from colony.frontier_checks import check_name
    from colony.frontier_conjectures import load_state
    st = state if state is not None else load_state()
    return {check_name(r): r for r in (st.get("registry") or {}).values() if r.get("sig")}


_CACHE: dict[str, Any] = {}


def value(name: str, base: float) -> float:
    """Hunt value of a candidate name: the surprise credit for authored frontier conjectures (live),
    ``base`` (the existing hunt value) for everything else."""
    if not name.startswith(PREFIX):
        return base
    if "reg" not in _CACHE:
        try:
            _CACHE["reg"] = _registry_by_name()
        except Exception:  # noqa: BLE001
            _CACHE["reg"] = {}
    r = _CACHE["reg"].get(name)
    if r is None:
        return base
    key = "c:" + name
    if key not in _CACHE:
        _CACHE[key] = credit(r)["credit"]
    return _CACHE[key]


def _claim_from_source(name: str, src: str) -> dict[str, Any] | None:
    try:
        fn = next((n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == f"check_{name}"), None)
        lit = next((x for x in ast.walk(fn) if isinstance(x, ast.Dict)), None) if fn else None
        return None if lit is None else ast.literal_eval(lit)
    except Exception:  # noqa: BLE001
        return None


def past_keeps() -> list[str]:
    out: list[str] = []
    try:
        for ln in DESK_HISTORY.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if r.get("decision") == "keep" and r.get("mutation") and r["mutation"] not in out:
                out.append(r["mutation"])
    except OSError:
        pass
    return out


def ranking_check(write: bool = True) -> dict[str, Any]:
    """Credit of every past kept check; a frontier keep is 'hand-proved trivial' when the current
    triviality filter (whose rules were hand-proved) or a known-result rule settles it. Pass when
    every hand-proved trivial keep ranks at or below every remaining surprise (ties allowed only at 0)."""
    from colony import hunt
    from colony.frontier_conjectures import load_state, predict
    st = load_state()
    reg = _registry_by_name(st)
    try:
        from colony.authoring import _lemma_impl
        src = _lemma_impl().read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        src = ""
    hv = hunt.Valuer()
    rows = []
    for n in past_keeps():
        if n.startswith(PREFIX):
            r = reg.get(n)
            src_note = "registry"
            if r is None:
                lit = _claim_from_source(n, src)
                if lit is None:
                    rows.append({"name": n, "kind": "frontier", "credit": None, "note": "claim not found"})
                    continue
                r = dict(lit, unknown=True, prediction=predict(lit["kind"], st), hunt_value=1.0)
                src_note = "lemma_impl literal (prediction re-derived: pre-registered value not kept)"
            c = credit(r, trivial=trivial_any_seed(r))
            rows.append({"name": n, "kind": "frontier", "statement": r.get("statement") or r.get("lhs"),
                         "hand_trivial": bool(c["explained"]), **c, "source": src_note})
        else:
            v = hv.value(n)
            rows.append({"name": n, "kind": "sieve" if n.startswith("authored_sieve_") else
                         ("newdata" if n.startswith("authored_newdata_") else "other"), "credit": round(v, 4)})
    hand = {}
    try:  # the Stage 2 calibration's record of which past surprises the hand-written rules settle
        cal = json.loads((ROOT / "society" / "frontier" / "refcheck_calibration.json").read_text(encoding="utf-8"))
        hand = {x["statement"]: not str(x.get("hand_rule_now") or "").startswith("(none") for x in cal.get("rows") or []}
    except Exception:  # noqa: BLE001
        pass
    for r in rows:
        if r["kind"] == "frontier" and r.get("statement") in hand:
            r["hand_settled_in_calibration"] = hand[r["statement"]]
    fr = [r for r in rows if r["kind"] == "frontier" and r.get("credit") is not None]
    cal_t = [r["credit"] for r in fr if r.get("hand_settled_in_calibration") is True]
    cal_s = [r["credit"] for r in fr if r.get("hand_settled_in_calibration") is False]
    triv = [r["credit"] for r in fr if r["hand_trivial"]]
    sur = [r["credit"] for r in fr if not r["hand_trivial"]]
    ok = (not triv or not sur) or max(triv) <= min(sur)
    rows.sort(key=lambda r: -(r.get("credit") or 0))
    out = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "mode": mode(),
           "n_keeps": len(rows), "n_frontier": len(fr), "n_hand_trivial": len(triv), "n_surprise": len(sur),
           "max_trivial_credit": max(triv) if triv else None, "min_surprise_credit": min(sur) if sur else None,
           "trivial_ranked_lowest": ok,
           "calibration_check": {"hand_settled": len(cal_t), "still_surprise": len(cal_s),
                                 "max_hand_settled_credit": max(cal_t) if cal_t else None,
                                 "min_still_surprise_credit": min(cal_s) if cal_s else None,
                                 "hand_settled_ranked_lowest": (not cal_t or not cal_s) or max(cal_t) <= min(cal_s)},
           "sieve_mean_credit": round(sum(r["credit"] for r in rows if r["kind"] == "sieve") /
                                      max(1, sum(1 for r in rows if r["kind"] == "sieve")), 4),
           "rows": rows,
           "rule": {"span_ref": SPAN_REF, "retest_ref": RETEST_REF, "w_span": W_SPAN, "w_retest": W_RETEST}}
    if write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    res = ranking_check()
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))
    for r in res["rows"]:
        print(f"{r.get('credit')!s:>7}  {r['kind']:9} {r['name'][:48]:48} {str(r.get('explained') or '')[:60]}")
