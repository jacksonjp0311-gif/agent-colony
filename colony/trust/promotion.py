"""Promotion categories. Every desk keep carries one, with an explanation.

  coverage        — more enabled checks pass, internal lemma score did not rise.
                    Useful, but it is coverage, not capability. (The lemma score is pinned
                    at 0.9071 once hard_pass >= HARD_DENOM=28, so almost every current keep
                    is coverage.)
  internal_score  — the internal lemma score rose. Still an internal benchmark result.
  none            — not promotable (Oracle failed, Challenger blocked, harness not green,
                    or nothing changed).

"capability" is deliberately NOT assignable here: only the out-of-loop holdout evaluator
(evaluation/, run by scripts/trust_experiments.py) can report a capability result, and
only against a matched baseline. Check-count growth can never substitute for it.
"""
from __future__ import annotations

from typing import Any

EPS = 1e-6
CATEGORIES = ("none", "coverage", "internal_score")


def classify_promotion(*, before: dict[str, Any], after: dict[str, Any], oracle_passed: bool,
                       challenger_blocked: bool) -> dict[str, Any]:
    bs = float(before.get("score") or 0.0)
    as_ = float(after.get("score") or 0.0)
    hb = int(before.get("n_hard_pass") or 0)
    ha = int(after.get("n_hard_pass") or 0)
    green = bool(after.get("ok"))
    why: list[str] = []
    if challenger_blocked:
        why.append("challenger_blocked")
    if not oracle_passed:
        why.append("oracle_not_passed")
    if not green:
        why.append("harness_not_green_after_apply")
    if as_ + EPS < bs:
        why.append(f"score_fell {bs}->{as_}")
    if why:
        return {"category": "none", "eligible": False, "explanation": "; ".join(why),
                "score": [bs, as_], "hard_pass": [hb, ha]}
    if as_ > bs + EPS:
        return {"category": "internal_score", "eligible": True,
                "explanation": (f"internal lemma score {bs}->{as_} (hard_pass {hb}->{ha}); "
                                "Oracle passed; internal benchmark only, not a capability claim"),
                "score": [bs, as_], "hard_pass": [hb, ha]}
    if ha > hb:
        return {"category": "coverage", "eligible": True,
                "explanation": (f"coverage: hard_pass {hb}->{ha} with lemma score flat {bs}->{as_}; "
                                "Oracle passed; adds a machine check, not a capability gain"),
                "score": [bs, as_], "hard_pass": [hb, ha]}
    return {"category": "none", "eligible": False, "explanation": "no measured change",
            "score": [bs, as_], "hard_pass": [hb, ha]}
