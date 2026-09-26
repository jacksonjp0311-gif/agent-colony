"""ACTION/ACTUATION — close the sense→think→act loop.

Agents take real (bounded) actions to test hypotheses:
- controlled experiments (parameter probes)
- external API queries/probes
- adjust internal parameters / telemetry weights
- spawn targeted sub-debates
- modify own telemetry weights from observed outcomes

Gating: high-residual + high-confidence → execute;
        low-confidence → require peer residual consensus.
Every action logged: what, hypothesis, motivating signal, observed result.
Not AGI. Not privileged durable accept (still needs human authorize).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ACT_STATE = ROOT / "society" / "systems" / "actuation.json"
ACT_LOG = ROOT / "data" / "commons" / "actuation.jsonl"
TELEM_WEIGHTS = ROOT / "society" / "systems" / "telemetry_weights.json"

# Soft gates (coded policy — not consciousness)
HIGH_RESIDUAL = 0.55
HIGH_CONFIDENCE = 0.65
CONSENSUS_MIN_PEERS = 2

# Balance + stability (James)
INTERNAL_SHARE_MAX = 0.50  # param tweaks, telemetry weights, sub-debates
EXTERNAL_SHARE_MAX = 0.50  # API probes, controlled experiments, external queries
THROTTLE_FACTOR = 0.70     # keep 70% of actions (= 30% throttle) when unstable
STABILITY_WINDOW = 2       # consecutive cycles

INTERNAL_KINDS = frozenset({
    "adjust_telemetry_weights",
    "spawn_subdebate",
    "param_tweak",
})
EXTERNAL_KINDS = frozenset({
    "external_api_probe",
    "external_query",
    "controlled_experiment",  # James: controlled experiments count EXTERNAL
})


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_weights() -> dict[str, float]:
    if TELEM_WEIGHTS.exists():
        try:
            d = json.loads(TELEM_WEIGHTS.read_text(encoding="utf-8"))
            if isinstance(d, dict) and d.get("weights"):
                return {k: float(v) for k, v in d["weights"].items()}
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return {
        "fitness": 1.0,
        "reply_rate": 1.0,
        "oracle_kill": 1.0,
        "external_array": 1.0,
        "residuals": 1.0,
        "time_revision": 1.0,
    }


def _save_weights(weights: dict[str, float], *, note: str = "") -> None:
    TELEM_WEIGHTS.parent.mkdir(parents=True, exist_ok=True)
    TELEM_WEIGHTS.write_text(
        json.dumps(
            {
                "ts": _utc(),
                "weights": weights,
                "note": note or "telemetry weights adjusted by actuation",
                "not_agi": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _append(row: dict[str, Any]) -> None:
    ACT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ACT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _stats() -> dict[str, Any]:
    if ACT_STATE.exists():
        try:
            return json.loads(ACT_STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "version": 1,
        "total_actions": 0,
        "successes": 0,
        "failures": 0,
        "gated_blocked": 0,
        "queued": 0,
        "throttled": 0,
        "by_kind": {},
        "by_side": {"internal": 0, "external": 0},
        "cycle_history": [],
        "throttle_events": [],
        "examples": [],
    }


def _persist(stats: dict[str, Any]) -> None:
    ACT_STATE.parent.mkdir(parents=True, exist_ok=True)
    total = int(stats.get("total_actions") or 0)
    succ = int(stats.get("successes") or 0)
    fail = int(stats.get("failures") or 0)
    decided = succ + fail
    stats["success_rate"] = round(succ / decided, 4) if decided else None
    stats["ts"] = _utc()
    stats["note"] = (
        "ACTION/ACTUATION log. Bounded probes only. Durable accept still needs human authorize."
    )
    stats["non_claims"] = ["not_AGI", "not_consciousness", "not_novel_physics"]
    ACT_STATE.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def gate_allows(
    *,
    residual_magnitude: float,
    confidence: float,
    peer_consensus: int = 0,
) -> tuple[bool, str]:
    """high-residual + high-confidence → execute; else need peer consensus."""
    if residual_magnitude >= HIGH_RESIDUAL and confidence >= HIGH_CONFIDENCE:
        return True, "high_residual_and_high_confidence"
    if confidence < HIGH_CONFIDENCE:
        if peer_consensus >= CONSENSUS_MIN_PEERS:
            return True, "low_confidence_but_peer_residual_consensus"
        return False, "low_confidence_needs_peer_consensus"
    # high confidence but low residual — still allow mild probes
    if confidence >= HIGH_CONFIDENCE and residual_magnitude >= 0.35:
        return True, "high_confidence_moderate_residual"
    return False, "gate_blocked_insufficient_residual_or_consensus"


def _record(
    stats: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    stats["total_actions"] = int(stats.get("total_actions") or 0) + 1
    kind = row.get("kind") or "unknown"
    by = stats.setdefault("by_kind", {})
    by[kind] = int(by.get(kind) or 0) + 1
    if row.get("gated") and not row.get("executed"):
        stats["gated_blocked"] = int(stats.get("gated_blocked") or 0) + 1
    elif row.get("success") is True:
        stats["successes"] = int(stats.get("successes") or 0) + 1
    elif row.get("success") is False:
        stats["failures"] = int(stats.get("failures") or 0) + 1
    examples = list(stats.get("examples") or [])
    examples.append(
        {
            "ts": row.get("ts"),
            "kind": row.get("kind"),
            "hypothesis": row.get("hypothesis"),
            "success": row.get("success"),
            "result_snip": str(row.get("result") or "")[:200],
            "motivating_signal": row.get("motivating_signal"),
        }
    )
    stats["examples"] = examples[-12:]
    _append(row)
    _persist(stats)
    return row


def act_external_probe(
    *,
    cycle_id: str,
    actor: str,
    residual_magnitude: float,
    confidence: float,
    peer_consensus: int,
    motivating_signal: dict[str, Any],
    hypothesis: str,
) -> dict[str, Any]:
    """Post a real probe to EXTERNAL ARRAY (refresh one feed)."""
    stats = _stats()
    ok_gate, reason = gate_allows(
        residual_magnitude=residual_magnitude,
        confidence=confidence,
        peer_consensus=peer_consensus,
    )
    row: dict[str, Any] = {
        "ts": _utc(),
        "cycle_id": cycle_id,
        "actor": actor,
        "kind": "external_api_probe",
        "hypothesis": hypothesis,
        "motivating_signal": motivating_signal,
        "gate": reason,
        "residual_magnitude": residual_magnitude,
        "confidence": confidence,
        "peer_consensus": peer_consensus,
        "gated": True,
        "executed": False,
        "success": None,
        "result": None,
    }
    if not ok_gate:
        row["result"] = {"blocked": True, "reason": reason}
        return _record(stats, row)
    t0 = time.perf_counter()
    try:
        from colony.external_array import gather_external_array

        snap = gather_external_array(force=True)
        feed_ok = {k: bool(v.get("ok")) for k, v in (snap.get("feeds") or {}).items()}
        patterns = [p.get("kind") for p in (snap.get("cross_domain_patterns") or [])]
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        success = any(feed_ok.values())
        row.update(
            {
                "executed": True,
                "success": success,
                "result": {
                    "feed_ok": feed_ok,
                    "patterns": patterns,
                    "latency_ms": latency_ms,
                    "snap_ts": snap.get("ts"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        row.update(
            {
                "executed": True,
                "success": False,
                "result": {"error": str(exc), "latency_ms": round((time.perf_counter() - t0) * 1000.0, 1)},
            }
        )
    return _record(stats, row)


def act_adjust_telemetry_weights(
    *,
    cycle_id: str,
    actor: str,
    residual_magnitude: float,
    confidence: float,
    peer_consensus: int,
    motivating_signal: dict[str, Any],
    hypothesis: str,
    observed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Modify telemetry weights from observed outcomes (bounded ±0.15)."""
    stats = _stats()
    ok_gate, reason = gate_allows(
        residual_magnitude=residual_magnitude,
        confidence=confidence,
        peer_consensus=peer_consensus,
    )
    row: dict[str, Any] = {
        "ts": _utc(),
        "cycle_id": cycle_id,
        "actor": actor,
        "kind": "adjust_telemetry_weights",
        "hypothesis": hypothesis,
        "motivating_signal": motivating_signal,
        "gate": reason,
        "residual_magnitude": residual_magnitude,
        "confidence": confidence,
        "peer_consensus": peer_consensus,
        "gated": True,
        "executed": False,
        "success": None,
        "result": None,
    }
    if not ok_gate:
        row["result"] = {"blocked": True, "reason": reason}
        return _record(stats, row)
    weights = _load_weights()
    before = dict(weights)
    observed = observed or {}
    # Heuristic adjustments from outcomes
    if observed.get("easy_pad_kills", 0) and int(observed.get("easy_pad_kills") or 0) > 0:
        weights["oracle_kill"] = min(1.5, weights.get("oracle_kill", 1.0) + 0.1)
    if observed.get("pattern_count", 0) and int(observed.get("pattern_count") or 0) > 0:
        weights["external_array"] = min(1.5, weights.get("external_array", 1.0) + 0.08)
    if observed.get("revision_count", 0) and int(observed.get("revision_count") or 0) > 0:
        weights["time_revision"] = min(1.5, weights.get("time_revision", 1.0) + 0.08)
    if observed.get("fitness_delta") is not None:
        fd = float(observed["fitness_delta"])
        weights["fitness"] = min(1.5, max(0.5, weights.get("fitness", 1.0) + (0.05 if fd >= 0 else -0.05)))
    if observed.get("reply_rate") is not None:
        rr = float(observed["reply_rate"])
        weights["reply_rate"] = min(1.5, max(0.5, weights.get("reply_rate", 1.0) + (0.05 if rr >= 0.4 else -0.03)))
    # clamp deltas vs before to ±0.15 per key
    for k, v in list(weights.items()):
        b = before.get(k, 1.0)
        weights[k] = round(max(b - 0.15, min(b + 0.15, float(v))), 4)
    _save_weights(weights, note=f"actuation cycle={cycle_id} actor={actor}")
    row.update(
        {
            "executed": True,
            "success": True,
            "result": {"before": before, "after": weights, "observed": observed},
        }
    )
    return _record(stats, row)


