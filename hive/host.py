"""Call-time hooks a host application may bind.

Hive never imports the host. The Agent Colony adapter calls
``bind(heal=..., checker=...)`` with those modules; Hive then looks
up helpers on them at call time so test monkeypatches still apply.

With no host bound, Hive uses shipped knob bounds, its own invariant
fragment list, empty observations, and no-op trial helpers, so it is
runnable and testable with zero colony code present.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

_DATA = Path(__file__).resolve().parent / "data"

# Bound host modules. Looked up at call time; never imported by name.
_heal: Any = None
_checker: Any = None

# Names that can never appear as a knob or rule target. Kept in the
# same spirit as the colony's frozen-rule list; Hive also applies this
# list on its own when no host is bound.
INVARIANT_FRAGMENTS = (
    "p_min", "pmin", "standing_trust", "authorize_p",
    "authored_cap", "max_authored", "authored_check",
    "athanor", "dphi", "delta_phi", "h7", "coherence_c",
    "authorize", "human_authorize", "authorization", "human_guide",
    "witness", "rewrite_witness",
    "oracle_threshold", "oracle_p", "live_oracle",
    "w_targets", "w_depth", "w_passes",
)


def bind(*, heal: Any = None, checker: Any = None) -> None:
    """Attach a host's live modules. Pass ``None`` to unbind one."""
    global _heal, _checker
    _heal = heal
    _checker = checker


def is_bound() -> bool:
    return _heal is not None


def _norm(s: Any) -> str:
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum() or ch == "_")


@dataclass(frozen=True)
class KnobSpec:
    name: str
    default: int | float
    lo: int | float
    hi: int | float
    kind: str
    group: str
    doc: str


def _load_default_specs() -> dict[str, KnobSpec]:
    raw = json.loads((_DATA / "knob_specs.json").read_text(encoding="utf-8"))
    out: dict[str, KnobSpec] = {}
    for row in raw:
        spec = KnobSpec(
            name=str(row["name"]),
            default=row["default"],
            lo=row["lo"],
            hi=row["hi"],
            kind=str(row["kind"]),
            group=str(row["group"]),
            doc=str(row.get("doc") or ""),
        )
        out[spec.name] = spec
    return out


def _load_default_suggestions() -> dict[str, list[tuple[str, str]]]:
    raw = json.loads((_DATA / "diagnosis_suggestions.json").read_text(encoding="utf-8"))
    return {k: [(str(a), str(b)) for a, b in v] for k, v in raw.items()}


_DEFAULT_KNOB_SPECS: dict[str, KnobSpec] = _load_default_specs()
_DEFAULT_SUGGESTIONS: dict[str, list[tuple[str, str]]] = _load_default_suggestions()


def knob_specs() -> Mapping[str, Any]:
    if _heal is not None:
        return _heal.KNOB_SPECS
    return _DEFAULT_KNOB_SPECS


def diagnosis_suggestions() -> Mapping[str, list[tuple[str, str]]]:
    if _heal is not None:
        return _heal.DIAGNOSIS_SUGGESTIONS
    return _DEFAULT_SUGGESTIONS


# Attribute-style aliases so call sites can use host.KNOB_SPECS /
# host.DIAGNOSIS_SUGGESTIONS and still see a bound host at call time.
# These are functions wrapped by a tiny proxy in __getattr__.


def __getattr__(name: str) -> Any:
    if name == "KNOB_SPECS":
        return knob_specs()
    if name == "DIAGNOSIS_SUGGESTIONS":
        return diagnosis_suggestions()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def heal_is_invariant_name(name: str) -> bool:
    if _heal is not None:
        try:
            if _heal.is_invariant_name(name):
                return True
        except Exception:
            pass
    key = _norm(name)
    if not key:
        return False
    for frag in INVARIANT_FRAGMENTS:
        if frag.replace("_", "") in key.replace("_", ""):
            return True
    return False


def _cast(spec: Any, value: Any) -> int | float:
    if getattr(spec, "kind", "int") == "float":
        return float(value)
    return int(round(float(value)))


