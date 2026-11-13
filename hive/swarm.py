"""Hive: agents label failures, retrieve fixes, and learn.

Each evolve cycle:

* every swarm role independently labels observed failures and proposes
  a bounded fix action from the closed vocabulary in ``hive.ops``
* proposals are scored by Bitwork retrieval against the shared,
  append-only fix library
* disagreements are resolved by a vote plus Bitwork confidence; the
  Wilson 95% gate abstains when the calibrated lower bound is below
  700 permille
* at most ``MAX_ACTIONS_PER_CYCLE`` accepted actions are applied,
  knob changes through the existing self-heal trial / adopt / revert
  machinery (and its corrected ``new_depth`` metric), other ops
  through an equivalent windowed trial using the same fixed metric
* outcomes (adopt = positive example, revert = negative example) are
  written back to the shared library so the next cycle's routing
  compounds what just happened

The Oracle, the P ≥ 0.70 gate, the 150 cap, Athanor math, the
append-only witness, and human authorize are not in this loop and
cannot be set. Failures here never break the evolve cycle. No
external model is called.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import hive.ops as FA
import hive.library as FL
from hive.bitwork import (
    WILSON_ACCEPT_PERMILLE,
    Match,
    Router,
    action_fingerprint,
    wilson_lower_permille,
)

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "society" / "systems" / "swarm_learn.json"
EVENT_LOG = ROOT / "data" / "commons" / "swarm_learn.jsonl"
RULES_PATH = ROOT / "society" / "systems" / "swarm_rules.json"

# At most this many accepted actions begin a trial on one cycle.
# One is enough: self-heal already allows only one knob trial at a time.
MAX_ACTIONS_PER_CYCLE = 1

# Existing colony personas used as swarm roles. Each has a focus.
SWARM_ROLES: tuple[str, ...] = (
    "improver",
    "pathfinder",
    "stem_checker",
    "surveyor",
    "archivist",
    "legislator",
)

# Role → diagnosis kinds it will label, and ops it may propose.
_ROLE_FOCUS: dict[str, dict[str, Any]] = {
    "improver": {
        "labels": (
            "repeated_targets", "no_progress_perturb", "immediate_reentry",
            "dead_end_streak", "flat_passes", "high_revert_rate",
        ),
        "ops": ("set_knob",),
        "preferred_knobs": (
            "perturb_epsilon", "unused_menu_cycles", "perturb_cooldown_cycles",
            "step_size", "evaluation_window", "park_cycles",
        ),
    },
    "pathfinder": {
        "labels": (
            "repeated_targets", "no_progress_perturb", "dead_end_streak",
            "empty_claim_label", "parked_proof_chain", "immediate_reentry",
        ),
        "ops": ("add_skip_rule", "add_park_rule"),
        "preferred_knobs": (),
    },
    "stem_checker": {
        "labels": ("trivial_claim", "empty_claim_label"),
        "ops": ("add_triviality_candidate",),
        "preferred_knobs": (),
    },
    "surveyor": {
        "labels": ("depth_at_physical_cap",),
        "ops": ("set_knob", "mark_ceiling"),
        "preferred_knobs": (
            "fast_term_cap", "gf_term_cap", "deep_term_cap",
            "deep_digits", "deep_seconds",
        ),
    },
    "archivist": {
        # Pure retrieval: any label, whatever Bitwork ranks first.
        "labels": (),
        "ops": tuple(FA.OPS),
        "preferred_knobs": (),
    },
    "legislator": {
        "labels": ("invariant_touch",),
        "ops": (),  # votes, does not propose
        "preferred_knobs": (),
    },
}

METRICS_KEEP = 48
EVIDENCE_KEEP = 200
CURVE_KEEP = 200


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _event_id() -> str:
    return uuid.uuid4().hex[:16]


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(dict(record), sort_keys=True, default=str, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _empty_state() -> dict[str, Any]:
    return {
        "version": 1,
        "seeded": False,
        "trial": None,
        "rules": [],
        "evidence": [],
        "curve": [],
        "adopted_count": 0,
        "reverted_count": 0,
        "abstained_count": 0,
        "applied_count": 0,
        "proposals_count": 0,
        "library_size": 0,
        "last_replay": None,
        "last_decision": None,
        "first_seen": {},
        "first_adopted": {},
        "seen_heal_ids": [],
        "seen_shadow_ids": [],
        "cycle_index": 0,
        "cycles": [],
        "calibration": None,
        "replay_calibrated": None,
        "shadows": [],
        "library_persisted": False,
    }


def load_state() -> dict[str, Any]:
    st = _empty_state()
    if not STATE_PATH.exists():
        return st
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return st
    if not isinstance(raw, dict):
        return st
    for k in st:
        if k in raw:
            st[k] = raw[k]
    st["adopted_count"] = int(st.get("adopted_count") or 0)
    st["reverted_count"] = int(st.get("reverted_count") or 0)
    st["abstained_count"] = int(st.get("abstained_count") or 0)
    st["applied_count"] = int(st.get("applied_count") or 0)
    st["proposals_count"] = int(st.get("proposals_count") or 0)
    st["library_size"] = int(st.get("library_size") or 0)
    st["cycle_index"] = int(st.get("cycle_index") or 0)
    st["seen_heal_ids"] = list(st.get("seen_heal_ids") or [])[-400:]
    st["cycles"] = list(st.get("cycles") or [])[-200:]
    st["evidence"] = list(st.get("evidence") or [])[-EVIDENCE_KEEP:]
    st["curve"] = list(st.get("curve") or [])[-CURVE_KEEP:]
    st["rules"] = [r for r in list(st.get("rules") or []) if isinstance(r, dict)]
    st["shadows"] = [s for s in list(st.get("shadows") or []) if isinstance(s, dict)]
    st["seen_shadow_ids"] = list(st.get("seen_shadow_ids") or [])[-400:]
    if not isinstance(st.get("calibration"), dict):
        st["calibration"] = None
    return st


def save_state(state: dict[str, Any]) -> None:
    cleaned = dict(state)
    cleaned["evidence"] = list(cleaned.get("evidence") or [])[-EVIDENCE_KEEP:]
    cleaned["curve"] = list(cleaned.get("curve") or [])[-CURVE_KEEP:]
    cleaned["applied_to_live_oracle"] = False
    cleaned["authorized"] = False
    _atomic_write(STATE_PATH, json.dumps(cleaned, indent=2, sort_keys=True, default=str))


def append_log(record: Mapping[str, Any]) -> None:
    row = dict(record)
    row.setdefault("ts", _utc())
    row.setdefault("id", _event_id())
    row["applied_to_live_oracle"] = False
    row["authorized"] = False
    _append_jsonl(EVENT_LOG, row)


def append_evidence(state: dict[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    ev = dict(event)
    ev.setdefault("id", _event_id())
    ev.setdefault("ts", _utc())
    ev["applied_to_live_oracle"] = False
    ev["authorized"] = False
    evidence = list(state.get("evidence") or [])
    evidence.append(ev)
    state["evidence"] = evidence[-EVIDENCE_KEEP:]
    append_log(ev)
    return ev


# ---------------------------------------------------------------------------
# Observations and role proposals
# ---------------------------------------------------------------------------

def observe(cycle_id: str = "") -> list[dict[str, Any]]:
    """Current-cycle findings, plus any raw failures just mined."""
    findings: list[dict[str, Any]] = []
    try:
        from hive import host
        findings.extend(host.diagnose(cycle_id) or [])
    except Exception:
        pass
    return [f for f in findings if isinstance(f, dict) and f.get("kind")]


@dataclass
class Proposal:
    role: str
    label: str
    action: dict[str, Any]
    fingerprint: str
    symptom: str
    match: Match | None = None
    ok: bool = True
    reason: str = "ok"
    veto: bool = False

    def as_dict(self) -> dict[str, Any]:
        m = self.match
        return {
            "role": self.role,
            "label": self.label,
            "action": self.action,
            "fingerprint": self.fingerprint,
            "symptom": self.symptom,
            "ok": self.ok,
            "reason": self.reason,
            "veto": self.veto,
            "score": None if m is None else m.score,
            "margin": None if m is None else m.margin,
            "lower_permille": None if m is None else m.lower_permille,
            "abstained": None if m is None else m.abstained,
            "accepted": None if m is None else m.accepted,
            "prototype_key": None if m is None else m.prototype_key,
        }


def _symptom_for(finding: Mapping[str, Any]) -> str:
    ev = finding.get("evidence") if isinstance(finding.get("evidence"), Mapping) else {}
    kind = str(finding.get("kind") or "").replace("_", " ")
    parts = [kind]
    for k, v in list(ev.items())[:6]:
        parts.append(f"{k} {v}")
    return " ".join(str(p) for p in parts)


def _action_for_role(
    role: str,
    finding: Mapping[str, Any],
    retrieved: Match | None,
) -> dict[str, Any] | None:
    """Pick a legal action for this role, preferring a Bitwork retrieval."""
    focus = _ROLE_FOCUS[role]
    kind = str(finding.get("kind") or "")
    ev = finding.get("evidence") if isinstance(finding.get("evidence"), Mapping) else {}
    # Archivist: whatever Bitwork retrieved, if the op is legal.
    if role == "archivist" and retrieved is not None:
        # retrieved.action_key is a fingerprint; we need the action dict
        # from the prototype source. Fall through if we cannot parse it.
        return None  # filled by the caller with the library action
    ops = focus.get("ops") or ()
    if "set_knob" in ops:
        knobs = list(focus.get("preferred_knobs") or [])
        # Prefer a diagnosis suggestion from self-heal when the knob is
        # in this role's list.
        try:
            from hive import host
            for knob, direction in host.DIAGNOSIS_SUGGESTIONS.get(kind, []):
                if knobs and knob not in knobs:
                    continue
                return {"op": "set_knob", "name": knob, "direction": direction}
        except Exception:
            pass
        if knobs:
            return {"op": "set_knob", "name": knobs[0], "direction": "up"}
    if "add_skip_rule" in ops and kind in (
        "repeated_targets", "no_progress_perturb", "empty_claim_label",
    ):
        targets = list(ev.get("targets") or ev.get("session_targets") or [])
        target = str(targets[0]) if targets else ""
        kind_tag = {
            "empty_claim_label": "empty_label",
            "no_progress_perturb": "already_held_range",
            "repeated_targets": "repeated_target",
        }.get(kind, kind)
        action: dict[str, Any] = {"op": "add_skip_rule", "cycles": 8, "target_kind": kind_tag}
        if target and FA._clean_id(target):
            action["target"] = FA._clean_id(target)
        return action
    if "add_park_rule" in ops and kind in ("dead_end_streak", "parked_proof_chain"):
        return {"op": "add_park_rule", "cycles": 12, "target_kind": "proof_chain_parked" if "proof" in kind else "dead_end"}
    if "mark_ceiling" in ops and kind == "depth_at_physical_cap":
        target = FA._clean_id(ev.get("target") or ev.get("id") or "held-at-cap") or "held-at-cap"
        depth = ev.get("depth") or ev.get("cap") or 1200
        return {"op": "mark_ceiling", "target": target, "depth": depth, "reason": "evaluator_cap"}
    if "set_knob" in ops and kind == "depth_at_physical_cap":
        return {"op": "set_knob", "name": "fast_term_cap", "direction": "up"}
    if "add_triviality_candidate" in ops:
        pattern = str(ev.get("pattern") or "textbook identity restated")[:FA.PATTERN_LEN_HI]
        return {
            "op": "add_triviality_candidate",
            "pattern": pattern,
            "pattern_type": "literal",
        }
    return None


def _library_action(router: Router, match: Match | None) -> dict[str, Any] | None:
    if match is None:
        return None
    # Recover the action dict from the prototype key via the library.
    try:
        for row in FL.load_records():
            if str(row.get("id") or "") == match.prototype_key:
                action = row.get("action")
                if isinstance(action, Mapping):
                    return dict(action)
    except Exception:
        return None
    return None


def propose_for_role(
    role: str,
    findings: list[dict[str, Any]],
    router: Router,
) -> Proposal | None:
    """One proposal from one role. Deterministic given findings and library."""
    focus = _ROLE_FOCUS[role]
    wanted = set(focus.get("labels") or ())
    # Legislator never proposes; it only vetoes later.
    if role == "legislator":
        return None
    # Prefer a finding this role cares about; archivist takes the first.
    chosen: dict[str, Any] | None = None
    for f in findings:
        kind = str(f.get("kind") or "")
        if not wanted or kind in wanted:
            chosen = f
            break
    if chosen is None and role == "archivist" and findings:
        chosen = findings[0]
    if chosen is None:
        return None
    symptom = _symptom_for(chosen)
    retrieved = router.classify(symptom)
    action = None
    if role == "archivist":
        action = _library_action(router, retrieved)
    if action is None:
        action = _action_for_role(role, chosen, retrieved)
    if action is None:
        return None
    validated = FA.validate(action)
    if not validated.ok:
        return Proposal(
            role=role,
            label=str(chosen.get("kind") or ""),
            action=dict(action),
            fingerprint=validated.fingerprint,
            symptom=symptom,
            match=retrieved,
            ok=False,
            reason=validated.reason,
        )
    # Score the accepted action against the library.
    scored = router.score_action(symptom, validated.fingerprint)
    return Proposal(
        role=role,
        label=str(chosen.get("kind") or ""),
        action=validated.as_dict(),
        fingerprint=validated.fingerprint,
        symptom=symptom,
        match=scored or retrieved,
        ok=True,
        reason="ok",
    )


def swarm_propose(
    findings: list[dict[str, Any]],
    router: Router,
) -> list[Proposal]:
    """Every role proposes independently, in a fixed role order."""
    out: list[Proposal] = []
    for role in SWARM_ROLES:
        p = propose_for_role(role, findings, router)
        if p is not None:
            out.append(p)
    return out


def _legislator_veto(proposals: list[Proposal]) -> list[Proposal]:
    """Mark proposals that touch a frozen rule. They cannot win a vote."""
    for p in proposals:
        if FA.touches_invariant(p.fingerprint) or FA.touches_invariant(p.action.get("name") or ""):
            p.veto = True
            p.ok = False
            p.reason = "legislator_veto_invariant"
        if str(p.action.get("op") or "") == "set_knob":
            if FA.touches_invariant(str(p.action.get("name") or "")):
                p.veto = True
                p.ok = False
                p.reason = "legislator_veto_invariant"
        v = FA.validate(p.action)
        if not v.ok and v.reason == "invariant":
            p.veto = True
            p.ok = False
            p.reason = "legislator_veto_invariant"
    return proposals


@dataclass
class VoteResult:
    winner: Proposal | None
    abstained: bool
    reason: str
    tallies: dict[str, int]
    lower_permille: int
    margin: int
    n_votes: int
    n_vetoes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "winner": None if self.winner is None else self.winner.as_dict(),
            "abstained": self.abstained,
            "reason": self.reason,
            "tallies": self.tallies,
            "lower_permille": self.lower_permille,
            "margin": self.margin,
            "n_votes": self.n_votes,
            "n_vetoes": self.n_vetoes,
            "wilson_gate": WILSON_ACCEPT_PERMILLE,
        }


def vote(
    proposals: list[Proposal],
    router: Router,
) -> VoteResult:
    """Majority of legal, non-vetoed proposals; ties broken by Bitwork score.

    The Wilson gate abstains when the winning margin's calibrated lower
    bound is below 700 permille (including when the bucket is empty).
    """
    _legislator_veto(proposals)
    legal = [p for p in proposals if p.ok and not p.veto]
    n_vetoes = sum(1 for p in proposals if p.veto)
    if not legal:
        return VoteResult(None, True, "no_legal_proposal", {}, 0, 0, 0, n_vetoes)
    tallies: dict[str, int] = {}
    by_fp: dict[str, list[Proposal]] = {}
    for p in legal:
        tallies[p.fingerprint] = tallies.get(p.fingerprint, 0) + 1
        by_fp.setdefault(p.fingerprint, []).append(p)
    # Sort: more votes, then higher Bitwork score, then fingerprint.
    def _key(fp: str) -> tuple[int, int, str]:
        score = max((p.match.score if p.match is not None else -10**9) for p in by_fp[fp])
        return (tallies[fp], score, fp)

    ranked = sorted(tallies, key=_key, reverse=True)
    winner_fp = ranked[0]
    winner = sorted(
        by_fp[winner_fp],
        key=lambda p: (-(p.match.score if p.match is not None else -10**9), p.role),
    )[0]
    margin = 0
    if winner.match is not None:
        margin = int(winner.match.margin)
    accepted, lower, _n = router.would_accept(margin)
    # If this exact action has a scored match, prefer that gate.
    if winner.match is not None:
        lower = int(winner.match.lower_permille)
        accepted = bool(winner.match.accepted)
    if not accepted:
        return VoteResult(
            winner, True, "wilson_abstain", tallies, lower, margin,
            len(legal), n_vetoes,
        )
    return VoteResult(
        winner, False, "accepted", tallies, lower, margin,
        len(legal), n_vetoes,
    )


# ---------------------------------------------------------------------------
# Applying a winner through self-heal or an equivalent rule trial
# ---------------------------------------------------------------------------

def _heal_busy() -> bool:
    try:
        from hive import host
        return bool(host.heal_load_state().get("trial"))
    except Exception:
        return False


def _heal_window_rows(window: int) -> list[dict[str, Any]]:
    """Metric rows rescored with the corrected ``new_depth`` (PR #7)."""
    try:
        from hive import host
        st = host.heal_load_state()
        rows = [host.heal_rescore_metric_row(r) for r in list(st.get("metrics") or [])[-int(window):]]
        return rows
    except Exception:
        return []


def _heal_window_score(window: int) -> float | None:
    try:
        from hive import host
        w = int(window or host.heal_current_knob("evaluation_window"))
        rows = _heal_window_rows(w)
        if len(rows) < w:
            return None
        return float(host.heal_window_score(rows))
    except Exception:
        return None


def start_knob_trial(proposal: Proposal, *, cycle_id: str, state: dict[str, Any]) -> dict[str, Any]:
    """Hand a set_knob winner to self-heal's ``start_trial``."""
    if _heal_busy():
        return {"ok": False, "reason": "self_heal_trial_running"}
    action = proposal.action
    name = str(action.get("name") or "")
    direction = str(action.get("direction") or "up")
    try:
        from hive import host
        current_knob = host.heal_current_knob
        stepped_value = host.heal_stepped_value
        replay_proposal = host.heal_replay_proposal
        load_heal = host.heal_load_state
        start_trial = host.heal_start_trial
        window_score = host.heal_window_score
        rescore_metric_row = host.heal_rescore_metric_row
        KNOB_SPECS = host.KNOB_SPECS
        is_invariant_name = host.heal_is_invariant_name
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"self_heal_unavailable:{exc}"}
    if is_invariant_name(name) or name not in KNOB_SPECS:
        return {"ok": False, "reason": "unknown_or_invariant_knob"}
    st = load_heal()
    window = int(current_knob("evaluation_window"))
    metrics = list(st.get("metrics") or [])
    if len(metrics) < window:
        return {"ok": False, "reason": "not_enough_metrics"}
    cur = current_knob(name)
    if "value" in action and action.get("direction"):
        nxt = stepped_value(name, direction, current=cur)
    elif "value" in action:
        nxt = action.get("value")
    else:
        nxt = stepped_value(name, direction, current=cur)
    if nxt is None:
        return {"ok": False, "reason": "step_hits_bound"}
    replay = replay_proposal(name, cur, nxt, direction=direction, evidence=list(st.get("evidence") or []))
    if not replay.get("accepted"):
        return {"ok": False, "reason": "self_heal_replay_rejected", "replay": replay}
    baseline_rows = [rescore_metric_row(r) for r in metrics[-window:]]
    try:
        current_fp = host.heal_environment_fingerprint(state=st)["digest"]
    except Exception:
        current_fp = ""
    if not current_fp or any(str(r.get("env_fingerprint") or "") != current_fp for r in baseline_rows):
        return {"ok": False, "reason": "confounded_baseline"}
    trial = {
        "knob": name,
        "from": cur,
        "to": nxt,
        "direction": direction,
        "reason": proposal.label or "swarm",
        "finding": {"kind": proposal.label, "source": "swarm", "role": proposal.role},
        "replay": {k: replay.get(k) for k in ("accepted", "reasons", "simulated", "note")},
        "window": window,
        "baseline_score": window_score(baseline_rows),
        "baseline_metrics": [
            {k: r.get(k) for k in (
                "cycle_id", "new_oracle_targets", "new_depth",
                "oracle_pass_delta", "oracle_passes", "score",
                "env_fingerprint",
            ) if k in r}
            for r in baseline_rows
        ],
        "trial_metrics": [],
        "started_cycle": cycle_id,
        "started_index": int(st.get("cycle_index") or 0),
        "applied_to_live_oracle": False,
        "authorized": False,
        "source": "swarm",
        "swarm_fingerprint": proposal.fingerprint,
    }
    start_trial(trial, state=st, cycle_id=cycle_id)
    return {"ok": True, "reason": "trial_started", "trial": trial, "via": "self_heal"}