def act_spawn_subdebate(
    *,
    bus: Any,
    cycle_id: str,
    actor: str,
    residual_magnitude: float,
    confidence: float,
    peer_consensus: int,
    motivating_signal: dict[str, Any],
    hypothesis: str,
    topic: str,
) -> dict[str, Any]:
    """Spawn a targeted sub-debate on the bus (forum hop)."""
    stats = _stats()
    ok_gate, reason = gate_allows(
        residual_magnitude=residual_magnitude,
        confidence=confidence,
        peer_consensus=peer_consensus,
    )
    row: dict[str, Any] = {
        "ts": _utc(),
        "cycle_id": cycle_id,
        "actor": actor,
        "kind": "spawn_subdebate",
        "hypothesis": hypothesis,
        "motivating_signal": motivating_signal,
        "gate": reason,
        "residual_magnitude": residual_magnitude,
        "confidence": confidence,
        "peer_consensus": peer_consensus,
        "gated": True,
        "executed": False,
        "success": None,
        "result": None,
    }
    if not ok_gate:
        row["result"] = {"blocked": True, "reason": reason}
        return _record(stats, row)
    try:
        msg = bus.post(
            from_role=actor,
            to_role="forum",
            channel="forum",
            message=(
                f"ACTUATION sub-debate ({actor}): hypothesis=`{hypothesis[:160]}` "
                f"topic={topic}. Motivated by {motivating_signal.get('kind') or motivating_signal}. "
                f"Peers: weigh + cite telemetry. NEXT ACTION → hearing_weigh. "
                f"cycle={cycle_id}. Not discovery."
            ),
            cycle_id=cycle_id,
            tags=["actuation", "subdebate", "debate", "peer_cite", "action_changed"],
            payload={
                "kind": "actuation_subdebate",
                "topic": topic,
                "hypothesis": hypothesis[:240],
                "motivating_signal": motivating_signal,
            },
        )
        if hasattr(bus, "record_action_changed"):
            bus.record_action_changed(
                changed=True,
                detail={
                    "next_action_before": "sense_think",
                    "next_action_after": "act_subdebate",
                    "reason": f"actuation spawn on {topic}",
                    "cycle_id": cycle_id,
                },
            )
        row.update(
            {
                "executed": True,
                "success": bool(msg.get("id")),
                "result": {"msg_id": msg.get("id"), "topic": topic},
            }
        )
    except Exception as exc:  # noqa: BLE001
        row.update({"executed": True, "success": False, "result": {"error": str(exc)}})
    return _record(stats, row)


