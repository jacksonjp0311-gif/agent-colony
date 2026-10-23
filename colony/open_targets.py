"""Open targets in the generator menu (James-approved 2026-10-23). COLONY_OPEN_TARGETS = off | shadow | live.

The pool (society/frontier/open_targets.json, built by tools/build_open_targets.py from free OEIS
JSON searches, polite and cached) holds OEIS entries that carry a genuine open problem:
  conjecture_formula   a line of the entry's FORMULA section starts "Conjecture" (an unproved
                       formula / recurrence / g.f. for the sequence itself)
  conjecture_comment   a COMMENT line states a conjecture about the sequence
  no_formula           no FORMULA lines and no g.f. / closed form / recurrence in the comments
each with a b-file of >= 300 terms that agrees with the entry's DATA. The entries become ordinary
'ox' + A-number primitives (colony/obscure_pool.py loads them), so every filter, the reference and
known-results checks (which read the entry's own text, conjecture included), the Oracle, P, the
0.70 bar and the 150 cap apply unchanged.

Incentives only; the colony still picks its own claims:
  live    the generator samples open-target primitives with weight x OPEN_BONUS on top of UCB, and
          the surprise credit (colony/surprise_credit.py) of a claim that uses one is x OPEN_CREDIT
          (capped at 1). A claim about the entry is NOT a proof of the entry's conjecture: credit
          still needs the claim to survive the triviality and compositional checks.
  shadow  pool loaded for reporting only (not sampled, no credit change); off  not loaded.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
POOL = ROOT / "society" / "frontier" / "open_targets.json"
OPEN_BONUS = 2.0
OPEN_CREDIT = 2.0
NOTE = ("OEIS entries with an open problem (unproved conjecture or no known formula); CC BY-SA 4.0, "
        "https://oeis.org. Built by tools/build_open_targets.py; terms from b-files cross-checked against DATA.")


def mode() -> str:
    m = os.environ.get("COLONY_OPEN_TARGETS", "off").strip().lower()
    return m if m in ("off", "shadow", "live") else "off"


def live() -> bool:
    return mode() == "live"


def load() -> list[dict[str, Any]]:
    try:
        return json.loads(POOL.read_text(encoding="utf-8")).get("pool") or []
    except Exception:  # noqa: BLE001
        return []


def entries_for_menu() -> list[dict[str, Any]]:
    """Entries the obscure-pool loader adds as primitives.

    Always all of them, whatever the mode: an authored check that names an open-target primitive must
    still evaluate in a process without COLONY_OPEN_TARGETS (the post-evolve trust gate runs benches
    with no COLONY_* env; runs 39967609775, 39970713450, 39972077325 failed lemma_microbench on
    ValueError: oxa177115). Only sampling (frontier_conjectures.menu_prims) and credit depend on live()."""
    return load()


_ALL = load()
PRIMS = tuple("ox" + e["anum"].lower() for e in _ALL)
TARGET = {"ox" + e["anum"].lower(): e.get("target", "") for e in _ALL}


def prims_in(text: str) -> list[str]:
    return sorted({p for p in re.findall(r"ox(?:a|A)\d{6}", text or "") if p.lower() in TARGET})


def credit_weight(r: dict[str, Any]) -> float:
    if not live():
        return 1.0
    return OPEN_CREDIT if prims_in(f"{r.get('lhs') or ''} {r.get('rhs') or ''}") else 1.0
