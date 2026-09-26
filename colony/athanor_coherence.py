"""ATHANOR coherence governor — ported into agent-colony (inform only).

Pipeline: INTERNAL RESIDUALS trajectory → ΔΦ drift → C → H₇ → APPROVE/REFINE/REJECT.

Hard ceiling (James):
- Inform Oracle + coherence stabilizer (50/50 mix, 30% throttle).
- Must NOT double-gate durable ledger rows.
- Must NOT silently accept; P≥0.70 human authorize remains the ceiling.
- UNKNOWN stays UNKNOWN. Not AGI / consciousness / Millennium / novel theorems.

Source adapted from jacksonjp0311-gif/Athanor (core/coherence + VerifierAgent).
Pure-Python first; optional numpy acceleration when present.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parent.parent
VERDICT_STATE = ROOT / "society" / "systems" / "athanor_coherence.json"
VERDICT_LOG = ROOT / "data" / "commons" / "athanor_coherence.jsonl"

# Defaults match Athanor VerifierAgent
DEFAULT_H7_THRESHOLD = 0.70
DEFAULT_REFINE_FLOOR = 0.50
DEFAULT_MODE = "l2"

try:
    import numpy as np  # type: ignore

    _HAS_NUMPY = True
except Exception:  # noqa: BLE001
    np = None  # type: ignore
    _HAS_NUMPY = False


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_traj(traj: Sequence[Sequence[float]] | Any) -> list[list[float]]:
    if _HAS_NUMPY and hasattr(traj, "tolist"):
        arr = traj  # noqa: F841 — keep type flexible
        try:
            return [[float(x) for x in row] for row in traj.tolist()]
        except Exception:
            pass
    out: list[list[float]] = []
    for row in traj:
        out.append([float(x) for x in row])
    return out


def delta_phi(traj: Sequence[Sequence[float]] | Any, mode: str = "l2") -> list[float]:
    """ΔΦ local residual drift between consecutive trajectory rows."""
    rows = _as_traj(traj)
    if len(rows) < 2:
        return []
    out: list[float] = []
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        n = min(len(a), len(b))
        if n == 0:
            out.append(0.0)
            continue
        if mode == "cosine":
            dot = sum(a[j] * b[j] for j in range(n))
            na = math.sqrt(sum(a[j] * a[j] for j in range(n))) + 1e-9
            nb = math.sqrt(sum(b[j] * b[j] for j in range(n))) + 1e-9
            cos = max(-1.0, min(1.0, dot / (na * nb)))
            out.append(float(math.acos(cos)))
        else:
            out.append(float(math.sqrt(sum((b[j] - a[j]) ** 2 for j in range(n)))))
    return out


def coherence_from_dphi(dphi: Sequence[float]) -> list[float]:
    """C = 1 / (1 + |ΔΦ|)."""
    return [float(1.0 / (1.0 + abs(float(x)))) for x in dphi]


def h7_horizon(C: Sequence[float], threshold: float = DEFAULT_H7_THRESHOLD) -> float:
    if not C:
        return 0.0
    thr = float(threshold)
    return float(sum(1 for c in C if float(c) >= thr) / len(C))


def weighted_coherence_mean(C: Sequence[float], power: float = 1.0) -> float:
    if not C:
        return 0.0
    p = max(float(power), 0.0)
    clipped = [max(0.0, min(1.0, float(c))) for c in C]
    w = [c ** p for c in clipped]
    den = sum(w)
    if den <= 1e-12:
        return float(sum(clipped) / len(clipped))
    return float(sum(wi * ci for wi, ci in zip(w, clipped)) / den)


def cusp_limited_h7(
    C: Sequence[float],
    threshold: float = DEFAULT_H7_THRESHOLD,
    survival_floor: float = 0.0,
) -> float:
    if not C:
        return 0.0
    sf = max(0.0, min(1.0, float(survival_floor)))
    kept = [float(c) for c in C if float(c) >= sf]
    if not kept:
        return 0.0
    return h7_horizon(kept, threshold=threshold)


def omega_lipschitz_kappa_bound(C0: float) -> float:
    c0 = max(0.0, min(1.0, float(C0)))
    return float(c0 ** 2)


def immunity_index(C: Sequence[float], C_perturbed: Sequence[float]) -> float:
    if not C or not C_perturbed:
        return 0.0
    n = min(len(C), len(C_perturbed))
    base = [float(C[i]) for i in range(n)]
    pert = [float(C_perturbed[i]) for i in range(n)]
    num = sum(abs(pert[i] - base[i]) for i in range(n)) / n
    den = (sum(abs(b) for b in base) / n) + 1e-9
    return float(max(0.0, min(1.0, 1.0 - (num / den))))


def basin_drift(C: Sequence[float], C_perturbed: Sequence[float]) -> float:
    if not C or not C_perturbed:
        return 0.0
    n = min(len(C), len(C_perturbed))
    return float(sum(float(C_perturbed[i]) - float(C[i]) for i in range(n)) / n)


def inject_bounded_noise(
    dphi: Sequence[float],
    sigma: float,
    *,
    seed: int | None = None,
) -> list[float]:
    if not dphi:
        return []
    s = max(float(sigma), 0.0)
    # Deterministic LCG so tests don't need numpy.random
    state = int(seed if seed is not None else 7)

    def _u() -> float:
        nonlocal state
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        return state / 0xFFFFFFFF

    out: list[float] = []
    for x in dphi:
        eps = (_u() * 2.0 - 1.0) * s
        out.append(float(x) + eps)
    return out


def boundary_excess(value: float, boundary: float) -> float:
    return float(value - boundary)


def commensurability_suppression_score(value: float, max_denominator: int = 64) -> float:
    v = float(value)
    m = max(int(max_denominator), 2)
    best = float("inf")
    for q in range(1, m + 1):
        p = round(v * q)
        err = abs(v - (p / q))
        if err < best:
            best = err
    return float(best)


def select_boundary_invariant(
    candidates: list[float],
    degree: int = 2,
    suppression_weight: float = 1.0,
) -> dict[str, Any]:
    if not candidates:
        return {"selected": None, "score": 0.0, "degree": int(degree)}
    deg = max(int(degree), 1)
    sw = max(float(suppression_weight), 0.0)
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    plastic = 1.3247179572447458
    target = {1: 1.0, 2: phi, 3: plastic}.get(deg, phi)
    best_val = None
    best_score = -1e18
    for x in candidates:
        xv = float(x)
        prox = -abs(xv - target)
        sup = commensurability_suppression_score(xv)
        score = prox + (sw * sup)
        if score > best_score:
            best_score = score
            best_val = xv
    return {"selected": best_val, "score": float(best_score), "degree": deg, "target": float(target)}


@dataclass
class DeltaPhiEstimate:
    dphi: list[float]
    coherence: list[float]
    h7: float
    summary: dict[str, Any] = field(default_factory=dict)


def estimate(
    traj: Sequence[Sequence[float]] | Any,
    threshold: float = DEFAULT_H7_THRESHOLD,
    mode: str = DEFAULT_MODE,
) -> DeltaPhiEstimate:
    d = delta_phi(traj, mode=mode)
    C = coherence_from_dphi(d)
    h7 = h7_horizon(C, threshold=threshold)
    c_mean = float(sum(C) / len(C)) if C else 0.0
    summary = {
        "threshold": float(threshold),
        "mode": str(mode),
        "dphi_mean": float(sum(d) / len(d)) if d else 0.0,
        "dphi_std": _std(d),
        "C_mean": c_mean,
        "C_std": _std(C),
        "h7": float(h7),
        "h7_weighted": float(weighted_coherence_mean(C, power=1.0)),
        "h7_cusp": float(cusp_limited_h7(C, threshold=threshold, survival_floor=0.50)),
        "kappa_bound": float(omega_lipschitz_kappa_bound(c_mean)),
    }
    return DeltaPhiEstimate(dphi=d, coherence=C, h7=h7, summary=summary)


def _std(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    m = sum(xs) / len(xs)
    return float(math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs)))


# ---------------------------------------------------------------------------
# INTERNAL RESIDUALS → trajectory (replaces synthetic numpy toys)
# ---------------------------------------------------------------------------

RESIDUAL_KEYS = ("activation", "error_gradient", "confidence", "attention", "arousal")


def residual_vector(agent: dict[str, Any]) -> list[float]:
    """Map one agent's residual schema → fixed-dim feature row."""
    act = agent.get("activation") or [0.1, 0.1, 0.1, 0.1]
    if not isinstance(act, list):
        act = [0.1, 0.1, 0.1, 0.1]
    act4 = (list(act) + [0.0, 0.0, 0.0, 0.0])[:4]
    conf = agent.get("confidence_vector") or [0.5]
    conf0 = float(conf[0]) if isinstance(conf, list) and conf else 0.5
    return [
        float(act4[0]),
        float(act4[1]),
        float(act4[2]),
        float(act4[3]),
        float(agent.get("error_gradient") or 0.0),
        conf0,
        float(agent.get("attention_weight") or 0.5),
        float(agent.get("arousal") or 0.3),
    ]