def start_rule_trial(proposal: Proposal, *, cycle_id: str, state: dict[str, Any]) -> dict[str, Any]:
    """Equivalent windowed trial for a non-knob action, same fixed metric."""
    if state.get("trial"):
        return {"ok": False, "reason": "swarm_trial_running"}
    try:
        from hive import host
        current_knob = host.heal_current_knob
        window_score = host.heal_window_score
        rescore_metric_row = host.heal_rescore_metric_row
        window = int(current_knob("evaluation_window"))
    except Exception:
        window = 6
    rows = _heal_window_rows(window)
    if len(rows) < window:
        return {"ok": False, "reason": "not_enough_metrics"}
    try:
        from hive import host
        baseline = float(host.heal_window_score(rows))
        env = host.heal_environment_fingerprint()
    except Exception:
        baseline = float(sum(float(r.get("score") or 0) for r in rows))
        env = {}
        try:
            from hive import host as _host
            env = _host.heal_environment_fingerprint()
        except Exception:
            env = {}
    try:
        current_fp = str((env or {}).get("digest") or "")
        if not current_fp or any(str(r.get("env_fingerprint") or "") != current_fp for r in rows):
            return {"ok": False, "reason": "confounded_baseline"}
    except Exception:
        current_fp = str((env or {}).get("digest") or "")
    trial = {
        "op": proposal.action.get("op"),
        "action": proposal.action,
        "fingerprint": proposal.fingerprint,
        "role": proposal.role,
        "label": proposal.label,
        "symptom": proposal.symptom,
        "window": window,
        "baseline_score": baseline,
        "baseline_metrics": [
            {k: r.get(k) for k in (
                "cycle_id", "new_oracle_targets", "new_depth",
                "oracle_pass_delta", "oracle_passes", "score",
                "env_fingerprint",
            ) if k in r}
            for r in rows
        ],
        "trial_metrics": [],
        "started_cycle": cycle_id,
        "applied_to_live_oracle": False,
        "authorized": False,
        "source": "swarm",
        "environment_fingerprint": (env or {}).get("digest"),
        "environment": {
            "code": (env or {}).get("code"),
            "tree": (env or {}).get("tree"),
            "knobs": (env or {}).get("knobs"),
        } if env else None,
    }
    # Activate the rule for the trial window (skip/park/ceiling/family/desk).
    rules = list(state.get("rules") or [])
    rules.append({
        "fingerprint": proposal.fingerprint,
        "action": proposal.action,
        "active": True,
        "trial": True,
        "started_cycle": cycle_id,
        "applied_to_live_oracle": False,
    })
    state["rules"] = rules
    state["trial"] = trial
    return {"ok": True, "reason": "trial_started", "trial": trial, "via": "swarm_rule"}


