"""Colony-wide learning loop: method cards and failures become Hive trials.

The colony improver proposes at most one legal trial per cycle, built
from research-desk method cards and current self-heal findings, and
sends it through Hive's deterministic retrieval and vote. Nothing
fetched is executed. Adopt is recorded as "kept" only when the
self-heal trial window is strictly better than its baseline *and* the
twin control does not lead on the same metric. Adopt and revert are
append-only labeled examples; per-card and per-op-family rates are
derived from those records. Hive shadow picks are scored each cycle.

Control is a no-op. Pytest does not write the repo. The Wilson 700‰
gate, the Oracle, the 0.70 authorize threshold, the 150 cap, and
Athanor are untouched.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PREFIX = "card_"
LOG_NAME = "learning_loop.jsonl"
STATE_NAME = "learning_loop.json"

# Every Hive-known desk exposes at least one bounded knob already in
# KNOB_SPECS. This is a registry, not a new bound and not a widening
# of any existing one. Values are knob names the desk reads or that
# govern its budget / routing / retry.
DESK_KNOBS: dict[str, tuple[str, ...]] = {
    "conjecture": ("curriculum_pace", "retry_policy_cycles"),
    "hunt": ("routing_explore_weight", "curriculum_pace"),
    "frontier": ("deep_term_cap", "deep_digits", "deep_seconds"),
    "oeis": ("fast_term_cap", "gf_term_cap", "deep_term_cap"),
    "proof": ("park_cycles", "retry_policy_cycles"),
    "gather": ("unused_menu_cycles", "routing_explore_weight"),
    "improve": ("step_size", "evaluation_window", "perturb_cooldown_cycles"),
    "oracle_scribe": ("evaluation_window",),
    "stem_checker": ("quarantine_cycles", "quarantine_fail_threshold"),
    "research": ("desk_budget", "curriculum_pace", "retry_policy_cycles",
                 "routing_explore_weight"),
}


def _repo() -> Path:
    return Path(__file__).resolve().parents[1]


def log_path() -> Path:
    if os.environ.get("COLONY_LEARNING_LOG"):
        return Path(os.environ["COLONY_LEARNING_LOG"])
    try:
        from colony.arm import data_dir
        return data_dir() / "commons" / LOG_NAME
    except Exception:
        return _repo() / "data" / "commons" / LOG_NAME


def state_path() -> Path:
    if os.environ.get("COLONY_LEARNING_STATE"):
        return Path(os.environ["COLONY_LEARNING_STATE"])
    try:
        from colony.arm import society_dir
        return society_dir() / "systems" / STATE_NAME
    except Exception:
        return _repo() / "society" / "systems" / STATE_NAME


def markdown_path() -> Path:
    if os.environ.get("COLONY_LEARNING_MD"):
        return Path(os.environ["COLONY_LEARNING_MD"])
    try:
        from colony.arm import society_dir
        return society_dir() / "LEARNING.md"
    except Exception:
        return _repo() / "society" / "LEARNING.md"


def self_mod_ok() -> bool:
    try:
        from colony.arm import self_mod_enabled
        return bool(self_mod_enabled())
    except Exception:
        return True


def _pytest_would_write_repo(path: Path) -> bool:
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    try:
        real = _repo().resolve()
        resolved = path.resolve()
        return real in resolved.parents or resolved.parent == real
    except Exception:
        return True


def _utc() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _event_id(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _append(path: Path, row: dict[str, Any]) -> None:
    if _pytest_would_write_repo(path):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _atomic_write(path: Path, text: str) -> None:
    if _pytest_would_write_repo(path):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _empty_state() -> dict[str, Any]:
    return {
        "version": 1,
        "pending": [],
        "examples": [],
        "cards": {},
        "families": {},
        "shadow": {
            "pending": 0, "resolved": 0, "correct": 0,
            "incorrect": 0, "accuracy_permille": None, "ts": "",
        },
        "twin_pending": [],
        "last_cycle": "",
        "n_proposed": 0,
        "n_kept": 0,
        "n_reverted": 0,
        "n_voided": 0,
        "n_twin_held": 0,
        "applied_to_live_oracle": False,
        "authorized": False,
        "note": (
            "Method-card trials judged by self-heal windows and the twin "
            "control. Kept only if strictly better on both. Not AGI."
        ),
    }


def load_state() -> dict[str, Any]:
    path = state_path()
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _empty_state()
                base.update(data)
                return base
    except Exception:
        pass
    return _empty_state()


def save_state(state: dict[str, Any]) -> None:
    payload = dict(state)
    payload["applied_to_live_oracle"] = False
    payload["authorized"] = False
    _atomic_write(state_path(), json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def load_log() -> list[dict[str, Any]]:
    path = log_path()
    rows: list[dict[str, Any]] = []
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
    except Exception:
        return []
    return rows


def op_family(action: Mapping[str, Any] | None) -> str:
    if not isinstance(action, Mapping):
        return "unknown"
    op = str(action.get("op") or "")
    if op == "set_knob":
        return f"set_knob:{action.get('name') or ''}"
    if op:
        return op
    return "unknown"


def _validate_action(action: Mapping[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    try:
        from hive import ops as HO
        v = HO.validate(dict(action))
        payload = dict(getattr(v, "payload", None) or action)
        reason = str(getattr(v, "reason", "") or "")
        return bool(getattr(v, "ok", False)), reason, payload
    except Exception as exc:  # noqa: BLE001
        op = str(action.get("op") or "")
        if op not in ("set_knob", "add_family_rotation", "reorder_desk"):
            return False, f"hive_unavailable:{type(exc).__name__}", dict(action)
        return True, "", dict(action)


def _load_cards() -> list[dict[str, Any]]:
    try:
        from colony.research_desk import load_cards
        return list(load_cards() or [])
    except Exception:
        return []


def _tried_ids(state: dict[str, Any] | None = None) -> set[str]:
    st = state if state is not None else load_state()
    ids = set((st.get("cards") or {}).keys())
    for row in list(st.get("pending") or []) + list(st.get("examples") or []):
        cid = str(row.get("card_id") or "")
        if cid:
            ids.add(cid)
    return ids


def next_card_proposal(
    findings: list[Mapping[str, Any]] | None = None,
    *,
    cards: list[Mapping[str, Any]] | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Deterministic next untried legal method-card action, or None.

    Prefers a card whose op family is mentioned in a current failure
    finding; otherwise the oldest untried legal card. One card only.
    """
    if not self_mod_ok():
        return None
    st = state if state is not None else load_state()
    pool = list(cards if cards is not None else _load_cards())
    tried = _tried_ids(st)
    legal: list[dict[str, Any]] = []
    for card in pool:
        cid = str(card.get("id") or "")
        if not cid or cid in tried:
            continue
        action = card.get("op") if isinstance(card.get("op"), Mapping) else {}
        ok, reason, payload = _validate_action(action)
        if not ok:
            continue
        legal.append({
            "card_id": cid,
            "method": str(card.get("method") or ""),
            "action": {
                k: payload[k] if k in payload else action[k]
                for k in ("op", "name", "direction", "family", "order", "value")
                if k in payload or k in action
            },
            "source": card.get("source") or {},
            "evidence": str(card.get("evidence") or "")[:160],
            "reason": reason,
        })
    if not legal:
        return None
    # Prefer a card whose knob/op is hinted by a current finding.
    hints: set[str] = set()
    for f in findings or []:
        if not isinstance(f, Mapping):
            continue
        for key in ("knob", "name", "cap_name"):
            if f.get(key):
                hints.add(str(f[key]))
        ev = f.get("evidence") if isinstance(f.get("evidence"), Mapping) else {}
        for key in ("knob", "name", "cap_name"):
            if ev.get(key):
                hints.add(str(ev[key]))
        for pair in list(f.get("suggest") or ev.get("suggest") or []):
            if isinstance(pair, (list, tuple)) and pair:
                hints.add(str(pair[0]))
    for item in legal:
        name = str((item["action"] or {}).get("name") or "")
        if name and name in hints:
            return item
    return legal[0]


