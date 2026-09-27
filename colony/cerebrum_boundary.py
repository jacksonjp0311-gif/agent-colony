"""Cerebrum boundary — gateway for inform-only Cortex sidecar signals.

The Cerebrum boundary is the ONLY path Cortex signals may take into the colony.
It enforces:
- inform-only (feeds Oracle/actuation mix advice)
- never silent durable accept
- never authority over the ledger
- never double-gate durable rows
- ceiling untouched: P≥0.70 human authorize selective

Same pattern as Athanor / PulseMesh: feeds in, no authority out.
Not AGI. Not consciousness. Not Millennium.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
CEREBRUM_STATE = ROOT / "society" / "systems" / "cerebrum_boundary.json"
CEREBRUM_LOG = ROOT / "data" / "commons" / "cerebrum_boundary.jsonl"

# Hard flags — boundary refuses to elevate these
FORBIDDEN_OUT = frozenset(
    {
        "durable_accept",
        "ledger_accept",
        "authorize",
        "accept_all",
        "double_gate",
        "override_oracle",
        "disable_oracle",
        "silent_accept",
    }
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CerebrumBoundary:
    """Gate: Cortex → inform signals only. No ledger authority."""

    def __init__(self) -> None:
        self.inform_only = True
        self.ledger_authority = False
        self.durable_accept = False
        self.double_gate = False

    def admit(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Admit a Cortex payload; strip/forbid any authority fields."""
        src = dict(raw or {})
        # Refuse any attempt to claim ledger power
        for key in FORBIDDEN_OUT:
            if src.get(key) is True or src.get(key) == "accepted":
                src[key] = False
        signal = {
            "source": "cerebrum_boundary",
            "sidecar": src.get("sidecar") or "cortex",
            "kind": src.get("kind") or "memory_drift",
            "drift": float(src.get("drift") or 0.0),
            "memory_reuse": float(src.get("memory_reuse") or 0.0),
            "stability_hint": float(src.get("stability_hint") or 0.5),
            "oracle_mix_delta": float(src.get("oracle_mix_delta") or 0.0),
            "actuation_mix_delta": float(src.get("actuation_mix_delta") or 0.0),
            "suggest_throttle_factor": float(src.get("suggest_throttle_factor") or 1.0),
            "redebate_bias": float(src.get("redebate_bias") or 0.0),
            "summary": str(src.get("summary") or "")[:400],
            "inform_only": True,
            "ledger_authority": False,
            "durable_accept": False,
            "double_gate": False,
            "can_accept_ledger": False,
            "note": (
                "Cerebrum admits Cortex inform-only. No ledger authority. "
                "P>=0.70 human authorize remains ceiling. Not AGI."
            ),
            "ts": _utc(),
        }
        # Clamp advisory deltas to tiny, reversible band
        signal["oracle_mix_delta"] = max(-0.05, min(0.05, signal["oracle_mix_delta"]))
        signal["actuation_mix_delta"] = max(-0.05, min(0.05, signal["actuation_mix_delta"]))
        signal["suggest_throttle_factor"] = max(0.70, min(1.0, signal["suggest_throttle_factor"]))
        signal["redebate_bias"] = max(0.0, min(0.35, signal["redebate_bias"]))
        signal["drift"] = max(0.0, min(1.0, signal["drift"]))
        signal["memory_reuse"] = max(0.0, min(1.0, signal["memory_reuse"]))
        signal["stability_hint"] = max(0.0, min(1.0, signal["stability_hint"]))
        return signal

    def refuse_ledger_accept(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        """Explicit refuse — Cortex/Cerebrum cannot accept ledger findings."""
        return {
            "accepted": False,
            "refused": True,
            "reason": "cerebrum_boundary_no_ledger_authority",
            "inform_only": True,
            "durable_accept": False,
            "ceiling": "P>=0.70 human authorize selective",
        }


def persist_boundary_signal(
    signal: dict[str, Any],
    *,
    cycle_id: str = "",
) -> dict[str, Any]:
    row = dict(signal)
    row["cycle_id"] = cycle_id
    snap = {
        "ts": _utc(),
        "version": 1,
        "mile": "cortex-cerebrum-sidecar",
        "latest": row,
        "inform_only": True,
        "ledger_authority": False,
        "durable_accept": False,
        "double_gate": False,
        "ceiling": "P>=0.70 human authorize; no silent durable accept; no double-gate",
        "non_claims": ["not_AGI", "not_consciousness", "not_Millennium", "inform_only"],
    }
    CEREBRUM_STATE.parent.mkdir(parents=True, exist_ok=True)
    CEREBRUM_STATE.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    CEREBRUM_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CEREBRUM_LOG.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": snap["ts"],
                    "cycle_id": cycle_id,
                    "kind": row.get("kind"),
                    "drift": row.get("drift"),
                    "memory_reuse": row.get("memory_reuse"),
                    "inform_only": True,
                    "durable_accept": False,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return snap


def latest_boundary() -> dict[str, Any]:
    if CEREBRUM_STATE.exists():
        try:
            return json.loads(CEREBRUM_STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def map_to_oracle_actuation_mix(signal: dict[str, Any] | None) -> dict[str, Any]:
    """Advisory mix deltas for Oracle/actuation — INFORM ONLY."""
    if not signal:
        return {
            "source": "cerebrum_boundary",
            "inform_only": True,
            "oracle_mix_delta": 0.0,
            "actuation_mix_delta": 0.0,
            "suggest_throttle_factor": 1.0,
            "redebate_bias": 0.0,
            "durable_accept": False,
            "double_gate": False,
        }
    return {
        "source": "cerebrum_boundary",
        "inform_only": True,
        "oracle_mix_delta": float(signal.get("oracle_mix_delta") or 0.0),
        "actuation_mix_delta": float(signal.get("actuation_mix_delta") or 0.0),
        "suggest_throttle_factor": float(signal.get("suggest_throttle_factor") or 1.0),
        "redebate_bias": float(signal.get("redebate_bias") or 0.0),
        "drift": float(signal.get("drift") or 0.0),
        "memory_reuse": float(signal.get("memory_reuse") or 0.0),
        "stability_hint": float(signal.get("stability_hint") or 0.5),
        "durable_accept": False,
        "double_gate": False,
        "ledger_authority": False,
        "note": "Inform Oracle/actuation mix only; human authorize ceiling untouched.",
    }


__all__ = [
    "CerebrumBoundary",
    "FORBIDDEN_OUT",
    "persist_boundary_signal",
    "latest_boundary",
    "map_to_oracle_actuation_mix",
]