def residuals_to_trajectory(
    agents: dict[str, dict[str, Any]] | None,
    *,
    history: list[dict[str, Any]] | None = None,
    min_rows: int = 4,
) -> list[list[float]]:
    """Build a live trajectory from INTERNAL RESIDUALS (activation/gradients/…).

    Preference order:
    1) Explicit residual history snapshots (list of {role: residual_dict})
    2) Current agent residuals sorted by role (spatial proxy of peer field)
    Pad/repeat to min_rows so ΔΦ is defined.
    """
    traj: list[list[float]] = []
    if history:
        for snap in history:
            if not isinstance(snap, dict):
                continue
            # mean residual across agents in snapshot, or single vector
            if "activation" in snap or "arousal" in snap:
                traj.append(residual_vector(snap))
            else:
                vecs = [residual_vector(v) for v in snap.values() if isinstance(v, dict)]
                if vecs:
                    dim = len(vecs[0])
                    mean = [sum(v[i] for v in vecs) / len(vecs) for i in range(dim)]
                    traj.append(mean)
    if not traj and agents:
        for role in sorted(agents.keys()):
            traj.append(residual_vector(agents[role]))
    if not traj:
        # Neutral baseline — honest empty field, not a fake high-coherence toy
        traj = [[0.1, 0.1, 0.1, 0.1, 0.0, 0.5, 0.5, 0.3] for _ in range(min_rows)]
    while len(traj) < min_rows:
        traj.append(list(traj[-1]))
    return traj


