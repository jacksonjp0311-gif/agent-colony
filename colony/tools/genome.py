"""Genome. The schedule the system runs.

Pattern: read the dials. Propose one field. Keep only if the score beats the prior.
Fail-open returns the last kept genome.
A genome is a receipt. It is not an order to another lineage.

Distinct from Avida: one field, measured, public, reversible.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
GENOME = ROOT / "data" / "commons" / "genome.json"
HISTORY = ROOT / "data" / "commons" / "genome_history.jsonl"

DEFAULT = {
    "lineage": "colony",
    "keep_bar": 0,
    "max_fields_per_cycle": 1,
    "tools": ["vote", "self_heal", "exchange"],
    "wilson_gate": 700,
    "generation": 0,
}


def load() -> dict:
    try:
        if GENOME.exists():
            return json.loads(GENOME.read_text(encoding="utf-8"))
    except Exception:
        pass
    return dict(DEFAULT)


def save(g: dict) -> None:
    try:
        GENOME.parent.mkdir(parents=True, exist_ok=True)
        GENOME.write_text(json.dumps(g, indent=2) + "\n", encoding="utf-8")
        with HISTORY.open("a", encoding="utf-8") as f:
            f.write(json.dumps(g) + "\n")
    except Exception:
        return


def propose(field: str, value, score: float, prior_score: float) -> dict:
    """One field. Kept only if score beats prior. Else the genome is unchanged."""
    g = load()
    if field not in g and field not in DEFAULT:
        return {"kept": False, "reason": "unknown_field"}
    if score <= prior_score:
        return {"kept": False, "reason": "not_better", "genome": g}
    g = dict(g)
    g[field] = value
    g["generation"] = int(g.get("generation") or 0) + 1
    g["last_change"] = {"field": field, "value": value, "score": score, "prior": prior_score}
    save(g)
    return {"kept": True, "genome": g}


def ensure() -> dict:
    g = load()
    if not GENOME.exists():
        save(g)
    return g


def grow(name: str, score: float, prior_score: float) -> dict:
    """Add one tool. Kept only if the score beats the prior."""
    g = load()
    tools = list(g.get("tools") or [])
    if name in tools:
        return {"kept": False, "reason": "already_present"}
    if score <= prior_score:
        return {"kept": False, "reason": "not_better"}
    tools.append(name)
    return propose("tools", tools, score, prior_score)


def prune(name: str, score: float, bar: float) -> dict:
    """Remove one tool if its score is at or below the bar."""
    g = load()
    tools = list(g.get("tools") or [])
    if name not in tools:
        return {"kept": False, "reason": "absent"}
    if score > bar:
        return {"kept": False, "reason": "still_above_bar"}
    tools = [t for t in tools if t != name]
    g = dict(g)
    g["tools"] = tools
    g["generation"] = int(g.get("generation") or 0) + 1
    g["last_change"] = {"field": "tools", "pruned": name, "score": score, "bar": bar}
    save(g)
    return {"kept": True, "pruned": name, "genome": g}