def heal_in_bounds(name: str, value: Any) -> bool:
    if _heal is not None:
        return bool(_heal.in_bounds(name, value))
    specs = knob_specs()
    if name not in specs:
        return False
    spec = specs[name]
    try:
        v = _cast(spec, value)
    except (TypeError, ValueError):
        return False
    return float(spec.lo) <= float(v) <= float(spec.hi)


def heal_current_knob(name: str) -> int | float:
    if _heal is not None:
        return _heal.current_knob(name)
    specs = knob_specs()
    if name not in specs:
        raise KeyError(name)
    return specs[name].default


def heal_stepped_value(
    name: str,
    direction: str,
    *,
    current: int | float | None = None,
    step_size: float | None = None,
) -> int | float | None:
    if _heal is not None:
        return _heal.stepped_value(name, direction, current=current, step_size=step_size)
    specs = knob_specs()
    if heal_is_invariant_name(name) or name not in specs:
        return None
    spec = specs[name]
    cur = current if current is not None else heal_current_knob(name)
    cur = _cast(spec, cur)
    if step_size is None:
        try:
            step_size = float(heal_current_knob("step_size"))
        except Exception:
            step_size = float(specs["step_size"].default)
    span = float(spec.hi) - float(spec.lo)
    raw = float(step_size) * span
    if spec.kind == "int":
        delta = max(1, int(round(raw)))
        nxt = int(cur) + (delta if direction == "up" else -delta)
        nxt = int(min(spec.hi, max(spec.lo, nxt)))
    else:
        delta = raw
        nxt = float(cur) + (delta if direction == "up" else -delta)
        nxt = float(min(float(spec.hi), max(float(spec.lo), round(nxt, 4))))
    if nxt == cur:
        return None
    return nxt


def heal_load_state() -> dict[str, Any]:
    if _heal is not None:
        return _heal.load_state()
    return {}


def heal_start_trial(trial: dict[str, Any], *, state: dict[str, Any] | None = None, cycle_id: str = "") -> dict[str, Any]:
    if _heal is not None:
        return _heal.start_trial(trial, state=state, cycle_id=cycle_id)
    return {"ok": False, "reason": "no_host"}


def heal_replay_proposal(*args: Any, **kwargs: Any) -> dict[str, Any]:
    if _heal is not None:
        return _heal.replay_proposal(*args, **kwargs)
    return {"accepted": True, "reasons": ["no_host"], "simulated": True, "note": "standalone"}


def heal_window_score(rows: Iterable[dict[str, Any]]) -> float:
    if _heal is not None:
        return float(_heal.window_score(rows))
    rows = list(rows)
    if not rows:
        return 0.0
    return float(sum(float(r.get("score") or 0) for r in rows))


def heal_rescore_metric_row(row: Mapping[str, Any]) -> dict[str, Any]:
    if _heal is not None:
        return _heal.rescore_metric_row(row)
    return dict(row)


def heal_collect_metrics(cycle_id: str = "") -> dict[str, Any]:
    if _heal is not None:
        return _heal.collect_metrics(cycle_id)
    return {"cycle_id": cycle_id, "new_oracle_targets": 0, "new_depth": 0,
            "oracle_pass_delta": 0, "oracle_passes": 0, "score": 0}


def diagnose(cycle_id: str = "") -> list[dict[str, Any]]:
    if _heal is not None:
        return list(_heal.diagnose(cycle_id) or [])
    return []


def tighten_only_guard(candidate: Mapping[str, Any], history: Iterable[Any] | None = None) -> dict[str, Any]:
    if _checker is not None:
        return _checker.tighten_only_guard(candidate, history=list(history or []))
    return {"accepted": True, "reason": "no_host"}


def invariant_hits(candidate: Mapping[str, Any]) -> list[str]:
    if _checker is not None:
        return list(_checker.invariant_hits(candidate) or [])
    # Standalone: scan string values for frozen-rule fragments.
    hits: list[str] = []
    for v in (candidate or {}).values():
        if heal_is_invariant_name(str(v)):
            hits.append(str(v))
    return hits