@dataclass
class CoherenceVerdict:
    verdict: str  # APPROVE | REFINE | REJECT
    reason: str
    h7: float
    threshold: float
    refine_floor: float
    summary: dict[str, Any] = field(default_factory=dict)
    inform_only: bool = True
    double_gate: bool = False
    durable_accept: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "h7": self.h7,
            "threshold": self.threshold,
            "refine_floor": self.refine_floor,
            "summary": self.summary,
            "inform_only": self.inform_only,
            "double_gate": self.double_gate,
            "durable_accept": self.durable_accept,
            "note": (
                "ATHANOR H7 inform-only. Does NOT authorize durable ledger rows. "
                "P>=0.70 human authorize remains ceiling. Not AGI."
            ),
            "ts": _utc(),
        }


class CoherenceGovernor:
    """Verifier: H₇ → APPROVE / REFINE / REJECT. Inform-only for colony."""

    def __init__(
        self,
        threshold_h7: float = DEFAULT_H7_THRESHOLD,
        refine_floor: float = DEFAULT_REFINE_FLOOR,
        dphi_mode: str = DEFAULT_MODE,
    ) -> None:
        self.threshold = float(threshold_h7)
        self.refine_floor = float(refine_floor)
        self.mode = str(dphi_mode)

    def verify_trajectory(self, traj: Sequence[Sequence[float]] | Any) -> CoherenceVerdict:
        est = estimate(traj, threshold=self.threshold, mode=self.mode)
        h7 = float(est.h7)
        if h7 >= self.threshold:
            verdict, reason = "APPROVE", "H7>=threshold"
        elif h7 >= self.refine_floor:
            verdict, reason = "REFINE", "H7 in refine band"
        else:
            verdict, reason = "REJECT", "H7 below refine floor"
        return CoherenceVerdict(
            verdict=verdict,
            reason=reason,
            h7=h7,
            threshold=self.threshold,
            refine_floor=self.refine_floor,
            summary=est.summary,
            inform_only=True,
            double_gate=False,
            durable_accept=False,
        )

    def verify_residuals(
        self,
        agents: dict[str, dict[str, Any]] | None = None,
        *,
        history: list[dict[str, Any]] | None = None,
    ) -> CoherenceVerdict:
        traj = residuals_to_trajectory(agents, history=history)
        return self.verify_trajectory(traj)


def map_h7_to_stabilizer(verdict: CoherenceVerdict | dict[str, Any]) -> dict[str, Any]:
    """Map H₇ onto existing 50/50 action mix + 30% throttle — INFORM ONLY.

    Does not execute throttle itself; returns advisory fields for actuation.py.
    REJECT → suggest throttle; REFINE → mild caution; APPROVE → nominal mix.
    """
    if isinstance(verdict, CoherenceVerdict):
        d = verdict.to_dict()
    else:
        d = dict(verdict)
    v = str(d.get("verdict") or "REFINE")
    h7 = float(d.get("h7") or 0.0)
    advice = {
        "source": "athanor_h7",
        "verdict": v,
        "h7": h7,
        "action_mix_internal": 0.50,
        "action_mix_external": 0.50,
        "suggest_throttle_factor": 1.0,
        "confidence_gate_delta": 0.0,
        "redebate_bias": 0.0,
        "inform_only": True,
        "double_gate": False,
        "durable_accept": False,
        "note": "Advisory for actuation stabilizer; human authorize ceiling untouched.",
    }
    if v == "REJECT":
        advice["suggest_throttle_factor"] = 0.70  # 30% throttle
        advice["confidence_gate_delta"] = 0.08  # raise bar slightly for action
        advice["redebate_bias"] = 0.35
    elif v == "REFINE":
        advice["suggest_throttle_factor"] = 0.85
        advice["confidence_gate_delta"] = 0.04
        advice["redebate_bias"] = 0.15
    else:  # APPROVE
        advice["suggest_throttle_factor"] = 1.0
        advice["confidence_gate_delta"] = -0.02  # slight ease (still gated)
        advice["redebate_bias"] = 0.0
    return advice


