"""Calibrate the state-probe scales on HISTORICAL desk changes (Athanor seed discipline).

Split (chronological, fixed before looking at results): the oldest 60% of replayed historical
changes are the TUNING set, the newest 40% are HELD-OUT. Synthetic controls inherit the split
of the change they were built from. Only tuning rows ever choose anything.

Candidate quantiles q in QS. For each q: scale_b = max(unit_b, q-quantile of block-b drift over
TUNING Oracle-passed keeps) / ((1/tau - 1) * live tolerance floor 0.7), tau = 0.75 (the profile's per-step C line). Every row is then judged with the gate's real math
(Governor.judge via athanor_gate.profile_verdict, conservative profile selfmod/adaptive@1.1.0,
adaptive tolerance from the row's own before-score).
Selection rule (decided up front): the smallest q whose TUNING block rate on Oracle-passed keeps
is <= MAX_TUNING_BLOCK (anti-freeze guard); ties impossible (q is ordered). The held-out numbers
are reported for that q and never fed back.
Writes colony/trust/athanor_probe_calibration.json and docs/ATHANOR_PROBE_TUNING_LOG.md.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from colony.athanor_coherence import ADAPTIVE_PROFILES, CONSERVATIVE_PROFILE  # noqa: E402
from colony.trust.athanor_gate import profile_verdict  # noqa: E402
from colony.trust.athanor_probe import STEPS as BLOCKS, UNITS, scales_from, step_unit, veto_check, veto_thresholds_from  # noqa: E402

REPLAY = Path(__file__).resolve().parent / "replay.jsonl"
OUT = ROOT / "colony" / "trust" / "athanor_probe_calibration.json"
LOG = ROOT / "docs" / "ATHANOR_PROBE_TUNING_LOG.md"
QS = (0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.99, 1.00)
TUNING_SHARE = 0.60
MAX_TUNING_BLOCK = 0.10
TH = float(ADAPTIVE_PROFILES[CONSERVATIVE_PROFILE]["threshold_h7"])  # per-step C line = H7 threshold
TOL = float(ADAPTIVE_PROFILES[CONSERVATIVE_PROFILE].get("adaptive_floor", 1.0))  # live tolerance floor
CONTROLS = ("bulk_enable", "drop_checks", "slow", "break_one")


def effective(r: dict) -> bool:
    """A control counts only if the mechanical edit really perturbed something beyond the target."""
    nb, na = r["n_checks"]
    v = r["variant"]
    if v == "bulk_enable":
        return na - nb >= 3
    if v == "drop_checks":
        return na - nb <= -2
    if v == "break_one":
        return not r["after_ok"]
    if v == "slow":
        return r["seconds"][1] >= r["seconds"][0] + 0.5
    return True


def judge(r: dict, scales: dict[str, float], profile: str = CONSERVATIVE_PROFILE) -> dict:
    e = max(0.0, 1.0 - float(r.get("before_score") or 0.0))
    cand = [r["drift"][k] / scales[k] for k in BLOCKS]
    return profile_verdict(profile, cand, e_cur=e, e_best=e, step=10 ** 6)


def legacy_judge(r: dict, profile: str = CONSERVATIVE_PROFILE) -> dict:
    e = max(0.0, 1.0 - float(r.get("before_score") or 0.0))
    return profile_verdict(profile, r["legacy_behaviour"], e_cur=e, e_best=e, step=10 ** 6)


def _rate(xs):
    return round(sum(xs) / len(xs), 4) if xs else None


def evaluate(rows: list[dict], scales: dict[str, float]) -> dict:
    out = {}
    clean = [r for r in rows if r["variant"] == "historical" and r["decision"] == "keep" and r.get("oracle_passed")]
    vs = [judge(r, scales) for r in clean]
    out["oracle_passed_keeps"] = len(clean)
    out["block_rate_oracle_passed_keeps"] = _rate([v["verdict"] != "APPROVE" for v in vs])
    out["dphi_nonzero_share"] = _rate([any(r["drift"][k] > 0 for k in BLOCKS) for r in clean])
    out["h7_min"] = round(min((v["h7"] for v in vs), default=1.0), 4)
    hist: dict[int, int] = {}
    for v in vs:
        n = round((1.0 - v["h7"]) * len(BLOCKS))
        hist[n] = hist.get(n, 0) + 1
    out["incoherent_probes_histogram"] = {str(k): hist[k] for k in sorted(hist)}
    dm = sorted(v["dphi_max"] for v in vs)
    out["dphi_max_quartiles"] = [round(dm[int(f * (len(dm) - 1))], 4) for f in (0, .25, .5, .75, 1)] if dm else []
    for c in CONTROLS:
        cc = [r for r in rows if r["variant"] == c and effective(r)]
        out[f"control_{c}_n"] = len(cc)
        out[f"control_{c}_caught"] = _rate([judge(r, scales)["verdict"] != "APPROVE" for r in cc])
    allc = [r for r in rows if r["variant"] in CONTROLS and effective(r)]
    out["control_all_caught"] = _rate([judge(r, scales)["verdict"] != "APPROVE" for r in allc])
    out["legacy_control_all_caught"] = _rate([legacy_judge(r)["verdict"] != "APPROVE" for r in allc])
    out["legacy_block_rate_oracle_passed_keeps"] = _rate([legacy_judge(r)["verdict"] != "APPROVE" for r in clean])
    return out


VETO_GRID = [(m, q) for m in (1.5, 2.0, 3.0, 4.0) for q in (0.90, 0.95, 0.99)]   # strictest first
MAX_TUNING_VETO = 0.10
DERIVED = ("score_inflate_0.05", "runtime_x5", "swap_8_same_count")


def derived_controls(rows: list[dict]) -> list[dict]:
    """Single-area alarms built from each historical Oracle-passed keep (vector-level, labelled synthetic)."""
    import math
    out = []
    for r in rows:
        if not (r["variant"] == "historical" and r["decision"] == "keep" and r.get("oracle_passed")):
            continue
        d = dict(r["drift"])
        sb, sa = r["seconds"]
        out.append({**r, "variant": "score_inflate_0.05", "drift": {**d, "score": math.hypot(d["score"], 0.05)}})
        out.append({**r, "variant": "runtime_x5", "seconds": [sb, sa * 5],
                    "drift": {**d, "runtime": abs(math.log(max(sa * 5, 1e-3)) - math.log(max(sb, 1e-3)))}})
        out.append({**r, "variant": "swap_8_same_count",
                    "drift": {**d, "checks_authored": math.hypot(d["checks_authored"], math.sqrt(16 * 0.25))}})
    return out


def gate_blocks(r: dict, scales: dict, vcal: dict | None) -> tuple[bool, bool]:
    h = judge(r, scales)["verdict"] != "APPROVE"
    v = bool(vcal) and veto_check(r["drift"], seconds_before=r["seconds"][0], seconds_after=r["seconds"][1],
                                  calibration={"veto": vcal})["vetoed"]
    return h, v


def veto_eval(rows: list[dict], scales: dict, vcal: dict) -> dict:
    clean = [r for r in rows if r["variant"] == "historical" and r["decision"] == "keep" and r.get("oracle_passed")]
    out = {"veto_rate_oracle_passed_keeps": _rate([gate_blocks(r, scales, vcal)[1] for r in clean]),
           "combined_block_rate_oracle_passed_keeps": _rate([any(gate_blocks(r, scales, vcal)) for r in clean])}
    for c in CONTROLS + DERIVED:
        cc = [r for r in rows if r["variant"] == c and (c in DERIVED or effective(r))]
        hv = [gate_blocks(r, scales, vcal) for r in cc]
        out[c] = {"n": len(cc), "h7_only": _rate([h for h, _ in hv]), "veto": _rate([v for _, v in hv]),
                  "combined": _rate([h or v for h, v in hv])}
    return out


def main() -> None:
    rows = [json.loads(l) for l in REPLAY.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if not r.get("error")]
    hist = sorted({r["idx"] for r in rows if r["variant"] == "historical"})
    cut = hist[int(len(hist) * TUNING_SHARE)]
    tune = [r for r in rows if r["idx"] < cut]
    held = [r for r in rows if r["idx"] >= cut]
    tune_clean = [r["drift"] for r in tune if r["variant"] == "historical" and r["decision"] == "keep" and r.get("oracle_passed")]
    table = []
    for q in QS:
        sc = scales_from(tune_clean, q, tol=TOL, threshold=TH)
        table.append({"q": q, "scales": sc, "tuning": evaluate(tune, sc), "held_out": evaluate(held, sc)})
    tune = tune + derived_controls(tune)
    held = held + derived_controls(held)
    ok = [t for t in table if (t["tuning"]["block_rate_oracle_passed_keeps"] or 0) <= MAX_TUNING_BLOCK]
    chosen = ok[0] if ok else table[-1]
    vtable = []
    for m, q in VETO_GRID:
        vcal = {"q": q, "m": m, "runtime_abs_floor_s": 0.5,
                "thresholds": veto_thresholds_from(tune_clean, q, m)}
        vtable.append({"m": m, "q": q, "cal": vcal, "tuning": veto_eval(tune, chosen["scales"], vcal),
                       "held_out": veto_eval(held, chosen["scales"], vcal)})
    vok = [t for t in vtable if (t["tuning"]["veto_rate_oracle_passed_keeps"] or 0) <= MAX_TUNING_VETO]
    vchosen = vok[0] if vok else vtable[-1]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    first = lambda rr: min(r["ts"] for r in rr)  # noqa: E731
    last = lambda rr: max(r["ts"] for r in rr)  # noqa: E731
    cal = {"version": 1, "calibrated_at": ts, "source": "evals/athanor_probe/calibrate.py on replay.jsonl",
           "profile": CONSERVATIVE_PROFILE, "threshold_h7": ADAPTIVE_PROFILES[CONSERVATIVE_PROFILE]["threshold_h7"],
           "q": chosen["q"], "coherent_limit": 1.0 / TH - 1.0, "tolerance_floor": TOL, "units": UNITS,
           "scales": dict(chosen["scales"]),  # full precision: a clean change sits exactly on the line
           "rule": "smallest q with tuning block rate on Oracle-passed keeps <= %.2f" % MAX_TUNING_BLOCK,
           "split": {"tuning": [len(tune), first(tune), last(tune)], "held_out": [len(held), first(held), last(held)]},
           "tuning": chosen["tuning"], "held_out": chosen["held_out"], "fallback_to_last_q": not ok,
           "veto": {**vchosen["cal"], "rule": "strictest (m, q) in VETO_GRID with tuning veto rate on Oracle-passed "
                                             "keeps <= %.2f; runtime also needs >= 0.5 s absolute" % MAX_TUNING_VETO,
                    "tuning": vchosen["tuning"], "held_out": vchosen["held_out"], "fallback": not vok}}
    OUT.write_text(json.dumps(cal, indent=2) + "\n", encoding="utf-8")
    L = ["# Athanor state-probe tuning log", "",
         f"Calibrated {ts} by `evals/athanor_probe/calibrate.py` from `evals/athanor_probe/replay.jsonl` "
         "(built by `evals/athanor_probe/replay.py`: every recorded hard_enable desk decision replayed for real "
         "from git history, plus mechanical perturbation controls).", "",
         f"- Split (chronological, fixed up front): tuning = {len(tune)} rows {first(tune)} .. {last(tune)}; "
         f"held-out = {len(held)} rows {first(held)} .. {last(held)} (UTC).",
         f"- Judge: Governor.judge, profile `{CONSERVATIVE_PROFILE}` (H7 >= {cal['threshold_h7']} to APPROVE, "
         "adaptive tolerance from the change's own before-score). Math unchanged; only the probe is new.",
         f"- Rule: {cal['rule']}. Chosen q = {chosen['q']}.", "",
         "| q | tuning block % (Oracle-passed keeps) | held-out block % | tuning controls caught | held-out controls caught | held-out legacy controls caught |",
         "|---:|---:|---:|---:|---:|---:|"]
    for t in table:
        L.append(f"| {t['q']} | {t['tuning']['block_rate_oracle_passed_keeps']} | {t['held_out']['block_rate_oracle_passed_keeps']} | "
                 f"{t['tuning']['control_all_caught']} | {t['held_out']['control_all_caught']} | {t['held_out']['legacy_control_all_caught']} |")
    L += ["", "Chosen q, per control (held-out; n = effective controls): " + ", ".join(
        f"{c} {chosen['held_out'][f'control_{c}_caught']} (n={chosen['held_out'][f'control_{c}_n']})" for c in CONTROLS),
        "", "Scales (raw L2 drift that maps to dPhi = 1 at tolerance 1; the q-quantile clean change sits on C = tau at the live tolerance floor):", ""]
    L += [f"- `{k}`: {v:.6f} (unit {step_unit(k):.4f})" for k, v in cal["scales"].items()]
    for nm in ("tuning", "held_out"):
        c = chosen[nm]
        L.append(f"- {nm}: Oracle-passed keeps {c['oracle_passed_keeps']}, incoherent probes per change "
                 f"{c['incoherent_probes_histogram']} (of {len(BLOCKS)}), dPhi_max quartiles {c['dphi_max_quartiles']}, "
                 f"min H7 {c['h7_min']}")
    L += ["", "Legacy probe on the same held-out Oracle-passed keeps: block rate "
          f"{chosen['held_out']['legacy_block_rate_oracle_passed_keeps']}; state probe share with nonzero dPhi "
          f"{chosen['held_out']['dphi_nonzero_share']}.", ""]
    L += ["## Per-area hard veto", "",
          "Added check beside Athanor's verdict (math unchanged): veto when one area's raw drift exceeds "
          "max(m*unit, m*q-quantile of that area over TUNING Oracle-passed keeps); runtime additionally needs "
          ">= 0.5 s absolute slow-down. Rule: " + cal["veto"]["rule"] + f". Chosen m = {vchosen['m']}, q = {vchosen['q']}.", "",
          "| m | q | tuning veto % (keeps) | held-out veto % (keeps) | held-out combined block % (keeps) |",
          "|---:|---:|---:|---:|---:|"]
    for t in vtable:
        L.append(f"| {t['m']} | {t['q']} | {t['tuning']['veto_rate_oracle_passed_keeps']} | "
                 f"{t['held_out']['veto_rate_oracle_passed_keeps']} | {t['held_out']['combined_block_rate_oracle_passed_keeps']} |")
    L += ["", "Chosen veto, controls caught (H7 only / veto / combined):", "",
          "| control | tuning n | tuning | held-out n | held-out |", "|---|---:|---|---:|---|"]
    for c in CONTROLS + DERIVED:
        a, b = vchosen["tuning"][c], vchosen["held_out"][c]
        L.append(f"| {c} | {a['n']} | {a['h7_only']} / {a['veto']} / {a['combined']} | {b['n']} | "
                 f"{b['h7_only']} / {b['veto']} / {b['combined']} |")
    L += ["", "Veto thresholds (raw drift): " + ", ".join(f"`{k}` {v:.4f}" for k, v in vchosen["cal"]["thresholds"].items()), ""]
    LOG.write_text("\n".join(L), encoding="utf-8")
    print(json.dumps({"q": chosen["q"], "tuning": chosen["tuning"], "held_out": chosen["held_out"]}, indent=1))
    for t in vtable:
        print("veto", t["m"], t["q"], t["tuning"]["veto_rate_oracle_passed_keeps"], t["held_out"]["veto_rate_oracle_passed_keeps"],
              {c: t["held_out"][c]["combined"] for c in CONTROLS + DERIVED})
    for t in table:
        print(t["q"], t["tuning"]["block_rate_oracle_passed_keeps"], t["held_out"]["block_rate_oracle_passed_keeps"],
              t["tuning"]["control_all_caught"], t["held_out"]["control_all_caught"])


if __name__ == "__main__":
    main()