def void_rule_trial_for_confound(
    state: dict[str, Any],
    cycle_id: str,
    *,
    old_fingerprint: str,
    new_fingerprint: str,
    reason: str = "environment_changed",
) -> dict[str, Any]:
    """Void a Hive rule trial whose environment changed mid-window.

    Drops the in-trial rule (neither adopt nor keep). Does not increment
    adopted_count or reverted_count, and writes ``trial_voided_confound``
    rather than adopt/revert, so Bitwork is not taught a positive or
    negative example from a confounded window.
    """
    trial = dict(state.get("trial") or {})
    if not trial:
        return state
    fp = str(trial.get("fingerprint") or "")
    rules = [
        r for r in list(state.get("rules") or [])
        if not (str(r.get("fingerprint") or "") == fp and r.get("trial"))
    ]
    state["rules"] = rules
    ev = append_evidence(state, {
        "event": "trial_voided_confound",
        "cycle_id": cycle_id,
        "fingerprint": fp,
        "action": trial.get("action"),
        "role": trial.get("role"),
        "label": trial.get("label"),
        "symptom": trial.get("symptom"),
        "reason": reason,
        "old_fingerprint": old_fingerprint,
        "new_fingerprint": new_fingerprint,
        "environment": trial.get("environment"),
        "baseline_score": trial.get("baseline_score"),
        "trial_metrics": list(trial.get("trial_metrics") or []),
        "window": trial.get("window"),
        "started_cycle": trial.get("started_cycle"),
        "helped": None,
        "adopted": False,
        "reverted": False,
        "via": "swarm_rule",
    })
    state["last_decision"] = ev
    state["trial"] = None
    return state


