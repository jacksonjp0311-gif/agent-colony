"""H₇ residual diagnosis — tools/report ONLY (h7-diagnosis).

Instruments why Athanor H₇ stays in REFINE (~0.54 historically).
Looks at residuals variance, κ bound, cusp vs weighted, APPROVE/REFINE/REJECT dist.

NO behavior scripting. NO durable-accept double-gate. Diagnostics only —
leave the city free to use the report.
Not AGI. Not consciousness.
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from colony.athanor_coherence import (
    DEFAULT_H7_THRESHOLD,
    DEFAULT_REFINE_FLOOR,
    CoherenceGovernor,
    estimate,
    residuals_to_trajectory,
)

ROOT = Path(__file__).resolve().parent.parent
ATHANOR_STATE = ROOT / "society" / "systems" / "athanor_coherence.json"
ATHANOR_LOG = ROOT / "data" / "commons" / "athanor_coherence.jsonl"
RESIDUALS_STATE = ROOT / "society" / "systems" / "residuals.json"
RESIDUALS_LOG = ROOT / "data" / "commons" / "residuals.jsonl"
RECEIPTS = ROOT / "society" / "receipts"
MD_PATH = RECEIPTS / "H7_RESIDUAL_DIAGNOSIS.md"
JSON_PATH = RECEIPTS / "H7_RESIDUAL_DIAGNOSIS.json"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_et() -> str:
    return datetime.now().strftime("%Y-%m-%d %I:%M %p ET")


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    return float(statistics.pstdev(xs))


def _mean(xs: list[float]) -> float:
    return float(sum(xs) / len(xs)) if xs else 0.0


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return rows


def _agent_feature_stats(agents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    roles = sorted(agents.keys())
    eg = [float(agents[r].get("error_gradient") or 0.0) for r in roles]
    aro = [float(agents[r].get("arousal") or 0.0) for r in roles]
    att = [float(agents[r].get("attention_weight") or 0.0) for r in roles]
    conf0 = []
    act_means = []
    for r in roles:
        conf = agents[r].get("confidence_vector") or [0.5]
        conf0.append(float(conf[0]) if isinstance(conf, list) and conf else 0.5)
        act = agents[r].get("activation") or [0.1, 0.1, 0.1, 0.1]
        if isinstance(act, list) and act:
            act_means.append(sum(float(x) for x in act[:4]) / len(act[:4]))
        else:
            act_means.append(0.1)
    traj = residuals_to_trajectory(agents)
    pairwise = []
    for i in range(len(traj)):
        for j in range(i + 1, len(traj)):
            a, b = traj[i], traj[j]
            n = min(len(a), len(b))
            pairwise.append(math.sqrt(sum((a[k] - b[k]) ** 2 for k in range(n))))
    return {
        "n_agents": len(roles),
        "roles": roles,
        "error_gradient": {"mean": _mean(eg), "std": _std(eg), "min": min(eg) if eg else 0, "max": max(eg) if eg else 0},
        "arousal": {"mean": _mean(aro), "std": _std(aro), "min": min(aro) if aro else 0, "max": max(aro) if aro else 0},
        "attention": {"mean": _mean(att), "std": _std(att)},
        "confidence0": {"mean": _mean(conf0), "std": _std(conf0)},
        "activation_mean": {"mean": _mean(act_means), "std": _std(act_means)},
        "pairwise_l2": {
            "mean": _mean(pairwise),
            "std": _std(pairwise),
            "min": min(pairwise) if pairwise else 0,
            "max": max(pairwise) if pairwise else 0,
            "n_pairs": len(pairwise),
        },
    }


def diagnose() -> dict[str, Any]:
    ath = _load_json(ATHANOR_STATE)
    res = _load_json(RESIDUALS_STATE)
    ath_log = _load_jsonl(ATHANOR_LOG)
    res_log = _load_jsonl(RESIDUALS_LOG)

    latest = ath.get("latest") or {}
    summary = latest.get("summary") or {}
    dist = ath.get("distribution") or {"APPROVE": 0, "REFINE": 0, "REJECT": 0}
    agents = (res.get("agents") or {}) if isinstance(res, dict) else {}

    live_est = None
    live_verdict = None
    agent_stats: dict[str, Any] = {}
    if agents:
        agent_stats = _agent_feature_stats(agents)
        traj = residuals_to_trajectory(agents)
        live_est = estimate(traj)
        live_verdict = CoherenceGovernor().verify_residuals(agents)

    h7_hist = [float(r["h7"]) for r in ath_log if r.get("h7") is not None]
    verdict_hist: dict[str, int] = {"APPROVE": 0, "REFINE": 0, "REJECT": 0}
    for r in ath_log:
        v = str(r.get("verdict") or "")
        if v in verdict_hist:
            verdict_hist[v] += 1

    h7 = float(latest.get("h7") or (live_est.h7 if live_est else 0.0) or 0.0)
    h7_weighted = float(summary.get("h7_weighted") or (live_est.summary.get("h7_weighted") if live_est else 0.0) or 0.0)
    h7_cusp = float(summary.get("h7_cusp") or (live_est.summary.get("h7_cusp") if live_est else 0.0) or 0.0)
    kappa = float(summary.get("kappa_bound") or (live_est.summary.get("kappa_bound") if live_est else 0.0) or 0.0)
    c_mean = float(summary.get("C_mean") or (live_est.summary.get("C_mean") if live_est else 0.0) or 0.0)
    c_std = float(summary.get("C_std") or (live_est.summary.get("C_std") if live_est else 0.0) or 0.0)
    dphi_mean = float(summary.get("dphi_mean") or (live_est.summary.get("dphi_mean") if live_est else 0.0) or 0.0)
    dphi_std = float(summary.get("dphi_std") or (live_est.summary.get("dphi_std") if live_est else 0.0) or 0.0)

    factors = []
    if h7 < DEFAULT_H7_THRESHOLD and h7 >= DEFAULT_REFINE_FLOOR:
        factors.append({
            "id": "refine_band",
            "detail": (
                f"H7={h7:.4f} sits in REFINE band [{DEFAULT_REFINE_FLOOR}, {DEFAULT_H7_THRESHOLD}). "
                "Fraction of C_i ≥ 0.70 is only ~half the trajectory steps."
            ),
        })
    if h7_weighted > h7 + 0.15:
        factors.append({
            "id": "weighted_vs_horizon_gap",
            "detail": (
                f"Weighted coherence mean ({h7_weighted:.4f}) >> horizon H7 ({h7:.4f}). "
                "Many steps are moderately coherent, but not enough clear the 0.70 threshold "
                "for the horizon fraction — weighted metric masks the cusp shortfall."
            ),
        })
    if h7_cusp > h7 + 0.1:
        factors.append({
            "id": "cusp_survival_lift",
            "detail": (
                f"Cusp-limited H7 ({h7_cusp:.4f}) > raw H7 ({h7:.4f}) after dropping C<0.50. "
                "Low-coherence outlier steps dilute the horizon; surviving mass is healthier."
            ),
        })
    pairwise = (agent_stats.get("pairwise_l2") or {}) if agent_stats else {}
    if float(pairwise.get("std") or 0) > 0.2 or float(pairwise.get("mean") or 0) > 0.3:
        factors.append({
            "id": "agent_residual_variance",
            "detail": (
                f"Agent residual pairwise L2 mean={pairwise.get('mean')} std={pairwise.get('std')}. "
                "Heterogeneous activation/arousal/error across roles → larger ΔΦ → lower C on "
                "more trajectory edges → H7 stuck below APPROVE threshold."
            ),
        })
    if kappa < DEFAULT_H7_THRESHOLD:
        factors.append({
            "id": "kappa_bound_below_threshold",
            "detail": (
                f"κ=ω Lipschitz bound (C_mean²)={kappa:.4f} < H7 threshold {DEFAULT_H7_THRESHOLD}. "
                "Mean coherence squared cannot underwrite APPROVE-level horizon stability."
            ),
        })
    if dphi_std > 0.3:
        factors.append({
            "id": "dphi_dispersion",
            "detail": (
                f"ΔΦ std={dphi_std:.4f} (mean={dphi_mean:.4f}) — drift is bursty across the "
                "peer residual field, so C oscillates and H7 fraction stays mid-band."
            ),
        })

    total_v = sum(int(v) for v in dist.values()) or 1
    refine_share = int(dist.get("REFINE") or 0) / total_v

    return {
        "title": "H7_RESIDUAL_DIAGNOSIS",
        "when": _utc(),
        "when_et": _utc_et(),
        "mile": "h7-diagnosis",
        "scope": "diagnostics_report_only",
        "behavior_scripting": False,
        "durable_accept_double_gate": False,
        "inform_only_athanor_unchanged": True,
        "latest": {
            "verdict": latest.get("verdict") or (live_verdict.verdict if live_verdict else None),
            "h7": h7,
            "h7_weighted": h7_weighted,
            "h7_cusp": h7_cusp,
            "kappa_bound": kappa,
            "C_mean": c_mean,
            "C_std": c_std,
            "dphi_mean": dphi_mean,
            "dphi_std": dphi_std,
            "threshold": DEFAULT_H7_THRESHOLD,
            "refine_floor": DEFAULT_REFINE_FLOOR,
            "reason": latest.get("reason"),
            "n_agents": (latest.get("extra") or {}).get("n_agents") or agent_stats.get("n_agents"),
        },
        "distribution": dist,
        "distribution_log": verdict_hist,
        "refine_share": round(refine_share, 4),
        "h7_history": {
            "n": len(h7_hist),
            "mean": _mean(h7_hist),
            "std": _std(h7_hist),
            "min": min(h7_hist) if h7_hist else None,
            "max": max(h7_hist) if h7_hist else None,
            "last5": h7_hist[-5:],
        },
        "agent_residual_stats": agent_stats,
        "cusp_vs_weighted": {
            "h7_horizon": h7,
            "h7_weighted": h7_weighted,
            "h7_cusp": h7_cusp,
            "gap_weighted_minus_horizon": round(h7_weighted - h7, 6),
            "gap_cusp_minus_horizon": round(h7_cusp - h7, 6),
            "reading": (
                "Weighted mean looks healthy while horizon fraction stays REFINE — "
                "APPROVE needs more steps with C≥0.70, not just a higher average C."
            ),
        },
        "kappa": {
            "bound": kappa,
            "formula": "kappa = C_mean^2 (omega Lipschitz)",
            "C_mean": c_mean,
            "below_approve_threshold": kappa < DEFAULT_H7_THRESHOLD,
        },
        "factors": factors,
        "residuals_log_n": len(res_log),
        "athanor_log_n": len(ath_log),
        "recommendation_for_city": (
            "Report only. City may later reduce residual heterogeneity (attention/arousal "
            "spread) or tolerate REFINE as honest plateau signal. Do NOT double-gate durable "
            "accept. Do NOT script behavior from this report. Human authorize ceiling untouched."
        ),
        "non_claims": ["not_AGI", "not_consciousness", "not_Millennium", "diagnostics_only"],
        "ethos": "We light the spark and witness. We do not micromanage the city.",
    }


def render_md(report: dict[str, Any]) -> str:
    latest = report["latest"]
    dist = report["distribution"]
    cusp = report["cusp_vs_weighted"]
    kappa = report["kappa"]
    hist = report["h7_history"]
    factors = report["factors"]
    ag = report.get("agent_residual_stats") or {}
    lines = [
        "# H₇ Residual Diagnosis",
        "",
        f"**When:** {report['when_et']} (`{report['when']}`)",
        f"**Mile:** `{report['mile']}` — diagnostics / report ONLY",
        f"**Scope:** no behavior scripting · no durable-accept double-gate · Athanor stays inform-only",
        "",
        "## Snapshot",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Verdict | `{latest.get('verdict')}` |",
        f"| H₇ (horizon) | `{latest.get('h7')}` |",
        f"| H₇ weighted | `{latest.get('h7_weighted')}` |",
        f"| H₇ cusp | `{latest.get('h7_cusp')}` |",
        f"| κ bound (C̄²) | `{latest.get('kappa_bound')}` |",
        f"| C̄ / C σ | `{latest.get('C_mean')}` / `{latest.get('C_std')}` |",
        f"| ΔΦ μ / σ | `{latest.get('dphi_mean')}` / `{latest.get('dphi_std')}` |",
        f"| Threshold / floor | `{latest.get('threshold')}` / `{latest.get('refine_floor')}` |",
        f"| Agents | `{latest.get('n_agents')}` |",
        "",
        "## Distribution (APPROVE / REFINE / REJECT)",
        "",
        f"- State counters: `{dist}` (REFINE share ≈ `{report.get('refine_share')}`)",
        f"- Log counters: `{report.get('distribution_log')}`",
        "",
        "## H₇ history",
        "",
        f"- n=`{hist.get('n')}` mean=`{hist.get('mean')}` std=`{hist.get('std')}` "
        f"min=`{hist.get('min')}` max=`{hist.get('max')}`",
        f"- last5=`{hist.get('last5')}`",
        "",
        "## Cusp vs weighted",
        "",
        f"- horizon=`{cusp['h7_horizon']}` weighted=`{cusp['h7_weighted']}` cusp=`{cusp['h7_cusp']}`",
        f"- gap weighted−horizon=`{cusp['gap_weighted_minus_horizon']}`",
        f"- gap cusp−horizon=`{cusp['gap_cusp_minus_horizon']}`",
        f"- Reading: {cusp['reading']}",
        "",
        "## κ bound",
        "",
        f"- κ=`{kappa['bound']}` via `{kappa['formula']}` with C̄=`{kappa['C_mean']}`",
        f"- Below APPROVE threshold: `{kappa['below_approve_threshold']}`",
        "",
        "## Agent residual variance",
        "",
    ]
    if ag:
        lines += [
            f"- n_agents=`{ag.get('n_agents')}` roles=`{ag.get('roles')}`",
            f"- error_gradient=`{ag.get('error_gradient')}`",
            f"- arousal=`{ag.get('arousal')}`",
            f"- attention=`{ag.get('attention')}`",
            f"- confidence0=`{ag.get('confidence0')}`",
            f"- activation_mean=`{ag.get('activation_mean')}`",
            f"- pairwise_l2=`{ag.get('pairwise_l2')}`",
            "",
        ]
    else:
        lines += ["- (no agents in residuals state)", ""]
    lines += ["## Why REFINE (~0.54)", ""]
    if factors:
        for f in factors:
            lines.append(f"- **{f['id']}:** {f['detail']}")
    else:
        lines.append("- No dominant factor isolated; see snapshot.")
    lines += [
        "",
        "## Recommendation (city-free)",
        "",
        report["recommendation_for_city"],
        "",
        "## Non-claims",
        "",
        f"- {', '.join(report.get('non_claims') or [])}",
        "",
        f"_{report.get('ethos')}_",
        "",
    ]
    return "\n".join(lines)


def write_reports(report: dict[str, Any] | None = None) -> dict[str, Path]:
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    rep = report or diagnose()
    JSON_PATH.write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    MD_PATH.write_text(render_md(rep), encoding="utf-8")
    return {"json": JSON_PATH, "md": MD_PATH}


if __name__ == "__main__":
    paths = write_reports()
    print(json.dumps({"wrote": {k: str(v) for k, v in paths.items()}}, indent=2))