def attach_card_findings(
    findings: list[dict[str, Any]],
    cycle_id: str = "",
    *,
    cards: list[Mapping[str, Any]] | None = None,
    state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Append at most one method_card finding with a legal card_action.

    Existing findings are left intact (and gain a card_action copy when
    the card targets a knob they already mention). Control is a no-op.
    """
    out = [dict(f) for f in findings if isinstance(f, Mapping)]
    if not self_mod_ok():
        return out
    proposal = next_card_proposal(out, cards=cards, state=state)
    if proposal is None:
        return out
    action = dict(proposal["action"])
    card_id = proposal["card_id"]
    for f in out:
        name = str(f.get("knob") or f.get("name") or "")
        if name and name == str(action.get("name") or ""):
            f.setdefault("card_action", action)
            f.setdefault("card_id", card_id)
    out.append({
        "kind": "method_card",
        "label": "method_card",
        "failure_class": "method_card",
        "card_id": card_id,
        "card_action": action,
        "method": proposal["method"],
        "suggest": (
            [(action.get("name"), action.get("direction") or "up")]
            if action.get("op") == "set_knob" and action.get("name")
            else []
        ),
        "evidence": {
            "card_id": card_id,
            "method": proposal["method"],
            "source": proposal.get("source") or {},
            "snippet": proposal.get("evidence") or "",
            "cycle_id": cycle_id,
        },
        "applied_to_live_oracle": False,
        "authorized": False,
    })
    return out


def _bump_rate(bucket: dict[str, Any], key: str, outcome: str) -> None:
    # Provisional adopts wait for a twin judgment; do not count them twice.
    if outcome not in ("kept", "reverted", "reverted_twin", "voided"):
        return
    row = dict(bucket.get(key) or {"n": 0, "kept": 0, "reverted": 0, "voided": 0})
    row["n"] = int(row.get("n") or 0) + 1
    if outcome == "kept":
        row["kept"] = int(row.get("kept") or 0) + 1
    elif outcome in ("reverted", "reverted_twin"):
        row["reverted"] = int(row.get("reverted") or 0) + 1
    elif outcome == "voided":
        row["voided"] = int(row.get("voided") or 0) + 1
    n = max(1, int(row["n"]))
    row["keep_rate_permille"] = int(1000 * int(row["kept"]) / n)
    bucket[key] = row


def record_example(
    event: Mapping[str, Any],
    *,
    state: dict[str, Any] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Append one labeled adopt/revert/void example and update rates."""
    st = state if state is not None else load_state()
    outcome = str(event.get("outcome") or event.get("event") or "")
    action = event.get("action") if isinstance(event.get("action"), Mapping) else {}
    family = str(event.get("family") or op_family(action))
    card_id = str(event.get("card_id") or "")
    row = {
        "event": "labeled_example",
        "outcome": outcome,
        "card_id": card_id,
        "method": str(event.get("method") or ""),
        "family": family,
        "action": dict(action) if action else {},
        "knob": event.get("knob"),
        "cycle_id": event.get("cycle_id") or "",
        "baseline_score": event.get("baseline_score"),
        "trial_score": event.get("trial_score"),
        "twin": event.get("twin"),
        "self_heal_helped": event.get("self_heal_helped"),
        "strictly_better": event.get("strictly_better"),
        "source": event.get("source") or "learning_loop",
        "applied_to_live_oracle": False,
        "authorized": False,
        "ts": event.get("ts") or _utc(),
    }
    row["id"] = str(event.get("id") or _event_id(row))
    # Dedupe by id so harvest is idempotent.
    seen = {str(x.get("id")) for x in (st.get("examples") or []) if isinstance(x, dict)}
    if row["id"] in seen:
        return row
    examples = list(st.get("examples") or [])
    examples.append(row)
    st["examples"] = examples[-400:]
    if outcome == "kept":
        st["n_kept"] = int(st.get("n_kept") or 0) + 1
    elif outcome in ("reverted", "reverted_twin"):
        st["n_reverted"] = int(st.get("n_reverted") or 0) + 1
    elif outcome == "voided":
        st["n_voided"] = int(st.get("n_voided") or 0) + 1
    if card_id:
        cards = dict(st.get("cards") or {})
        _bump_rate(cards, card_id, outcome)
        if card_id in cards and row.get("method"):
            cards[card_id]["method"] = row["method"]
        st["cards"] = cards
    families = dict(st.get("families") or {})
    _bump_rate(families, family, outcome)
    st["families"] = families
    if write and self_mod_ok():
        _append(log_path(), row)
        save_state(st)
    return row


def self_heal_strictly_better(
    trial_score: Any, baseline_score: Any,
) -> bool:
    """Same rule self-heal uses: trial window score must be strictly higher."""
    try:
        return float(trial_score) > float(baseline_score)
    except (TypeError, ValueError):
        return False


def twin_strictly_better(
    treatment: Mapping[str, Any] | None,
    control: Mapping[str, Any] | None,
) -> tuple[bool, dict[str, Any]]:
    """Treatment is strictly better than control on the self-heal metric.

    Metric, in order, is oracle pass count, then verified depth, then
    (only as a last documented signal, never as a discovery claim)
    fitness. A missing arm fails closed (not better). Equal is not
    strictly better. Fitness alone never decides a keep.
    """
    info: dict[str, Any] = {
        "compared": False,
        "reason": "missing_arm",
        "oracle_passes": None,
        "verified_depth_sum": None,
        "fitness": None,
    }
    if not isinstance(treatment, Mapping) or not isinstance(control, Mapping):
        return False, info
    def _num(row: Mapping[str, Any], key: str) -> float | None:
        if key not in row or row[key] is None:
            return None
        try:
            return float(row[key])
        except (TypeError, ValueError):
            return None
    t_pass, c_pass = _num(treatment, "oracle_passes"), _num(control, "oracle_passes")
    t_depth, c_depth = _num(treatment, "verified_depth_sum"), _num(control, "verified_depth_sum")
    t_fit, c_fit = _num(treatment, "fitness"), _num(control, "fitness")
    info.update({
        "compared": True,
        "oracle_passes": {"treatment": t_pass, "control": c_pass},
        "verified_depth_sum": {"treatment": t_depth, "control": c_depth},
        "fitness": {"treatment": t_fit, "control": c_fit},
    })
    if t_pass is None or c_pass is None:
        info["reason"] = "missing_oracle"
        return False, info
    if t_pass > c_pass:
        info["reason"] = "oracle_passes"
        return True, info
    if t_pass < c_pass:
        info["reason"] = "control_leads_passes"
        return False, info
    if t_depth is None or c_depth is None:
        info["reason"] = "missing_depth"
        return False, info
    if t_depth > c_depth:
        info["reason"] = "verified_depth"
        return True, info
    if t_depth < c_depth:
        info["reason"] = "control_leads_depth"
        return False, info
    info["reason"] = "tied_or_fitness_only"
    # Fitness can fluctuate; a fitness-only lead is not a keep.
    return False, info


def decide_keep(
    *,
    trial_score: Any,
    baseline_score: Any,
    treatment: Mapping[str, Any] | None,
    control: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Adopt only if strictly better on the self-heal window *and* the twin."""
    heal_ok = self_heal_strictly_better(trial_score, baseline_score)
    twin_ok, twin_info = twin_strictly_better(treatment, control)
    keep = bool(heal_ok and twin_ok)
    reason = "kept" if keep else (
        "self_heal_not_better" if not heal_ok else (
            "twin_not_better" if twin_info.get("compared") else "twin_unavailable"
        )
    )
    return {
        "keep": keep,
        "reason": reason,
        "self_heal_helped": heal_ok,
        "twin_better": twin_ok,
        "twin": twin_info,
        "baseline_score": baseline_score,
        "trial_score": trial_score,
    }


def load_twin_arms() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        from colony.twin import load_scoreboard
        board = load_scoreboard() or {}
        t = board.get("treatment") if isinstance(board.get("treatment"), Mapping) else None
        c = board.get("control") if isinstance(board.get("control"), Mapping) else None
        return (dict(t) if t else None, dict(c) if c else None)
    except Exception:
        return None, None


def score_shadows(
    hive_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize Hive shadow picks (resolved and still open)."""
    try:
        if hive_state is None:
            from colony.hive_adapter import load_state as load_hive
            hive_state = load_hive() or {}
    except Exception:
        hive_state = hive_state or {}
    shadows = list((hive_state or {}).get("shadows") or [])
    resolved = [s for s in shadows if isinstance(s, dict) and s.get("resolved")]
    pending = [s for s in shadows if isinstance(s, dict) and not s.get("resolved")]
    correct = [s for s in resolved if s.get("correct") is True]
    incorrect = [s for s in resolved if s.get("correct") is False]
    n_res = len(resolved)
    acc = int(1000 * len(correct) / n_res) if n_res else None
    return {
        "pending": len(pending),
        "resolved": n_res,
        "correct": len(correct),
        "incorrect": len(incorrect),
        "unlabeled": n_res - len(correct) - len(incorrect),
        "accuracy_permille": acc,
        "ts": _utc(),
        "source": "hive_shadows",
    }


def _heal_evidence() -> list[dict[str, Any]]:
    try:
        from colony.self_heal import load_state as load_heal
        ev = list((load_heal() or {}).get("evidence") or [])
        return [e for e in ev if isinstance(e, dict)]
    except Exception:
        return []


def _map_heal_outcome(event: Mapping[str, Any]) -> str | None:
    name = str(event.get("event") or "")
    if name in ("adopt", "trial_adopted"):
        return "provisional_adopt"
    if name in ("revert", "trial_reverted"):
        return "reverted"
    if "void" in name:
        return "voided"
    return None


def harvest_outcomes(
    cycle_id: str = "",
    *,
    state: dict[str, Any] | None = None,
    evidence: list[Mapping[str, Any]] | None = None,
    treatment: Mapping[str, Any] | None = None,
    control: Mapping[str, Any] | None = None,
    write: bool = True,
) -> list[dict[str, Any]]:
    """Turn new self-heal close events into labeled examples."""
    st = state if state is not None else load_state()
    ev = list(evidence if evidence is not None else _heal_evidence())
    if treatment is None and control is None:
        treatment, control = load_twin_arms()
    seen = {str(x.get("source_id") or x.get("id")) for x in (st.get("examples") or [])}
    seen |= {str(x.get("source_id") or "") for x in (st.get("twin_pending") or [])}
    written: list[dict[str, Any]] = []
    pending_cards = list(st.get("pending") or [])

    def _card_for(event: Mapping[str, Any]) -> dict[str, Any]:
        knob = str(event.get("knob") or "")
        fp = str(event.get("swarm_fingerprint") or event.get("fingerprint") or "")
        for p in pending_cards:
            if fp and str(p.get("fingerprint") or "") == fp:
                return p
            if knob and str(p.get("knob") or "") == knob:
                return p
        return {}

    for event in ev:
        outcome = _map_heal_outcome(event)
        if not outcome:
            continue
        sid = str(event.get("id") or "")
        if sid and sid in seen:
            continue
        card = _card_for(event)
        action = event.get("action") if isinstance(event.get("action"), Mapping) else {}
        if not action and event.get("knob"):
            action = {
                "op": "set_knob",
                "name": event.get("knob"),
                "direction": event.get("direction"),
                "value": event.get("to"),
            }
        decision = decide_keep(
            trial_score=event.get("trial_score"),
            baseline_score=event.get("baseline_score"),
            treatment=treatment,
            control=control,
        )
        final = outcome
        if outcome == "provisional_adopt":
            if decision["keep"]:
                final = "kept"
            elif decision["reason"] == "twin_unavailable":
                final = "provisional_adopt"
            else:
                final = "reverted_twin" if decision["self_heal_helped"] else "reverted"
        row = record_example(
            {
                "outcome": final,
                "card_id": card.get("card_id") or event.get("card_id") or "",
                "method": card.get("method") or event.get("method") or "",
                "action": action,
                "family": op_family(action),
                "knob": event.get("knob"),
                "cycle_id": event.get("cycle_id") or cycle_id,
                "baseline_score": event.get("baseline_score"),
                "trial_score": event.get("trial_score"),
                "twin": decision.get("twin"),
                "self_heal_helped": decision.get("self_heal_helped"),
                "strictly_better": decision.get("keep"),
                "source": "self_heal",
                "source_id": sid,
                "id": sid or None,
                "ts": event.get("ts"),
            },
            state=st,
            write=False,
        )
        row["source_id"] = sid
        if final == "provisional_adopt":
            tpend = list(st.get("twin_pending") or [])
            tpend.append({
                "source_id": sid,
                "card_id": row.get("card_id"),
                "method": row.get("method"),
                "action": row.get("action"),
                "knob": row.get("knob"),
                "cycle_id": row.get("cycle_id"),
                "baseline_score": row.get("baseline_score"),
                "trial_score": row.get("trial_score"),
                "ts": row.get("ts"),
            })
            st["twin_pending"] = tpend[-50:]
            st["n_twin_held"] = int(st.get("n_twin_held") or 0) + 1
        written.append(row)
        if sid:
            seen.add(sid)
    if write and self_mod_ok() and written:
        for row in written:
            _append(log_path(), row)
        save_state(st)
    return written


def judge_twin_pending(
    *,
    treatment: Mapping[str, Any] | None = None,
    control: Mapping[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    write: bool = True,
) -> list[dict[str, Any]]:
    """Close provisional adopts once a twin snapshot is available.

    Called from the twin-scoreboard job. Does not move knobs (the
    treatment arm is not running here). A twin_not_better result is a
    labeled revert; a later treatment cycle may restore the knob.
    """
    st = state if state is not None else load_state()
    if treatment is None and control is None:
        treatment, control = load_twin_arms()
    remaining: list[dict[str, Any]] = []
    written: list[dict[str, Any]] = []
    for pend in list(st.get("twin_pending") or []):
        decision = decide_keep(
            trial_score=pend.get("trial_score"),
            baseline_score=pend.get("baseline_score"),
            treatment=treatment,
            control=control,
        )
        if decision["reason"] == "twin_unavailable":
            remaining.append(pend)
            continue
        final = "kept" if decision["keep"] else "reverted_twin"
        # Remove the provisional from keep-rate by recording the final only.
        row = record_example(
            {
                **pend,
                "outcome": final,
                "twin": decision.get("twin"),
                "self_heal_helped": decision.get("self_heal_helped"),
                "strictly_better": decision.get("keep"),
                "source": "twin_judge",
                "id": f"twin:{pend.get('source_id') or pend.get('id') or _event_id(pend)}",
            },
            state=st,
            write=False,
        )
        written.append(row)
    st["twin_pending"] = remaining
    if write and self_mod_ok():
        for row in written:
            _append(log_path(), row)
        save_state(st)
        write_markdown(st)
    return written


def note_proposal(
    proposal: Mapping[str, Any],
    *,
    cycle_id: str = "",
    state: dict[str, Any] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Remember a method-card proposal that went to Hive this cycle."""
    st = state if state is not None else load_state()
    row = {
        "event": "proposed",
        "card_id": proposal.get("card_id") or "",
        "method": proposal.get("method") or "",
        "action": dict(proposal.get("action") or proposal.get("card_action") or {}),
        "knob": (proposal.get("action") or proposal.get("card_action") or {}).get("name")
                if isinstance(proposal.get("action") or proposal.get("card_action"), Mapping)
                else proposal.get("knob"),
        "fingerprint": proposal.get("fingerprint") or "",
        "cycle_id": cycle_id or proposal.get("cycle_id") or "",
        "ts": _utc(),
    }
    pending = list(st.get("pending") or [])
    # Replace an older pending row for the same card.
    pending = [p for p in pending if str(p.get("card_id")) != str(row["card_id"])]
    pending.append(row)
    st["pending"] = pending[-50:]
    st["n_proposed"] = int(st.get("n_proposed") or 0) + 1
    st["last_cycle"] = cycle_id or st.get("last_cycle") or ""
    if write and self_mod_ok():
        _append(log_path(), {**row, "applied_to_live_oracle": False, "authorized": False})
        save_state(st)
    return row


def desk_knobs() -> dict[str, tuple[str, ...]]:
    return {k: tuple(v) for k, v in DESK_KNOBS.items()}


def knobs_are_bounded(specs: Mapping[str, Any] | None = None) -> tuple[bool, list[str]]:
    """Every registered desk knob exists in KNOB_SPECS with lo < hi."""
    if specs is None:
        try:
            from colony.self_heal import KNOB_SPECS
            specs = KNOB_SPECS
        except Exception:
            return False, ["no_knob_specs"]
    missing: list[str] = []
    for desk, names in DESK_KNOBS.items():
        for name in names:
            spec = specs.get(name) if hasattr(specs, "get") else None
            if spec is None and isinstance(specs, Mapping):
                # KnobSpec objects or dicts
                spec = specs.get(name)
            if spec is None:
                missing.append(f"{desk}:{name}:missing")
                continue
            lo = getattr(spec, "lo", None)
            hi = getattr(spec, "hi", None)
            if lo is None and isinstance(spec, Mapping):
                lo, hi = spec.get("lo"), spec.get("hi")
            try:
                if not (float(lo) < float(hi)):
                    missing.append(f"{desk}:{name}:unbounded")
            except (TypeError, ValueError):
                missing.append(f"{desk}:{name}:unbounded")
    return (not missing), missing


def format_visibility(state: dict[str, Any] | None = None) -> str:
    st = state if state is not None else load_state()
    cards = st.get("cards") or {}
    shadow = st.get("shadow") or {}
    acc = shadow.get("accuracy_permille")
    acc_s = f"{acc}‰" if acc is not None else "n/a"
    return (
        f"method cards tried {len(cards)}, kept {st.get('n_kept') or 0}, "
        f"reverted {st.get('n_reverted') or 0}, voided {st.get('n_voided') or 0}; "
        f"proposed {st.get('n_proposed') or 0}; "
        f"twin-held {len(st.get('twin_pending') or [])}; "
        f"Hive shadows resolved {shadow.get('resolved') or 0} "
        f"(correct {shadow.get('correct') or 0}, accuracy {acc_s}). "
        "Kept only if strictly better than the self-heal baseline and the twin. "
        "Not AGI."
    )


def render_markdown(state: dict[str, Any] | None = None) -> str:
    """Plain-English page: method cards tried, kept, reverted."""
    st = state if state is not None else load_state()
    cards = st.get("cards") or {}
    families = st.get("families") or {}
    examples = list(st.get("examples") or [])
    shadow = st.get("shadow") or {}
    lines = [
        "# Colony learning loop",
        "",
        "The colony proposes trials from public method cards and from its",
        "own failures. Hive's deterministic vote chooses at most one legal",
        "op. A change is **kept** only when the self-heal trial window is",
        "strictly better than its baseline *and* the twin control does not",
        "lead on Oracle passes or verified depth. Fitness alone never",
        "decides a keep. Reverts and voids are recorded too. This is not",
        "AGI, not a novel theorem, and not a breakthrough claim.",
        "",
        f"- Method cards tried: **{len(cards)}**",
        f"- Kept: **{st.get('n_kept') or 0}**",
        f"- Reverted (including twin-not-better): **{st.get('n_reverted') or 0}**",
        f"- Voided (environment changed mid-trial): **{st.get('n_voided') or 0}**",
        f"- Proposed this snapshot: **{st.get('n_proposed') or 0}**",
        f"- Waiting on a twin judgment: **{len(st.get('twin_pending') or [])}**",
        (
            f"- Hive shadow picks: resolved {shadow.get('resolved') or 0}, "
            f"correct {shadow.get('correct') or 0}, "
            f"pending {shadow.get('pending') or 0}, "
            f"accuracy {shadow.get('accuracy_permille') if shadow.get('accuracy_permille') is not None else 'n/a'}"
            + ("‰" if shadow.get("accuracy_permille") is not None else "")
        ),
        "",
        "## Per method card",
        "",
    ]
    if not cards:
        lines.append("_None yet._")
        lines.append("")
    else:
        lines.append("| Card | Method | Tried | Kept | Reverted | Keep rate |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
        for cid, row in sorted(cards.items()):
            rate = row.get("keep_rate_permille")
            rate_s = f"{rate}‰" if rate is not None else "—"
            lines.append(
                f"| `{cid}` | {row.get('method') or '—'} | {row.get('n') or 0} | "
                f"{row.get('kept') or 0} | {row.get('reverted') or 0} | {rate_s} |"
            )
        lines.append("")
    lines.extend(["## Per op family", ""])
    if not families:
        lines.append("_None yet._")
        lines.append("")
    else:
        lines.append("| Family | Tried | Kept | Reverted | Keep rate |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for fam, row in sorted(families.items()):
            rate = row.get("keep_rate_permille")
            rate_s = f"{rate}‰" if rate is not None else "—"
            lines.append(
                f"| `{fam}` | {row.get('n') or 0} | {row.get('kept') or 0} | "
                f"{row.get('reverted') or 0} | {rate_s} |"
            )
        lines.append("")
    lines.extend(["## Recent outcomes", ""])
    if not examples:
        lines.append("_None yet._")
    else:
        for ex in examples[-12:]:
            lines.append(
                f"- `{ex.get('outcome')}` · card `{ex.get('card_id') or '—'}` · "
                f"family `{ex.get('family') or '—'}` · cycle `{ex.get('cycle_id') or '—'}` "
                f"(baseline {ex.get('baseline_score')}, trial {ex.get('trial_score')})"
            )
    lines.extend(["", "Not AGI. Not discovery. Human authorize still required for durable accepts.", ""])
    return "\n".join(lines) + "\n"


def write_markdown(state: dict[str, Any] | None = None) -> Path:
    path = markdown_path()
    _atomic_write(path, render_markdown(state))
    return path


def dashboard_section(state: dict[str, Any] | None = None) -> str:
    """HTML snippet for the colony dashboard."""
    from html import escape
    st = state if state is not None else load_state()
    body = escape(format_visibility(st))
    rows = []
    for cid, row in list((st.get("cards") or {}).items())[:12]:
        rows.append(
            "<li><code>{}</code> {} — tried {}, kept {}, reverted {}</li>".format(
                escape(str(cid)),
                escape(str(row.get("method") or "")),
                int(row.get("n") or 0),
                int(row.get("kept") or 0),
                int(row.get("reverted") or 0),
            )
        )
    listing = "".join(rows) or "<li><em>None yet.</em></li>"
    return (
        "<h2>Method cards tried, kept, reverted</h2>\n"
        f"<p>{body}</p>\n"
        f"<ul>{listing}</ul>\n"
    )


def run_cycle(cycle_id: str = "", **kwargs: Any) -> dict[str, Any]:
    """Harvest outcomes, score shadows, write the snapshot. Fail-soft."""
    try:
        if not self_mod_ok():
            return {"ran": False, "reason": "control_arm", "examples": [], "shadow": {}}
        st = load_state()
        # Remember a fresh method-card finding if the caller passed one.
        proposal = kwargs.get("proposal")
        if isinstance(proposal, Mapping) and proposal.get("card_id"):
            note_proposal(proposal, cycle_id=cycle_id, state=st, write=False)
        harvested = harvest_outcomes(cycle_id, state=st, write=False)
        judged = judge_twin_pending(state=st, write=False)
        shadow = score_shadows(kwargs.get("hive_state"))
        st["shadow"] = shadow
        st["last_cycle"] = cycle_id or st.get("last_cycle") or ""
        if self_mod_ok():
            for row in harvested + judged:
                _append(log_path(), row)
            save_state(st)
            write_markdown(st)
        return {
            "ran": True,
            "cycle_id": cycle_id,
            "examples": harvested,
            "twin_judged": judged,
            "shadow": shadow,
            "visibility": format_visibility(st),
            "n_kept": st.get("n_kept") or 0,
            "n_reverted": st.get("n_reverted") or 0,
            "applied_to_live_oracle": False,
            "authorized": False,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ran": False,
            "reason": f"error:{type(exc).__name__}",
            "examples": [],
            "shadow": {},
        }


on_cycle = run_cycle
