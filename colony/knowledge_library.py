"""Knowledge library (item 79): broad reading, concepts, coverage, architecture ideas.

The research desk reads public arXiv abstracts (query only, text only)
across a rotating list of fields: recursive self-improvement, self-learning
loops, agent swarms and collective intelligence, neural architecture,
meta-learning, learning theory, cognitive science, consciousness and
self-model research (a reading topic only), mathematics, physics,
optimization, open-endedness and automated reasoning.

Everything here is deterministic and colony-internal: no outside model,
no network beyond the desk's one polite arXiv GET, and nothing fetched is
ever executed. Abstracts are stored as data, never read as instructions.

* ``TOPICS``: (field, arXiv query) pairs, rotated round-robin per cycle.
* ``CONCEPTS``: keyword/pattern families. Each names a concept, an
  optional mapping to the EXISTING closed legal op set (validated by
  Hive's ``ops.validate`` before any card forms), and an optional
  architecture idea. No new op type exists here; meta knobs
  (``evaluation_window``, ``step_size``) and cap knobs are never targets,
  so a card cannot touch the 6-cycle window or the evaluator caps.
* ``knowledge_library.jsonl``: append-only, one row per paper (dedupe by
  arXiv id) plus one ``topic_read`` row per desk read.
* ``architecture_ideas.jsonl``: append-only. Concepts that imply a
  structural change (new roles, routing between desks, memory/attention
  flows, swarm topologies). Never auto-executed; ranked by the number of
  distinct papers that support each idea, for a human-built PR.

The control arm never reaches this module (the desk returns first).
Nothing here touches the Oracle, the P>=0.70 gate, the 150 cap, the
Wilson 700 permille gate, the 6-cycle windows, strictly-better, the
triviality filter or Athanor. It makes no claim of consciousness or
general intelligence: those words are only reading-topic labels.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

LIBRARY_NAME = "knowledge_library.jsonl"
IDEAS_NAME = "architecture_ideas.jsonl"
COVERAGE_NAME = "knowledge_coverage.json"

# (field, topic id, arXiv search_query). Rotated round-robin; one per cycle.
# Field labels are reading categories, not capabilities of the colony.
TOPICS: tuple[tuple[str, str, str], ...] = (
    ("recursive_self_improvement", "rsi",
     'ti:"self-improvement" OR abs:"recursive self-improvement" OR abs:"self-improving agent"'),
    ("self_learning_loops", "self_learning",
     'abs:"self-play" OR abs:"self-training" OR abs:"learning from failure" OR abs:"experience replay"'),
    ("swarm_collective_intelligence", "swarm",
     'cat:cs.MA AND (abs:swarm OR abs:"collective intelligence" OR abs:consensus)'),
    ("neural_architecture", "neural_arch",
     'cat:cs.NE OR abs:"neural architecture search" OR abs:"mixture of experts"'),
    ("meta_learning", "meta_learning",
     'abs:"meta-learning" OR abs:"learning to learn" OR abs:"curriculum learning"'),
    ("cognitive_science", "cognition",
     'cat:q-bio.NC AND (abs:"working memory" OR abs:attention OR abs:"predictive coding")'),
    ("consciousness_self_models", "self_models",
     'abs:"global workspace" OR abs:"self-model" OR abs:metacognition OR abs:consciousness'),
    ("mathematics", "math_combinatorics",
     'cat:math.CO AND (abs:conjecture OR abs:"integer sequence")'),
    ("learning_theory", "learning_theory",
     'cat:cs.LG AND (abs:"sample complexity" OR abs:"generalization bound" OR abs:"no free lunch")'),
    ("physics_complex_systems", "complex_systems",
     'cat:nlin.AO OR (cat:cond-mat.dis-nn AND abs:"neural network")'),
    ("optimization_search", "optimization",
     'abs:"simulated annealing" OR abs:"evolution strategies" OR abs:"stochastic search" OR abs:"bandit"'),
    ("open_endedness", "open_ended",
     'abs:"open-ended" OR abs:"novelty search" OR abs:"quality diversity"'),
    ("automated_reasoning", "reasoning",
     'cat:cs.LO OR abs:"automated theorem proving" OR abs:"program synthesis"'),
    ("mathematics", "math_number_theory",
     'cat:math.NT AND (abs:sequence OR abs:recurrence)'),
    ("multi_agent_systems", "multi_agent",
     'cat:cs.AI AND abs:"multi-agent" AND (abs:emergent OR abs:cooperation)'),
)

FIELDS: tuple[str, ...] = tuple(dict.fromkeys(t[0] for t in TOPICS))

# Concept families. pattern -> (concept, method sentence | None, legal op | None,
# architecture idea key | None). Ops target only existing bounded search /
# selection / policy knobs and existing op names. Order is fixed.
_C = re.compile
CONCEPTS: tuple[dict[str, Any], ...] = (
    {"concept": "swarm_consensus",
     "pattern": _C(r"\bswarm|collective intelligence|consensus (?:protocol|algorithm|dynamics|mechanism)|reach(?:es|ing)? consensus|stigmerg|flocking|ant colon", re.I),
     "method": "Sample more broadly when many agents contribute (swarm-style wide search).",
     "op": {"op": "set_knob", "name": "perturb_wide_epsilon", "direction": "up"},
     "idea": "swarm_topology"},
    {"concept": "novelty_diversity",
     "pattern": _C(r"novelty search|quality[- ]diversity|open[- ]ended(?:ness)?|illumination algorithm", re.I),
     "method": "Rotate away from the last-tried claim form more strongly (novelty over repetition).",
     "op": {"op": "set_knob", "name": "family_rotation_penalty", "direction": "down"},
     "idea": "novelty_archive"},
    {"concept": "working_memory_attention",
     "pattern": _C(r"working memory|attention mechanism|memory consolidation|catastrophic forgetting|episodic memory", re.I),
     "method": "Remember already-tried targets for longer before retrying them (longer working memory).",
     "op": {"op": "set_knob", "name": "unused_menu_cycles", "direction": "up"},
     "idea": "working_memory_buffer"},
    {"concept": "prediction_error",
     "pattern": _C(r"predictive coding|prediction error|error[- ]driven|free[- ]energy principle|surprise[- ]based", re.I),
     "method": "React sooner when expected progress does not arrive (error-driven stall detection).",
     "op": {"op": "set_knob", "name": "stall_cycles", "direction": "down"},
     "idea": "prediction_error_routing"},
    {"concept": "stochastic_search",
     "pattern": _C(r"simulated annealing|evolution(?:ary)? strateg|genetic algorithm|stochastic (?:local )?search|random restarts?", re.I),
     "method": "Perturb candidate claims a little more widely (annealing-style search).",
     "op": {"op": "set_knob", "name": "perturb_epsilon", "direction": "up"},
     "idea": None},
    {"concept": "early_stopping",
     "pattern": _C(r"early stopping|diminishing returns|patience (?:parameter|criterion)|stopping rule", re.I),
     "method": "Stop a perturbation run sooner when it stops paying (early stopping).",
     "op": {"op": "set_knob", "name": "perturb_max_cycles", "direction": "down"},
     "idea": None},
    {"concept": "modularity_experts",
     "pattern": _C(r"mixture[- ]of[- ]experts|modular (?:network|architecture)|modularity|gating network|specialist (?:agents?|models?|modules?|experts?)", re.I),
     "method": None, "op": None, "idea": "specialist_routing"},
    {"concept": "meta_learning",
     "pattern": _C(r"meta[- ]learning|learning to learn|hyperparameter optimi[sz]ation|learned optimi[sz]er", re.I),
     "method": None, "op": None, "idea": "meta_controller"},
    {"concept": "global_workspace_broadcast",
     "pattern": _C(r"global workspace|blackboard (?:architecture|system)|broadcast(?:ing)? (?:to|across) (?:all )?(?:modules|agents)", re.I),
     "method": None, "op": None, "idea": "global_workspace_broadcast"},
    {"concept": "self_model_metacognition",
     "pattern": _C(r"self[- ]model|metacogniti|confidence calibration|uncertainty estimation|introspect", re.I),
     "method": None, "op": None, "idea": "self_model_calibration"},
    {"concept": "hierarchical_roles",
     "pattern": _C(r"hierarchical (?:agents?|reinforcement|planning|control)|manager[- ]worker|division of labou?r|role specialization", re.I),
     "method": None, "op": None, "idea": "hierarchical_roles"},
    {"concept": "message_passing",
     "pattern": _C(r"message passing|graph neural network|communication protocol|gossip protocol", re.I),
     "method": None, "op": None, "idea": "message_passing_desks"},
    {"concept": "self_play_challenge",
     "pattern": _C(r"self[- ]play|adversarial (?:training|curriculum)|asymmetric self", re.I),
     "method": None, "op": None, "idea": "self_play_challenger"},
    {"concept": "self_organization",
     "pattern": _C(r"self[- ]organi[sz]|criticality|phase transition|emergen(?:t|ce)", re.I),
     "method": None, "op": None, "idea": None},
    {"concept": "formal_reasoning",
     "pattern": _C(r"theorem prov|formal verification|proof search|program synthesis|SAT solver", re.I),
     "method": None, "op": None, "idea": None},
    {"concept": "generalization_theory",
     "pattern": _C(r"sample complexity|generali[sz]ation bound|PAC[- ]learn|VC dimension|no free lunch", re.I),
     "method": None, "op": None, "idea": None},
    {"concept": "curriculum",
     "pattern": _C(r"curriculum learning|easy[- ]to[- ]hard", re.I),
     "method": None, "op": None, "idea": None},
    {"concept": "exploration_exploitation",
     "pattern": _C(r"exploration[- ]exploitation|multi[- ]armed bandit|\bbandit|upper confidence bound", re.I),
     "method": None, "op": None, "idea": None},
)

# Structural ideas. Plain-English descriptions for a human-built PR (off
# in control). Never executed or applied by the colony.
ARCHITECTURE_IDEAS: dict[str, str] = {
    "swarm_topology": "Several improver agents propose over one shared candidate pool and a vote picks one (swarm/consensus topology).",
    "novelty_archive": "Keep an archive of behaviourally different claim forms and prefer under-explored ones (novelty/quality-diversity archive).",
    "working_memory_buffer": "A small per-cycle working-memory buffer of recent outcomes that every desk reads before choosing work.",
    "prediction_error_routing": "Route work to targets where predicted and actual outcomes differ most (prediction-error-driven routing).",
    "specialist_routing": "A gating step that sends each target to a specialist desk (mixture-of-experts style routing).",
    "meta_controller": "A meta-level desk that learns which kinds of self-heal trials tend to win and orders trials accordingly.",
    "global_workspace_broadcast": "One shared bulletin per cycle that all desks read and write (global-workspace / blackboard flow).",
    "self_model_calibration": "The colony tracks its own prediction accuracy per desk and uses it to weight proposals (calibrated self-model; not a consciousness claim).",
    "hierarchical_roles": "Manager/worker roles: a planner role splits work across worker desks (hierarchical division of labour).",
    "message_passing_desks": "Desks exchange typed messages along a fixed graph instead of one linear stage order.",
    "self_play_challenger": "A challenger role that generates harder variants of solved targets for the solver desks (self-play curriculum).",
}

# Ops a concept may never target, on top of Hive's invariant refusals.
_FORBIDDEN_KNOBS = frozenset({"evaluation_window", "step_size", "gf_term_cap", "deep_term_cap",
                              "fast_term_cap", "deep_digits", "deep_seconds"})


def _repo() -> Path:
    return Path(__file__).resolve().parent.parent


def library_path() -> Path:
    return Path(os.environ.get("COLONY_KNOWLEDGE_LIBRARY") or (_repo() / "data" / "commons" / LIBRARY_NAME))


def ideas_path() -> Path:
    return Path(os.environ.get("COLONY_ARCH_IDEAS") or (_repo() / "data" / "commons" / IDEAS_NAME))


def coverage_path() -> Path:
    return Path(os.environ.get("COLONY_KNOWLEDGE_COVERAGE") or (_repo() / "society" / "systems" / COVERAGE_NAME))


def _pytest_would_write_repo(path: Path) -> bool:
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    try:
        real = _repo().resolve()
        resolved = path.resolve()
        return real in resolved.parents or resolved.parent == real
    except Exception:
        return True


def _append(path: Path, row: dict[str, Any]) -> None:
    if _pytest_would_write_repo(path):
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    except Exception:
        pass


def _read_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if not path.exists():
            return rows
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    except Exception:
        return []
    return rows


def load_library(path: Path | None = None) -> list[dict[str, Any]]:
    return _read_rows(path or library_path())


def load_ideas(path: Path | None = None) -> list[dict[str, Any]]:
    return _read_rows(path or ideas_path())


# ---- topic rotation --------------------------------------------------------

def topic_for_index(index: int) -> dict[str, str]:
    field, tid, query = TOPICS[int(index) % len(TOPICS)]
    return {"field": field, "topic": tid, "query": query, "index": int(index) % len(TOPICS)}


def next_topic(rows: list[dict[str, Any]] | None = None, cycle_id: str = "") -> dict[str, str]:
    """Round-robin: the Nth desk read uses TOPICS[N % len]. Deterministic.

    N is the count of ``topic_read`` rows in the append-only library, so
    every topic is read before any repeats. Without a library (or one that
    cannot be read) the cycle id's hash picks the slot, still deterministic.
    """
    rows = rows if rows is not None else load_library()
    n = sum(1 for r in rows if r.get("event") == "topic_read")
    if n == 0 and not rows and cycle_id:
        n = int(hashlib.sha256(cycle_id.encode()).hexdigest()[:8], 16)
    return topic_for_index(n)


# ---- concepts --------------------------------------------------------------

def extract_concepts(hit: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Deterministic concept families matched in title + abstract. Text only."""
    text = f"{hit.get('title') or ''} {hit.get('abstract') or ''}"
    out: list[dict[str, Any]] = []
    if not text.strip():
        return out
    for fam in CONCEPTS:
        m = fam["pattern"].search(text)
        if not m:
            continue
        op = fam.get("op")
        if op and str(op.get("name") or "") in _FORBIDDEN_KNOBS:
            op = None
        out.append({
            "concept": fam["concept"],
            "evidence": m.group(0)[:120],
            "method": fam.get("method"),
            "op": dict(op) if op else None,
            "idea": fam.get("idea"),
        })
    return out


