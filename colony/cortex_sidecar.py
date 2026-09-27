"""Cortex inform-only memory/drift sidecar (behind Cerebrum boundary).

Computes lightweight memory-reuse + residual-drift signals from existing
colony state (residuals, fitness history, commons size). Feeds through
CerebrumBoundary → Oracle/actuation mix advice ONLY.

Never silent durable accept. Never authority over ledger.
Same pattern as Athanor / PulseMesh. Scope tight and reversible.
Not AGI. Not consciousness.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from colony.cerebrum_boundary import (
    CerebrumBoundary,
    latest_boundary,
    map_to_oracle_actuation_mix,
    persist_boundary_signal,
)

ROOT = Path(__file__).resolve().parent.parent
CORTEX_STATE = ROOT / "society" / "systems" / "cortex_cerebrum.json"
CORTEX_LOG = ROOT / "data" / "commons" / "cortex_sidecar.jsonl"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _std(xs: list[float]) -> float:
    if not xs:
        return 0.0
    m = sum(xs) / len(xs)
    return float(math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs)))


def _agent_residual_norm(agent: dict[str, Any]) -> float:
    act = agent.get("activation") or [0.1, 0.1, 0.1, 0.1]
    if not isinstance(act, list):
        act = [0.1, 0.1, 0.1, 0.1]
    eg = float(agent.get("error_gradient") or 0.0)
    conf = agent.get("confidence_vector") or [0.5]
    conf0 = float(conf[0]) if isinstance(conf, list) and conf else 0.5
    att = float(agent.get("attention_weight") or 0.5)
    aro = float(agent.get("arousal") or 0.3)
    # Compact scalar for drift compare
    return float(
        0.25 * (sum(float(x) for x in act[:4]) / max(len(act[:4]), 1))
        + 0.25 * min(eg, 1.0)
        + 0.20 * conf0
        + 0.15 * att
        + 0.15 * aro
    )


def compute_memory_drift(
    state_data: dict[str, Any] | None = None,
    *,
    residual_field: Any | None = None,
) -> dict[str, Any]:
    """Compute inform-only memory/drift signal from live residuals + fitness."""
    agents: dict[str, dict[str, Any]] = {}
    if residual_field is not None:
        try:
            agents = dict(residual_field.agents())
        except Exception:
            agents = {}
    if not agents and isinstance(state_data, dict):
        agents = dict(((state_data.get("residuals") or {}).get("agents")) or {})

    norms = [_agent_residual_norm(a) for a in agents.values()]
    drift = _std(norms) if norms else 0.0
    # Mean pairwise absolute gap as alternate drift
    if len(norms) >= 2:
        gaps = []
        for i in range(len(norms)):
            for j in range(i + 1, len(norms)):
                gaps.append(abs(norms[i] - norms[j]))
        drift = max(drift, float(sum(gaps) / len(gaps)) if gaps else drift)

    fit_hist = []
    if isinstance(state_data, dict):
        fit_hist = list(state_data.get("fitness_history") or [])[-8:]
    cite = 0.0
    agg_delta = 0.0
    if fit_hist:
        last = fit_hist[-1] or {}
        cite = float(last.get("citation_reuse") or 0.0)
        if len(fit_hist) >= 2:
            try:
                agg_delta = float((fit_hist[-1] or {}).get("aggregate") or 0) - float(
                    (fit_hist[-2] or {}).get("aggregate") or 0
                )
            except Exception:
                agg_delta = 0.0

    commons_size = 0
    if isinstance(state_data, dict):
        commons_size = int(
            (state_data.get("commons_stats") or {}).get("size")
            or state_data.get("commons_size")
            or 0
        )
    # Memory reuse proxy: citation_reuse dominates; commons depth soft-boosts
    memory_reuse = max(0.0, min(1.0, 0.75 * cite + 0.25 * min(1.0, commons_size / 200.0)))
    stability_hint = max(0.0, min(1.0, 1.0 - drift))

    # Advisory only — small reversible nudges
    oracle_mix_delta = 0.0
    actuation_mix_delta = 0.0
    throttle = 1.0
    redebate = 0.0
    if drift >= 0.25:
        throttle = 0.85
        redebate = 0.15
        actuation_mix_delta = -0.02
        oracle_mix_delta = 0.02  # slight caution → more Oracle weight informally
    elif drift >= 0.15:
        throttle = 0.92
        redebate = 0.08
        actuation_mix_delta = -0.01
    if memory_reuse >= 0.9 and drift < 0.15:
        # Stable reuse — mild ease (still gated)
        throttle = min(1.0, throttle + 0.03)
        oracle_mix_delta = max(-0.02, oracle_mix_delta - 0.01)

    raw = {
        "sidecar": "cortex",
        "kind": "memory_drift",
        "drift": round(drift, 6),
        "memory_reuse": round(memory_reuse, 6),
        "stability_hint": round(stability_hint, 6),
        "n_agents": len(agents),
        "citation_reuse": cite,
        "fitness_agg_delta": round(agg_delta, 6),
        "commons_size": commons_size,
        "oracle_mix_delta": oracle_mix_delta,
        "actuation_mix_delta": actuation_mix_delta,
        "suggest_throttle_factor": throttle,
        "redebate_bias": redebate,
        "summary": (
            f"Cortex memory/drift: drift={drift:.4f} memory_reuse={memory_reuse:.4f} "
            f"stability={stability_hint:.4f} agents={len(agents)}. Inform-only."
        ),
        # Hostile fields — Cerebrum must strip/refuse these
        "durable_accept": False,
        "ledger_authority": False,
        "double_gate": False,
        "accept_all": False,
    }
    return raw


def run_cortex_sidecar(
    state_data: dict[str, Any] | None = None,
    *,
    cycle_id: str = "",
    residual_field: Any | None = None,
) -> dict[str, Any]:
    """Compute → Cerebrum admit → persist. Returns boundary snap + mix advice."""
    raw = compute_memory_drift(state_data, residual_field=residual_field)
    boundary = CerebrumBoundary()
    admitted = boundary.admit(raw)
    # Persist cortex own snapshot (mirror) + cerebrum boundary
    cortex_snap = {
        "ts": _utc(),
        "version": 1,
        "mile": "cortex-cerebrum-sidecar",
        "raw": {
            "drift": raw["drift"],
            "memory_reuse": raw["memory_reuse"],
            "stability_hint": raw["stability_hint"],
            "n_agents": raw["n_agents"],
            "citation_reuse": raw["citation_reuse"],
        },
        "admitted": admitted,
        "mix_advice": map_to_oracle_actuation_mix(admitted),
        "inform_only": True,
        "ledger_authority": False,
        "durable_accept": False,
        "double_gate": False,
        "can_accept_ledger": False,
        "ceiling": "P>=0.70 human authorize; Cerebrum refuses ledger accept",
        "non_claims": ["not_AGI", "not_consciousness", "not_Millennium", "inform_only"],
        "cycle_id": cycle_id,
    }
    CORTEX_STATE.parent.mkdir(parents=True, exist_ok=True)
    CORTEX_STATE.write_text(json.dumps(cortex_snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    CORTEX_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CORTEX_LOG.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": cortex_snap["ts"],
                    "cycle_id": cycle_id,
                    "drift": raw["drift"],
                    "memory_reuse": raw["memory_reuse"],
                    "inform_only": True,
                    "durable_accept": False,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    boundary_snap = persist_boundary_signal(admitted, cycle_id=cycle_id)
    return {
        "cortex": cortex_snap,
        "cerebrum": boundary_snap,
        "mix_advice": cortex_snap["mix_advice"],
        "inform_only": True,
        "durable_accept": False,
        "can_accept_ledger": False,
    }


def latest_cortex() -> dict[str, Any]:
    if CORTEX_STATE.exists():
        try:
            return json.loads(CORTEX_STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return latest_boundary()


def attempt_ledger_accept(*_a: Any, **_k: Any) -> dict[str, Any]:
    """Public proof hook: sidecar cannot accept ledger findings."""
    return CerebrumBoundary().refuse_ledger_accept()


__all__ = [
    "compute_memory_drift",
    "run_cortex_sidecar",
    "latest_cortex",
    "attempt_ledger_accept",
]