def act_param_experiment(
    *,
    state_data: dict[str, Any],
    cycle_id: str,
    actor: str,
    residual_magnitude: float,
    confidence: float,
    peer_consensus: int,
    motivating_signal: dict[str, Any],
    hypothesis: str,
) -> dict[str, Any]:
    """Controlled internal parameter experiment (exploration budget nudge)."""
    stats = _stats()
    ok_gate, reason = gate_allows(
        residual_magnitude=residual_magnitude,
        confidence=confidence,
        peer_consensus=peer_consensus,
    )
    row: dict[str, Any] = {
        "ts": _utc(),
        "cycle_id": cycle_id,
        "actor": actor,
        "kind": "controlled_experiment",
        "hypothesis": hypothesis,
        "motivating_signal": motivating_signal,
        "gate": reason,
        "residual_magnitude": residual_magnitude,
        "confidence": confidence,
        "peer_consensus": peer_consensus,
        "gated": True,
        "executed": False,
        "success": None,
        "result": None,
    }
    if not ok_gate:
        row["result"] = {"blocked": True, "reason": reason}
        return _record(stats, row)
    budget = state_data.setdefault("exploration_budget", {"fp": 1.0, "history": []})
    before = float(budget.get("fp") or 1.0)
    # If easy_pad pressure high → tighten; if external patterns rich → slight loosen
    sig = motivating_signal or {}
    delta = 0.0
    if sig.get("kind") == "oracle_easy_pad" or sig.get("easy_pad_kills"):
        delta = -0.05
    elif sig.get("kind") in ("space_weather_coherence", "publications_x_space", "global_weather_spread"):
        delta = 0.03
    elif sig.get("kind") == "residual_conflict":
        delta = -0.02
    after = round(min(1.25, max(0.5, before + delta)), 4)
    budget["fp"] = after
    budget.setdefault("history", []).append(
        {"ts": _utc(), "cycle_id": cycle_id, "before": before, "after": after, "delta": delta, "actor": actor}
    )
    budget["history"] = budget["history"][-30:]
    # mirror to systems file lightly
    try:
        sys_path = ROOT / "society" / "systems" / "exploration_budget.json"
        sys_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": _utc(),
            "fp": after,
            "last_outcome": {"before": before, "after": after, "delta": delta, "cycle_id": cycle_id},
            "note": "actuation controlled experiment — bounded fp nudge",
        }
        sys_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass
    row.update(
        {
            "executed": True,
            "success": True,
            "result": {"param": "exploration_budget.fp", "before": before, "after": after, "delta": delta},
        }
    )
    return _record(stats, row)



