"""INTERNAL RESIDUALS — non-textual peer channels (pheromone/EM-like).

Channels: activation patterns, error gradients, confidence vectors,
attention weights, arousal scalars. Agents read peers' residuals in real time.
High-residual agents get more attention. Conflicting residuals trigger re-debate.
Log residual traces alongside Oracle/authorize metrics. Not consciousness.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RESIDUAL_STATE = ROOT / "society" / "systems" / "residuals.json"
RESIDUAL_LOG = ROOT / "data" / "commons" / "residuals.jsonl"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def _blank(role: str) -> dict[str, Any]:
    return {
        "role": role,
        "activation": [0.1, 0.1, 0.1, 0.1],  # small vector
        "error_gradient": 0.0,
        "confidence_vector": [0.5, 0.5, 0.5],
        "attention_weight": 0.5,
        "arousal": 0.3,
        "updated_at": _utc(),
        "cycle_id": "",
        "not_consciousness": True,
    }


class ResidualField:
    """Shared residual field stored in society_state + systems snapshot."""

    def __init__(self, state_data: dict[str, Any] | None = None) -> None:
        self.data = state_data if state_data is not None else {}
        field = self.data.setdefault(
            "residuals",
            {"agents": {}, "conflicts": [], "stats": {"updates": 0, "conflicts": 0, "redebatess": 0}},
        )
        field.setdefault("agents", {})
        field.setdefault("conflicts", [])
        field.setdefault("stats", {"updates": 0, "conflicts": 0, "redebatess": 0})

    def agents(self) -> dict[str, dict[str, Any]]:
        return self.data["residuals"].setdefault("agents", {})

    def ensure(self, role: str) -> dict[str, Any]:
        ag = self.agents()
        if role not in ag:
            ag[role] = _blank(role)
        return ag[role]

    def update(
        self,
        role: str,
        *,
        cycle_id: str = "",
        activation: list[float] | None = None,
        error_gradient: float | None = None,
        confidence_vector: list[float] | None = None,
        attention_weight: float | None = None,
        arousal: float | None = None,
        source: str = "cycle",
    ) -> dict[str, Any]:
        r = self.ensure(role)
        if activation is not None:
            r["activation"] = [ _clamp(x) for x in activation[:8] ]
        if error_gradient is not None:
            r["error_gradient"] = _clamp(abs(error_gradient), 0.0, 2.0)
        if confidence_vector is not None:
            r["confidence_vector"] = [ _clamp(x) for x in confidence_vector[:6] ]
        if attention_weight is not None:
            r["attention_weight"] = _clamp(attention_weight)
        if arousal is not None:
            r["arousal"] = _clamp(arousal)
        r["updated_at"] = _utc()
        r["cycle_id"] = cycle_id
        r["last_source"] = source
        stats = self.data["residuals"].setdefault("stats", {})
        stats["updates"] = int(stats.get("updates") or 0) + 1
        return r

    def emit_from_signals(
        self,
        role: str,
        *,
        cycle_id: str,
        fitness_delta: float = 0.0,
        oracle_kill: bool = False,
        reply_rate: float = 0.5,
        authorize_reject: bool = False,
        external_arousal: float = 0.0,
    ) -> dict[str, Any]:
        """Derive residual vector from measurable colony signals (coded, not felt)."""
        err = abs(fitness_delta) + (0.4 if oracle_kill else 0.0) + (0.25 if authorize_reject else 0.0)
        conf = _clamp(0.55 + 0.3 * reply_rate - 0.2 * err)
        arousal = _clamp(0.25 + 0.5 * err + 0.3 * external_arousal)
        attn = _clamp(0.35 + 0.4 * arousal + 0.2 * abs(fitness_delta))
        act = [
            _clamp(0.2 + reply_rate * 0.5),
            _clamp(err),
            _clamp(conf),
            _clamp(arousal),
        ]
        return self.update(
            role,
            cycle_id=cycle_id,
            activation=act,
            error_gradient=err,
            confidence_vector=[conf, _clamp(1.0 - err), _clamp(reply_rate)],
            attention_weight=attn,
            arousal=arousal,
            source="signal_derive",
        )

    def residual_magnitude(self, role: str) -> float:
        r = self.ensure(role)
        act = r.get("activation") or [0.0]
        return _clamp(
            0.35 * float(r.get("arousal") or 0)
            + 0.25 * float(r.get("error_gradient") or 0)
            + 0.2 * float(r.get("attention_weight") or 0)
            + 0.2 * (sum(act) / max(1, len(act))),
            0.0,
            1.5,
        )

    def high_residual_roles(self, *, top_k: int = 3) -> list[tuple[str, float]]:
        scored = [(role, self.residual_magnitude(role)) for role in self.agents()]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def detect_conflicts(self, *, threshold: float = 0.35) -> list[dict[str, Any]]:
        """Conflicting confidence/arousal between peers → re-debate trigger."""
        roles = list(self.agents().keys())
        conflicts: list[dict[str, Any]] = []
        for i, a in enumerate(roles):
            ra = self.agents()[a]
            ca = (ra.get("confidence_vector") or [0.5])[0]
            aa = float(ra.get("arousal") or 0)
            for b in roles[i + 1 :]:
                rb = self.agents()[b]
                cb = (rb.get("confidence_vector") or [0.5])[0]
                ab = float(rb.get("arousal") or 0)
                gap = abs(ca - cb) + 0.5 * abs(aa - ab)
                if gap >= threshold:
                    conflicts.append(
                        {
                            "a": a,
                            "b": b,
                            "confidence_gap": round(abs(ca - cb), 4),
                            "arousal_gap": round(abs(aa - ab), 4),
                            "score": round(gap, 4),
                            "trigger_redebate": True,
                            "ts": _utc(),
                        }
                    )
        self.data["residuals"]["conflicts"] = conflicts[-20:]
        stats = self.data["residuals"].setdefault("stats", {})
        stats["conflicts"] = int(stats.get("conflicts") or 0) + len(conflicts)
        if conflicts:
            stats["redebatess"] = int(stats.get("redebatess") or 0) + 1
        return conflicts

    def read_peers(self, role: str) -> dict[str, Any]:
        """What one agent sees of others — real-time residual read."""
        peers = {k: v for k, v in self.agents().items() if k != role}
        high = self.high_residual_roles(top_k=5)
        return {
            "reader": role,
            "peers": peers,
            "high_residual": high,
            "attention_recommendation": [r for r, _ in high if r != role][:3],
            "ts": _utc(),
            "not_consciousness": True,
        }

    def persist(self) -> dict[str, Any]:
        snap = {
            "ts": _utc(),
            "version": 1,
            "agents": self.agents(),
            "conflicts": self.data["residuals"].get("conflicts") or [],
            "stats": self.data["residuals"].get("stats") or {},
            "high_residual": self.high_residual_roles(),
            "note": "INTERNAL RESIDUALS snapshot. Coded channels — not consciousness.",
            "non_claims": ["not_consciousness", "not_AGI", "not_sentience"],
        }
        RESIDUAL_STATE.parent.mkdir(parents=True, exist_ok=True)
        RESIDUAL_STATE.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        RESIDUAL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with RESIDUAL_LOG.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": snap["ts"],
                        "n_agents": len(snap["agents"]),
                        "n_conflicts": len(snap["conflicts"]),
                        "high": snap["high_residual"],
                        "stats": snap["stats"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        return snap

    def trace_sample(self, limit: int = 5) -> list[dict[str, Any]]:
        out = []
        for role, mag in self.high_residual_roles(top_k=limit):
            r = self.ensure(role)
            out.append(
                {
                    "role": role,
                    "magnitude": round(mag, 4),
                    "activation": r.get("activation"),
                    "error_gradient": r.get("error_gradient"),
                    "confidence_vector": r.get("confidence_vector"),
                    "attention_weight": r.get("attention_weight"),
                    "arousal": r.get("arousal"),
                    "cycle_id": r.get("cycle_id"),
                }
            )
        return out


def query_residuals(state_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Agent API entry."""
    if state_data is not None:
        return ResidualField(state_data).persist()
    if RESIDUAL_STATE.exists():
        try:
            return json.loads(RESIDUAL_STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return ResidualField({}).persist()
