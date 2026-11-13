"""Self-healing and self-improvement through a bounded, versioned policy.

Each evolve cycle this module:

* reads the colony's own run history (stall state, attempt log, Oracle
  pass totals, prior policy trials) and diagnoses recurring failure
  patterns — loops, dead ends, no-progress PERTURB sessions, immediate
  re-entry, and optional steps that threw
* proposes a change to one colony-owned knob (park length, epsilon,
  cooldowns, family-rotation weight, the step size and evaluation
  window themselves, and similar). The Oracle, the P ≥ 0.70 gate, the
  150 authored-check cap, Athanor math, human authorize, and the
  append-only witness are not knobs and cannot be set
* evaluates a proposal by an A/B trial across a fixed window of cycles,
  using a fixed metric (new Oracle-reaching targets + new verified
  depth past a published range + Oracle-pass change). A conservative
  replay of prior evidence rejects a change that was already tried in
  the same direction and reverted
* adopts the change only when the trial score is strictly higher than
  the baseline; otherwise it reverts. Every adopt and revert is
  appended to an evidence log with the numbers, so a later gain can be
  traced to a self-made change
* records a fingerprint of the code and of every knob except the one
  under trial. If that fingerprint changes during the baseline or the
  trial window (a code merge, a raised evaluator cap, any other knob),
  the trial is voided: an append-only ``trial_voided_confound`` event
  is written, the knob is restored, there is no adopt and no
  revert-as-negative, and a fresh same-fingerprint baseline starts
* if an optional cycle step throws, records the error and quarantines
  that step for N cycles after a threshold of failures. Protected
  gates (trust gate, Oracle, authorize, Athanor, witness, the P gate)
  cannot be quarantined or silenced

Nothing here generates or applies source-code changes. Failures in
this module never break the evolve cycle, never authorize, and never
write human_guide lessons.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS_PATH = Path(__file__).resolve().parent / "self_heal_defaults.json"
STATE_PATH = ROOT / "society" / "systems" / "self_heal.json"
EVENT_LOG = ROOT / "data" / "commons" / "self_heal.jsonl"

# Fixed metric weights. These are not knobs: redefining "improvement"
# would let the loop grade itself on a moving scale.
W_TARGETS = 1.0
W_DEPTH = 1.0
W_PASSES = 3.0

# After a revert, wait this many cycles before retrying the same knob
# in the same direction. Not a knob.
KNOB_RETRY_COOLDOWN = 6

# One trial at a time. Not a knob.
MAX_CONCURRENT_TRIALS = 1

# How many recent metric rows and evidence events the snapshot keeps.
# The evidence list is append-only: old events are never rewritten.
# A bounded tail is stored in the snapshot; the jsonl is the full log.
METRICS_KEEP = 48
EVIDENCE_KEEP = 200
FAILURES_KEEP = 24

PROTECTED_STEPS = frozenset({
    "trust_gate",
    "oracle",
    "authorize",
    "athanor",
    "witness",
    "p_gate",
    "standing_trust",
    "authored_cap",
    "human_guide",
    "human_authorize",
})

# Names that can never appear as knobs, in any casing or punctuation.
_INVARIANT_FRAGMENTS = (
    "p_min", "pmin", "standing_trust", "authorize_p",
    "authored_cap", "max_authored", "authored_check",
    "athanor", "dphi", "delta_phi", "h7", "coherence_c",
    "authorize", "human_authorize", "authorization",
    "witness", "rewrite_witness",
    "oracle_threshold", "oracle_p", "live_oracle",
    "w_targets", "w_depth", "w_passes",  # metric weights stay fixed
)

# Diagnosis → candidate (knob, direction) pairs, in preference order.
# Mechanisms, not a list of sequence ids.
DIAGNOSIS_SUGGESTIONS: dict[str, list[tuple[str, str]]] = {
    "repeated_targets": [
        ("unused_menu_cycles", "up"),
        ("perturb_epsilon", "up"),
        ("perturb_cooldown_cycles", "up"),
    ],
    "no_progress_perturb": [
        ("perturb_cooldown_cycles", "up"),
        ("perturb_epsilon", "up"),
        ("unused_menu_cycles", "up"),
    ],
    "immediate_reentry": [
        ("perturb_cooldown_cycles", "up"),
    ],
    "dead_end_streak": [
        ("park_cycles", "up"),
        ("block_streak_to_park", "down"),
    ],
    "flat_passes": [
        ("perturb_epsilon", "up"),
        ("unused_menu_cycles", "up"),
        ("perturb_max_cycles", "up"),
    ],
    "high_revert_rate": [
        ("step_size", "down"),
        ("evaluation_window", "up"),
    ],
    "depth_at_physical_cap": [
        ("fast_term_cap", "up"),
        ("gf_term_cap", "up"),
        ("deep_digits", "up"),
        ("deep_seconds", "up"),
    ],
}


@dataclass(frozen=True)
class KnobSpec:
    name: str
    default: int | float
    lo: int | float
    hi: int | float
    kind: str  # "int" or "float"
    group: str
    doc: str


# Authoritative bounds. The JSON file may not widen these.
# Defaults match the stall.py / oeis_conjectures.py constants at the
# time this lane was added.
KNOB_SPECS: dict[str, KnobSpec] = {
    "park_cycles": KnobSpec("park_cycles", 6, 3, 18, "int", "search",
                            "Cycles a repeated proposal stays parked."),
    "block_streak_to_park": KnobSpec("block_streak_to_park", 2, 2, 5, "int", "search",
                                    "Consecutive repeat-blocks before a proposal is parked."),
    "stall_cycles": KnobSpec("stall_cycles", 6, 4, 12, "int", "search",
                             "Flat Oracle-pass cycles before STALL fires."),
    "stall_dead_end_cycles": KnobSpec("stall_dead_end_cycles", 3, 2, 6, "int", "search",
                                      "All-dead-end cycles before STALL fires."),
    "perturb_max_cycles": KnobSpec("perturb_max_cycles", 9, 4, 15, "int", "search",
                                   "PERTURB exits after this many cycles if nothing new is found."),
    "perturb_epsilon": KnobSpec("perturb_epsilon", 0.3, 0.1, 0.7, "float", "search",
                                "Epsilon-greedy exploration rate in PERTURB."),
    "perturb_wide_epsilon": KnobSpec("perturb_wide_epsilon", 0.5, 0.2, 0.9, "float", "search",
                                     "Wider exploration rate after a PERTURB timeout."),
    "perturb_min_targets": KnobSpec("perturb_min_targets", 2, 1, 5, "int", "search",
                                    "Minimum distinct targets a PERTURB turn should draw."),
    "perturb_cooldown_cycles": KnobSpec("perturb_cooldown_cycles", 6, 3, 18, "int", "search",
                                        "Cycles to wait after a no-progress timeout."),
    "perturb_zero_pick_cycles": KnobSpec("perturb_zero_pick_cycles", 1, 1, 3, "int", "search",
                                         "Consecutive 0-pick PERTURB cycles before a no_candidates exit."),
    "unused_menu_cycles": KnobSpec("unused_menu_cycles", 20, 8, 40, "int", "search",
                                   "How far back PERTURB looks to treat a target as already tried."),
    "family_rotation_penalty": KnobSpec("family_rotation_penalty", 0.85, 0.5, 0.95, "float",
                                        "selection",
                                        "Score multiplier for the claim form just attempted."),
    "quarantine_cycles": KnobSpec("quarantine_cycles", 6, 2, 12, "int", "healing",
                                  "Cycles a failing optional step stays quarantined."),
    "quarantine_fail_threshold": KnobSpec("quarantine_fail_threshold", 2, 1, 4, "int", "healing",
                                          "Failures of one step before it is quarantined."),
    "step_size": KnobSpec("step_size", 0.15, 0.05, 0.4, "float", "meta",
                          "Fraction of a knob's range used as one adjustment step."),
    "evaluation_window": KnobSpec("evaluation_window", 6, 3, 12, "int", "meta",
                                  "Cycles of trial vs baseline compared before adopt or revert."),
    # Evaluator caps. Raisable only where computation stays cheap and exact.
    # The Oracle, P-gate, 150 cap, and Athanor are not knobs.
    "gf_term_cap": KnobSpec("gf_term_cap", 1200, 600, 8000, "int", "caps",
                            "Slow series-arithmetic term cap (algebraic / EGF / fallback g.f.)."),
    "deep_term_cap": KnobSpec("deep_term_cap", 20000, 5000, 40000, "int", "caps",
                              "Term cap for non-C-finite deep search (relations, properties)."),
    "fast_term_cap": KnobSpec("fast_term_cap", 8000, 2000, 20000, "int", "caps",
                              "Term cap used when a C-finite exact iterator applies."),
    "deep_digits": KnobSpec("deep_digits", 5000, 3000, 12000, "int", "caps",
                            "Decimal-digit budget for exact integer terms."),
    "deep_seconds": KnobSpec("deep_seconds", 8.0, 4.0, 16.0, "float", "caps",
                             "Time budget in seconds for one evaluator call. Kept inside CI limits."),
}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _event_id() -> str:
    return uuid.uuid4().hex[:16]


# Cached per-process: colony/ source does not change mid-run.
_CODE_FINGERPRINT_CACHE: str | None = None

# Marker for a trial that started before fingerprints were recorded.
UNRECORDED_FINGERPRINT = "unrecorded"


def _code_roots() -> list[tuple[str, Path]]:
    """Source trees that belong in the environment fingerprint.

    ``colony/`` is always included. ``hive/`` is included when present,
    so a Hive code change mid-trial is a confound the same way a colony
    change is. Library JSONL and other data files are not hashed.
    """
    roots: list[tuple[str, Path]] = [("colony", Path(__file__).resolve().parent)]
    hive = ROOT / "hive"
    if hive.is_dir():
        roots.append(("hive", hive))
    return roots


def _colony_file_digest() -> str:
    """SHA-256 of colony/ and hive/ Python and default JSON, in path order."""
    global _CODE_FINGERPRINT_CACHE
    if _CODE_FINGERPRINT_CACHE is not None:
        return _CODE_FINGERPRINT_CACHE
    parts: list[str] = []
    for label, root in _code_roots():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            if path.suffix not in {".py", ".json"}:
                continue
            rel = path.relative_to(root).as_posix()
            try:
                data = path.read_bytes()
            except OSError:
                continue
            parts.append(f"{label}/{rel}:{hashlib.sha256(data).hexdigest()}")
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    _CODE_FINGERPRINT_CACHE = digest
    return digest


def _git_tree_sha(subtree: str) -> str:
    """Git tree SHA of one subtree. Empty if git is unavailable."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", f"HEAD:{subtree}"],
            cwd=str(ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return out or ""
    except Exception:
        return ""


def _colony_tree_sha() -> str:
    """Git tree SHA of colony/ (and hive/ when present).

    Data-only commits that do not touch those trees leave this unchanged,
    so a spark-loop data push does not void a trial.
    """
    parts = [f"colony:{_git_tree_sha('colony')}"]
    if (ROOT / "hive").is_dir():
        parts.append(f"hive:{_git_tree_sha('hive')}")
    return ",".join(parts)


def environment_fingerprint(
    *,
    exclude_knob: str | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fingerprint of running code and of every knob except ``exclude_knob``.

    The digest is what a trial stores and later compares. The parts are
    kept so a void event can show what changed (code vs a cap or knob).
    """
    if state is not None and isinstance(state.get("knobs"), dict):
        knobs_src = state["knobs"]
    else:
        try:
            knobs_src = (load_state().get("knobs") or default_knobs())
        except Exception:
            knobs_src = default_knobs()
    knobs: dict[str, int | float] = {}
    skip = str(exclude_knob or "")
    for name, spec in KNOB_SPECS.items():
        if name == skip:
            continue
        raw = (knobs_src or {}).get(name, spec.default)
        try:
            knobs[name] = _cast(spec, raw)
        except Exception:
            knobs[name] = spec.default
    parts = {
        "code": _colony_file_digest(),
        "tree": _colony_tree_sha(),
        "knobs": knobs,
    }
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return {
        "digest": digest,
        "code": parts["code"],
        "tree": parts["tree"],
        "knobs": knobs,
    }


def trial_fingerprint_mismatch(
    trial: dict[str, Any] | None,
    *,
    state: dict[str, Any] | None = None,
) -> tuple[bool, str, str]:
    """True when the trial's recorded environment no longer matches.

    A trial that started before fingerprints were recorded (``unrecorded``)
    is a mismatch: we cannot prove the environment was stable, and the
    in-flight perturb_cooldown trial straddles a cap-raising merge.
    """
    if not isinstance(trial, dict) or not trial:
        return False, "", ""
    current = environment_fingerprint(
        exclude_knob=str(trial.get("knob") or "") or None,
        state=state,
    )
    new_fp = str(current.get("digest") or "")
    old_fp = str(trial.get("environment_fingerprint") or "")
    if not old_fp:
        return True, UNRECORDED_FINGERPRINT, new_fp
    return old_fp != new_fp, old_fp, new_fp


def is_invariant_name(name: str) -> bool:
    """True if this name refers to a fixed rule that is not a knob."""
    key = "".join(ch for ch in str(name or "").lower() if ch.isalnum() or ch == "_")
    key_compact = key.replace("_", "")
    for frag in _INVARIANT_FRAGMENTS:
        f = frag.replace("_", "")
        if frag in key or f in key_compact:
            return True
    return False


def _cast(spec: KnobSpec, value: Any) -> int | float:
    if spec.kind == "int":
        return int(round(float(value)))
    return float(value)


def clamp(name: str, value: Any) -> int | float:
    """Project a value onto the hard bounds. Raises if ``name`` is not a knob."""
    if is_invariant_name(name) or name not in KNOB_SPECS:
        raise ValueError(f"not a tunable knob: {name}")
    spec = KNOB_SPECS[name]
    v = _cast(spec, value)
    if v < spec.lo:
        v = _cast(spec, spec.lo)
    if v > spec.hi:
        v = _cast(spec, spec.hi)
    return v


def in_bounds(name: str, value: Any) -> bool:
    if is_invariant_name(name) or name not in KNOB_SPECS:
        return False
    spec = KNOB_SPECS[name]
    try:
        v = _cast(spec, value)
    except (TypeError, ValueError):
        return False
    return spec.lo <= v <= spec.hi


def load_defaults_file() -> dict[str, Any]:
    """Read the committed defaults file. Code bounds always win."""
    if not DEFAULTS_PATH.exists():
        return {}
    try:
        return json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def default_knobs() -> dict[str, int | float]:
    """Code defaults, optionally replaced by a file default that stays in bounds."""
    out = {name: spec.default for name, spec in KNOB_SPECS.items()}
    blob = load_defaults_file()
    file_knobs = blob.get("knobs") if isinstance(blob, dict) else None
    if not isinstance(file_knobs, dict):
        return out
    for name, entry in file_knobs.items():
        if is_invariant_name(name) or name not in KNOB_SPECS:
            continue
        if not isinstance(entry, dict):
            continue
        if "default" in entry:
            try:
                if in_bounds(name, entry["default"]):
                    out[name] = _cast(KNOB_SPECS[name], entry["default"])
            except (TypeError, ValueError):
                pass
    return out


# ---------------------------------------------------------------------------
# State: load, save, evidence append-only
# ---------------------------------------------------------------------------

def _empty_state() -> dict[str, Any]:
    knobs = default_knobs()
    return {
        "version": 1,
        "knobs": knobs,
        "trial": None,
        "metrics": [],
        "quarantine": {},
        "failures": [],
        "evidence": [],
        "adopted_count": 0,
        "reverted_count": 0,
        "cycle_index": 0,
        "cycles": [],
        "last_self_change": None,
        "knob_last_trial": {},
    }


def load_state() -> dict[str, Any]:
    state = _empty_state()
    if not STATE_PATH.exists():
        return state
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return state
    if not isinstance(raw, dict):
        return state
    # Start from defaults, then take only in-bound knob values.
    knobs = dict(state["knobs"])
    for name, value in (raw.get("knobs") or {}).items():
        if name in KNOB_SPECS and not is_invariant_name(name) and in_bounds(name, value):
            knobs[name] = _cast(KNOB_SPECS[name], value)
    knobs = _enforce_epsilon_pair(knobs)
    state["knobs"] = knobs
    for key in (
        "trial", "metrics", "quarantine", "failures", "evidence",
        "adopted_count", "reverted_count", "cycle_index", "cycles",
        "last_self_change", "knob_last_trial",
    ):
        if key in raw:
            state[key] = raw[key]
    # Evidence from disk is the source of truth (append-only).
    if not isinstance(state.get("evidence"), list):
        state["evidence"] = []
    if not isinstance(state.get("metrics"), list):
        state["metrics"] = []
    if not isinstance(state.get("quarantine"), dict):
        state["quarantine"] = {}
    if not isinstance(state.get("cycles"), list):
        state["cycles"] = []
    if not isinstance(state.get("failures"), list):
        state["failures"] = []
    state["adopted_count"] = int(state.get("adopted_count") or 0)
    state["reverted_count"] = int(state.get("reverted_count") or 0)
    state["cycle_index"] = int(state.get("cycle_index") or 0)
    return state


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def save_state(state: dict[str, Any]) -> None:
    """Persist state. Existing evidence events are never rewritten."""
    on_disk: list[dict[str, Any]] = []
    if STATE_PATH.exists():
        try:
            old = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(old, dict) and isinstance(old.get("evidence"), list):
                on_disk = [e for e in old["evidence"] if isinstance(e, dict)]
        except Exception:
            on_disk = []
    incoming = [e for e in (state.get("evidence") or []) if isinstance(e, dict)]
    merged: list[dict[str, Any]] = list(on_disk)
    seen = {e.get("id") for e in merged if e.get("id")}
    for e in incoming:
        eid = e.get("id")
        if eid and eid in seen:
            continue
        if not eid:
            e = dict(e)
            e["id"] = _event_id()
        merged.append(e)
        seen.add(e["id"])
    state = dict(state)
    state["evidence"] = merged[-EVIDENCE_KEEP:]
    state["metrics"] = list(state.get("metrics") or [])[-METRICS_KEEP:]
    state["failures"] = list(state.get("failures") or [])[-FAILURES_KEEP:]
    state["cycles"] = list(state.get("cycles") or [])[-80:]
    knobs = dict(state.get("knobs") or default_knobs())
    # Drop anything that is not a legal knob.
    cleaned = {}
    for name, value in knobs.items():
        if name in KNOB_SPECS and not is_invariant_name(name) and in_bounds(name, value):
            cleaned[name] = _cast(KNOB_SPECS[name], value)
    for name, spec in KNOB_SPECS.items():
        cleaned.setdefault(name, spec.default)
    state["knobs"] = _enforce_epsilon_pair(cleaned)
    _atomic_write(STATE_PATH, json.dumps(state, indent=2, sort_keys=False) + "\n")


def append_log(record: dict[str, Any]) -> None:
    """Append one JSON line. Never rewrites the file."""
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with EVENT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line)


def append_evidence(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Append an evidence event to state and the jsonl. Returns the event with id."""
    ev = dict(event)
    ev.setdefault("id", _event_id())
    ev.setdefault("ts", _utc())
    ev.setdefault("applied_to_live_oracle", False)
    ev.setdefault("authorized", False)
    evidence = list(state.get("evidence") or [])
    evidence.append(ev)
    state["evidence"] = evidence
    if ev.get("event") in ("adopt", "revert", "trial_voided_confound"):
        state["last_self_change"] = ev
    try:
        append_log(ev)
    except Exception:
        pass
    return ev


# ---------------------------------------------------------------------------
# Knobs: read, set, step
# ---------------------------------------------------------------------------

def _enforce_epsilon_pair(knobs: dict[str, int | float]) -> dict[str, int | float]:
    """perturb_wide_epsilon must be >= perturb_epsilon, still inside bounds."""
    out = dict(knobs)
    eps = float(out.get("perturb_epsilon", KNOB_SPECS["perturb_epsilon"].default))
    wide = float(out.get("perturb_wide_epsilon", KNOB_SPECS["perturb_wide_epsilon"].default))
    if wide < eps:
        # Raise wide to match, clamped to its own hi.
        out["perturb_wide_epsilon"] = clamp("perturb_wide_epsilon", eps)
        # If wide is already at hi and still below eps, lower eps instead.
        if float(out["perturb_wide_epsilon"]) < eps:
            out["perturb_epsilon"] = clamp("perturb_epsilon", out["perturb_wide_epsilon"])
    return out


def active_knob(name: str) -> int | float | None:
    """Live adopted (or in-trial) value, or None to mean 'use the caller's default'.

    Returns None for unknown or invariant names, and None when the live
    value equals the code default and no trial is running on this knob —
    so existing tests that monkeypatch module constants keep working
    unless a real policy override is in effect.
    """
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return None
    except Exception:
        pass
    if is_invariant_name(name) or name not in KNOB_SPECS:
        return None
    try:
        state = load_state()
    except Exception:
        return None
    knobs = state.get("knobs") or {}
    if name not in knobs:
        return None
    value = knobs[name]
    if not in_bounds(name, value):
        return None
    value = _cast(KNOB_SPECS[name], value)
    trial = state.get("trial") or None
    in_trial = bool(trial) and str(trial.get("knob") or "") == name
    if (not in_trial) and value == KNOB_SPECS[name].default:
        return None
    return value


def current_knob(name: str) -> int | float:
    """The live value, falling back to the default. Raises on invariant names."""
    if is_invariant_name(name) or name not in KNOB_SPECS:
        raise ValueError(f"not a tunable knob: {name}")
    v = active_knob(name)
    if v is None:
        return KNOB_SPECS[name].default
    return v


def set_knob(name: str, value: Any, *, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Set a knob to a clamped value. Rejects invariant names. Does not save."""
    if is_invariant_name(name) or name not in KNOB_SPECS:
        return {"ok": False, "reason": f"not a tunable knob: {name}", "name": name}
    if not in_bounds(name, value):
        # Still clamp only after confirming it's a real knob; report reject
        # when the raw value is outside, so callers can test enforcement.
        return {
            "ok": False,
            "reason": "out_of_bounds",
            "name": name,
            "value": value,
            "lo": KNOB_SPECS[name].lo,
            "hi": KNOB_SPECS[name].hi,
        }
    st = state if state is not None else load_state()
    knobs = dict(st.get("knobs") or default_knobs())
    knobs[name] = _cast(KNOB_SPECS[name], value)
    knobs = _enforce_epsilon_pair(knobs)
    st["knobs"] = knobs
    return {"ok": True, "name": name, "value": knobs[name], "state": st}


def stepped_value(
    name: str,
    direction: str,
    *,
    current: int | float | None = None,
    step_size: float | None = None,
) -> int | float | None:
    """One step up or down, clamped. None if the value would not change."""
    if is_invariant_name(name) or name not in KNOB_SPECS:
        return None
    spec = KNOB_SPECS[name]
    cur = current if current is not None else current_knob(name)
    cur = _cast(spec, cur)
    if step_size is None:
        try:
            step_size = float(current_knob("step_size"))
        except Exception:
            step_size = float(KNOB_SPECS["step_size"].default)
    step_size = float(clamp("step_size", step_size))
    span = float(spec.hi) - float(spec.lo)
    raw = step_size * span
    if spec.kind == "int":
        delta = max(1, int(round(raw)))
        nxt = int(cur) + (delta if direction == "up" else -delta)
        nxt = int(clamp(name, nxt))
    else:
        delta = raw
        nxt = float(cur) + (delta if direction == "up" else -delta)
        nxt = float(clamp(name, round(nxt, 4)))
    if nxt == cur:
        return None
    return nxt


# ---------------------------------------------------------------------------
# Metric
# ---------------------------------------------------------------------------

def score_metrics(
    new_oracle_targets: int = 0,
    new_depth: int = 0,
    oracle_pass_delta: int = 0,
) -> float:
    """Fixed formula. Weights are not knobs."""
    return (
        W_TARGETS * int(new_oracle_targets)
        + W_DEPTH * int(new_depth)
        + W_PASSES * int(oracle_pass_delta)
    )


def _pass_total_for(hist: list[dict[str, Any]], cycle_id: str) -> tuple[int | None, int | None]:
    """(this cycle's pass_total, previous cycle's pass_total)."""
    this: int | None = None
    prev: int | None = None
    for row in hist:
        cid = str(row.get("cycle_id") or "")
        total = int(row.get("pass_total") or 0)
        if cid == cycle_id:
            this = total
            break
        prev = total
    return this, prev


def _row_verified_for_metric(row: dict[str, Any], tested_hi: int = 0) -> int:
    """Verified depth of one attempt-log row, for the new_depth metric."""
    try:
        from colony.oeis_conjectures import attempt_row_verified_depth
        return int(attempt_row_verified_depth(row, tested_hi) or 0)
    except Exception:
        if not isinstance(row, dict):
            return 0
        try:
            if "verified_depth" in row:
                return int(row.get("verified_depth") or 0)
        except (TypeError, ValueError):
            return 0
        return 0


def targets_with_new_depth(attempt_log: dict[str, Any] | None, cycle_id: str) -> list[str]:
    """Target ids whose verified depth strictly increased this cycle.

    A ``beyond=true`` same-depth hold (``extended`` 0, ``tested_hi`` unchanged)
    is not included. A first-time search past the published range, with no
    earlier past-b-file hold, is. ``extended > 0`` on a row is a direct
    signal. Order is first-seen in the log.
    """
    cid = str(cycle_id or "")
    if not cid or not isinstance(attempt_log, dict):
        return []
    attempts = list(attempt_log.get("attempts") or [])
    # Running explicit verified max, and whether a prior past-b-file hold exists.
    prior_v: dict[str, int] = {}
    prior_past: set[str] = set()
    counted: dict[str, bool] = {}
    for a in attempts:
        if not isinstance(a, dict):
            continue
        eid = str(a.get("id") or "")
        if not eid:
            continue
        this_cycle = str(a.get("cycle_id") or "") == cid
        try:
            bfile = int(a.get("bfile_hi") or 0)
        except (TypeError, ValueError):
            bfile = 0
        try:
            extended = int(a.get("extended") or 0)
        except (TypeError, ValueError):
            extended = 0
        v = _row_verified_for_metric(a, 0)
        # Post-PR #4 rows have verified_depth or planned; use that v.
        # Legacy rows: do not trust requested depth as verified.
        has_explicit = ("verified_depth" in a) or ("planned" in a)
        if this_cycle:
            advanced = False
            if extended > 0:
                advanced = True
            elif has_explicit:
                prev = prior_v.get(eid, 0)
                if v > prev and v > bfile:
                    if prev > 0:
                        advanced = True
                    elif eid not in prior_past:
                        # First recorded past-b-file hold, no earlier beyond hold.
                        advanced = True
                    # else: a prior beyond-b-file hold exists and this explicit
                    # verified is the first one we see — conservative 0 unless
                    # extended > 0 (already handled) or v > prev (prev is 0,
                    # so only the "not in prior_past" branch counts).
            if advanced and eid not in counted:
                counted[eid] = True
        if has_explicit and v > 0:
            prior_v[eid] = max(prior_v.get(eid, 0), v)
            if v > bfile:
                prior_past.add(eid)
        elif a.get("beyond") and a.get("status") in ("holds_on_range", "holds"):
            prior_past.add(eid)
        elif (not this_cycle) and a.get("beyond"):
            prior_past.add(eid)
    return list(counted)


def count_new_depth(attempt_log: dict[str, Any] | None, cycle_id: str) -> int:
    """Number of targets whose verified depth strictly increased this cycle."""
    return len(targets_with_new_depth(attempt_log, cycle_id))


def rescore_metric_row(
    row: dict[str, Any],
    *,
    attempt_log: dict[str, Any] | None = None,
    stall_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute ``new_depth`` and ``score`` from the attempt log. Other
    fields stay as recorded. Does not rewrite the metrics history.
    """
    out = dict(row)
    cid = str(row.get("cycle_id") or "")
    try:
        if attempt_log is None:
            from colony.oeis_conjectures import load_attempt_log
            log = load_attempt_log()
        else:
            log = attempt_log
        new_depth = count_new_depth(log, cid)
    except Exception:
        new_depth = int(row.get("new_depth") or 0)
    out["new_depth"] = int(new_depth)
    out["score"] = score_metrics(
        int(out.get("new_oracle_targets") or 0),
        int(out["new_depth"]),
        int(out.get("oracle_pass_delta") or 0),
    )
    return out


def reconcile_inflated_trial(
    state: dict[str, Any],
    *,
    attempt_log: dict[str, Any] | None = None,
    cycle_id: str = "",
) -> dict[str, Any]:
    """Honestly correct an in-flight trial whose baseline used the old
    ``beyond=true`` count. Append-only: evidence is appended, metric
    history is not rewritten. The live trial's baseline_score is updated.
    """
    trial = state.get("trial")
    if not isinstance(trial, dict) or trial.get("baseline_corrected"):
        return state
    baseline_rows = list(trial.get("baseline_metrics") or [])
    if not baseline_rows:
        return state
    try:
        if attempt_log is None:
            from colony.oeis_conjectures import load_attempt_log
            log = load_attempt_log()
        else:
            log = attempt_log
    except Exception:
        log = attempt_log or {"attempts": []}
    corrected = [rescore_metric_row(r, attempt_log=log) for r in baseline_rows]
    old_score = float(trial.get("baseline_score") or 0)
    new_score = window_score(corrected)
    old_depths = [int(r.get("new_depth") or 0) for r in baseline_rows]
    new_depths = [int(r.get("new_depth") or 0) for r in corrected]
    if old_score == new_score and old_depths == new_depths:
        return state
    trial = dict(trial)
    trial["baseline_score_original"] = old_score
    trial["baseline_score"] = new_score
    trial["baseline_metrics"] = corrected
    trial["baseline_corrected"] = True
    trial["baseline_correction_reason"] = (
        "new_depth counted same-depth beyond=true holds; "
        "recomputed from tested_hi advances"
    )
    state["trial"] = trial
    ev = append_evidence(state, {
        "event": "trial_baseline_corrected",
        "cycle_id": cycle_id or trial.get("started_cycle"),
        "knob": trial.get("knob"),
        "from": trial.get("from"),
        "to": trial.get("to"),
        "reason": trial.get("baseline_correction_reason"),
        "old_baseline_score": old_score,
        "baseline_score": new_score,
        "old_new_depth": old_depths,
        "new_depth": new_depths,
        "window": trial.get("window"),
        "started_cycle": trial.get("started_cycle"),
    })
    trial["baseline_correction_evidence_id"] = ev.get("id")
    state["trial"] = trial
    return state


def collect_metrics(
    cycle_id: str,
    *,
    stall_state: dict[str, Any] | None = None,
    attempt_log: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Measure this cycle: new Oracle-reaching targets, new depth, pass delta."""
    cid = str(cycle_id or "")
    this_targets: set[str] = set()
    prior_targets: set[str] = set()
    pass_total = 0
    prev_passes = 0
    try:
        if stall_state is None:
            from colony.stall import load_state as load_stall, ORACLE_TURN_OUTCOMES
            st = load_stall()
        else:
            st = stall_state
            from colony.stall import ORACLE_TURN_OUTCOMES
        for row in st.get("targets_tried") or []:
            # Depth-only extensions are counted by new_depth, not as Oracle targets.
            if str(row.get("kind") or "oracle") != "oracle":
                continue
            ids = [str(t) for t in (row.get("targets") or []) if t]
            if str(row.get("cycle_id") or "") == cid:
                this_targets.update(ids)
            elif cid:
                prior_targets.update(ids)
        for t in st.get("turns") or []:
            name = t.get("name")
            if not name or str(t.get("outcome") or "") not in ORACLE_TURN_OUTCOMES:
                continue
            if str(t.get("cycle_id") or "") == cid:
                this_targets.add(str(name))
            elif cid:
                prior_targets.add(str(name))
        hist = list(st.get("pass_history") or [])
        this_p, prev_p = _pass_total_for(hist, cid)
        if this_p is None and hist:
            this_p = int(hist[-1].get("pass_total") or 0)
            prev_p = int(hist[-2].get("pass_total") or 0) if len(hist) > 1 else this_p
        pass_total = int(this_p or 0)
        prev_passes = int(prev_p if prev_p is not None else pass_total)
    except Exception:
        pass

    new_depth = 0
    try:
        if attempt_log is None:
            from colony.oeis_conjectures import load_attempt_log
            log = load_attempt_log()
        else:
            log = attempt_log
        new_depth = count_new_depth(log, cid)
    except Exception:
        pass

    new_oracle_targets = len(this_targets - prior_targets)
    oracle_pass_delta = int(pass_total) - int(prev_passes)
    score = score_metrics(new_oracle_targets, new_depth, oracle_pass_delta)
    return {
        "cycle_id": cid,
        "new_oracle_targets": new_oracle_targets,
        "new_depth": new_depth,
        "oracle_passes": pass_total,
        "oracle_pass_delta": oracle_pass_delta,
        "score": score,
        "ts": _utc(),
    }


def window_score(rows: Iterable[dict[str, Any]]) -> float:
    return float(sum(float(r.get("score") or 0) for r in rows))


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------

def _distinct_recent_targets(stall_state: dict[str, Any], n_cycles: int = 3) -> tuple[set[str], list[str]]:
    cycles = list(stall_state.get("cycles") or [])
    last = set(cycles[-n_cycles:]) if cycles else set()
    targets: set[str] = set()
    cycle_ids: list[str] = []
    for row in stall_state.get("targets_tried") or []:
        cid = str(row.get("cycle_id") or "")
        if last and cid not in last:
            continue
        if cid and cid not in cycle_ids:
            cycle_ids.append(cid)
        for t in row.get("targets") or []:
            if t:
                targets.add(str(t))
    return targets, cycle_ids


def diagnose(
    cycle_id: str = "",
    *,
    stall_state: dict[str, Any] | None = None,
    heal_state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return findings with evidence. No hardcoded sequence ids."""
    findings: list[dict[str, Any]] = []
    try:
        st = stall_state if stall_state is not None else __import__(
            "colony.stall", fromlist=["load_state"]
        ).load_state()
    except Exception:
        st = {}
    hs = heal_state if heal_state is not None else load_state()

    targets, target_cycles = _distinct_recent_targets(st, 3)
    tried_rows = [r for r in (st.get("targets_tried") or []) if r.get("targets")]
    if tried_rows and target_cycles and len(targets) <= 1 and len(target_cycles) >= 2:
        findings.append({
            "kind": "repeated_targets",
            "evidence": {
                "distinct_targets_last_3": len(targets),
                "cycles_with_tries": target_cycles[-3:],
                "targets": sorted(targets)[:8],
            },
        })

    pert = st.get("perturb") or {}
    exit_reason = str(pert.get("exit_reason") or "")
    no_progress_exits = ("timeout", "timed_out", "max_cycles", "no_candidates", "no_eligible", "no_eligible_target")
    if (not pert.get("active")) and exit_reason in no_progress_exits and not pert.get("session_progress"):
        findings.append({
            "kind": "no_progress_perturb",
            "evidence": {
                "exit_reason": exit_reason,
                "exit_cycle": pert.get("exit_cycle"),
                "session_targets": list(pert.get("session_targets") or [])[:8],
                "timeout_count": pert.get("timeout_count"),
            },
        })

    # Immediate re-entry: a no-progress timeout, then PERTURB is already
    # active again with no cooldown remaining.
    try:
        from colony.stall import perturb_cooldown_remaining, in_perturb_cooldown
        cooldown = perturb_cooldown_remaining(cycle_id, st)
    except Exception:
        cooldown = int(pert.get("cooldown_until") or -1)
        cooldown = 0 if cooldown < 0 else cooldown
        in_perturb_cooldown = lambda *a, **k: False  # noqa: E731
    if (
        pert.get("active")
        and not in_perturb_cooldown(cycle_id, st)
        and int(pert.get("timeout_count") or 0) >= 1
        and str(pert.get("entered_at") or "") != str(pert.get("last_timeout_cycle") or "")
        and str(pert.get("reason") or "")
    ):
        # Only flag when the last exit was a no-progress timeout and we
        # entered again quickly. If a cooldown is running, this is fine.
        last_exit = str(pert.get("exit_reason") or "")
        if last_exit in ("timeout", "timed_out", "max_cycles", "no_candidates", "no_eligible", "no_eligible_target", "") and cooldown == 0:
            # Entered this cycle or last, after a timeout. Look at cycles.
            cycles = list(st.get("cycles") or [])
            entered = str(pert.get("entered_at") or "")
            timed = str(pert.get("last_timeout_cycle") or "")
            if entered and timed and entered in cycles and timed in cycles:
                if cycles.index(entered) - cycles.index(timed) <= 2:
                    findings.append({
                        "kind": "immediate_reentry",
                        "evidence": {
                            "entered_at": entered,
                            "last_timeout_cycle": timed,
                            "cooldown_remaining": cooldown,
                        },
                    })

    turns = list(st.get("turns") or [])
    cycles = list(st.get("cycles") or [])
    try:
        from colony.stall import DEAD_END_OUTCOMES
    except Exception:
        DEAD_END_OUTCOMES = frozenset({"block", "skip", "identical_kill"})
    dead_n = int(current_knob("stall_dead_end_cycles"))
    observed = [c for c in cycles if any(t.get("cycle_id") == c for t in turns)]
    if len(observed) >= dead_n:
        tail = observed[-dead_n:]
        all_dead = True
        for cid in tail:
            outcomes = [str(t.get("outcome") or "") for t in turns if t.get("cycle_id") == cid]
            if not outcomes or any(o not in DEAD_END_OUTCOMES for o in outcomes):
                all_dead = False
                break
        if all_dead:
            findings.append({
                "kind": "dead_end_streak",
                "evidence": {"cycles": tail, "window": dead_n},
            })

    stall_cycles = int(st.get("stall_cycles") or 0)
    stall_n = int(current_knob("stall_cycles"))
    if stall_cycles >= stall_n:
        findings.append({
            "kind": "flat_passes",
            "evidence": {"stall_cycles": stall_cycles, "threshold": stall_n},
        })

    evidence = list(hs.get("evidence") or [])
    recent = [e for e in evidence if e.get("event") in ("adopt", "revert")][-6:]
    reverts = [e for e in recent if e.get("event") == "revert"]
    if len(recent) >= 3 and len(reverts) >= 2 and len(reverts) >= (len(recent) + 1) // 2:
        findings.append({
            "kind": "high_revert_rate",
            "evidence": {
                "recent_trials": len(recent),
                "reverts": len(reverts),
            },
        })

    # Physical evaluator cap: a recent same-depth hold at a term/digit/time
    # /ref ceiling. Suggest raising the binding cap (self-heal knobs).
    try:
        from colony.oeis_conjectures import load_attempt_log, cap_of_row, CAP_TERM, CAP_DIGIT, CAP_TIME, CAP_REF
        log = load_attempt_log()
        cap_rows = []
        for a in reversed(log.get("attempts") or []):
            if not isinstance(a, dict):
                continue
            if a.get("status") != "holds_on_range":
                continue
            reason, val = cap_of_row(a, None)
            if not reason:
                continue
            try:
                ext = int(a.get("extended") or 0)
            except (TypeError, ValueError):
                ext = 0
            if ext > 0:
                continue
            cap_rows.append({
                "id": a.get("id"),
                "anum": a.get("anum"),
                "cap_reason": reason,
                "cap_value": val,
                "verified_depth": a.get("verified_depth") or a.get("depth"),
                "cycle_id": a.get("cycle_id"),
            })
            if len(cap_rows) >= 3:
                break
        if cap_rows:
            reasons = [r["cap_reason"] for r in cap_rows]
            suggest: list[tuple[str, str]] = []
            if CAP_TERM in reasons:
                suggest.extend([("fast_term_cap", "up"), ("gf_term_cap", "up")])
            if CAP_DIGIT in reasons or "digit_or_time_cap" in reasons:
                suggest.append(("deep_digits", "up"))
            if CAP_TIME in reasons or "digit_or_time_cap" in reasons:
                suggest.append(("deep_seconds", "up"))
            findings.append({
                "kind": "depth_at_physical_cap",
                "evidence": {
                    "recent": cap_rows[:3],
                    "suggest": suggest,
                },
                "suggest": suggest,
            })
    except Exception:
        pass

    return findings


# ---------------------------------------------------------------------------
# Replay (conservative) and trial lifecycle
# ---------------------------------------------------------------------------

def replay_proposal(
    knob: str,
    old: Any,
    new: Any,
    *,
    direction: str,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Reject only when prior evidence already shows this change failed.

    Faithful resimulation of epsilon-greedy draws is not possible from
    the logs alone, so this does not invent a simulated score. The
    online A/B trial is the real evaluation.
    """
    if is_invariant_name(knob) or knob not in KNOB_SPECS:
        return {"accepted": False, "reasons": ["not a tunable knob"], "simulated": False}
    if not in_bounds(knob, new):
        return {"accepted": False, "reasons": ["out_of_bounds"], "simulated": False}
    ev = evidence if evidence is not None else (load_state().get("evidence") or [])
    reasons: list[str] = []
    for e in ev:
        if e.get("event") != "revert":
            continue
        if str(e.get("knob") or "") != knob:
            continue
        # Same direction and same target, or same from→to.
        same_pair = (e.get("from") == old and e.get("to") == new)
        same_dir = str(e.get("direction") or "") == direction
        if same_pair:
            reasons.append("already_reverted_same_change")
            break
        if same_dir:
            reasons.append("recent_revert_same_direction")
            # Keep looking for an exact pair; one same-direction revert
            # in the whole history is enough to skip this direction
            # until the cooldown on knob_last_trial expires — handled
            # by propose_trial. Here we only hard-reject exact repeats.
            continue
    if "already_reverted_same_change" in reasons:
        return {
            "accepted": False,
            "reasons": ["already_reverted_same_change"],
            "simulated": True,
            "note": "this exact from→to was already trialled and reverted",
        }
    return {
        "accepted": True,
        "reasons": [],
        "simulated": False,
        "note": "online trial will decide",
    }


def _knob_on_cooldown(state: dict[str, Any], knob: str, direction: str) -> bool:
    last = (state.get("knob_last_trial") or {}).get(knob) or {}
    if not last:
        return False
    if str(last.get("direction") or "") != direction:
        return False
    last_idx = int(last.get("cycle_index") or -10**9)
    return (int(state.get("cycle_index") or 0) - last_idx) < KNOB_RETRY_COOLDOWN


def propose_trial(
    findings: list[dict[str, Any]],
    *,
    state: dict[str, Any] | None = None,
    cycle_id: str = "",
) -> dict[str, Any] | None:
    """Pick at most one legal knob change from the findings."""
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return None
    except Exception:
        pass
    st = state if state is not None else load_state()
    if st.get("trial"):
        return None
    window = int(current_knob("evaluation_window"))
    metrics = list(st.get("metrics") or [])
    if len(metrics) < window:
        return None
    # A baseline that spans a code or cap change is not a fair comparison.
    # Wait until ``window`` consecutive cycles share the current fingerprint.
    try:
        current_fp = environment_fingerprint(state=st)["digest"]
    except Exception:
        current_fp = ""
    window_rows = metrics[-window:]
    if not current_fp or any(str(r.get("env_fingerprint") or "") != current_fp for r in window_rows):
        return None
    tried: set[tuple[str, str]] = set()
    for finding in findings:
        kind = str(finding.get("kind") or "")
        suggested = list(finding.get("suggest") or [])
        pairs = suggested + [p for p in DIAGNOSIS_SUGGESTIONS.get(kind, []) if p not in suggested]
        for knob, direction in pairs:
            if (knob, direction) in tried:
                continue
            tried.add((knob, direction))
            if _knob_on_cooldown(st, knob, direction):
                continue
            cur = current_knob(knob)
            nxt = stepped_value(knob, direction, current=cur, step_size=float(current_knob("step_size")))
            if nxt is None:
                continue
            # Keep the epsilon pair legal if this is one of those two.
            if knob == "perturb_epsilon" and float(nxt) > float(current_knob("perturb_wide_epsilon")):
                # Step wide first, or skip if wide cannot rise.
                wide_nxt = stepped_value("perturb_wide_epsilon", "up")
                if wide_nxt is None or float(wide_nxt) < float(nxt):
                    if float(KNOB_SPECS["perturb_wide_epsilon"].hi) < float(nxt):
                        continue
            replay = replay_proposal(knob, cur, nxt, direction=direction, evidence=list(st.get("evidence") or []))
            if not replay.get("accepted"):
                continue
            baseline_rows = [rescore_metric_row(r) for r in metrics[-window:]]
            return {
                "knob": knob,
                "from": cur,
                "to": nxt,
                "direction": direction,
                "reason": kind,
                "finding": finding,
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
            }
    return None


def _apply_knob(state: dict[str, Any], name: str, value: Any) -> None:
    knobs = dict(state.get("knobs") or default_knobs())
    knobs[name] = clamp(name, value)
    state["knobs"] = _enforce_epsilon_pair(knobs)


def start_trial(trial: dict[str, Any], *, state: dict[str, Any] | None = None, cycle_id: str = "") -> dict[str, Any]:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return state if state is not None else load_state()
    except Exception:
        pass
    st = state if state is not None else load_state()
    if st.get("trial"):
        return st
    _apply_knob(st, trial["knob"], trial["to"])
    st["trial"] = trial
    last = dict(st.get("knob_last_trial") or {})
    last[trial["knob"]] = {
        "direction": trial.get("direction"),
        "cycle_index": int(st.get("cycle_index") or 0),
        "cycle_id": cycle_id,
    }
    st["knob_last_trial"] = last
    fp = environment_fingerprint(exclude_knob=str(trial.get("knob") or "") or None, state=st)
    trial["environment_fingerprint"] = fp["digest"]
    trial["environment"] = {"code": fp["code"], "tree": fp["tree"], "knobs": fp["knobs"]}
    ev = append_evidence(st, {
        "event": "trial_start",
        "cycle_id": cycle_id,
        "knob": trial["knob"],
        "from": trial["from"],
        "to": trial["to"],
        "direction": trial.get("direction"),
        "reason": trial.get("reason"),
        "baseline_score": trial.get("baseline_score"),
        "window": trial.get("window"),
        "replay": trial.get("replay"),
        "environment_fingerprint": fp["digest"],
        "environment": trial["environment"],
    })
    trial["evidence_id"] = ev["id"]
    st["trial"] = trial
    save_state(st)
    return st


def void_trial_for_confound(
    state: dict[str, Any],
    cycle_id: str,
    *,
    old_fingerprint: str,
    new_fingerprint: str,
    reason: str = "environment_changed",
) -> dict[str, Any]:
    """Void an in-flight trial whose environment changed mid-window.

    Restores the knob to its pre-trial value. Does not adopt, does not
    increment ``reverted_count``, and does not write a ``revert`` event,
    so a later clean trial of the same change is not treated as a repeat
    failure. Evidence is append-only; trial and baseline rows are not
    rewritten. A fresh baseline of same-fingerprint cycles must accumulate
    before a new trial can start.

    On the control arm (self-mod frozen) this is a no-op: the trial,
    knobs, and evidence are left untouched.
    """
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return state
    except Exception:
        pass
    trial = dict(state.get("trial") or {})
    if not trial:
        return state
    knob = str(trial.get("knob") or "")
    if knob:
        _apply_knob(state, knob, trial.get("from"))
    ev = append_evidence(state, {
        "event": "trial_voided_confound",
        "cycle_id": cycle_id,
        "knob": knob,
        "from": trial.get("to"),
        "to": trial.get("from"),
        "direction": trial.get("direction"),
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
    })
    state["last_self_change"] = ev
    state["trial"] = None
    return state


def _close_trial(state: dict[str, Any], cycle_id: str, decision: str) -> dict[str, Any]:
    trial = dict(state.get("trial") or {})
    if not trial:
        return state
    trial_rows = list(trial.get("trial_metrics") or [])
    trial_score = window_score(trial_rows)
    baseline_score = float(trial.get("baseline_score") or 0)
    helped = trial_score > baseline_score
    knob = str(trial.get("knob") or "")
    if decision == "adopt" and helped and knob:
        # Value is already the trial value.
        state["adopted_count"] = int(state.get("adopted_count") or 0) + 1
        ev = append_evidence(state, {
            "event": "adopt",
            "cycle_id": cycle_id,
            "knob": knob,
            "from": trial.get("from"),
            "to": trial.get("to"),
            "direction": trial.get("direction"),
            "reason": trial.get("reason"),
            "baseline_score": baseline_score,
            "trial_score": trial_score,
            "window": trial.get("window"),
            "baseline_metrics": trial.get("baseline_metrics"),
            "trial_metrics": trial_rows,
            "helped": True,
        })
        state["last_self_change"] = ev
        state["trial"] = None
        return state
    # Revert (explicit, or adopt that did not help).
    if knob:
        _apply_knob(state, knob, trial.get("from"))
    state["reverted_count"] = int(state.get("reverted_count") or 0) + 1
    ev = append_evidence(state, {
        "event": "revert",
        "cycle_id": cycle_id,
        "knob": knob,
        "from": trial.get("to"),  # leaving the trial value
        "to": trial.get("from"),  # restoring the previous value
        "direction": trial.get("direction"),
        "reason": trial.get("reason") if decision == "revert" else "did_not_improve",
        "baseline_score": baseline_score,
        "trial_score": trial_score,
        "window": trial.get("window"),
        "baseline_metrics": trial.get("baseline_metrics"),
        "trial_metrics": trial_rows,
        "helped": False,
        "decision_requested": decision,
    })
    state["last_self_change"] = ev
    state["trial"] = None
    return state


def maybe_close_trial(state: dict[str, Any], cycle_id: str) -> dict[str, Any]:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return state
    except Exception:
        pass
    trial = state.get("trial") or None
    if not trial:
        return state
    changed, old_fp, new_fp = trial_fingerprint_mismatch(trial, state=state)
    if changed:
        reason = (
            "unrecorded_environment" if old_fp == UNRECORDED_FINGERPRINT
            else "environment_changed"
        )
        return void_trial_for_confound(
            state, cycle_id,
            old_fingerprint=old_fp, new_fingerprint=new_fp, reason=reason,
        )
    window = int(trial.get("window") or current_knob("evaluation_window"))
    rows = list(trial.get("trial_metrics") or [])
    if len(rows) < window:
        return state
    trial_score = window_score(rows)
    baseline_score = float(trial.get("baseline_score") or 0)
    decision = "adopt" if trial_score > baseline_score else "revert"
    return _close_trial(state, cycle_id, decision)


# ---------------------------------------------------------------------------
# Quarantine / self-healing
# ---------------------------------------------------------------------------

def is_protected_step(name: str) -> bool:
    key = str(name or "").strip().lower()
    if key in PROTECTED_STEPS:
        return True
    # Prefix match: "oracle_check" or "trust_gate_pre" stay protected.
    for p in PROTECTED_STEPS:
        if key == p or key.startswith(p + "_") or key.startswith(p + "-"):
            return True
    if is_invariant_name(key):
        return True
    return False


def is_quarantined(name: str, cycle_id: str = "", *, state: dict[str, Any] | None = None) -> bool:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return False
    except Exception:
        pass
    if is_protected_step(name):
        return False
    st = state if state is not None else load_state()
    rec = (st.get("quarantine") or {}).get(str(name))
    if not rec:
        return False
    until = int(rec.get("until_index") or -1)
    idx = int(st.get("cycle_index") or 0)
    return idx < until


def quarantined_steps(*, state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    st = state if state is not None else load_state()
    idx = int(st.get("cycle_index") or 0)
    out = []
    for name, rec in (st.get("quarantine") or {}).items():
        if is_protected_step(name):
            continue
        until = int(rec.get("until_index") or -1)
        if idx < until:
            out.append({
                "step": name,
                "until_index": until,
                "remaining": max(0, until - idx),
                "reason": rec.get("reason"),
                "error": rec.get("error"),
                "first_seen": rec.get("first_seen"),
            })
    return out


def expire_quarantines(state: dict[str, Any]) -> dict[str, Any]:
    idx = int(state.get("cycle_index") or 0)
    q = dict(state.get("quarantine") or {})
    kept = {}
    for name, rec in q.items():
        if is_protected_step(name):
            continue  # drop any that slipped in
        until = int(rec.get("until_index") or -1)
        if idx < until:
            kept[name] = rec
    state["quarantine"] = kept
    return state


def note_failure(
    name: str,
    exc: BaseException | str,
    cycle_id: str = "",
    *,
    state: dict[str, Any] | None = None,
    save: bool = True,
) -> dict[str, Any]:
    """Record a thrown optional step. May quarantine it. Never touches a gate."""
    st = state if state is not None else load_state()
    result: dict[str, Any] = {
        "step": name,
        "quarantined": False,
        "protected": is_protected_step(name),
        "recorded": False,
    }
    if is_protected_step(name):
        result["reason"] = "protected_step"
        return result
    err = f"{type(exc).__name__}:{exc}" if isinstance(exc, BaseException) else str(exc)
    fail = {
        "step": name,
        "cycle_id": cycle_id,
        "cycle_index": int(st.get("cycle_index") or 0),
        "error": err[:400],
        "ts": _utc(),
    }
    failures = list(st.get("failures") or [])
    failures.append(fail)
    st["failures"] = failures[-FAILURES_KEEP:]
    result["recorded"] = True
    threshold = int(current_knob("quarantine_fail_threshold"))
    window = int(current_knob("evaluation_window"))
    idx = int(st.get("cycle_index") or 0)
    recent = [
        f for f in failures
        if f.get("step") == name and (idx - int(f.get("cycle_index") or 0)) <= window
    ]
    if len(recent) >= threshold and not is_quarantined(name, cycle_id, state=st):
        q_cycles = int(current_knob("quarantine_cycles"))
        rec = {
            "until_index": idx + q_cycles,
            "reason": f"{len(recent)} failures in {window} cycles",
            "error": err[:400],
            "first_seen": recent[0].get("cycle_id") or cycle_id,
            "count": len(recent),
        }
        q = dict(st.get("quarantine") or {})
        q[name] = rec
        st["quarantine"] = q
        result["quarantined"] = True
        result["until_index"] = rec["until_index"]
        append_evidence(st, {
            "event": "quarantine",
            "cycle_id": cycle_id,
            "step": name,
            "error": err[:400],
            "until_index": rec["until_index"],
            "reason": rec["reason"],
        })
    if save and state is None:
        try:
            save_state(st)
        except Exception:
            pass
    result["state"] = st
    return result


def run_step(
    name: str,
    fn: Callable[[], Any],
    *,
    cycle_id: str = "",
) -> dict[str, Any]:
    """Run an optional step. Skip if quarantined. Record throws. Never wraps a gate.

    If ``name`` is protected, ``fn`` is called with no quarantine and
    exceptions propagate — this helper must not silence a gate.
    """
    if is_protected_step(name):
        return {"ok": True, "skipped": False, "protected": True, "result": fn()}
    if is_quarantined(name, cycle_id):
        return {
            "ok": False,
            "skipped": True,
            "quarantined": True,
            "step": name,
            "protected": False,
        }
    try:
        result = fn()
        return {"ok": True, "skipped": False, "quarantined": False, "result": result, "step": name}
    except Exception as exc:  # noqa: BLE001
        note = note_failure(name, exc, cycle_id)
        return {
            "ok": False,
            "skipped": False,
            "quarantined": bool(note.get("quarantined")),
            "error": f"{type(exc).__name__}:{exc}",
            "step": name,
            "protected": False,
        }


@contextmanager
def step(name: str, cycle_id: str = "") -> Iterator[str]:
    """Context manager: yields 'run', 'skip', or re-raises for protected steps.

    On an optional-step exception, records it and suppresses it (the
    same fail-soft behaviour the cycle already uses). Protected steps
    are not swallowed.
    """
    if is_protected_step(name):
        yield "run"
        return
    if is_quarantined(name, cycle_id):
        yield "skip"
        return
    try:
        yield "run"
    except Exception as exc:  # noqa: BLE001
        note_failure(name, exc, cycle_id)


# ---------------------------------------------------------------------------
# Cycle hook
# ---------------------------------------------------------------------------

def _remember_cycle(state: dict[str, Any], cycle_id: str) -> dict[str, Any]:
    cid = str(cycle_id or "")
    cycles = list(state.get("cycles") or [])
    if cid and cid not in cycles:
        cycles.append(cid)
        state["cycle_index"] = len(cycles) - 1
    elif cid and cid in cycles:
        state["cycle_index"] = cycles.index(cid)
    else:
        state["cycle_index"] = int(state.get("cycle_index") or 0)
    state["cycles"] = cycles
    return state


def on_cycle(
    cycle_id: str = "",
    *,
    metrics: dict[str, Any] | None = None,
    stall_state: dict[str, Any] | None = None,
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evolve-cycle entry point. Exceptions are swallowed and returned."""
    try:
        return run_cycle(cycle_id, metrics=metrics, stall_state=stall_state, findings=findings)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"{type(exc).__name__}:{exc}",
            "cycle_id": cycle_id,
            "applied_to_live_oracle": False,
            "authorized": False,
        }


def run_cycle(
    cycle_id: str = "",
    *,
    metrics: dict[str, Any] | None = None,
    stall_state: dict[str, Any] | None = None,
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Diagnose, record metrics, close or start a trial, expire quarantines."""
    st = load_state()
    st = _remember_cycle(st, cycle_id)
    st = expire_quarantines(st)
    try:
        st = reconcile_inflated_trial(st, cycle_id=cycle_id)
    except Exception:
        pass

    row = metrics if metrics is not None else collect_metrics(cycle_id, stall_state=stall_state)
    row = dict(row)
    if not row.get("env_fingerprint"):
        try:
            row["env_fingerprint"] = environment_fingerprint(state=st)["digest"]
        except Exception:
            pass
    hist = list(st.get("metrics") or [])
    # Replace a row already recorded for this cycle; otherwise append.
    hist = [r for r in hist if str(r.get("cycle_id") or "") != str(cycle_id or "")]
    hist.append(row)
    st["metrics"] = hist[-METRICS_KEEP:]

    trial = st.get("trial")
    self_mod = True
    try:
        from colony.arm import self_mod_enabled
        self_mod = bool(self_mod_enabled())
    except Exception:
        self_mod = True
    # Control arm: record metrics, but do not void, close, or start a trial.
    if trial and self_mod:
        changed, old_fp, new_fp = trial_fingerprint_mismatch(trial, state=st)
        if changed:
            # Do not add this cycle to the voided trial's metrics, and do
            # not adopt. The row stays in the metrics history (fresh baseline).
            reason = (
                "unrecorded_environment" if old_fp == UNRECORDED_FINGERPRINT
                else "environment_changed"
            )
            st = void_trial_for_confound(
                st, cycle_id,
                old_fingerprint=old_fp, new_fingerprint=new_fp, reason=reason,
            )
        else:
            tmetrics = list(trial.get("trial_metrics") or [])
            tmetrics = [r for r in tmetrics if str(r.get("cycle_id") or "") != str(cycle_id or "")]
            tmetrics.append(row)
            trial = dict(trial)
            trial["trial_metrics"] = tmetrics
            st["trial"] = trial
            st = maybe_close_trial(st, cycle_id)

    started = False
    proposal = None
    found = findings
    if not st.get("trial"):
        if found is None:
            found = diagnose(cycle_id, stall_state=stall_state, heal_state=st)
        proposal = propose_trial(found, state=st, cycle_id=cycle_id)
        if proposal is not None:
            st = start_trial(proposal, state=st, cycle_id=cycle_id)
            started = True
        else:
            try:
                save_state(st)
            except Exception:
                pass
    else:
        try:
            save_state(st)
        except Exception:
            pass

    vis = visibility(state=st)
    return {
        "ok": True,
        "cycle_id": cycle_id,
        "metrics": row,
        "findings": found if found is not None else [],
        "trial_started": started,
        "trial": st.get("trial"),
        "proposal": proposal,
        "self_changes_adopted": vis["self_changes_adopted"],
        "self_changes_reverted": vis["self_changes_reverted"],
        "last_self_change": vis["last_self_change"],
        "quarantined_steps": vis["quarantined_steps"],
        "applied_to_live_oracle": False,
        "authorized": False,
    }


def visibility(state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fields for telemetry and the dashboard. Not scored, not the Oracle."""
    try:
        st = state if state is not None else load_state()
        last = st.get("last_self_change")
        last_out = None
        if isinstance(last, dict):
            last_out = {
                "event": last.get("event"),
                "knob": last.get("knob"),
                "from": last.get("from"),
                "to": last.get("to"),
                "baseline_score": last.get("baseline_score"),
                "trial_score": last.get("trial_score"),
                "reason": last.get("reason"),
                "cycle_id": last.get("cycle_id"),
                "helped": last.get("helped"),
                "ts": last.get("ts"),
                "old_fingerprint": last.get("old_fingerprint"),
                "new_fingerprint": last.get("new_fingerprint"),
                "adopted": last.get("adopted"),
                "reverted": last.get("reverted"),
            }
        trial = st.get("trial")
        trial_out = None
        if isinstance(trial, dict):
            trial_out = {
                "knob": trial.get("knob"),
                "from": trial.get("from"),
                "to": trial.get("to"),
                "reason": trial.get("reason"),
                "window": trial.get("window"),
                "n_trial_metrics": len(trial.get("trial_metrics") or []),
                "baseline_score": trial.get("baseline_score"),
            }
        return {
            "self_changes_adopted": int(st.get("adopted_count") or 0),
            "self_changes_reverted": int(st.get("reverted_count") or 0),
            "last_self_change": last_out,
            "quarantined_steps": quarantined_steps(state=st),
            "self_heal_trial": trial_out,
        }
    except Exception:
        return {
            "self_changes_adopted": 0,
            "self_changes_reverted": 0,
            "last_self_change": None,
            "quarantined_steps": [],
            "self_heal_trial": None,
        }


def format_visibility(vis: dict[str, Any] | None = None) -> str:
    v = vis if vis is not None else visibility()
    adopted = int(v.get("self_changes_adopted") or 0)
    reverted = int(v.get("self_changes_reverted") or 0)
    last = v.get("last_self_change")
    q = v.get("quarantined_steps") or []
    trial = v.get("self_heal_trial")
    parts = [
        f"self_changes_adopted {adopted}",
        f"self_changes_reverted {reverted}",
    ]
    if last:
        ev = last.get("event")
        knob = last.get("knob")
        evidence = (
            f"{ev} {knob} {last.get('from')}→{last.get('to')} "
            f"(baseline {last.get('baseline_score')}, trial {last.get('trial_score')}"
            f"{', ' + str(last.get('reason')) if last.get('reason') else ''})"
        )
        parts.append(f"last_self_change {evidence}")
    else:
        parts.append("last_self_change none")
    if trial:
        parts.append(
            f"trial {trial.get('knob')} {trial.get('from')}→{trial.get('to')} "
            f"({trial.get('n_trial_metrics')}/{trial.get('window')})"
        )
    if q:
        names = ", ".join(
            f"{s.get('step')} ({s.get('remaining')} left)" for s in q[:6]
        )
        parts.append(f"quarantined steps: {names}")
    else:
        parts.append("quarantined steps: none")
    return "; ".join(parts)