def maybe_close_rule_trial(state: dict[str, Any], cycle_id: str) -> dict[str, Any]:
    """Close a non-knob trial once the window is full, using the fixed metric."""
    trial = state.get("trial")
    if not isinstance(trial, dict):
        return state
    try:
        from hive import host
        heal_state = None
        try:
            heal_state = host.heal_load_state()
        except Exception:
            heal_state = None
        changed, old_fp, new_fp = host.heal_trial_fingerprint_mismatch(
            trial, state=heal_state,
        )
        if changed:
            reason = (
                "unrecorded_environment" if old_fp == host.UNRECORDED_FINGERPRINT
                else "environment_changed"
            )
            return void_rule_trial_for_confound(
                state, cycle_id,
                old_fingerprint=old_fp, new_fingerprint=new_fp, reason=reason,
            )
    except Exception:
        pass
    try:
        from hive import host
        current_knob = host.heal_current_knob
        window_score = host.heal_window_score
        rescore_metric_row = host.heal_rescore_metric_row
        collect_metrics = host.heal_collect_metrics
        window = int(trial.get("window") or current_knob("evaluation_window"))
        # Pull the latest metric row (corrected new_depth) from the host.
        try:
            row = collect_metrics(cycle_id)
            row = rescore_metric_row(row)
        except Exception:
            rows = _heal_window_rows(window)
            row = rows[-1] if rows else None
        if row:
            tmetrics = [r for r in list(trial.get("trial_metrics") or [])
                        if str(r.get("cycle_id") or "") != str(cycle_id or "")]
            tmetrics.append(row)
            trial = dict(trial)
            trial["trial_metrics"] = tmetrics
            state["trial"] = trial
        tmetrics = list(trial.get("trial_metrics") or [])
        if len(tmetrics) < window:
            return state
        trial_score = float(window_score([rescore_metric_row(r) for r in tmetrics]))
        baseline_score = float(trial.get("baseline_score") or 0)
    except Exception:
        tmetrics = list(trial.get("trial_metrics") or [])
        window = int(trial.get("window") or 6)
        if len(tmetrics) < window:
            return state
        trial_score = float(sum(float(r.get("score") or 0) for r in tmetrics))
        baseline_score = float(trial.get("baseline_score") or 0)

    helped = trial_score > baseline_score
    fp = str(trial.get("fingerprint") or "")
    decision = "adopt" if helped else "revert"
    # Activate or drop the rule.
    rules = []
    for r in list(state.get("rules") or []):
        if str(r.get("fingerprint") or "") == fp and r.get("trial"):
            if helped:
                r = dict(r)
                r["trial"] = False
                r["active"] = True
                r["adopted_cycle"] = cycle_id
                rules.append(r)
            # else: drop (revert)
        else:
            rules.append(r)
    state["rules"] = rules
    if helped:
        state["adopted_count"] = int(state.get("adopted_count") or 0) + 1
    else:
        state["reverted_count"] = int(state.get("reverted_count") or 0) + 1
    ev = append_evidence(state, {
        "event": decision,
        "cycle_id": cycle_id,
        "fingerprint": fp,
        "action": trial.get("action"),
        "role": trial.get("role"),
        "label": trial.get("label"),
        "symptom": trial.get("symptom"),
        "baseline_score": baseline_score,
        "trial_score": trial_score,
        "window": trial.get("window"),
        "helped": helped,
        "via": "swarm_rule",
    })
    state["last_decision"] = ev
    state["trial"] = None
    return state


def teach_from_event(
    router: Router,
    event: Mapping[str, Any],
    *,
    path: Path | None = None,
) -> dict[str, Any] | None:
    """Append an adopt / revert as a Bitwork teaching example.

    A ``trial_voided_confound`` event is neither a positive nor a
    negative example: the window was not a fair test of the action.
    """
    event_name = str(event.get("event") or "")
    if event_name not in ("adopt", "revert"):
        return None
    action = event.get("action")
    if not isinstance(action, Mapping) and event.get("knob"):
        action = {
            "op": "set_knob",
            "name": event.get("knob"),
            "direction": event.get("direction") or "",
            "value": event.get("to") if event_name == "adopt" else event.get("from"),
        }
    symptom = str(event.get("symptom") or "")
    if not symptom:
        knob = event.get("knob") or (action or {}).get("name")
        symptom = (
            f"self heal {event_name} knob {knob} {event.get('direction') or ''} "
            f"reason {str(event.get('reason') or '').replace('_', ' ')}"
        )
    label = str(event.get("label") or event.get("reason") or event_name)
    record = {
        "id": f"teach:{event_name}:{event.get('id') or event.get('cycle_id')}:{action_fingerprint(action or {})}",
        "cycle_id": str(event.get("cycle_id") or ""),
        "source": "swarm" if event.get("via") == "swarm_rule" else "self_heal",
        "kind": "fix" if event_name == "adopt" else "failure",
        "label": label,
        "symptom": symptom,
        "action": action,
        "outcome": "positive" if event_name == "adopt" else "negative",
        "evidence": {
            "event": event_name,
            "baseline_score": event.get("baseline_score"),
            "trial_score": event.get("trial_score"),
            "helped": event.get("helped"),
        },
    }
    written = FL.append_record(record, path=path)
    if written is None:
        return None
    key = str(written.get("action_key") or action_fingerprint(action or {}))
    router.learn(
        written["symptom"],
        category=label,
        action_key=key,
        positive=(event_name == "adopt"),
        source_id=written["id"],
        proto_key=written["id"],
        cues=label.replace("_", " ").split(),
    )
    return written


