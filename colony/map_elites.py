"""Item 108: MAP-Elites archive for the desk's proposals (James 2026-11-16: "Evolve and expand the swarms").

After Mouret & Clune, "Illuminating search spaces by mapping elites" (arXiv:1504.04909),
reimplemented deterministically (no randomness, no fetched code). Cells are

    mutation kind  x  family / domain  x  proof status
    (hard_enable:catalog | hard_enable:authored | hard_enable:oeis_supply | stem_enable:catalog | ...)
    (binomial, lattice_paths, linear_recurrence, number_theory, ... circuits, optics, thermo, ...)
    (checked | held_out)

and an ELITE is a proposal that passed the novelty gate with no kill AND whose desk outcome was an
Oracle PASS keep (data/commons/novelty_gate.jsonl joined with desk_outcomes.jsonl). Trivial or
killed rows only count as attempts in their cell.

Use: an ORDER factor inside exploration_budget.pick_mutation_order (after item 99's family bias).
Candidates whose cell is empty or thin (< 3 attempts) are moved up (1 + 0.8 / (1 + attempts)); a
barren cell (>= 3 attempts, no elite) and easy pads are moved down (x0.8); a candidate whose
domain already holds an elite under a DIFFERENT mutation kind gets x1.15 (elites seed neighbouring
cells through the existing operators); a candidate in a cell that already has an elite and many
attempts is moved down (x0.8). Clamped to [0.5, 2.0]. Nothing is removed, no gate changes; the
Oracle, novelty gate, cooldowns and strictly-better rule decide exactly as before.

Switch ``COLONY_MAP_ELITES`` = shadow (default) | live | off; always off on the control arm.
shadow builds the archive and records what the factor WOULD reorder (society/systems/map_elites.json)
without changing the order: the replay (scripts/replay_item108_map_elites.py) projects a LOWER
novelty-gate hit rate for the reordered picks (thin cells have been low-yield so far), so the order
is not changed by default. live applies it.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
GATE_LOG = ROOT / "data" / "commons" / "novelty_gate.jsonl"
DESK_LOG = ROOT / "data" / "commons" / "desk_outcomes.jsonl"
SNAPSHOT = ROOT / "society" / "systems" / "map_elites.json"
DESK_KINDS = ("hard_enable", "stem_enable", "easy_pad", "stem_easy_pad", "hard_check")
LOOKBACK = 2000
THIN_BONUS = 0.8
NEIGHBOR_BONUS = 1.15
CROWDED = 0.8
CROWDED_AT = 4
BARREN_AT = 3
MIN_F, MAX_F = 0.5, 2.0

DOMAINS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("linear_recurrence", ("fibonacci", "fib", "lucas", "pell", "cassini", "tribonacci", "jacobsthal", "padovan")),
    ("lattice_paths", ("catalan", "motzkin", "narayana", "ballot", "dyck", "schroder", "delannoy", "riordan",
                       "trinomial", "fine")),
    ("binomial", ("binomial", "pascal", "vandermonde", "hockey", "central", "apery", "franel")),
    ("set_partitions_perms", ("stirling", "bell", "derangement", "subfactorial", "euler", "involution",
                              "permutation", "fubini")),
    ("number_theory", ("gcd", "totient", "sigma", "prime", "divisor", "mobius", "legendre_symbol")),
    ("sums_series", ("geometric", "sum_first", "power_sum", "harmonic", "telescop")),
    ("orthogonal_poly", ("hermite", "legendre", "chebyshev", "laguerre")),
    ("geometry", ("pythagorean", "triangle", "polygon", "area")),
    ("mechanics", ("suvat", "projectile", "centripetal", "energy", "collision", "kepler", "shm")),
    ("circuits", ("resistor", "wheatstone", "rc_", "kirchhoff", "capacitor")),
    ("thermo", ("isothermal", "adiabatic", "carnot", "ideal_gas")),
    ("optics", ("snell", "lens", "mirror", "refraction")),
    ("relativity", ("velocity_addition", "lorentz", "rapidity")),
)


def mode() -> str:
    """off on the control arm; otherwise COLONY_MAP_ELITES = shadow (default) | live | off."""
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return "off"
    except Exception:  # noqa: BLE001
        return "off"
    m = (os.environ.get("COLONY_MAP_ELITES") or "shadow").strip().lower()
    return m if m in ("shadow", "live", "off") else "shadow"


def enabled() -> bool:
    """True only in live mode: the order factor is applied."""
    return mode() == "live"


def domain(name: str) -> str:
    n = (name or "").lower()
    if n.startswith("easy_pad"):
        return "easy_pad"
    for dom, keys in DOMAINS:
        if any(k in n for k in keys):
            return dom
    return "other"


def operator(name: str) -> str:
    n = (name or "").lower()
    if n.startswith("authored_"):
        return "authored"
    if n.startswith("oeis_"):
        return "oeis_supply"
    if n.startswith("adversarial_"):
        return "adversarial"
    return "catalog"


def mutation_kind(kind: str, name: str) -> str:
    return "%s:%s" % (kind or "unknown", operator(name))


def proof_status(row: dict[str, Any] | None) -> str:
    ho = (row or {}).get("held_out") or {}
    if ho.get("survives") and str(ho.get("test") or "").startswith("stem_held_out") or \
            ho.get("survives") and ho.get("reason") == "stem_harder_instance_green":
        return "held_out"
    return "checked"


def cell_of(kind: str, name: str, status: str = "checked") -> tuple[str, str, str]:
    return (mutation_kind(kind, name), domain(name), status)


def _read(path: Path, lookback: int) -> list[dict[str, Any]]:
    out = []
    try:
        for ln in path.read_text(encoding="utf-8").splitlines()[-lookback:]:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return out


def _oracle_keeps(desk_rows: Iterable[dict[str, Any]]) -> set[tuple[str, str]]:
    keeps = set()
    for r in desk_rows:
        if r.get("decision") == "keep" and "oracle=PASS" in str(r.get("note") or ""):
            keeps.add((str(r.get("cycle_id") or ""), str(r.get("mutation") or "")))
    return keeps


def build(gate_rows: list[dict[str, Any]] | None = None, desk_rows: list[dict[str, Any]] | None = None
          ) -> dict[str, Any]:
    gate_rows = _read(GATE_LOG, LOOKBACK) if gate_rows is None else gate_rows
    desk_rows = _read(DESK_LOG, LOOKBACK) if desk_rows is None else desk_rows
    keeps = _oracle_keeps(desk_rows)
    cells: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(lambda: {"attempts": 0, "elite": None})
    for r in gate_rows:
        kind = str(r.get("kind") or "")
        if kind not in DESK_KINDS:
            continue
        name = str(r.get("mutation") or "")
        c = cells[cell_of(kind, name, proof_status(r))]
        c["attempts"] += 1
        c["hits"] = int(c.get("hits") or 0) + int(bool(r.get("novel_to_commons")))
        trivial = bool((r.get("stem_triviality") or {}).get("trivial"))
        if r.get("novel_to_commons") and not r.get("kills") and not trivial \
                and (str(r.get("cycle_id") or ""), name) in keeps and c["elite"] is None:
            c["elite"] = {"mutation": name, "ts": r.get("ts"), "cycle_id": r.get("cycle_id")}
    return {"cells": {"|".join(k): v for k, v in sorted(cells.items())}}


def _index(archive: dict[str, Any]):
    attempts: dict[tuple[str, str], int] = defaultdict(int)
    hits: dict[tuple[str, str], int] = defaultdict(int)
    elite_cells: set[tuple[str, str]] = set()
    elite_domains: dict[str, set[str]] = defaultdict(set)
    for key, v in (archive.get("cells") or {}).items():
        mk, dom, _st = key.split("|")
        attempts[(mk, dom)] += int(v.get("attempts") or 0)
        hits[(mk, dom)] += int(v.get("hits") or 0)
        if v.get("elite"):
            elite_cells.add((mk, dom))
            elite_domains[dom].add(mk)
    tot_a = sum(attempts.values())
    tot_h = sum(hits.values())
    glob = (tot_h + 1) / (tot_a + 2)
    rate = {c: ((hits[c] + 2 * glob) / (attempts[c] + 2)) / glob for c in attempts}
    return attempts, elite_cells, elite_domains, rate


def factor(kind: str, name: str, archive: dict[str, Any], _idx=None) -> float:
    attempts, elite_cells, elite_domains, rate = _idx or _index(archive)
    mk, dom = mutation_kind(kind, name), domain(name)
    n = attempts.get((mk, dom), 0)
    if dom == "easy_pad":
        f = CROWDED                      # easy pads exist to be killed; never explored on purpose
    elif (mk, dom) in elite_cells:
        f = CROWDED if n >= CROWDED_AT else 1.0
    elif n >= BARREN_AT:
        f = CROWDED                      # tried often, never produced an elite: barren, not thin
    else:
        # thin bonus, scaled by the cell's own (Laplace) hit rate relative to the global rate,
        # so a thin cell whose few tries were all killed is not pushed (illuminate, don't spam)
        f = 1.0 + THIN_BONUS / (1.0 + n) * min(1.0, rate.get((mk, dom), 1.0))
        if elite_domains.get(dom) and mk not in elite_domains[dom]:
            f *= NEIGHBOR_BONUS
    return max(MIN_F, min(MAX_F, f))


def factors(candidates: list[tuple[str, str, str]], archive: dict[str, Any] | None = None) -> dict[str, float]:
    archive = build() if archive is None else archive
    idx = _index(archive)
    return {n: factor(k, n, archive, idx) for n, k, _s in candidates}


def snapshot(archive: dict[str, Any] | None = None) -> dict[str, Any]:
    archive = build() if archive is None else archive
    cells = archive.get("cells") or {}
    out = {"n_cells": len(cells), "n_elites": sum(1 for v in cells.values() if v.get("elite")),
           "cells": cells,
           "note": "derived from append-only logs; elites = novelty-gate hits with an Oracle PASS keep"}
    return out


def write_snapshot(archive: dict[str, Any] | None = None) -> None:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snapshot(archive), indent=1, sort_keys=True) + "\n")


def shadow_record(candidates: list[tuple[str, str, str]], ordered: list[tuple[str, str, str]]) -> None:
    """Shadow: write the archive snapshot plus the top picks with and without the factor."""
    try:
        arch = build()
        f = factors(candidates, arch)
        base = [t[0] for t in ordered[:5]]
        alt = [t[0] for t in sorted(ordered, key=lambda t: -f.get(t[0], 1.0))[:5]]
        snap = snapshot(arch)
        snap["shadow"] = {"top_without": base, "top_with": alt, "would_change_first": base[:1] != alt[:1]}
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(snap, indent=1, sort_keys=True) + "\n")
    except Exception:  # noqa: BLE001
        pass
