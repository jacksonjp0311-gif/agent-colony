"""Hunt guidance — COLONY_HUNT=live|shadow|off. Steers ORDER and REWARD only.

live    the colony's own exploration prefers unknown-and-unexpected work and chains of proven
        blocks over sweeping already-proven families or bare textbook enables:
          * conjecture desk candidate order (exploration_budget.pick_mutation_order),
          * authoring candidate order (authoring.author_checks),
          * the keep reward in the exploration distribution (exploration_budget.record_outcome).
        Nothing is removed, killed or blocked; the Oracle, P, the 0.70 authorize bar, novelty
        kills and desk keep/revert decisions are untouched (the hunt shadow keeps reporting
        P_shadow beside P on the shortlist).
shadow  (code default) today's behaviour: hunt values are computed for the report only.
off     no hunt reporting or guidance at all.

Hunt value v(name) in [0, 1] of a candidate before it is tried (same rules as the shadow):
  * authored claim:   v = 1 - expected = K / (s + K), s = Oracle-passed members of its claim
                      family (colony.hunt_shadow.claim_family), K = hunt_shadow.K_PRIOR
                      (calibrated). A brand-new family / new chain of two blocks scores 1; one
                      more sweep of a family that already passed many times scores ~0.
  * textbook / catalog / classical-identity target (building block): v = min(1, n / 2), n =
                      distinct Oracle-passed authored claims that chain it. A bare enable earns 0.
Anti-freeze: strength = 1.0, halved while more than half of the last ANTI_FREEZE_WINDOW desk
results were idle (no keep/revert), quartered when all were. Strength blends the hunt order with
the old order (0 = old behaviour).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from colony import hunt_shadow as HS

ROOT = Path(__file__).resolve().parent.parent
ORACLE = ROOT / "data" / "commons" / "oracle.jsonl"
DESK_HISTORY = ROOT / "society" / "benchmarks" / "conjecture_history.jsonl"
MODES = ("live", "shadow", "off")
ANTI_FREEZE_WINDOW = 6
KEEP_REWARD_GAIN = 0.25  # old flat keep multiplier was 1.25 = 1 + 0.25
EPS = 0.05  # keeps the old order among equal hunt values


def mode() -> str:
    m = os.environ.get("COLONY_HUNT", "shadow").strip().lower()
    return m if m in MODES else "shadow"


def live() -> bool:
    return mode() == "live"


def _jsonl(path: Path, tail: int = 4000) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-tail:]
    except Exception:  # noqa: BLE001
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:  # noqa: BLE001
            pass
    return out


def strength(history: list[dict[str, Any]] | None = None) -> float:
    rows = history if history is not None else _jsonl(DESK_HISTORY, tail=ANTI_FREEZE_WINDOW)
    rows = rows[-ANTI_FREEZE_WINDOW:]
    if len(rows) < ANTI_FREEZE_WINDOW:
        return 1.0
    idle = sum(1 for r in rows if r.get("decision") not in ("keep", "revert"))
    if idle == len(rows):
        return 0.25
    if idle * 2 > len(rows):
        return 0.5
    return 1.0


class Valuer:
    """Hunt value of candidate names given Oracle history (pure given oracle_rows)."""

    def __init__(self, oracle_rows: list[dict[str, Any]] | None = None, k: float | None = None):
        rows = oracle_rows if oracle_rows is not None else _jsonl(ORACLE)
        self.k = float(k if k is not None else HS.K_PRIOR)
        passed = {o.get("mutation") for o in rows if o.get("passed") and o.get("mutation")}
        self.fam: dict[str, set[str]] = {}
        for t in passed:
            self.fam.setdefault(HS.claim_family(t), set()).add(t)
        self.chains = HS.chained_blocks(rows, [])

    def value(self, name: str) -> float:
        from colony.shortlist import building_block_kind
        name = str(name or "")
        if not name:
            return 0.0
        if building_block_kind(name):
            return min(1.0, len(self.chains.get(name, set())) / 2.0)
        s = len(self.fam.get(HS.claim_family(name), set()) - {name})
        base = self.k / (s + self.k)
        try:  # Stage 3 (COLONY_SURPRISE=live): frontier conjectures earn surprise credit, not passing
            from colony import surprise_credit
            if surprise_credit.live():
                return surprise_credit.value(name, base)
        except Exception:
            pass
        return base


def reorder(items: list[Any], name_of, *, valuer: Valuer | None = None, s: float | None = None) -> list[Any]:
    """Stable blend of old position and hunt value; s = 0 returns ``items`` unchanged."""
    if not items:
        return list(items)
    s = strength() if s is None else s
    if s <= 0:
        return list(items)
    v = valuer or Valuer()
    n = len(items)
    keyed = [(s * (1.0 - v.value(name_of(it))) + (1.0 - s) * (i / n), i, it) for i, it in enumerate(items)]
    keyed.sort(key=lambda t: (t[0], t[1]))
    return [it for _k, _i, it in keyed]


def weight_factor(name: str, *, valuer: Valuer | None = None, s: float | None = None) -> float:
    """Multiplier on an exploration weight: 1 at strength 0, EPS + v at full strength."""
    s = strength() if s is None else s
    v = (valuer or Valuer()).value(name)
    return (1.0 - s) + s * (EPS + v)


def keep_multiplier(name: str, *, valuer: Valuer | None = None, s: float | None = None) -> float:
    """Keep reward: old flat 1.25; live 1 + 0.25 * blend(v) — sweeps of proven families earn ~nothing."""
    s = strength() if s is None else s
    v = (valuer or Valuer()).value(name)
    return 1.0 + KEEP_REWARD_GAIN * ((1.0 - s) + s * v)
