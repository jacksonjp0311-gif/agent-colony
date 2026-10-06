"""Exploration budget — weak roles spawn/retire on hard-tier deltas;
mutate distribution MUST change after reverts.

Not open-ended RL. Bounded weights over conjecture mutations.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BUDGET_PATH = ROOT / "society" / "systems" / "exploration_budget.json"
HISTORY = ROOT / "society" / "benchmarks" / "conjecture_history.jsonl"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_dist(names: list[str]) -> dict[str, float]:
    if not names:
        return {}
    w = 1.0 / len(names)
    return {n: round(w, 6) for n in names}


def load_budget() -> dict[str, Any]:
    if BUDGET_PATH.exists():
        try:
            return json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "version": 1,
        "updated_at": _utc(),
        "mutate_distribution": {},
        "revert_penalties": {},
        "keep_rewards": {},
        "spawn_retire_log": [],
        "note": "Exploration budget. Distribution must change after reverts.",
    }


def save_budget(data: dict[str, Any]) -> None:
    data["updated_at"] = _utc()
    BUDGET_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUDGET_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def ensure_distribution(names: list[str]) -> dict[str, float]:
    data = load_budget()
    dist = dict(data.get("mutate_distribution") or {})
    changed = False
    for n in names:
        if n not in dist:
            dist[n] = 0.05
            changed = True
    # drop unknown
    dist = {k: float(v) for k, v in dist.items() if k in names}
    if not dist:
        dist = _default_dist(names)
        changed = True
    # renormalize
    s = sum(dist.values()) or 1.0
    dist = {k: round(v / s, 6) for k, v in dist.items()}
    if changed or data.get("mutate_distribution") != dist:
        data["mutate_distribution"] = dist
        save_budget(data)
    return dist


def record_outcome(mutation: str, decision: str, *, kind: str = "") -> dict[str, Any]:
    """After keep/revert, mutate distribution MUST change (especially on revert)."""
    from colony.conjecture_mutations import MUTATION_SNIPPETS

    names = [n for n, _, _ in MUTATION_SNIPPETS]
    data = load_budget()
    dist = ensure_distribution(names)
    before = dict(dist)
    penalties = dict(data.get("revert_penalties") or {})
    rewards = dict(data.get("keep_rewards") or {})

    if decision == "revert" and mutation:
        penalties[mutation] = int(penalties.get(mutation) or 0) + 1
        # Cut weight on reverted; boost least-tried / non-penalized
        dist[mutation] = max(0.001, float(dist.get(mutation) or 0.05) * 0.35)
        for n in names:
            if n == mutation:
                continue
            if n.startswith("easy_pad"):
                dist[n] = max(0.001, float(dist.get(n) or 0.05) * 0.5)
            else:
                dist[n] = float(dist.get(n) or 0.05) * 1.15
    elif decision == "keep" and mutation:
        rewards[mutation] = int(rewards.get(mutation) or 0) + 1
        dist[mutation] = float(dist.get(mutation) or 0.05) * 1.25
        # slight explore toward unused hard_enable
        for n in names:
            if n.startswith("easy_pad"):
                dist[n] = max(0.001, float(dist.get(n) or 0.05) * 0.7)

    s = sum(dist.values()) or 1.0
    dist = {k: round(v / s, 6) for k, v in dist.items()}
    changed = before != dist
    data["mutate_distribution"] = dist
    data["revert_penalties"] = penalties
    data["keep_rewards"] = rewards
    data["last_outcome"] = {
        "mutation": mutation,
        "decision": decision,
        "kind": kind,
        "distribution_changed": changed,
        "ts": _utc(),
    }
    save_budget(data)
    return data["last_outcome"]


def pick_mutation_order(candidates: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Reorder mutation candidates by exploration distribution (high weight first).

    Phase 1/2: prepend mutations listed in recent lesson catalog_hint.add_mutation.
    """
    boosted: list[tuple[str, str, str]] = []
    try:
        from colony.lessons import catalog_hints_from_lessons
        hints = catalog_hints_from_lessons(lookback=20)
        want = [str(h.get("add_mutation") or "") for h in hints if h.get("add_mutation")]
        by_name = {n: (n, k, s) for n, k, s in candidates}
        for name in want:
            if name in by_name:
                boosted.append(by_name.pop(name))
        rest = list(by_name.values())
    except Exception:
        rest = list(candidates)
        boosted = []
    names = [n for n, _, _ in rest]
    dist = ensure_distribution(names) if names else {}
    rest_sorted = sorted(rest, key=lambda t: float(dist.get(t[0]) or 0.0), reverse=True)
    return boosted + rest_sorted


def apply_hard_tier_spawn_retire(
    *,
    evo: Any,
    cycle_id: str,
    delta_pass: float,
) -> dict[str, Any]:
    """Weak roles spawn/retire keyed to measured hard-tier + Oracle-pass deltas."""
    data = load_budget()
    log = list(data.get("spawn_retire_log") or [])
    spawned: list[str] = []
    retired: list[str] = []
    if evo is None:
        return {"spawned": [], "retired": [], "delta_pass": delta_pass}
    oracle_passes = 0
    try:
        from colony.oracle import counts as oracle_counts
        oracle_passes = int(oracle_counts().get("passes") or 0)
    except Exception:
        pass
    prev_op = int(data.get("last_oracle_passes") or oracle_passes)
    op_delta = oracle_passes - prev_op
    data["last_oracle_passes"] = oracle_passes
    # Positive hard or oracle delta → credit / spawn specialist signals
    if delta_pass > 0 or op_delta > 0:
        log.append({
            "ts": _utc(), "cycle_id": cycle_id, "event": "credit",
            "delta_pass": delta_pass, "oracle_pass_delta": op_delta,
        })
        for role in ("oracle_scribe", "stem_checker", "geometer"):
            if evo is not None and hasattr(evo, "registry"):
                if role not in evo.registry.active():
                    spawned.append(role)
    else:
        # No Oracle-pass lift → pressure retire of flourish specialists
        log.append({
            "ts": _utc(), "cycle_id": cycle_id, "event": "pressure_retire_no_oracle_lift",
            "delta_pass": delta_pass, "oracle_pass_delta": op_delta,
        })
        if evo is not None and hasattr(evo, "registry"):
            founding = {"spark", "tribute_keeper"}
            for role, agent in list(evo.registry.active().items()):
                if role in founding:
                    continue
                if role in ("oracle_scribe", "stem_checker", "debate_deepener") and int(agent.get("cycles_served") or 0) >= 4:
                    agent["oracle_no_lift_retire"] = True
                    retired.append(role)
    data["spawn_retire_log"] = log[-40:]
    save_budget(data)
    return {
        "spawned": spawned,
        "retired": retired,
        "delta_pass": delta_pass,
        "oracle_pass_delta": op_delta,
        "logged": True,
    }


def distribution_fingerprint() -> str:
    data = load_budget()
    dist = data.get("mutate_distribution") or {}
    items = sorted((k, round(float(v), 4)) for k, v in dist.items())
    return json.dumps(items, separators=(",", ":"))