def harvest_self_heal_outcomes(
    router: Router,
    state: dict[str, Any],
    *,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Teach Bitwork from self-heal adopt / revert events not yet seen."""
    try:
        from hive import host
        evidence = list(host.heal_load_state().get("evidence") or [])
    except Exception:
        evidence = []
    seen = set(state.get("seen_heal_ids") or [])
    taught: list[dict[str, Any]] = []
    for ev in evidence:
        if not isinstance(ev, Mapping):
            continue
        eid = str(ev.get("id") or "")
        if not eid or eid in seen:
            continue
        # Voided trials are not teaching examples (positive or negative).
        if ev.get("event") not in ("adopt", "revert"):
            continue
        written = teach_from_event(router, ev, path=path)
        seen.add(eid)
        if written is not None:
            taught.append(written)
            # Calibration: the trial's score margin is not a Bitwork
            # margin. Record outcome against the retrieval margin
            # only when we can re-score the symptom; otherwise skip.
            # Tagged source=apply (a live trial, not a shadow).
            symptom = written.get("symptom") or ""
            if symptom:
                hit = router.score_action(symptom, written.get("action_key") or "")
                if hit is not None:
                    record_apply_outcome(
                        router, state,
                        margin=hit.margin,
                        correct=ev.get("event") == "adopt",
                        case_id=f"apply:{eid}",
                        extra={"event": ev.get("event"), "label": ev.get("label") or ev.get("reason")},
                    )
        # A later self-heal resolution can score a pending shadow pick.
        resolve_shadows(router, state, ev)
    state["seen_heal_ids"] = list(seen)[-400:]
    return taught


def _record_first_seen(state: dict[str, Any], findings: list[dict[str, Any]], cycle_id: str, index: int) -> None:
    first = dict(state.get("first_seen") or {})
    for f in findings:
        kind = str(f.get("kind") or "")
        if kind and kind not in first:
            first[kind] = {"cycle_id": cycle_id, "index": index}
    state["first_seen"] = first


def _record_first_adopted(state: dict[str, Any], label: str, cycle_id: str, index: int) -> None:
    if not label:
        return
    adopted = dict(state.get("first_adopted") or {})
    if label not in adopted:
        adopted[label] = {"cycle_id": cycle_id, "index": index}
        state["first_adopted"] = adopted


def time_to_fix(state: dict[str, Any]) -> dict[str, Any]:
    """Cycles from first seeing a failure kind to first adopting a fix for it."""
    first = state.get("first_seen") or {}
    adopted = state.get("first_adopted") or {}
    times: dict[str, int] = {}
    for kind, info in first.items():
        if kind in adopted:
            try:
                times[kind] = int(adopted[kind]["index"]) - int(info["index"])
            except Exception:
                continue
    if not times:
        return {"n": 0, "mean": None, "by_kind": {}}
    mean = int(round(sum(times.values()) / len(times)))
    return {"n": len(times), "mean": mean, "by_kind": times}


def learning_curve_point(
    router: Router,
    state: dict[str, Any],
    *,
    cycle_id: str,
) -> dict[str, Any]:
    records = FL.load_records(path=FL.LIBRARY_LOG)
    cases = FL.held_out_cases(records if records else FL.seed_patterns())
    replay = router.replay_accuracy(cases, hold_out=True)
    adopted = int(state.get("adopted_count") or 0)
    reverted = int(state.get("reverted_count") or 0)
    decided = adopted + reverted
    adopt_rate = int((adopted * 1000) // decided) if decided else 0
    point = {
        "cycle_id": cycle_id,
        "ts": _utc(),
        "library_size": router.library_size(),
        "replay_n": replay["n"],
        "replay_correct": replay["correct"],
        "replay_accuracy_permille": replay["accuracy_permille"],
        "replay_lower_permille": replay["lower_permille"],
        "replay_abstained": replay["abstained"],
        "adopted_count": adopted,
        "reverted_count": reverted,
        "adopt_rate_permille": adopt_rate,
        "abstained_count": int(state.get("abstained_count") or 0),
        "applied_count": int(state.get("applied_count") or 0),
        "time_to_fix": time_to_fix(state),
        "applied_to_live_oracle": False,
    }
    return point


# ---------------------------------------------------------------------------
# Cycle entry, visibility
# ---------------------------------------------------------------------------


CALIBRATION_OUTCOMES_KEEP = 1000
SHADOW_KEEP = 200
REPLAY_ID_KEEP = 4000

HUMAN_FIX_SOURCES = frozenset({
    "human", "human_guide", "human_merged", "merged", "pr",
})


def _empty_calibration() -> dict[str, Any]:
    from hive.bitwork import MARGIN_BUCKETS
    return {
        "buckets": [
            {
                "min_margin": b,
                "n": 0,
                "correct": 0,
                "lower_permille": 0,
                "accuracy_permille": 0,
                "by_source": {
                    "replay": {"n": 0, "correct": 0},
                    "shadow": {"n": 0, "correct": 0},
                    "apply": {"n": 0, "correct": 0},
                },
            }
            for b in MARGIN_BUCKETS
        ],
        "outcomes": [],
    }


def _ensure_calibration(state: dict[str, Any]) -> dict[str, Any]:
    cal = state.get("calibration")
    if not isinstance(cal, dict) or not isinstance(cal.get("buckets"), list):
        cal = _empty_calibration()
        state["calibration"] = cal
    cal.setdefault("outcomes", [])
    cal.setdefault("buckets", _empty_calibration()["buckets"])
    from hive.bitwork import MARGIN_BUCKETS
    have = {int(b.get("min_margin")): b for b in cal["buckets"] if isinstance(b, dict) and "min_margin" in b}
    buckets = []
    for edge in MARGIN_BUCKETS:
        raw = have.get(edge) or {
            "min_margin": edge, "n": 0, "correct": 0,
            "by_source": {
                "replay": {"n": 0, "correct": 0},
                "shadow": {"n": 0, "correct": 0},
                "apply": {"n": 0, "correct": 0},
            },
        }
        raw.setdefault("by_source", {})
        for src in ("replay", "shadow", "apply"):
            raw["by_source"].setdefault(src, {"n": 0, "correct": 0})
        buckets.append(raw)
    cal["buckets"] = buckets
    return cal


def _recompute_bucket_totals(cal: dict[str, Any]) -> None:
    from hive.bitwork import wilson_lower_permille
    for bucket in cal.get("buckets") or []:
        n = 0
        correct = 0
        for src, v in (bucket.get("by_source") or {}).items():
            if not isinstance(v, dict):
                continue
            n += int(v.get("n") or 0)
            correct += int(v.get("correct") or 0)
        bucket["n"] = n
        bucket["correct"] = correct
        bucket["lower_permille"] = wilson_lower_permille(correct, n)
        bucket["accuracy_permille"] = int((correct * 1000) // n) if n else 0


def _bucket_for(cal: dict[str, Any], margin: int) -> dict[str, Any] | None:
    from hive.bitwork import margin_bucket
    edge = margin_bucket(int(margin))
    for bucket in cal.get("buckets") or []:
        if int(bucket.get("min_margin") or 0) == edge:
            return bucket
    return None


def _add_source_count(cal: dict[str, Any], *, source: str, margin: int, correct: bool, n: int = 1, correct_n: int | None = None) -> None:
    bucket = _bucket_for(cal, margin)
    if bucket is None:
        return
    src = bucket.setdefault("by_source", {}).setdefault(source, {"n": 0, "correct": 0})
    add_n = int(n)
    add_c = int(correct_n) if correct_n is not None else (add_n if correct else 0)
    src["n"] = int(src.get("n") or 0) + add_n
    src["correct"] = int(src.get("correct") or 0) + add_c
    _recompute_bucket_totals(cal)


def _append_outcome(state: dict[str, Any], outcome: Mapping[str, Any]) -> None:
    cal = _ensure_calibration(state)
    rows = list(cal.get("outcomes") or [])
    rows.append(dict(outcome))
    cal["outcomes"] = rows[-CALIBRATION_OUTCOMES_KEEP:]


def apply_calibration_to_router(router: Router, state: dict[str, Any]) -> None:
    """Copy persisted bucket totals onto a freshly trained router."""
    cal = _ensure_calibration(state)
    router.load_buckets(cal.get("buckets") or [])


def calibration_snapshot(router: Router, state: dict[str, Any]) -> dict[str, Any]:
    """Keep provenance in state; totals match the live router."""
    cal = _ensure_calibration(state)
    by_edge = {int(b.get("min_margin")): b for b in cal["buckets"]}
    from hive.bitwork import MARGIN_BUCKETS
    for edge in MARGIN_BUCKETS:
        live = router.buckets[edge]
        raw = by_edge.get(edge)
        if raw is None:
            continue
        # Do not let a stale router shrink append-only shadow/apply
        # counts. Totals are the sum of by_source, which is authoritative.
        _recompute_bucket_totals(cal)
    return cal


def _stable_case_id(text: str, expected: str, index: int) -> str:
    import hashlib
    h = hashlib.sha256(f"{text}\0{expected}".encode("utf-8")).hexdigest()[:16]
    return f"replay:{index}:{h}"


def calibrate_from_replay(
    router: Router,
    state: dict[str, Any],
    cases: Iterable[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Seed (or refresh) the replay slice of each calibration bucket.

    The counts are a deterministic function of the current labeled
    library: leave-one-out top picks, scored correct or incorrect
    against the known action, tagged ``source=replay``. The replay
    slice is replaced each call so it is never double-counted.
    Shadow and apply slices are left alone. The Wilson 95% lower
    bound and the 700 permille accept threshold are not changed.
    Outcomes are not fabricated: a case with no retrieval is skipped.
    """
    cal = _ensure_calibration(state)
    if cases is None:
        records = FL.load_records() or FL.seed_patterns()
        case_list = FL.held_out_cases(records)
    else:
        case_list = list(cases)
    raw = router.leave_one_out_outcomes(case_list)
    # Reset the replay slice only.
    for bucket in cal["buckets"]:
        bucket.setdefault("by_source", {})["replay"] = {"n": 0, "correct": 0}
    cal["outcomes"] = [o for o in (cal.get("outcomes") or []) if o.get("source") != "replay"]
    outcomes: list[dict[str, Any]] = []
    for item in raw:
        margin = int(item["margin"])
        correct = bool(item["correct"])
        case_id = _stable_case_id(str(item.get("text") or ""), str(item.get("expected") or ""), int(item.get("index") or 0))
        _add_source_count(cal, source="replay", margin=margin, correct=correct)
        row = {
            "source": "replay",
            "id": case_id,
            "ts": _utc(),
            "margin": margin,
            "correct": correct,
            "expected": item.get("expected"),
            "predicted": item.get("predicted"),
            "index": item.get("index"),
        }
        outcomes.append(row)
        _append_outcome(state, row)
    apply_calibration_to_router(router, state)
    state["calibration"] = cal
    state["replay_calibrated"] = {
        "n": len(outcomes),
        "correct": sum(1 for o in outcomes if o["correct"]),
        "source": "replay",
        "updated_at": _utc(),
    }
    return {"n": len(outcomes), "correct": state["replay_calibrated"]["correct"], "outcomes": outcomes, "source": "replay"}


def record_apply_outcome(
    router: Router,
    state: dict[str, Any],
    *,
    margin: int,
    correct: bool,
    case_id: str,
    extra: Mapping[str, Any] | None = None,
) -> None:
    """Append-only live (apply) calibration from an adopted or reverted trial."""
    cal = _ensure_calibration(state)
    router.record_outcome(margin, correct)
    _add_source_count(cal, source="apply", margin=int(margin), correct=bool(correct))
    row = {
        "source": "apply",
        "id": case_id,
        "ts": _utc(),
        "margin": int(margin),
        "correct": bool(correct),
    }
    if extra:
        row.update(dict(extra))
    _append_outcome(state, row)
    # Router was incremented; keep by_source totals in sync (already
    # done) and do not reload from state (that would double-count).
    state["calibration"] = cal


def record_shadow(
    state: dict[str, Any],
    vote_result: "VoteResult",
    *,
    cycle_id: str,
) -> dict[str, Any] | None:
    """When the Wilson gate abstains, remember the top pick for later scoring."""
    winner = vote_result.winner
    if winner is None:
        return None
    shadow = {
        "id": _event_id(),
        "ts": _utc(),
        "cycle_id": cycle_id,
        "label": winner.label,
        "symptom": winner.symptom,
        "action": winner.action,
        "fingerprint": winner.fingerprint,
        "margin": int(vote_result.margin),
        "source": "shadow",
        "resolved": False,
        "matched": None,
        "correct": None,
        "resolved_by": None,
        "resolved_source": None,
    }
    shadows = list(state.get("shadows") or [])
    shadows.append(shadow)
    state["shadows"] = _compact_shadows(shadows)
    return shadow


def _compact_shadows(shadows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    open_rows = [s for s in shadows if not s.get("resolved")]
    closed = [s for s in shadows if s.get("resolved")][-100:]
    kept = open_rows + closed
    if len(kept) > SHADOW_KEEP:
        # Prefer keeping unresolved, then the newest resolved.
        kept = open_rows[:SHADOW_KEEP] + closed[-(max(SHADOW_KEEP - len(open_rows), 0)):]
    return kept[-SHADOW_KEEP:]


def _norm_label(value: Any) -> str:
    return " ".join(str(value or "").replace("-", "_").replace("_", " ").split()).strip().lower()


def _family_fingerprint(action: Mapping[str, Any] | None, fingerprint: str | None = None) -> str:
    """Compare actions by closed-op family, ignoring a stepped ``value``.

    ``set_knob park_cycles up`` is the same decision whether the
    concrete stepped value was 8 or 10; that number depends on the
    current knob at the moment of validation, not on the intent.
    """
    if isinstance(action, Mapping) and action:
        op = str(action.get("op") or "")
        if op == "set_knob":
            parts = [op]
            name = action.get("name")
            direction = action.get("direction")
            if name:
                parts.append(f"name={name}")
            if direction:
                parts.append(f"direction={direction}")
            return ":".join(parts)
        return action_fingerprint(action)
    if fingerprint:
        parts = [p for p in str(fingerprint).split(":") if not p.startswith("value=")]
        return ":".join(parts)
    return ""


def _event_action_fingerprint(event: Mapping[str, Any]) -> str | None:
    action = event.get("action")
    if isinstance(action, Mapping) and action:
        return action_fingerprint(action)
    knob = event.get("knob") or (action or {}).get("name") if isinstance(action, Mapping) else event.get("knob")
    if knob:
        direction = event.get("direction") or ""
        built: dict[str, Any] = {"op": "set_knob", "name": knob}
        if direction:
            built["direction"] = direction
        return action_fingerprint(built)
    fp = event.get("fingerprint") or event.get("swarm_fingerprint")
    return str(fp) if fp else None


def _event_failure_class(event: Mapping[str, Any]) -> str:
    for key in ("label", "reason", "kind", "finding_kind"):
        v = event.get(key)
        if v:
            return _norm_label(v)
        if key == "finding" and isinstance(event.get("finding"), Mapping):
            k = event["finding"].get("kind")
            if k:
                return _norm_label(k)
    return ""


def resolve_shadows(
    router: Router,
    state: dict[str, Any],
    event: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Score pending shadow picks against a later labeled resolution.

    A self-heal adopt, a self-heal revert, or a human-merged positive
    fix can resolve shadows of the same failure class:

    * adopt / human-merged positive: the resolving action is the
      labeled correct fix; the shadow is correct iff its fingerprint
      matches.
    * revert: the resolving action is labeled incorrect; if the
      shadow picked that same action, it is scored incorrect. If it
      picked something else, we have no label for the shadow and
      leave it unresolved.

    Outcomes are tagged ``source=shadow``. Nothing is fabricated.
    """
    event_name = str(event.get("event") or event.get("outcome") or "")
    source = str(event.get("source") or "")
    is_adopt = event_name in ("adopt", "positive") or (
        event.get("outcome") == "positive" and source in HUMAN_FIX_SOURCES
    )
    is_revert = event_name in ("revert", "negative")
    is_human = source in HUMAN_FIX_SOURCES and event.get("outcome") == "positive"
    if not (is_adopt or is_revert or is_human):
        return []
    failure = _event_failure_class(event)
    if not failure:
        return []
    action_fp = _family_fingerprint(event.get("action") if isinstance(event.get("action"), Mapping) else None,
                                    _event_action_fingerprint(event))
    if not action_fp:
        return []
    resolved: list[dict[str, Any]] = []
    seen_ids = set(state.get("seen_shadow_ids") or [])
    for shadow in list(state.get("shadows") or []):
        if shadow.get("resolved"):
            continue
        if _norm_label(shadow.get("label")) != failure:
            continue
        sid = str(shadow.get("id") or "")
        if sid and sid in seen_ids:
            continue
        shadow_fp = _family_fingerprint(
            shadow.get("action") if isinstance(shadow.get("action"), Mapping) else None,
            str(shadow.get("fingerprint") or "") or None,
        )
        matched = bool(shadow_fp) and shadow_fp == action_fp
        if is_revert and not is_adopt:
            if not matched:
                # No label for a different pick.
                continue
            correct = False
        else:
            correct = matched
        margin = int(shadow.get("margin") or 0)
        router.record_outcome(margin, correct)
        cal = _ensure_calibration(state)
        _add_source_count(cal, source="shadow", margin=margin, correct=correct)
        shadow["resolved"] = True
        shadow["matched"] = matched
        shadow["correct"] = correct
        shadow["resolved_by"] = event.get("id") or event.get("cycle_id")
        shadow["resolved_source"] = "human" if is_human else ("self_heal" if not event.get("via") else str(event.get("via")))
        shadow["resolved_at"] = _utc()
        _append_outcome(state, {
            "source": "shadow",
            "id": sid or _event_id(),
            "ts": _utc(),
            "margin": margin,
            "correct": correct,
            "matched": matched,
            "shadow_fingerprint": shadow.get("fingerprint"),
            "resolved_fingerprint": action_fp,
            "label": shadow.get("label"),
            "cycle_id": shadow.get("cycle_id"),
        })
        if sid:
            seen_ids.add(sid)
        resolved.append(shadow)
    state["seen_shadow_ids"] = list(seen_ids)[-REPLAY_ID_KEEP:]
    state["shadows"] = _compact_shadows(list(state.get("shadows") or []))
    return resolved


def _remember_cycle(state: dict[str, Any], cycle_id: str) -> dict[str, Any]:
    cycles = list(state.get("cycles") or [])
    if cycle_id and cycle_id not in cycles:
        cycles.append(cycle_id)
        state["cycle_index"] = int(state.get("cycle_index") or 0) + 1
    state["cycles"] = cycles[-200:]
    return state


def _build_router() -> Router:
    FL.ensure_seeded()
    return FL.train_router()


def run_cycle(cycle_id: str = "") -> dict[str, Any]:
    """One swarm cycle: mine, propose, vote, maybe start or close a trial."""
    st = load_state()
    st = _remember_cycle(st, cycle_id)
    if not st.get("seeded"):
        FL.ensure_seeded()
        st["seeded"] = True

    # Close a non-knob trial first, so a free slot can be used this cycle.
    if st.get("trial"):
        st = maybe_close_rule_trial(st, cycle_id)

    mined = FL.mine_all(cycle_id=cycle_id)
    router = _build_router()
    # Restore persisted shadow/apply counts, then refresh the replay
    # slice from current labeled leave-one-out results (idempotent).
    apply_calibration_to_router(router, st)
    calibrate_from_replay(router, st)
    taught = harvest_self_heal_outcomes(router, st)
    # Human-merged (or other host-provided) positive library records
    # can also resolve a pending shadow of the same failure class.
    for rec in FL.load_records():
        if str(rec.get("source") or "") in HUMAN_FIX_SOURCES and rec.get("outcome") == "positive":
            resolve_shadows(router, st, rec)

    findings = observe(cycle_id)
    _record_first_seen(st, findings, cycle_id, int(st.get("cycle_index") or 0))

    started = None
    vote_result = None
    proposals: list[Proposal] = []
    applied_this_cycle = 0

    if findings and not st.get("trial") and applied_this_cycle < MAX_ACTIONS_PER_CYCLE:
        proposals = swarm_propose(findings, router)
        st["proposals_count"] = int(st.get("proposals_count") or 0) + len(proposals)
        vote_result = vote(proposals, router)
        if vote_result.abstained or vote_result.winner is None:
            st["abstained_count"] = int(st.get("abstained_count") or 0) + 1
            shadow = record_shadow(st, vote_result, cycle_id=cycle_id)
            append_evidence(st, {
                "event": "abstain",
                "cycle_id": cycle_id,
                "reason": vote_result.reason,
                "lower_permille": vote_result.lower_permille,
                "margin": vote_result.margin,
                "tallies": vote_result.tallies,
                "n_votes": vote_result.n_votes,
                "winner": None if vote_result.winner is None else vote_result.winner.as_dict(),
                "shadow_id": None if shadow is None else shadow.get("id"),
                "source": "shadow" if shadow is not None else None,
            })
        else:
            winner = vote_result.winner
            if winner.action.get("op") == "set_knob":
                started = start_knob_trial(winner, cycle_id=cycle_id, state=st)
            else:
                started = start_rule_trial(winner, cycle_id=cycle_id, state=st)
            if started.get("ok"):
                st["applied_count"] = int(st.get("applied_count") or 0) + 1
                applied_this_cycle += 1
                append_evidence(st, {
                    "event": "trial_start",
                    "cycle_id": cycle_id,
                    "via": started.get("via"),
                    "fingerprint": winner.fingerprint,
                    "action": winner.action,
                    "role": winner.role,
                    "label": winner.label,
                    "symptom": winner.symptom,
                    "lower_permille": vote_result.lower_permille,
                    "margin": vote_result.margin,
                })
            else:
                append_evidence(st, {
                    "event": "apply_deferred",
                    "cycle_id": cycle_id,
                    "reason": started.get("reason"),
                    "fingerprint": winner.fingerprint,
                    "action": winner.action,
                })

    # If a rule trial just closed as adopt, record first-adopted.
    last = st.get("last_decision")
    # Only adopt / revert teach Bitwork. A void is neither.
    if (
        isinstance(last, dict)
        and last.get("event") in ("adopt", "revert")
        and last.get("cycle_id") == cycle_id
    ):
        if last.get("event") == "adopt":
            _record_first_adopted(st, str(last.get("label") or ""), cycle_id, int(st.get("cycle_index") or 0))
        # Teach from our own adopt/revert (self-heal harvest covers heal events).
        teach_from_event(router, last)
        if last.get("via") == "swarm_rule":
            hit = router.score_action(str(last.get("symptom") or ""), str(last.get("fingerprint") or ""))
            if hit is not None:
                record_apply_outcome(
                    router, st,
                    margin=hit.margin,
                    correct=last.get("event") == "adopt",
                    case_id=f"apply:swarm:{last.get('id') or last.get('cycle_id')}",
                    extra={"event": last.get("event"), "via": "swarm_rule"},
                )
        resolve_shadows(router, st, last)

    point = learning_curve_point(router, st, cycle_id=cycle_id)
    curve = list(st.get("curve") or [])
    curve.append(point)
    st["curve"] = curve[-CURVE_KEEP:]
    st["library_size"] = point["library_size"]
    st["last_replay"] = {
        "accuracy_permille": point["replay_accuracy_permille"],
        "lower_permille": point["replay_lower_permille"],
        "n": point["replay_n"],
        "correct": point["replay_correct"],
        "abstained": point["replay_abstained"],
    }
    try:
        save_state(st)
    except Exception:
        pass
    try:
        FL.persist_library()
        st["library_persisted"] = True
        save_state(st)
    except Exception:
        pass

    vis = visibility(state=st)
    return {
        "ok": True,
        "cycle_id": cycle_id,
        "findings": [f.get("kind") for f in findings],
        "n_proposals": len(proposals),
        "proposals": [p.as_dict() for p in proposals],
        "vote": None if vote_result is None else vote_result.as_dict(),
        "started": started,
        "mined": len(mined),
        "taught": len(taught),
        "library_size": vis["swarm_library_size"],
        "replay": vis["swarm_replay"],
        "applied_to_live_oracle": False,
        "authorized": False,
    }


def on_cycle(cycle_id: str = "") -> dict[str, Any]:
    """Evolve-cycle entry point. Exceptions are swallowed and returned."""
    try:
        return run_cycle(cycle_id)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"{type(exc).__name__}:{exc}",
            "cycle_id": cycle_id,
            "applied_to_live_oracle": False,
            "authorized": False,
        }


def active_rules(*, state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Currently active non-knob rules (skip, park, ceiling, family, desk)."""
    st = state if state is not None else load_state()
    return [r for r in list(st.get("rules") or []) if r.get("active")]


def visibility(state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fields for telemetry and the dashboard. Not scored, not the Oracle."""
    try:
        st = state if state is not None else load_state()
        replay = st.get("last_replay") or {}
        trial = st.get("trial")
        trial_out = None
        if isinstance(trial, dict):
            trial_out = {
                "op": trial.get("op"),
                "fingerprint": trial.get("fingerprint"),
                "label": trial.get("label"),
                "window": trial.get("window"),
                "n_trial_metrics": len(trial.get("trial_metrics") or []),
                "baseline_score": trial.get("baseline_score"),
            }
        last = st.get("last_decision")
        last_out = None
        if isinstance(last, dict):
            last_out = {
                "event": last.get("event"),
                "fingerprint": last.get("fingerprint"),
                "label": last.get("label"),
                "baseline_score": last.get("baseline_score"),
                "trial_score": last.get("trial_score"),
                "cycle_id": last.get("cycle_id"),
                "helped": last.get("helped"),
            }
        adopted = int(st.get("adopted_count") or 0)
        reverted = int(st.get("reverted_count") or 0)
        decided = adopted + reverted
        ttf = time_to_fix(st)
        cal = st.get("calibration") if isinstance(st.get("calibration"), dict) else {}
        shadows = [s for s in list(st.get("shadows") or []) if isinstance(s, dict)]
        return {
            "swarm_library_size": int(st.get("library_size") or 0),
            "swarm_calibration": cal or None,
            "swarm_shadows_open": sum(1 for s in shadows if not s.get("resolved")),
            "swarm_shadows_resolved": sum(1 for s in shadows if s.get("resolved")),
            "swarm_replay_calibrated": st.get("replay_calibrated"),
            "swarm_replay_accuracy_permille": replay.get("accuracy_permille"),
            "swarm_replay_lower_permille": replay.get("lower_permille"),
            "swarm_replay_n": replay.get("n"),
            "swarm_replay": replay or None,
            "swarm_adopted": adopted,
            "swarm_reverted": reverted,
            "swarm_adopt_rate_permille": int((adopted * 1000) // decided) if decided else 0,
            "swarm_abstained": int(st.get("abstained_count") or 0),
            "swarm_applied": int(st.get("applied_count") or 0),
            "swarm_proposals": int(st.get("proposals_count") or 0),
            "swarm_trial": trial_out,
            "swarm_last_decision": last_out,
            "swarm_active_rules": len(active_rules(state=st)),
            "swarm_time_to_fix": ttf,
            "swarm_roles": list(SWARM_ROLES),
            "swarm_max_actions_per_cycle": MAX_ACTIONS_PER_CYCLE,
        }
    except Exception:
        return {
            "swarm_library_size": 0,
            "swarm_calibration": None,
            "swarm_shadows_open": 0,
            "swarm_shadows_resolved": 0,
            "swarm_replay_calibrated": None,
            "swarm_replay_accuracy_permille": None,
            "swarm_replay_lower_permille": None,
            "swarm_replay_n": None,
            "swarm_replay": None,
            "swarm_adopted": 0,
            "swarm_reverted": 0,
            "swarm_adopt_rate_permille": 0,
            "swarm_abstained": 0,
            "swarm_applied": 0,
            "swarm_proposals": 0,
            "swarm_trial": None,
            "swarm_last_decision": None,
            "swarm_active_rules": 0,
            "swarm_time_to_fix": {"n": 0, "mean": None, "by_kind": {}},
            "swarm_roles": list(SWARM_ROLES),
            "swarm_max_actions_per_cycle": MAX_ACTIONS_PER_CYCLE,
        }


def format_visibility(vis: dict[str, Any] | None = None) -> str:
    v = vis if vis is not None else visibility()
    acc = v.get("swarm_replay_accuracy_permille")
    acc_s = "n/a" if acc is None else f"{acc} permille"
    lower = v.get("swarm_replay_lower_permille")
    lower_s = "" if lower is None else f", Wilson lower {lower} permille"
    ttf = v.get("swarm_time_to_fix") or {}
    ttf_s = "none yet" if not ttf.get("n") else f"mean {ttf.get('mean')} cycles over {ttf.get('n')} kinds"
    trial = v.get("swarm_trial")
    parts = [
        f"library {v.get('swarm_library_size') or 0}",
        f"replay accuracy {acc_s}{lower_s}",
        f"adopted {v.get('swarm_adopted') or 0}",
        f"reverted {v.get('swarm_reverted') or 0}",
        f"abstained {v.get('swarm_abstained') or 0}",
        f"time-to-fix {ttf_s}",
    ]
    if trial:
        parts.append(
            f"trial {trial.get('op') or trial.get('fingerprint')} "
            f"({trial.get('n_trial_metrics')}/{trial.get('window')})"
        )
    last = v.get("swarm_last_decision")
    if last:
        parts.append(
            f"last {last.get('event')} {last.get('label')} "
            f"(baseline {last.get('baseline_score')}, trial {last.get('trial_score')})"
        )
    return "; ".join(parts)