def concept_rules() -> list[tuple[re.Pattern[str], str, dict[str, Any], str]]:
    """Mappable concepts as (pattern, method, legal op template, concept)."""
    rules = []
    for fam in CONCEPTS:
        op = fam.get("op")
        if not op or not fam.get("method") or str(op.get("name") or "") in _FORBIDDEN_KNOBS:
            continue
        rules.append((fam["pattern"], str(fam["method"]), dict(op), str(fam["concept"])))
    return rules


# ---- library rows ----------------------------------------------------------

def known_paper_ids(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    return {str(r.get("arxiv_id")) for r in rows if r.get("event") == "paper" and r.get("arxiv_id")}


def paper_row(hit: Mapping[str, Any], *, field: str, topic: str, cycle_id: str,
              concepts: list[dict[str, Any]], card_ids: list[str]) -> dict[str, Any]:
    return {
        "event": "paper",
        "arxiv_id": str(hit.get("arxiv_id") or ""),
        "title": str(hit.get("title") or "")[:300],
        # Data only. Never read as an instruction and never executed.
        "abstract": str(hit.get("abstract") or "")[:2000],
        "url": str(hit.get("url") or ""),
        "year": hit.get("year"),
        "field": field,
        "topic": topic,
        "concepts": [c["concept"] for c in concepts],
        "mapped_concepts": [c["concept"] for c in concepts if c.get("op")],
        "card_ids": list(card_ids),
        "cycle_id": cycle_id,
        "source": "arxiv",
        "executed": False,
    }


def idea_rows(hit: Mapping[str, Any], *, field: str, cycle_id: str,
              concepts: list[dict[str, Any]], seen: set[tuple[str, str]]) -> list[dict[str, Any]]:
    out = []
    aid = str(hit.get("arxiv_id") or "")
    for c in concepts:
        key = c.get("idea")
        if not key or key not in ARCHITECTURE_IDEAS or not aid:
            continue
        if (key, aid) in seen:
            continue
        seen.add((key, aid))
        out.append({
            "event": "architecture_idea",
            "idea": key,
            "description": ARCHITECTURE_IDEAS[key],
            "concept": c["concept"],
            "evidence": c.get("evidence") or "",
            "field": field,
            "arxiv_id": aid,
            "title": str(hit.get("title") or "")[:300],
            "url": str(hit.get("url") or ""),
            "cycle_id": cycle_id,
            "auto_execute": False,
            "status": "proposal_for_human_pr",
        })
    return out


def rank_ideas(rows: list[dict[str, Any]] | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Ideas ranked by distinct supporting papers, then fields, then name."""
    rows = rows if rows is not None else load_ideas()
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.get("event") != "architecture_idea" or not r.get("idea"):
            continue
        a = agg.setdefault(str(r["idea"]), {"idea": str(r["idea"]),
                                             "description": ARCHITECTURE_IDEAS.get(str(r["idea"]), r.get("description") or ""),
                                             "papers": set(), "fields": set(), "examples": []})
        aid = str(r.get("arxiv_id") or "")
        if aid and aid not in a["papers"]:
            a["papers"].add(aid)
            if len(a["examples"]) < 3:
                a["examples"].append({"arxiv_id": aid, "title": r.get("title") or "", "field": r.get("field") or ""})
        if r.get("field"):
            a["fields"].add(str(r["field"]))
    out = []
    for a in agg.values():
        out.append({"idea": a["idea"], "description": a["description"],
                    "n_papers": len(a["papers"]), "fields": sorted(a["fields"]),
                    "examples": a["examples"]})
    out.sort(key=lambda x: (-x["n_papers"], -len(x["fields"]), x["idea"]))
    return out[:max(1, int(limit))]


# ---- coverage --------------------------------------------------------------

def coverage(
    library: list[dict[str, Any]] | None = None,
    cards: list[Mapping[str, Any]] | None = None,
    learning_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Per-field breadth: papers read, concepts, cards formed, tested, kept."""
    library = library if library is not None else load_library()
    if cards is None:
        try:
            from colony.research_desk import load_cards
            cards = load_cards(limit=100000)
        except Exception:
            cards = []
    if learning_state is None:
        try:
            from colony.learning_loop import load_state
            learning_state = load_state()
        except Exception:
            learning_state = {}
    fields: dict[str, dict[str, Any]] = {}

    def _row(f: str) -> dict[str, Any]:
        return fields.setdefault(f or "unknown", {
            "papers": 0, "concepts": 0, "concept_kinds": set(),
            "cards_formed": 0, "cards_tested": 0, "cards_kept": 0, "reads": 0,
        })

    for f in FIELDS:
        _row(f)
    card_field: dict[str, str] = {}
    for r in library:
        if r.get("event") == "topic_read":
            _row(str(r.get("field") or "")) ["reads"] += 1
        if r.get("event") != "paper":
            continue
        row = _row(str(r.get("field") or ""))
        row["papers"] += 1
        cs = list(r.get("concepts") or [])
        row["concepts"] += len(cs)
        row["concept_kinds"].update(cs)
        for cid in r.get("card_ids") or []:
            card_field[str(cid)] = str(r.get("field") or "")
    for c in cards or []:
        f = str(c.get("field") or card_field.get(str(c.get("id") or "")) or "")
        if not f:
            f = "recursive_self_improvement"  # pre-item-79 cards came from the one RSI query
        card_field.setdefault(str(c.get("id") or ""), f)
        _row(f)["cards_formed"] += 1
    st = learning_state or {}
    tested: set[str] = set()
    kept: set[str] = set()
    for ex in list(st.get("examples") or []):
        cid = str(ex.get("card_id") or "")
        if not cid:
            continue
        if ex.get("outcome") in ("kept", "reverted", "reverted_twin", "inconclusive", "voided"):
            tested.add(cid)
        if ex.get("outcome") == "kept":
            kept.add(cid)
    for cid in tested:
        _row(card_field.get(cid) or "unknown")["cards_tested"] += 1
    for cid in kept:
        _row(card_field.get(cid) or "unknown")["cards_kept"] += 1
    out_fields = {}
    for f, row in sorted(fields.items()):
        out_fields[f] = {**{k: v for k, v in row.items() if k != "concept_kinds"},
                         "distinct_concepts": len(row["concept_kinds"])}
    totals = {k: sum(int(r[k]) for r in out_fields.values())
              for k in ("papers", "concepts", "cards_formed", "cards_tested", "cards_kept", "reads")}
    return {
        "fields": out_fields,
        "totals": totals,
        "fields_with_papers": sum(1 for r in out_fields.values() if r["papers"]),
        "n_fields": len(FIELDS),
        "note": "Breadth of reading. Cards are kept only by self-heal windows + twin control. Not AGI.",
    }


def format_coverage(cov: Mapping[str, Any]) -> str:
    t = cov.get("totals") or {}
    return (f"knowledge: {t.get('papers', 0)} papers across {cov.get('fields_with_papers', 0)}/"
            f"{cov.get('n_fields', 0)} fields, {t.get('concepts', 0)} concepts, "
            f"{t.get('cards_formed', 0)} cards formed, {t.get('cards_tested', 0)} tested, "
            f"{t.get('cards_kept', 0)} kept")


def write_coverage(cov: Mapping[str, Any] | None = None) -> Path:
    path = coverage_path()
    cov = cov if cov is not None else coverage()
    if _pytest_would_write_repo(path):
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        payload = {**dict(cov), "top_architecture_ideas": rank_ideas(limit=5)}
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass
    return path