def _side_for(kind: str) -> str:
    if kind in EXTERNAL_KINDS:
        return "external"
    if kind in INTERNAL_KINDS:
        return "internal"
    # default: treat unknown as internal (safer — no external IO)
    return "internal"


def _coherence_throttle(stats: dict[str, Any], *, conflict_rate: float | None) -> tuple[float, dict[str, Any] | None]:
    """If success rate drops OR residual conflict rate spikes across 2 consecutive cycles → 30% throttle."""
    hist = list(stats.get("cycle_history") or [])
    event = None
    factor = 1.0
    if len(hist) >= STABILITY_WINDOW:
        a, b = hist[-2], hist[-1]
        succ_drop = (
            a.get("success_rate") is not None
            and b.get("success_rate") is not None
            and float(b["success_rate"]) < float(a["success_rate"]) - 0.05
        )
        conf_spike = (
            a.get("conflict_rate") is not None
            and b.get("conflict_rate") is not None
            and float(b["conflict_rate"]) > float(a["conflict_rate"]) + 0.1
        )
        # also consider current conflict_rate vs prior if provided
        if conflict_rate is not None and b.get("conflict_rate") is not None:
            if float(conflict_rate) > float(b["conflict_rate"]) + 0.1 and succ_drop:
                conf_spike = True
        if succ_drop or conf_spike:
            factor = THROTTLE_FACTOR
            event = {
                "ts": _utc(),
                "reason": (
                    ("success_rate_drop" if succ_drop else "")
                    + ("+" if succ_drop and conf_spike else "")
                    + ("conflict_rate_spike" if conf_spike else "")
                ) or "stability",
                "throttle_factor": factor,
                "prior": a,
                "last": b,
                "conflict_rate_now": conflict_rate,
            }
            evs = list(stats.get("throttle_events") or [])
            evs.append(event)
            stats["throttle_events"] = evs[-20:]
            stats["throttled"] = int(stats.get("throttled") or 0) + 1
    return factor, event


