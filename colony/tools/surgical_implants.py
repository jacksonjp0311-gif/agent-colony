"""Surgical implants — extracted invariants from recent non-LLM research.

Each function is one mathematical invariant from the literature,
translated into a pure, fail-open, lineage-preserving operation.
No new dependencies. No authority transfer. No LLM.

Invariants sourced:
- Distributed multi-armed bandits (2025 IEEE tutorial): agents sharing
  observations over a connected graph get lower regret than acting alone.
  Sharing only helps when the graph is connected.
- s-cubed (Nov 2025): agents learn when to work alone vs share;
  emergent specialization without predefined roles.
- W-ISA (Nov 2025): transactional rank-one interventions with
  shape-checked restoration — edit, verify, commit or roll back.
- Weight-space programming (MIT CSAIL, Nov 2025): sparse rank-one
  edits; store only the delta, never the full payload.
- SciMARS (Nov 2025): shared evidence graph with separate component
  editors — each component mutates only its scoped surface.
- SwarmEvolve (Brown): latent-space evaluation without text decoding;
  Bitwork already does this — documented, not duplicated.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 1. Bandit invariant: sharing reduces regret only on a connected graph
# ---------------------------------------------------------------------------

def graph_connected(my_source: str, exchange_path: Any = None) -> bool:
    """True if at least one foreign lineage has written a receipt.

    Distributed-bandit theorem: information sharing lowers regret versus
    solo play if and only if the observation graph is connected. A system
    with zero foreign sources is topologically solo — foreign priors are
    not evidence, they are noise.
    """
    try:
        from colony.tools.symbiotic_exchange import foreign_fingerprints
        fps = foreign_fingerprints(my_source, limit=50)
        return len(fps) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 2. s-cubed invariant: share vs solo decided by residual magnitude
# ---------------------------------------------------------------------------

def share_or_solo(residual_max: float, threshold: float = 0.5) -> str:
    """High residual -> share (broadcast receipt). Low residual -> solo.

    s-cubed's core finding: agents that learn when to coordinate beat
    agents with fixed coordination policy. Residual magnitude is the
    local signal of surprise; above threshold, the system is in a regime
    where shared evidence has expected value.
    """
    try:
        if float(residual_max) >= float(threshold):
            return "share"
        return "solo"
    except Exception:
        return "solo"


# ---------------------------------------------------------------------------
# 3. W-ISA invariant: transactional crystallize — commit or roll back
# ---------------------------------------------------------------------------

def transactional_crystallize(
    fn: Callable[[], T],
    verify: Callable[[T], bool],
) -> Optional[T]:
    """Run fn, verify the result, return it only if verification passes.

    W-ISA's transactional semantics for rank-one weight edits, translated
    to the prototype store: an edit that fails its shape check is not
    committed. No partial writes, no corrupted keys.
    """
    try:
        result = fn()
        if verify(result):
            return result
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 4. Weight-space invariant: store only the sparse delta
# ---------------------------------------------------------------------------

def sparse_delta(
    fingerprint: str,
    category: str,
    source: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Minimal payload: key, fingerprint, category, source, timestamp.

    Weight-space programming stores rank-one deltas, not full matrices.
    The crystallized record stores the delta (fingerprint + category),
    never the full treatment payload. Smaller, cheaper, less to corrupt.
    """
    from datetime import datetime, timezone
    rec = {
        "key": f"{source}:{fingerprint}",
        "fingerprint": str(fingerprint),
        "category": str(category),
        "source": str(source),
        "lineage": str(source),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        # Only allow a bounded set of extra keys
        for k in list(extra.keys())[:5]:
            rec[str(k)] = extra[k]
    return rec


# ---------------------------------------------------------------------------
# 5. SciMARS invariant: component-scoped mutation
# ---------------------------------------------------------------------------

_ROLE_SCOPE: Dict[str, tuple[str, ...]] = {
    "improver": ("set_knob", "add_family_rotation", "reorder_desk"),
    "pathfinder": ("add_skip_rule", "add_park_rule"),
    "stem_checker": ("add_triviality_candidate",),
    "surveyor": ("set_knob", "mark_ceiling"),
    "archivist": tuple(),  # read-only
    "legislator": tuple(),  # votes only
}


def component_scope(role: str, op: str) -> bool:
    """True if this role is permitted to propose this op.

    SciMARS separates the shared evidence graph from per-component editors.
    Each role mutates only its scoped operation surface. Cross-scope
    proposals are rejected before scoring.
    """
    try:
        allowed = _ROLE_SCOPE.get(str(role), tuple())
        return str(op) in allowed
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 6. SwarmEvolve invariant: latent evaluation (Bitwork already does this)
# ---------------------------------------------------------------------------

def latent_eval_invariant() -> str:
    """SwarmEvolve evaluates candidates in latent space without decoding.

    Bitwork's sparse binary overlap IS latent evaluation: no text is
    decoded, no model is called, scoring is integer AND/POPCOUNT.
    This function exists to name the invariant, not to add code.
    """
    return "bitwork_is_latent_evaluation"


# ---------------------------------------------------------------------------
# 7. Homeostasis: keep total prior mass bounded
# ---------------------------------------------------------------------------

def homeostatic_scale(score: int, recent_mean: float = 0.0, target: float = 0.0) -> int:
    """Pull score toward a target when recent mean drifts.

    Synaptic scaling: activity above target reduces gain; below raises it.
    Fail-open returns the original score.
    """
    try:
        drift = float(recent_mean) - float(target)
        if drift > 50:
            return int(score * 0.9)
        if drift < -50:
            return int(score * 1.1)
        return int(score)
    except Exception:
        return int(score)


# ---------------------------------------------------------------------------
# 8. Refractory: do not re-select the same fingerprint immediately
# ---------------------------------------------------------------------------

def refractory(fingerprint: str, last_fp: str = "") -> bool:
    """True if this fingerprint is allowed (not in refractory).

    Biological refractory period prevents immediate re-firing.
    Empty last_fp always allows.
    """
    try:
        if not last_fp:
            return True
        return str(fingerprint) != str(last_fp)
    except Exception:
        return True


# ---------------------------------------------------------------------------
# 9. Lateral inhibition / WTA: keep only the strongest of a small set
# ---------------------------------------------------------------------------

def winner_take_all(candidates: List[Mapping[str, Any]], k: int = 1) -> List[Mapping[str, Any]]:
    """Return the top-k by score. Others are inhibited.

    Lateral inhibition: the strongest suppresses the rest.
    Fail-open returns the original list.
    """
    try:
        if not candidates:
            return []
        ranked = sorted(candidates, key=lambda c: int(c.get("score", 0)), reverse=True)
        return ranked[: max(1, k)]
    except Exception:
        return list(candidates)


# ---------------------------------------------------------------------------
# 10. Pruning: drop weak prototypes under a mass cap
# ---------------------------------------------------------------------------

def prune_weak(records: List[Mapping[str, Any]], max_keep: int = 64) -> List[Mapping[str, Any]]:
    """Activity-dependent synaptic pruning.

    Biology: unused synapses die, used ones stay, under a fixed budget.
    Math: rank by use count (how often the fingerprint appears in the
    exchange). Keep the top max_keep. Ties broken by recency.
    Fail-open returns the original list.

        rank(r) = count(exchange.fingerprint == r.fingerprint)
        keep = top_max_keep(rank, then ts)
    """
    try:
        if len(records) <= max_keep:
            return list(records)
        from collections import Counter
        import json
        from pathlib import Path as P
        counts: Counter = Counter()
        ex = P(__file__).resolve().parent.parent.parent / "data" / "commons" / "exchange.jsonl"
        if ex.exists():
            for line in ex.read_text(encoding="utf-8").splitlines()[-400:]:
                try:
                    rec = json.loads(line)
                    if rec.get("fingerprint"):
                        counts[str(rec["fingerprint"])] += 1
                except Exception:
                    continue
        ranked = sorted(
            records,
            key=lambda r: (counts.get(str(r.get("fingerprint", "")), 0), str(r.get("ts", ""))),
            reverse=True,
        )
        return list(ranked[:max_keep])
    except Exception:
        return list(records)



# ---------------------------------------------------------------------------
# 11. CRAM invariant: stop when energy stops dropping
# ---------------------------------------------------------------------------

def energy_settled(scores: list, eps: int = 0) -> bool:
    """True if the last two scores did not decrease.

    Classical energy descent (Hopfield/CRAM): once E stops falling,
    the system has settled. Early stop is free. Fail-open returns False.
    """
    try:
        if not scores or len(scores) < 2:
            return False
        return int(scores[-1]) >= int(scores[-2]) - int(eps)
    except Exception:
        return False


def precision_weight(observation_count: int, floor: float = 0.25, cap: float = 1.0) -> float:
    """Active-inference precision: more observations, more trust.

    Precision scales a prior. It does not create one.
    Fail-open returns 1.0.
    """
    try:
        n = max(0, int(observation_count))
        return min(cap, floor + (1.0 - floor) * min(n, 8) / 8.0)
    except Exception:
        return 1.0


def eligible(fingerprint: str, recent: list, window: int = 12) -> bool:
    """Three-factor eligibility: only a recently touched fingerprint can be modified.

    Acetylcholine-style gate. No recent touch, no prior.
    Fail-open returns True.
    """
    try:
        if not fingerprint or not recent:
            return True
        tail = [str(x) for x in recent[-window:]]
        return fingerprint in tail or any(fingerprint.split(":")[0] in str(x) for x in tail)
    except Exception:
        return True


def tag_and_capture(fingerprint: str, kept_fingerprints: list) -> int:
    """Synaptic tagging and capture.

    A weak tag (this proposal) captures a protein (a kept record on the same knob).
    Returns a capped bonus. Not a keep. Fail-open returns 0.
    """
    try:
        if not fingerprint or not kept_fingerprints:
            return 0
        knob = str(fingerprint).split(":")[0]
        for fp in kept_fingerprints:
            if str(fp) == fingerprint or str(fp).startswith(knob + ":"):
                return 30
        return 0
    except Exception:
        return 0
