"""Hunt shadow — how P / ranking WOULD look if the colony were rewarded for the unknown. REPORT-ONLY.

Never changes P, scores, novelty kills, desk decisions or authorization: it reads the shortlist's
evaluated proposals and Oracle rows, and writes society/systems/hunt_shadow.json (overwritten; a
short bounded per-cycle history) plus shadow columns in the shortlist view.
Flag: COLONY_HUNT_SHADOW=0 turns it off (default on, logs only).

Rule 1 — unknown reward (replaces the novelty term in the shadow only):
  unknown = 1 if the target survived the Oracle in its own cycle AND is not textbook (not a desk
            catalog lemma / classical identity, live textbook_reuse < 0.34) AND is not in OEIS
            (OEIS-names novelty shadow, the shadow's own 0.75 flag line; "unchecked" when no
            corpus/row is available — then it is not treated as known)
  expected = s / (s + K): s = other distinct Oracle-passed targets in the same claim family
             (target minus trailing parameter tokens like _g4_2_6_w1); K = K_PRIOR prior strength,
             calibrated by evals/hunt/calibrate_k.py into colony/hunt_calibration.json (rule-of-
             succession ML; falls back to K_PRIOR_DEFAULT = 3 when the file is absent/invalid).
             A parameter sweep of a family that already passed many times is a fully expected result.
  u = unknown * (1 - expected)
Rule 2 — building blocks count only when combined:
  a catalog / textbook lemma earns combo = min(1, n / 2), n = distinct Oracle-passed AUTHORED claims
  that chain it (composed name authored_A__B, or "built from proven lemmas [...]" in a proposal);
  mere enabling earns 0.
Shadow P   = clip(P + 0.25 * (novelty_shadow - novelty_live))   (0.25 = P's novelty weight)
             novelty_shadow = u for authored claims, combo for building blocks.
Shadow rank = 0.6 * P_shadow + 0.2 * novelty_shadow + 0.2 * (builds_on | combo).
Rule 4 (near-miss tracking): per cycle, Oracle verdicts whose shifted held-out window failed and
kills with exactly one kill reason.
Rule 3 (pre-registered prediction scoring) is NOT implemented: the colony records no prediction
before a run, so scoring one would need a new desk hook (out of a report-only scope).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "society" / "systems" / "hunt_shadow.json"
NOVELTY_SHADOW = ROOT / "society" / "systems" / "novelty_shadow.json"
CALIBRATION = ROOT / "colony" / "hunt_calibration.json"
K_PRIOR_DEFAULT = 3.0


def load_k_prior(path: Path = CALIBRATION) -> float:
    """Named config param K (expected-discount prior strength); calibrated value or the default."""
    try:
        k = float(json.loads(path.read_text(encoding="utf-8"))["K_PRIOR"])
        return k if k > 0 else K_PRIOR_DEFAULT
    except Exception:  # noqa: BLE001
        return K_PRIOR_DEFAULT


K_PRIOR = load_k_prior()
OEIS_FLAG = 0.75
TEXTBOOK_KILL = 0.34
W_NOV_IN_P = 0.25
KEEP_CYCLES = 30
_COMPOSE_RE = re.compile(r"^authored_([a-z0-9_]+?)__([a-z0-9_]+?)(?:_w\d+)?$")
_PARAM = re.compile(r"^(g?\d+|w\d+)$")


def enabled() -> bool:
    return os.environ.get("COLONY_HUNT_SHADOW", "1") != "0"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def claim_family(target: str) -> str:
    toks = (target or "").split("_")
    while len(toks) > 1 and _PARAM.match(toks[-1]):
        toks.pop()
    return "_".join(toks)


def oeis_lookup_from_shadow_log(path: Path = NOVELTY_SHADOW):
    """target -> latest OEIS shadow textbook-reuse (None when never scored / corpus absent)."""
    try:
        rows = json.loads(path.read_text(encoding="utf-8")).get("rows") or []
    except Exception:  # noqa: BLE001
        rows = []
    last = {r.get("mutation"): r.get("shadow_textbook_reuse") for r in rows if r.get("status") == "ok"}

    def look(target: str) -> float | None:
        if target in last:
            return last[target]
        try:
            from colony.novelty_shadow import shadow_score
            r = shadow_score(target)
            return r.get("shadow_textbook_reuse") if r.get("status") == "ok" else None
        except Exception:  # noqa: BLE001
            return None
    return look


def chained_blocks(oracle_rows: list[dict[str, Any]], evals: list[dict[str, Any]]) -> dict[str, set[str]]:
    """block name -> distinct Oracle-passed authored claims that chain it."""
    passed = {o.get("mutation") for o in oracle_rows if o.get("passed") and o.get("mutation")}
    out: dict[str, set[str]] = {}
    for t in passed:
        m = _COMPOSE_RE.match(t or "")
        if m:
            for b in (m.group(1), m.group(2)):
                out.setdefault(b, set()).add(t)
    for e in evals:
        t = e.get("target") or ""
        if t.startswith("authored_") and t in passed:
            for b in e.get("building_blocks") or []:
                out.setdefault(b, set()).add(t)
    return out


def annotate(evals: list[dict[str, Any]], *, oracle_rows: list[dict[str, Any]], oeis=None) -> list[dict[str, Any]]:
    """Add ``hunt`` (shadow terms) to every evaluated proposal. Pure given inputs; P untouched."""
    oeis = oeis or oeis_lookup_from_shadow_log()
    passed = {o.get("mutation") for o in oracle_rows if o.get("passed") and o.get("mutation")}
    fam_pass: dict[str, set[str]] = {}
    for t in passed:
        fam_pass.setdefault(claim_family(t), set()).add(t)
    chains = chained_blocks(oracle_rows, evals)
    for e in evals:
        t = e.get("target") or ""
        why = " ".join(e.get("why_not") or [])
        surviving = bool(t) and "oracle" not in why
        nov_live = e.get("novelty_raw")
        textbook = bool(e.get("building_block")) or (nov_live is not None and 1.0 - float(nov_live) >= TEXTBOOK_KILL)
        o = oeis(t) if t else None
        in_oeis = o is not None and float(o) >= OEIS_FLAG
        sib = len(fam_pass.get(claim_family(t), set()) - {t})
        expected = sib / (sib + K_PRIOR)
        unknown = surviving and not textbook and not in_oeis
        if e.get("building_block"):
            n_ch = len(chains.get(t, set()))
            nov_s = min(1.0, n_ch / 2.0)
            third = nov_s
        else:
            n_ch = None
            nov_s = (1.0 - expected) if unknown else 0.0
            third = float(e.get("builds_on") or 0.0)
        P = e.get("P")
        Ps = None
        if P is not None:
            Ps = round(max(0.0, min(1.0, float(P) + W_NOV_IN_P * (nov_s - float(nov_live or 0.0)))), 4)
        e["hunt"] = {"unknown": bool(unknown), "in_oeis": in_oeis, "oeis_reuse": o,
                     "oeis_checked": o is not None, "family": claim_family(t), "siblings_passed": sib,
                     "expected": round(expected, 4), "novelty_shadow": round(nov_s, 4),
                     "chained_by": n_ch, "P_shadow": Ps,
                     "meets_bar_shadow": bool(Ps is not None and Ps >= 0.70 and
                                              all(w.startswith("P=") for w in (e.get("why_not") or []))),
                     "rank_shadow": round(0.6 * Ps + 0.2 * nov_s + 0.2 * third, 4) if Ps is not None else None}
    return evals


def near_misses(oracle_rows: list[dict[str, Any]], cycle_id: str) -> dict[str, Any]:
    rows = [o for o in oracle_rows if o.get("cycle_id") == cycle_id] if cycle_id else []
    sw_fail, near = [], []
    for o in rows:
        sw = (((o.get("sense") or {}).get("held_out") or {}).get("shifted_window") or {})
        if sw.get("applied") and sw.get("ok") is False:
            sw_fail.append(o.get("mutation"))
        if not o.get("passed") and len(o.get("kills") or []) == 1:
            near.append({"mutation": o.get("mutation"), "kill": (o.get("kills") or [""])[0][:80]})
    return {"oracle_rows": len(rows), "shifted_window_failures": sw_fail, "single_reason_kills": near}


def summarize(evals: list[dict[str, Any]], *, cycle_id: str = "", oracle_rows: list[dict[str, Any]] | None = None,
              top_n: int = 10) -> dict[str, Any]:
    bar = [e for e in evals if e.get("meets_bar")]
    act = sorted(bar, key=lambda e: (-(e.get("rank") or 0), e.get("id") or ""))
    act_pos = {e["id"]: i for i, e in enumerate(act, 1)}
    # shadow order over every proposal that clears the non-P bar conditions (P was computed)
    sh = sorted([e for e in evals if (e.get("hunt") or {}).get("rank_shadow") is not None],
                key=lambda e: (-(e["hunt"]["rank_shadow"] or 0), e.get("id") or ""))
    sh_pos = {e["id"]: i for i, e in enumerate(sh, 1)}
    sh_bar = {e["id"] for e in sh if e["hunt"]["meets_bar_shadow"]}
    moves = []
    for e in act + [x for x in sh if x["id"] not in act_pos]:
        a, s = act_pos.get(e["id"]), sh_pos.get(e["id"])
        moves.append({"id": e["id"], "target": e.get("target"), "actual_pos": a, "shadow_pos": s,
                      "meets_bar_shadow": e["id"] in sh_bar, "rank": e.get("rank"),
                      "rank_shadow": e["hunt"]["rank_shadow"],
                      "P": e.get("P"), "P_shadow": e["hunt"]["P_shadow"], "unknown": e["hunt"]["unknown"],
                      "building_block": e.get("building_block"), "expected": e["hunt"]["expected"]})
    unknown = [e for e in evals if (e.get("hunt") or {}).get("unknown")]
    return {"ts": _utc(), "cycle_id": cycle_id, "mode": "report_only",
            "n_meet_bar_actual": len(act), "n_meet_bar_shadow": len(sh_bar),
            "n_unknown_claims": len(unknown), "unknown_targets": sorted({e["target"] for e in unknown})[:20],
            "n_unknown_oeis_unchecked": sum(1 for e in unknown if not e["hunt"]["oeis_checked"]),
            "drop_out_of_bar": [m["id"] for m in moves if m["actual_pos"] and not m["meets_bar_shadow"]],
            "enter_bar": [m["id"] for m in moves if m["meets_bar_shadow"] and not m["actual_pos"]],
            "top_shadow": [m for m in sorted(moves, key=lambda m: m["shadow_pos"] or 10 ** 6) if m["shadow_pos"]][:top_n],
            "near_misses": near_misses(oracle_rows or [], cycle_id)}


def record(summary: dict[str, Any]) -> None:
    try:
        st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    except Exception:  # noqa: BLE001
        st = {}
    hist = [h for h in (st.get("history") or []) if h.get("cycle_id") != summary.get("cycle_id")]
    hist.append({k: summary[k] for k in ("ts", "cycle_id", "n_meet_bar_actual", "n_meet_bar_shadow",
                                         "n_unknown_claims", "drop_out_of_bar", "enter_bar")}
                | {"near_misses": {k: (len(v) if isinstance(v, list) else v)
                                   for k, v in summary["near_misses"].items()}})
    st = {"mode": "report_only", "note": "Shadow only: P, scores, novelty kills, desk decisions and "
          "authorization are unchanged. See colony/hunt_shadow.py for the rules.",
          "last": summary, "history": hist[-KEEP_CYCLES:]}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