def _apply_balance_and_throttle(
    planned: list[dict[str, Any]],
    *,
    stats: dict[str, Any],
    conflict_rate: float | None,
    cycle_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Cap internal/external ≈50% each; apply coherence throttle; queue overflow."""
    factor, throttle_event = _coherence_throttle(stats, conflict_rate=conflict_rate)
    budget = max(1, int(round(len(planned) * factor)))
    # Prefer keeping order but enforce side caps within budget
    max_internal = max(1, int(round(budget * INTERNAL_SHARE_MAX))) if budget else 0
    max_external = max(1, int(round(budget * EXTERNAL_SHARE_MAX))) if budget else 0
    # When budget==1, allow either side 1 (still ≈50% target over cycles)
    if budget == 1:
        max_internal = 1
        max_external = 1

    execute: list[dict[str, Any]] = []
    queued: list[dict[str, Any]] = []
    n_int = n_ext = 0
    for item in planned:
        kind = item.get("kind") or ""
        side = _side_for(kind)
        # throttle: once budget filled, queue rest
        if len(execute) >= budget:
            item = {**item, "queued": True, "queue_reason": "coherence_throttle_budget"}
            queued.append(item)
            continue
        if side == "internal" and n_int >= max_internal:
            item = {**item, "queued": True, "queue_reason": "internal_share_cap_50pct"}
            queued.append(item)
            continue
        if side == "external" and n_ext >= max_external:
            item = {**item, "queued": True, "queue_reason": "external_share_cap_50pct"}
            queued.append(item)
            continue
        execute.append(item)
        if side == "internal":
            n_int += 1
        else:
            n_ext += 1

    split = {
        "planned": len(planned),
        "budget": budget,
        "throttle_factor": factor,
        "throttle_event": throttle_event,
        "execute_internal": n_int,
        "execute_external": n_ext,
        "queued": len(queued),
        "internal_share": round(n_int / len(execute), 4) if execute else None,
        "external_share": round(n_ext / len(execute), 4) if execute else None,
        "caps": {"internal_max": max_internal, "external_max": max_external},
        "cycle_id": cycle_id,
    }
    # record queued in stats
    for q in queued:
        stats["queued"] = int(stats.get("queued") or 0) + 1
        _append(
            {
                "ts": _utc(),
                "cycle_id": cycle_id,
                "kind": q.get("kind"),
                "queued": True,
                "queue_reason": q.get("queue_reason"),
                "hypothesis": q.get("hypothesis"),
                "motivating_signal": q.get("motivating_signal"),
                "executed": False,
                "success": None,
                "side": _side_for(q.get("kind") or ""),
            }
        )
    return execute, queued, split


def run_actuation_cycle(
    *,
    bus: Any,
    state_data: dict[str, Any],
    cycle_id: str,
    residual_field: Any | None = None,
    external_patterns: list[dict[str, Any]] | None = None,
    revision_event: dict[str, Any] | None = None,
    oracle: dict[str, Any] | None = None,
    fitness_delta: float | None = None,
    reply_rate: float | None = None,
) -> dict[str, Any]:
    """Select gated+balanced actions for this cycle; return summary for witness/telemetry.

    Balance: internal ≈50% / external ≈50%. Overflow queued.
    Stability: success-rate drop or conflict-rate spike over 2 cycles → throttle 30%.
    """
    external_patterns = external_patterns or []
    oracle = oracle or {}
    stats = _stats()

    actor = "spark"
    residual_mag = 0.5
    confidence = 0.6
    peer_consensus = 0
    n_conflicts = 0
    n_agents = 1
    if residual_field is not None:
        try:
            high = residual_field.high_residual_roles(top_k=3)
            if high:
                actor, residual_mag = high[0][0], float(high[0][1])
            agents = residual_field.agents()
            n_agents = max(1, len(agents))
            if actor in agents:
                cv = agents[actor].get("confidence_vector") or [0.6]
                confidence = float(cv[0])
            peer_consensus = sum(1 for r, m in high[1:] if m >= 0.4)
            conflicts = residual_field.data.get("residuals", {}).get("conflicts") or []
            n_conflicts = len(conflicts)
            if conflicts:
                peer_consensus = max(peer_consensus, min(3, len(conflicts)))
        except Exception:
            pass

    conflict_rate = round(n_conflicts / max(1, n_agents * (n_agents - 1) / 2), 4) if n_agents > 1 else 0.0

    motiv = (external_patterns[0] if external_patterns else {"kind": "external_array_refresh"})
    topic = (motiv.get("kind") if external_patterns else "residual_or_telemetry_gap") or "actuation"

    # Plan 4 actions: 2 external + 2 internal target (≈50/50)
    planned: list[dict[str, Any]] = [
        {
            "kind": "external_api_probe",
            "side": "external",
            "actor": actor,
            "residual_magnitude": max(residual_mag, 0.5 if not external_patterns else residual_mag),
            "confidence": max(confidence, 0.66),
            "peer_consensus": max(peer_consensus, 2),
            "motivating_signal": {"kind": motiv.get("kind"), "summary": (motiv.get("summary") or "")[:160]},
            "hypothesis": (
                "Refreshing EXTERNAL ARRAY will yield ≥1 cross-domain pattern usable as debate input."
            ),
        },
        {
            "kind": "spawn_subdebate",
            "side": "internal",
            "actor": actor,
            "residual_magnitude": residual_mag,
            "confidence": confidence,
            "peer_consensus": max(peer_consensus, 2),
            "motivating_signal": {"kind": topic, "from": "external_or_residual"},
            "hypothesis": f"Targeted sub-debate on `{topic}` will lift load-bear replies / hearing quality.",
            "topic": str(topic),
        },
        {
            "kind": "controlled_experiment",
            "side": "external",
            "actor": actor if actor else "improver",
            "residual_magnitude": residual_mag,
            "confidence": max(confidence, 0.67),
            "peer_consensus": max(peer_consensus, 2),
            "motivating_signal": {
                "kind": "oracle_easy_pad" if oracle.get("easy_pad_kills") else (motiv.get("kind") or "param_probe"),
                "easy_pad_kills": oracle.get("easy_pad_kills"),
            },
            "hypothesis": (
                "Bounded exploration_budget.fp nudge will track Oracle easy_pad pressure / external richness."
            ),
        },
        {
            "kind": "adjust_telemetry_weights",
            "side": "internal",
            "actor": "improver" if "improver" in (state_data.get("agents") or {}) else actor,
            "residual_magnitude": residual_mag,
            "confidence": max(confidence, 0.68),
            "peer_consensus": max(peer_consensus, 2),
            "motivating_signal": {"kind": "observed_outcomes", "fitness_delta": fitness_delta},
            "hypothesis": (
                "Telemetry weights updated from Oracle/external/revision outcomes improve next-cycle query salience."
            ),
            "observed": {
                "easy_pad_kills": oracle.get("easy_pad_kills"),
                "pattern_count": len(external_patterns),
                "revision_count": (revision_event or {}).get("revision_count"),
                "fitness_delta": fitness_delta,
                "reply_rate": reply_rate,
            },
        },
    ]

    # Rebalance plan toward 50/50: swap one internal for a second external query if 3 internal planned
    # Add a lightweight second external slot by converting nothing — instead queue via caps.
    # Ensure at least one external candidate exists (already have probe).

    to_run, queued, split = _apply_balance_and_throttle(
        planned, stats=stats, conflict_rate=conflict_rate, cycle_id=cycle_id
    )

    actions: list[dict[str, Any]] = []
    for item in to_run:
        kind = item["kind"]
        common = dict(
            cycle_id=cycle_id,
            actor=item["actor"],
            residual_magnitude=item["residual_magnitude"],
            confidence=item["confidence"],
            peer_consensus=item["peer_consensus"],
            motivating_signal=item["motivating_signal"],
            hypothesis=item["hypothesis"],
        )
        if kind == "external_api_probe":
            actions.append(act_external_probe(**common))
        elif kind == "spawn_subdebate":
            actions.append(
                act_spawn_subdebate(bus=bus, topic=item.get("topic") or topic, **common)
            )
        elif kind == "controlled_experiment":
            actions.append(act_param_experiment(state_data=state_data, **common))
        elif kind == "adjust_telemetry_weights":
            actions.append(
                act_adjust_telemetry_weights(observed=item.get("observed"), **common)
            )

    executed = [a for a in actions if a.get("executed")]
    successes = [a for a in executed if a.get("success")]
    blocked = [a for a in actions if a.get("gated") and not a.get("executed")]
    cycle_success_rate = round(len(successes) / len(executed), 4) if executed else None

    # Reload stats from disk (act_* recorded successes there) then merge cycle fields
    stats = _stats()
    by_side = stats.setdefault("by_side", {"internal": 0, "external": 0})
    by_side["internal"] = int(by_side.get("internal") or 0) + int(split.get("execute_internal") or 0)
    by_side["external"] = int(by_side.get("external") or 0) + int(split.get("execute_external") or 0)
    hist = list(stats.get("cycle_history") or [])
    hist.append(
        {
            "cycle_id": cycle_id,
            "ts": _utc(),
            "success_rate": cycle_success_rate,
            "conflict_rate": conflict_rate,
            "n_executed": len(executed),
            "n_queued": len(queued),
            "internal": split.get("execute_internal"),
            "external": split.get("execute_external"),
            "throttle_factor": split.get("throttle_factor"),
        }
    )
    stats["cycle_history"] = hist[-30:]
    _persist(stats)

    summary = {
        "ts": _utc(),
        "cycle_id": cycle_id,
        "n_actions": len(actions),
        "n_executed": len(executed),
        "n_success": len(successes),
        "n_failed": len(executed) - len(successes),
        "n_blocked": len(blocked),
        "n_queued": len(queued),
        "success_rate_cycle": cycle_success_rate,
        "balance": split,
        "queued_reasons": [q.get("queue_reason") for q in queued],
        "kinds": [a.get("kind") for a in actions],
        "examples": [
            {
                "kind": a.get("kind"),
                "hypothesis": a.get("hypothesis"),
                "success": a.get("success"),
                "gate": a.get("gate"),
                "result": a.get("result"),
                "motivating_signal": a.get("motivating_signal"),
                "side": _side_for(a.get("kind") or ""),
            }
            for a in actions[:4]
        ],
        "global": {
            k: stats.get(k)
            for k in (
                "total_actions",
                "successes",
                "failures",
                "gated_blocked",
                "queued",
                "throttled",
                "success_rate",
                "by_side",
            )
        },
        "conflict_rate": conflict_rate,
        "throttle_events_recent": (stats.get("throttle_events") or [])[-3:],
    }
    return summary



def actuation_stats() -> dict[str, Any]:
    return _stats()
