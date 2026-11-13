"""Bounded, safe patch operations Hive may propose to a host such as the colony.

Each operation has hard bounds and is validated before use. Nothing
here can set or loosen Oracle thresholds, the P ≥ 0.70 gate, the 150
authored-check cap, Athanor math, the append-only witness, human
authorize, or human_guide lessons. Triviality-pattern candidates are
routed through the existing tighten-only checker lane and are never
applied to the live Oracle.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

# Operations the swarm may propose. The set is closed: unknown ops reject.
OPS = frozenset({
    "set_knob",
    "add_skip_rule",
    "add_park_rule",
    "reorder_desk",
    "add_family_rotation",
    "mark_ceiling",
    "add_triviality_candidate",
})

# Desks whose priority the colony may reorder. Names only; this does
# not create desks or retire them.
KNOWN_DESKS: tuple[str, ...] = (
    "conjecture",
    "hunt",
    "frontier",
    "oeis",
    "proof",
    "gather",
    "improve",
    "oracle_scribe",
    "stem_checker",
    "research",
)

# Families that may be added to rotation. Matches colony search families.
KNOWN_FAMILIES: frozenset[str] = frozenset({
    "collatz", "divisor", "goldbach", "pattern", "subset",
    "oeis", "erdos", "legendre", "algebraic",
})

# Skip / park rule lifetimes, in cycles.
SKIP_CYCLES_LO, SKIP_CYCLES_HI = 1, 24
PARK_CYCLES_LO, PARK_CYCLES_HI = 3, 18

# A ceiling mark records that a target has a computational cap; it
# does not change any Oracle or Athanor number.
CEILING_DEPTH_LO, CEILING_DEPTH_HI = 1, 10**9

# Target-id / chain-id length bound (prevents huge payloads).
ID_LEN_HI = 80

# Pattern text for a triviality candidate (checker lane, not Oracle).
PATTERN_LEN_HI = 160

# Names and fragments that can never appear as a knob or rule target.
# Kept in sync with the host's frozen-rule fragments in spirit;
# this module also rejects them on every other op.
_INVARIANT_FRAGMENTS = (
    "p_min", "pmin", "standing_trust", "authorize_p",
    "authored_cap", "max_authored", "authored_check",
    "athanor", "dphi", "delta_phi", "h7", "coherence_c",
    "authorize", "human_authorize", "authorization", "human_guide",
    "witness", "rewrite_witness",
    "oracle_threshold", "oracle_p", "live_oracle",
    "w_targets", "w_depth", "w_passes",
)


def _norm(s: Any) -> str:
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum() or ch == "_")


def touches_invariant(name: str) -> bool:
    """True if ``name`` is, or contains, a frozen-rule fragment."""
    key = _norm(name)
    if not key:
        return False
    try:
        from hive import host
        if host.heal_is_invariant_name(name) or host.heal_is_invariant_name(key):
            return True
    except Exception:
        pass
    for frag in _INVARIANT_FRAGMENTS:
        if frag.replace("_", "") in key.replace("_", ""):
            return True
    return False


@dataclass(frozen=True)
class ValidatedAction:
    op: str
    payload: dict[str, Any]
    fingerprint: str
    ok: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        out = {"op": self.op, **self.payload}
        return out


def _fp(op: str, payload: Mapping[str, Any]) -> str:
    from hive.bitwork import action_fingerprint
    return action_fingerprint({"op": op, **dict(payload)})


def _reject(op: str, payload: Mapping[str, Any], reason: str) -> ValidatedAction:
    return ValidatedAction(op=op or "unknown", payload=dict(payload),
                           fingerprint=_fp(op or "unknown", payload),
                           ok=False, reason=reason)


def _accept(op: str, payload: dict[str, Any]) -> ValidatedAction:
    return ValidatedAction(op=op, payload=payload,
                           fingerprint=_fp(op, payload),
                           ok=True, reason="ok")


def _bounded_int(value: Any, lo: int, hi: int, default: int | None = None) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        if default is None:
            return None
        n = int(default)
    if n < lo or n > hi:
        return None
    return n


def _clean_id(value: Any) -> str | None:
    s = str(value or "").strip()
    if not s or len(s) > ID_LEN_HI:
        return None
    # Identifiers only: letters, digits, dash, underscore, colon.
    if not all(ch.isalnum() or ch in "-_:" for ch in s):
        return None
    if touches_invariant(s):
        return None
    return s


def validate(action: Mapping[str, Any] | None) -> ValidatedAction:
    """Validate and canonicalize an action. Never raises on bad input."""
    if not isinstance(action, Mapping):
        return _reject("unknown", {}, "not_a_mapping")
    op = str(action.get("op") or "").strip()
    if op not in OPS:
        return _reject(op, dict(action), "unknown_op")
    # Refuse any payload key that names a frozen rule.
    for k, v in action.items():
        if touches_invariant(str(k)) or touches_invariant(str(v)):
            return _reject(op, dict(action), "invariant")
    if op == "set_knob":
        return _validate_set_knob(action)
    if op == "add_skip_rule":
        return _validate_skip_or_park(action, "add_skip_rule",
                                      SKIP_CYCLES_LO, SKIP_CYCLES_HI, 6)
    if op == "add_park_rule":
        return _validate_skip_or_park(action, "add_park_rule",
                                      PARK_CYCLES_LO, PARK_CYCLES_HI, 6)
    if op == "reorder_desk":
        return _validate_reorder(action)
    if op == "add_family_rotation":
        return _validate_family(action)
    if op == "mark_ceiling":
        return _validate_ceiling(action)
    if op == "add_triviality_candidate":
        return _validate_triviality(action)
    return _reject(op, dict(action), "unknown_op")


def _validate_set_knob(action: Mapping[str, Any]) -> ValidatedAction:
    name = str(action.get("name") or "").strip()
    if not name:
        return _reject("set_knob", dict(action), "missing_name")
    if touches_invariant(name):
        return _reject("set_knob", dict(action), "invariant")
    try:
        from hive import host
        KNOB_SPECS = host.KNOB_SPECS
        in_bounds = host.heal_in_bounds
        is_invariant_name = host.heal_is_invariant_name
        stepped_value = host.heal_stepped_value
        current_knob = host.heal_current_knob
    except Exception as exc:  # noqa: BLE001
        return _reject("set_knob", dict(action), f"self_heal_unavailable:{exc}")
    if is_invariant_name(name) or name not in KNOB_SPECS:
        return _reject("set_knob", dict(action), "unknown_or_invariant_knob")
    direction = str(action.get("direction") or "").strip().lower()
    if direction not in ("up", "down", ""):
        return _reject("set_knob", dict(action), "bad_direction")
    payload: dict[str, Any] = {"name": name}
    if direction:
        payload["direction"] = direction
    if "value" in action and action.get("value") is not None:
        if not in_bounds(name, action.get("value")):
            return _reject("set_knob", dict(action), "out_of_bounds")
        payload["value"] = action.get("value")
    elif direction:
        # Resolve the stepped value now so the fingerprint is concrete.
        nxt = stepped_value(name, direction, current=current_knob(name))
        if nxt is None:
            return _reject("set_knob", dict(action), "step_hits_bound")
        payload["value"] = nxt
        payload["direction"] = direction
    else:
        return _reject("set_knob", dict(action), "missing_value_or_direction")
    if not in_bounds(name, payload["value"]):
        return _reject("set_knob", dict(action), "out_of_bounds")
    return _accept("set_knob", payload)


def _validate_skip_or_park(
    action: Mapping[str, Any], op: str, lo: int, hi: int, default: int,
) -> ValidatedAction:
    target = _clean_id(action.get("target") or action.get("id") or "")
    chain = _clean_id(action.get("chain") or action.get("chain_id") or "")
    kind = str(action.get("target_kind") or "").strip().lower()
    if kind and (len(kind) > ID_LEN_HI or touches_invariant(kind)
                 or not all(ch.isalnum() or ch in "-_" for ch in kind)):
        return _reject(op, dict(action), "bad_target_kind")
    if not target and not chain and not kind:
        return _reject(op, dict(action), "missing_target")
    cycles = _bounded_int(action.get("cycles"), lo, hi, default)
    if cycles is None:
        return _reject(op, dict(action), "cycles_out_of_bounds")
    payload: dict[str, Any] = {"cycles": cycles}
    if target:
        payload["target"] = target
    if chain:
        payload["chain"] = chain
    if kind:
        payload["target_kind"] = kind
    return _accept(op, payload)


def _validate_reorder(action: Mapping[str, Any]) -> ValidatedAction:
    raw = action.get("order") or action.get("desks") or []
    if not isinstance(raw, (list, tuple)) or not raw:
        return _reject("reorder_desk", dict(action), "missing_order")
    desks = [str(d).strip() for d in raw]
    known = set(KNOWN_DESKS)
    if any(d not in known for d in desks):
        return _reject("reorder_desk", dict(action), "unknown_desk")
    if len(set(desks)) != len(desks):
        return _reject("reorder_desk", dict(action), "duplicate_desk")
    # Must be a permutation of a subset of known desks (not a new set).
    return _accept("reorder_desk", {"order": desks})


def _validate_family(action: Mapping[str, Any]) -> ValidatedAction:
    family = str(action.get("family") or action.get("name") or "").strip().lower()
    if family not in KNOWN_FAMILIES:
        return _reject("add_family_rotation", dict(action), "unknown_family")
    return _accept("add_family_rotation", {"family": family})


def _validate_ceiling(action: Mapping[str, Any]) -> ValidatedAction:
    target = _clean_id(action.get("target") or action.get("id") or "")
    if not target:
        return _reject("mark_ceiling", dict(action), "missing_target")
    depth = _bounded_int(action.get("depth") or action.get("cap"), 
                         CEILING_DEPTH_LO, CEILING_DEPTH_HI, None)
    if depth is None:
        return _reject("mark_ceiling", dict(action), "depth_out_of_bounds")
    reason = str(action.get("reason") or "evaluator_cap").strip()[:80]
    if touches_invariant(reason):
        return _reject("mark_ceiling", dict(action), "invariant")
    return _accept("mark_ceiling", {
        "target": target, "depth": depth, "reason": reason or "evaluator_cap",
    })


def _validate_triviality(action: Mapping[str, Any]) -> ValidatedAction:
    pattern = str(action.get("pattern") or "").strip()
    if not pattern or len(pattern) > PATTERN_LEN_HI:
        return _reject("add_triviality_candidate", dict(action), "bad_pattern")
    if touches_invariant(pattern):
        return _reject("add_triviality_candidate", dict(action), "invariant")
    ptype = str(action.get("pattern_type") or "literal").strip().lower()
    if ptype not in ("literal", "regex"):
        return _reject("add_triviality_candidate", dict(action), "bad_pattern_type")
    # Build a checker-lane-shaped candidate and run the tighten-only guard.
    candidate = {
        "kind": "triviality_pattern",
        "pattern": pattern,
        "pattern_type": ptype,
        "direction": "tighten",
    }
    try:
        from hive import host
        tighten_only_guard = host.tighten_only_guard
        invariant_hits = host.invariant_hits
        # History can be empty: the guard still rejects invariant hits
        # and loosening. Full replay happens in the checker lane itself.
        decision = tighten_only_guard(candidate, history=[])
        if isinstance(decision, dict) and decision.get("accepted") is False:
            return _reject(
                "add_triviality_candidate", dict(action),
                str(decision.get("reason") or "checker_rejected"),
            )
        if invariant_hits(candidate):
            return _reject("add_triviality_candidate", dict(action), "invariant")
    except Exception as exc:  # noqa: BLE001
        # If the lane cannot be imported, still accept as a *candidate*
        # only — never applied to the live Oracle.
        candidate["guard_error"] = f"{type(exc).__name__}:{exc}"
    return _accept("add_triviality_candidate", {
        "pattern": pattern,
        "pattern_type": ptype,
        "kind": "triviality_pattern",
        "direction": "tighten",
        "routed_to": "checker_lane",
        "applied_to_live_oracle": False,
    })


def legal_knob_names() -> list[str]:
    try:
        from hive import host
        return [n for n in host.KNOB_SPECS if not host.heal_is_invariant_name(n)]
    except Exception:
        return []


def describe(action: Mapping[str, Any]) -> str:
    """Short plain-English phrase for logs and dashboard lines."""
    v = validate(action)
    if not v.ok:
        return f"rejected {v.op} ({v.reason})"
    op, p = v.op, v.payload
    if op == "set_knob":
        d = p.get("direction") or ""
        return f"set knob {p.get('name')} {d} to {p.get('value')}".strip()
    if op == "add_skip_rule":
        who = p.get("target") or p.get("chain") or p.get("target_kind")
        return f"skip {who} for {p.get('cycles')} cycles"
    if op == "add_park_rule":
        who = p.get("target") or p.get("chain") or p.get("target_kind")
        return f"park {who} for {p.get('cycles')} cycles"
    if op == "reorder_desk":
        return "reorder desks: " + ", ".join(p.get("order") or [])
    if op == "add_family_rotation":
        return f"add family {p.get('family')} to rotation"
    if op == "mark_ceiling":
        return f"mark ceiling {p.get('target')} at {p.get('depth')}"
    if op == "add_triviality_candidate":
        return f"triviality candidate {p.get('pattern')!r} (checker lane)"
    return v.fingerprint