def apply_verdict_to_confidence(
    base_confidence: float,
    verdict: CoherenceVerdict | dict[str, Any] | None,
) -> float:
    """Inform-only confidence adjust for action gates (not ledger accept)."""
    if verdict is None:
        return float(base_confidence)
    advice = map_h7_to_stabilizer(verdict)
    delta = float(advice.get("confidence_gate_delta") or 0.0)
    # REJECT raises effective bar → lower perceived confidence
    adjusted = float(base_confidence) - delta
    return max(0.0, min(1.0, adjusted))


def persist_verdict(
    verdict: CoherenceVerdict | dict[str, Any],
    *,
    cycle_id: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = verdict.to_dict() if isinstance(verdict, CoherenceVerdict) else dict(verdict)
    row["cycle_id"] = cycle_id
    if extra:
        row["extra"] = extra
    # Rolling distribution
    dist = {"APPROVE": 0, "REFINE": 0, "REJECT": 0}
    if VERDICT_STATE.exists():
        try:
            prev = json.loads(VERDICT_STATE.read_text(encoding="utf-8"))
            dist.update((prev.get("distribution") or {}))
        except json.JSONDecodeError:
            pass
    v = str(row.get("verdict") or "REFINE")
    if v in dist:
        dist[v] = int(dist[v]) + 1
    snap = {
        "ts": _utc(),
        "version": 1,
        "mile": "spark3-port",
        "latest": row,
        "distribution": dist,
        "stabilizer_advice": map_h7_to_stabilizer(row),
        "non_claims": ["not_AGI", "not_consciousness", "not_Millennium", "inform_only"],
        "ceiling": "P>=0.70 human authorize; no silent durable accept; no double-gate",
    }
    VERDICT_STATE.parent.mkdir(parents=True, exist_ok=True)
    VERDICT_STATE.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    VERDICT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with VERDICT_LOG.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": snap["ts"],
                    "cycle_id": cycle_id,
                    "verdict": v,
                    "h7": row.get("h7"),
                    "reason": row.get("reason"),
                    "distribution": dist,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return snap


def latest_verdict() -> dict[str, Any]:
    if VERDICT_STATE.exists():
        try:
            return json.loads(VERDICT_STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def run_governor_on_state(
    state_data: dict[str, Any] | None = None,
    *,
    cycle_id: str = "",
    residual_field: Any | None = None,
) -> dict[str, Any]:
    """Convenience: pull residuals from society state / ResidualField → verify → persist."""
    agents: dict[str, dict[str, Any]] = {}
    if residual_field is not None:
        try:
            agents = dict(residual_field.agents())
        except Exception:
            agents = {}
    if not agents and isinstance(state_data, dict):
        agents = dict(((state_data.get("residuals") or {}).get("agents")) or {})
    gov = CoherenceGovernor()
    verdict = gov.verify_residuals(agents)
    return persist_verdict(verdict, cycle_id=cycle_id, extra={"n_agents": len(agents)})


# numpy-compatible wrappers for adapted Athanor unit tests
def _np_array(xs: Sequence[float] | Sequence[Sequence[float]], dtype: Any = None) -> Any:
    if _HAS_NUMPY:
        return np.asarray(xs, dtype=dtype or np.float32)
    return list(xs)


__all__ = [
    "delta_phi",
    "coherence_from_dphi",
    "h7_horizon",
    "weighted_coherence_mean",
    "cusp_limited_h7",
    "omega_lipschitz_kappa_bound",
    "immunity_index",
    "basin_drift",
    "inject_bounded_noise",
    "boundary_excess",
    "commensurability_suppression_score",
    "select_boundary_invariant",
    "estimate",
    "DeltaPhiEstimate",
    "CoherenceVerdict",
    "CoherenceGovernor",
    "residuals_to_trajectory",
    "residual_vector",
    "map_h7_to_stabilizer",
    "apply_verdict_to_confidence",
    "persist_verdict",
    "latest_verdict",
    "run_governor_on_state",
    "DEFAULT_H7_THRESHOLD",
    "DEFAULT_REFINE_FLOOR",
]
