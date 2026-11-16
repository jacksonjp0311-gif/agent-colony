"""Self-build pipeline (item 80): the colony composes, tries and keeps its own flows.

James, 2026-11-15 6:52 PM ET: "stop gating everything and let the system
start to self-build". The colony now changes the structure of its own
cycle without a human sign-off. What stays fixed is what makes a result
real: the Oracle, the P >= 0.70 claim gate, the 150 authored-check cap,
Athanor math, the frozen twin control, append-only logs and the full test
suite (the evolve workflow's pre-evolve trust gate runs it every run).

How it works, in plain words:

* **Building blocks.** ``COMPONENTS`` is a small library of flow pieces,
  each a bounded call into a desk API that already exists (nothing new is
  allowed to judge truth):

  - ``oeis_extra_pass``: one more OEIS conjecture pass with the colony's own
    choice (retry / curriculum flow).
  - ``oeis_beyond_bfile``: a pass that only searches past the published
    terms (self-play challenger: harder versions of held targets).
  - ``oeis_replay_buffer``: a working-memory buffer of recent outcomes,
    attention-weighted by how much depth each target recently gained.
  - ``oeis_consensus_vote``: four deterministic voters (memory, freshness,
    headroom, form credit) rank the open pool; Borda count with a quorum
    (swarm consensus).
  - ``oeis_form_router``: route a pass to the claim form with the best
    credit per attempt (specialist / mixture-of-experts style routing).
  - ``oeis_calibrated_vote``: weight each target by how often the colony's
    own depth prediction for its form came true (calibrated self-model; not
    a consciousness claim).
  - ``oeis_novelty_archive``: least-explored claim forms first (novelty /
    quality-diversity archive).
  - ``oeis_prediction_error``: targets whose last planned depth missed most
    (prediction-error routing).
  - ``frontier_extra_batch``: one more frontier-conjecture generator batch,
    only when an authored-check slot is free under the unchanged 150 cap.
  - ``new_data_extra_push``: a second new-data push past the OEIS frontier.

* **Blueprints.** A blueprint is data: an ordered list of steps
  (component + bounded size). The default blueprint is empty, which is
  exactly what the frozen control runs. A kept multi-step blueprint is
  registered as a *macro*, a self-built component later blueprints can use
  as one step, so the library grows from what worked.

* **Generator.** Deterministic, no outside model. From the active
  blueprint it makes candidates by adding, resizing, removing or swapping
  steps, by crossing over with earlier kept blueprints, and by using
  macros. Each component's weight is its own kept rate (Laplace) times the
  evidence for it, so the first blueprints are seeded from the top-ranked
  research-desk ideas: architecture ideas from the research desk
  (``data/commons/architecture_ideas.jsonl``, item 79; absent is fine),
  method cards and lessons whose text names the idea.

* **Fast self-test.** A candidate must validate (known components,
  bounds, no nested macros) and every step must plan at least one real
  action on the live state (a read-only dry run). Dead steps never spend
  a window.

* **Trial.** One candidate at a time, only while self-heal has no open
  trial (and self-heal waits while a blueprint trial is open), so neither
  is credited for the other. The window is 6 cycles plus the paired twin
  runs that cover it. The score is the treatment-minus-control *gain* over
  the window, (Oracle passes, then verified depth). Keep only if it is
  strictly better than the same quantity over the baseline window before
  the trial *and* strictly better than the twin (treatment gained more
  than control). Otherwise the colony reverts to the previous blueprint
  automatically. No paired data within 18 cycles is inconclusive and is
  reverted too. A trial never waits for signal in the baseline window: a
  flat baseline is (0, 0), so the twin comparison over the trial window
  decides.

* **Log.** ``data/commons/blueprint_log.jsonl`` is append-only. Every
  trial open and close is recorded with its parent blueprint, the
  operator that made it, its evidence and both scores (lineage).

Control is a no-op (``self_mod_enabled`` is false there). Blueprint
adoption needs no human authorize and authorizes nothing. Nothing here
touches the Oracle, the P >= 0.70 gate, the 150 cap, Hive's Wilson gate,
Athanor, or the self-heal 6-cycle windows. It claims no general
intelligence: a kept blueprint is one measured lead over a frozen copy.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "society" / "systems" / "self_build.json"
LOG_PATH = ROOT / "data" / "commons" / "blueprint_log.jsonl"
IDEAS_PATH = ROOT / "data" / "commons" / "architecture_ideas.jsonl"

WINDOW_CYCLES = 6           # same window length self-heal uses (not changed here)
INCONCLUSIVE_CYCLES = 18    # (pre item 84) no paired twin data by then: inconclusive, revert
# Item 84: a blueprint trial gets one window plus a short grace, then closes on the
# paired rows it has (still strictly better than baseline AND twin to keep) or is
# inconclusive (reverted). A code change inside the window voids it (no credit).
GRACE_CYCLES = 3
TRIAL_MAX_CYCLES = WINDOW_CYCLES + GRACE_CYCLES
MAX_STEPS = 4               # steps per blueprint after macro expansion
MAX_TOTAL_SIZE = 6          # sum of step sizes per blueprint
MAX_HEAVY = 1               # heavy components (whole generator batch) per blueprint
CYCLE_BUDGET_S = 90.0       # CPU seconds for all self-build flows in one cycle
MAX_MACROS = 12
DEFAULT_BLUEPRINT: dict[str, Any] = {"id": "bp_default", "steps": []}


# --------------------------------------------------------------------------- helpers

def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def self_mod_ok() -> bool:
    try:
        from colony.arm import self_mod_enabled
        return bool(self_mod_enabled())
    except Exception:
        return False


def _load_json(path: Path, default: Any) -> Any:
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _atomic_write(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def append_log(row: Mapping[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Append one row; never rewrites earlier rows."""
    p = Path(path or LOG_PATH)
    rec = {"ts": _utc(), **dict(row)}
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
    return rec


def load_log(path: Path | None = None) -> list[dict[str, Any]]:
    p = Path(path or LOG_PATH)
    out: list[dict[str, Any]] = []
    try:
        if not p.exists():
            return out
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return out


def empty_state() -> dict[str, Any]:
    return {
        "version": 1,
        "cycle_index": 0,
        "active": dict(DEFAULT_BLUEPRINT),
        "trial": None,
        "tried": {},           # signature -> outcome
        "component_stats": {},
        "macros": {},
        "last_run": None,
        "last_skip": None,
        "kept_count": 0,
        "reverted_count": 0,
        "inconclusive_count": 0,
    }


def load_state(path: Path | None = None) -> dict[str, Any]:
    st = _load_json(Path(path or STATE_PATH), None)
    base = empty_state()
    if isinstance(st, dict):
        base.update(st)
    return base


def save_state(st: Mapping[str, Any], path: Path | None = None) -> None:
    _atomic_write(Path(path or STATE_PATH), json.dumps(st, indent=1, sort_keys=False) + "\n")


# --------------------------------------------------------------------------- context

class Context:
    """Read/run surface the components use. Tests pass fakes for every call."""

    def __init__(self, cycle_id: str = "", *, oeis: Any = None, frontier: Any = None,
                 new_data: Any = None, authoring: Any = None, exclude_ids: Iterable[str] = ()):
        self.cycle_id = cycle_id or "self_build"
        self._oeis = oeis
        self._frontier = frontier
        self._new_data = new_data
        self._authoring = authoring
        self.exclude_ids = set(str(x) for x in exclude_ids)
        self.attempted: set[str] = set()
        self._pool: list[dict[str, Any]] | None = None
        self._state: dict[str, Any] | None = None

    # modules (lazy, so the control arm and tests never import heavy desks)
    @property
    def oeis(self) -> Any:
        if self._oeis is None:
            from colony import oeis_conjectures as _oc
            self._oeis = _oc
        return self._oeis

    @property
    def frontier(self) -> Any:
        if self._frontier is None:
            from colony import frontier_conjectures as _fc
            self._frontier = _fc
        return self._frontier

    @property
    def new_data(self) -> Any:
        if self._new_data is None:
            from colony import new_data as _nd
            self._new_data = _nd
        return self._new_data

    @property
    def authoring(self) -> Any:
        if self._authoring is None:
            from colony import authoring as _au
            self._authoring = _au
        return self._authoring

    def oeis_live(self) -> bool:
        try:
            return self.oeis.mode() == "live"
        except Exception:
            return False

    def oeis_state(self) -> dict[str, Any]:
        if self._state is None:
            try:
                self._state = self.oeis._load(self.oeis.STATE, {"targets": {}, "families": {}})
            except Exception:
                self._state = {"targets": {}, "families": {}}
        return self._state

    def oeis_pool(self, *, forms: set[str] | None = None, beyond_bfile: bool = False) -> list[dict[str, Any]]:
        """Open OEIS targets the colony's own chooser would still attempt now."""
        if forms is None and not beyond_bfile and self._pool is not None:
            pool = self._pool
        else:
            try:
                menu = self.oeis.load_menu() or []
                pool = list(self.oeis.choose(menu, self.oeis_state(), self.cycle_id, k=max(1, len(menu)),
                                             forms=forms, beyond_bfile=beyond_bfile) or [])
            except Exception:
                pool = []
            if forms is None and not beyond_bfile:
                self._pool = pool
        return [e for e in pool if str(e.get("id") or "") not in self.exclude_ids
                and str(e.get("id") or "") not in self.attempted]

    def attempt_log(self) -> list[dict[str, Any]]:
        try:
            return list((self.oeis.load_attempt_log() or {}).get("attempts") or [])
        except Exception:
            return []

    def free_authored_slots(self) -> int:
        try:
            return max(0, int(self.authoring.MAX_AUTHORED_TOTAL) - int(self.authoring.authored_count()))
        except Exception:
            return 0

    def new_data_open(self) -> int:
        nd = self.new_data
        try:
            if nd.mode() == "off":
                return 0
            idx = nd._load(nd.INDEX, {"entries": {}})
            return sum(1 for e in (idx.get("entries") or {}).values()
                       if isinstance(e, dict) and e.get("status") == "matched"
                       and not e.get("intractable") and not nd._done(e))
        except Exception:
            return 0

    def run_oeis(self, *, purpose: str, k: int | None = None, forms: set[str] | None = None,
                 beyond_bfile: bool = False, only_ids: list[str] | None = None) -> dict[str, Any]:
        rep = self.oeis.run_cycle(self.cycle_id, fetch=False, k=k, forms=forms, beyond_bfile=beyond_bfile,
                                  use_state_for_choice=True, purpose=f"self_build:{purpose}",
                                  only_ids=only_ids) or {}
        chosen = [str(c.get("id")) for c in (rep.get("chosen") or []) if c.get("id")]
        self.attempted.update(chosen)
        self._pool = None
        self._state = None
        return {"actions": len(chosen), "ids": chosen}


# --------------------------------------------------------------------------- voters / ranking

def _recent_gain(attempts: list[dict[str, Any]], horizon: int = 60, decay: float = 0.9) -> dict[str, float]:
    """Attention weight per target: decayed sum of recently verified extension."""
    out: dict[str, float] = {}
    rows = attempts[-horizon:]
    n = len(rows)
    for i, r in enumerate(rows):
        tid = str(r.get("id") or "")
        if not tid:
            continue
        try:
            ext = max(0, int(r.get("extended") or 0))
        except (TypeError, ValueError):
            ext = 0
        if r.get("beyond"):
            ext += 1
        out[tid] = out.get(tid, 0.0) + ext * (decay ** (n - 1 - i))
    return out


def _form(e: Mapping[str, Any]) -> str:
    return str((e.get("claim") or {}).get("form") or "")


def _rank(pool: list[dict[str, Any]], key: Callable[[dict[str, Any]], float]) -> list[str]:
    return [str(e["id"]) for e in sorted(pool, key=lambda e: (-key(e), str(e.get("id"))))]


def voters(ctx: Context, pool: list[dict[str, Any]]) -> dict[str, list[str]]:
    st = ctx.oeis_state()
    tg = st.get("targets") or {}
    fam = st.get("families") or {}
    gain = _recent_gain(ctx.attempt_log())

    def headroom(e: dict[str, Any]) -> float:
        prior = int((tg.get(e["id"]) or {}).get("tested_hi") or 0)
        try:
            planned = int(ctx.oeis.planned_depth(e, prior or None))
        except Exception:
            planned = prior
        return float(max(0, planned - prior))

    def form_credit(e: dict[str, Any]) -> float:
        f = fam.get(_form(e)) or {}
        return (float(f.get("credit") or 0.0) + 1.0) / (float(f.get("attempts") or 0) + 2.0)

    return {
        "memory": _rank(pool, lambda e: gain.get(e["id"], 0.0)),
        "fresh": _rank(pool, lambda e: 1.0 / (1 + int((tg.get(e["id"]) or {}).get("attempts") or 0))),
        "headroom": _rank(pool, headroom),
        "form_credit": _rank(pool, form_credit),
    }


def consensus(ballots: Mapping[str, list[str]], k: int, quorum: int) -> list[str]:
    """Borda count; a target needs ``quorum`` voters placing it in their top max(k, 3)."""
    top = max(int(k), 3)
    score: dict[str, int] = {}
    votes: dict[str, int] = {}
    for ranking in ballots.values():
        n = len(ranking)
        for pos, tid in enumerate(ranking):
            score[tid] = score.get(tid, 0) + (n - pos)
            if pos < top:
                votes[tid] = votes.get(tid, 0) + 1
    ok = [t for t in score if votes.get(t, 0) >= int(quorum)]
    ok.sort(key=lambda t: (-score[t], t))
    return ok[:max(0, int(k))]


# --------------------------------------------------------------------------- components

def _pick_replay(ctx: Context, n: int) -> list[str]:
    pool = ctx.oeis_pool()
    gain = _recent_gain(ctx.attempt_log())
    ranked = [e for e in pool if gain.get(str(e["id"]), 0.0) > 0]
    return _rank(ranked, lambda e: gain.get(str(e["id"]), 0.0))[:n]


def _pick_vote(ctx: Context, n: int, quorum: int = 2) -> list[str]:
    pool = ctx.oeis_pool()
    if not pool:
        return []
    return consensus(voters(ctx, pool), n, quorum)


def _route_form(ctx: Context) -> str | None:
    pool = ctx.oeis_pool()
    fam = ctx.oeis_state().get("families") or {}
    forms = sorted({_form(e) for e in pool if _form(e)})
    if not forms:
        return None

    def rate(f: str) -> float:
        r = fam.get(f) or {}
        return (float(r.get("credit") or 0.0) + 1.0) / (float(r.get("attempts") or 0) + 2.0)
    return sorted(forms, key=lambda f: (-rate(f), f))[0]


def _attempt_stats(ctx: Context) -> tuple[dict[str, int], dict[str, float], dict[str, tuple[int, int]]]:
    """Per form attempt counts, per target last |planned - verified| error,
    and per form (accurate, total) prediction calibration from the attempt log."""
    form_n: dict[str, int] = {}
    err: dict[str, float] = {}
    calib: dict[str, tuple[int, int]] = {}
    for r in ctx.attempt_log():
        f = str(r.get("form") or "")
        if f:
            form_n[f] = form_n.get(f, 0) + 1
        if r.get("planned") is None:
            continue
        try:
            planned = int(r.get("planned") or 0)
            got = int(r.get("verified_depth", r.get("depth")) or 0)
        except (TypeError, ValueError):
            continue
        tid = str(r.get("id") or "")
        if tid:
            err[tid] = float(abs(planned - got))
        if f:
            a, t = calib.get(f, (0, 0))
            calib[f] = (a + (1 if got >= planned else 0), t + 1)
    return form_n, err, calib


def _pick_novelty(ctx: Context, n: int) -> list[str]:
    """Novelty archive: least-explored claim forms first, then least-tried targets."""
    pool = ctx.oeis_pool()
    form_n, _, _ = _attempt_stats(ctx)
    tg = ctx.oeis_state().get("targets") or {}
    return [str(e["id"]) for e in sorted(pool, key=lambda e: (
        form_n.get(_form(e), 0), int((tg.get(e["id"]) or {}).get("attempts") or 0), str(e["id"])))][:n]


def _pick_prediction_error(ctx: Context, n: int) -> list[str]:
    """Prediction-error routing: targets whose last planned depth missed most."""
    pool = ctx.oeis_pool()
    _, err, _ = _attempt_stats(ctx)
    ranked = [e for e in pool if err.get(str(e["id"]), 0.0) > 0]
    return _rank(ranked, lambda e: err.get(str(e["id"]), 0.0))[:n]


def _pick_calibrated(ctx: Context, n: int) -> list[str]:
    """Calibrated self-model: weight each proposal by how often the colony's own
    depth prediction for that form came true (Laplace), times its headroom."""
    pool = ctx.oeis_pool()
    if not pool:
        return []
    _, _, calib = _attempt_stats(ctx)
    tg = ctx.oeis_state().get("targets") or {}

    def score(e: dict[str, Any]) -> float:
        a, t = calib.get(_form(e), (0, 0))
        prior = int((tg.get(e["id"]) or {}).get("tested_hi") or 0)
        try:
            head = max(0, int(ctx.oeis.planned_depth(e, prior or None)) - prior)
        except Exception:
            head = 0
        return (a + 1.0) / (t + 2.0) * (1.0 + head)
    return _rank(pool, score)[:n]


def improver_ballots(ctx: Context) -> dict[str, list[str]]:
    """Item 85 (swarm_topology, top-ranked research idea): every improver flow the colony
    already has ranks the ONE shared open pool; each ranking is one ballot.

    Improvers: replay buffer (recent depth gain), novelty archive, prediction error,
    calibrated self-model, and the consensus desk's own Borda result. Partial rankings
    (an improver with nothing to say about a target) simply give it no points.
    """
    pool = ctx.oeis_pool()
    if not pool:
        return {}
    n = len(pool)
    ballots = {
        "replay": _pick_replay(ctx, n),
        "novelty": _pick_novelty(ctx, n),
        "prediction_error": _pick_prediction_error(ctx, n),
        "calibrated": _pick_calibrated(ctx, n),
        "consensus": consensus(voters(ctx, pool), n, 1),
    }
    return {k: v for k, v in ballots.items() if v}


def _pick_swarm(ctx: Context, n: int, quorum: int = 2) -> list[str]:
    """Swarm of improvers over one shared pool; Borda vote with a quorum picks the pass."""
    ballots = improver_ballots(ctx)
    if not ballots:
        return []
    return consensus(ballots, n, min(int(quorum), len(ballots)))


_ID_PICKERS: dict[str, Callable[..., list[str]]] = {}


def _plan_oeis(ctx: Context, comp: str, n: int) -> int:
    if not ctx.oeis_live():
        return 0
    if comp == "oeis_extra_pass":
        return min(n, len(ctx.oeis_pool()))
    if comp == "oeis_beyond_bfile":
        return min(n, len(ctx.oeis_pool(beyond_bfile=True)))
    if comp == "oeis_replay_buffer":
        return len(_pick_replay(ctx, n))
    if comp == "oeis_consensus_vote":
        return len(_pick_vote(ctx, n))
    if comp == "oeis_form_router":
        f = _route_form(ctx)
        return min(n, len(ctx.oeis_pool(forms={f}))) if f else 0
    if comp in _ID_PICKERS:
        return len(_ID_PICKERS[comp](ctx, n))
    return 0


def _run_oeis(ctx: Context, comp: str, n: int) -> dict[str, Any]:
    if _plan_oeis(ctx, comp, n) <= 0:
        return {"actions": 0, "skipped": "nothing_open"}
    if comp == "oeis_replay_buffer":
        return ctx.run_oeis(purpose=comp, only_ids=_pick_replay(ctx, n))
    if comp == "oeis_consensus_vote":
        return ctx.run_oeis(purpose=comp, only_ids=_pick_vote(ctx, n))
    if comp in _ID_PICKERS:
        return ctx.run_oeis(purpose=comp, only_ids=_ID_PICKERS[comp](ctx, n))
    if comp == "oeis_form_router":
        f = _route_form(ctx)
        ids = [str(e["id"]) for e in ctx.oeis_pool(forms={f})][:n] if f else []
        return {**ctx.run_oeis(purpose=comp, only_ids=ids), "form": f}
    # Choice-based passes still honour self-heal's excluded targets: hand the
    # chooser's own picks over as ids after filtering.
    pool = ctx.oeis_pool(beyond_bfile=(comp == "oeis_beyond_bfile"))
    ids = [str(e["id"]) for e in pool][:n]
    return ctx.run_oeis(purpose=comp, only_ids=ids, beyond_bfile=(comp == "oeis_beyond_bfile"))


def _plan_frontier(ctx: Context, comp: str, n: int) -> int:
    try:
        if ctx.frontier.mode() == "off":
            return 0
    except Exception:
        return 0
    return 1 if ctx.free_authored_slots() > 0 else 0


def _run_frontier(ctx: Context, comp: str, n: int) -> dict[str, Any]:
    if _plan_frontier(ctx, comp, n) <= 0:
        return {"actions": 0, "skipped": "no_free_authored_slot_under_150_cap"}
    rep = ctx.frontier.run_cycle(ctx.cycle_id, seed=f"{ctx.cycle_id}:self_build") or {}
    counts = rep.get("counts") if isinstance(rep, dict) else None
    return {"actions": 1, "counts": {k: v for k, v in (counts or {}).items()
                                     if isinstance(v, (int, float))}}


def _plan_new_data(ctx: Context, comp: str, n: int) -> int:
    return min(n, ctx.new_data_open())


def _run_new_data(ctx: Context, comp: str, n: int) -> dict[str, Any]:
    if _plan_new_data(ctx, comp, n) <= 0:
        return {"actions": 0, "skipped": "nothing_open"}
    rep = ctx.new_data.run_cycle(ctx.cycle_id, budget_s=10.0 * n) or {}
    pushed = rep.get("pushed") if isinstance(rep, dict) else None
    return {"actions": len(pushed) if isinstance(pushed, list) else 1}


# name -> spec. ``ideas`` are item-79 architecture-idea keys that support it.
COMPONENTS: dict[str, dict[str, Any]] = {
    "oeis_extra_pass": {"desk": "oeis", "flow": "retry_curriculum", "max_n": 3, "heavy": False,
                        "ideas": ("meta_controller",), "plan": _plan_oeis, "run": _run_oeis},
    "oeis_beyond_bfile": {"desk": "oeis", "flow": "self_play_challenger", "max_n": 3, "heavy": False,
                          "ideas": ("self_play_challenger",), "plan": _plan_oeis, "run": _run_oeis},
    "oeis_replay_buffer": {"desk": "oeis", "flow": "working_memory_attention", "max_n": 3, "heavy": False,
                           "ideas": ("working_memory_buffer", "global_workspace_broadcast"),
                           "plan": _plan_oeis, "run": _run_oeis},
    "oeis_consensus_vote": {"desk": "oeis", "flow": "swarm_consensus", "max_n": 3, "heavy": False,
                            "ideas": ("swarm_topology", "hierarchical_roles", "message_passing_desks"),
                            "plan": _plan_oeis, "run": _run_oeis},
    "oeis_calibrated_vote": {"desk": "oeis", "flow": "self_model_calibration", "max_n": 3, "heavy": False,
                             "ideas": ("self_model_calibration",), "plan": _plan_oeis, "run": _run_oeis},
    "oeis_form_router": {"desk": "oeis", "flow": "specialist_routing", "max_n": 3, "heavy": False,
                         "ideas": ("specialist_routing",), "plan": _plan_oeis, "run": _run_oeis},
    "oeis_novelty_archive": {"desk": "oeis", "flow": "novelty_archive", "max_n": 3, "heavy": False,
                             "ideas": ("novelty_archive",), "plan": _plan_oeis, "run": _run_oeis},
    "oeis_prediction_error": {"desk": "oeis", "flow": "prediction_error_routing", "max_n": 3, "heavy": False,
                              "ideas": ("prediction_error_routing",), "plan": _plan_oeis, "run": _run_oeis},
    "oeis_swarm_improvers": {"desk": "oeis", "flow": "swarm_topology", "max_n": 3, "heavy": False,
                             "prior": 0.95, "ideas": ("swarm_topology",), "plan": _plan_oeis, "run": _run_oeis},
    "frontier_extra_batch": {"desk": "frontier", "flow": "open_ended_generation", "max_n": 1, "heavy": True,
                             "ideas": ("novelty_archive",), "plan": _plan_frontier, "run": _run_frontier},
    "new_data_extra_push": {"desk": "new_data", "flow": "retry_curriculum", "max_n": 2, "heavy": False,
                            "ideas": ("meta_controller",), "plan": _plan_new_data, "run": _run_new_data},
}
_ID_PICKERS.update({
    "oeis_novelty_archive": _pick_novelty,
    "oeis_prediction_error": _pick_prediction_error,
    "oeis_calibrated_vote": _pick_calibrated,
    "oeis_swarm_improvers": _pick_swarm,  # item 85
})

# Words in method cards / lessons that count as evidence for a component.
_EVIDENCE_PATTERNS: dict[str, re.Pattern[str]] = {
    "oeis_extra_pass": re.compile(r"\b(curriculum|retry|repeat(ed)? attempt|second pass)\b", re.I),
    "oeis_beyond_bfile": re.compile(r"\b(self-play|challenger|harder|beyond (the )?b-?file)\b", re.I),
    "oeis_replay_buffer": re.compile(r"\b(replay|working memory|attention|buffer|recency)\b", re.I),
    "oeis_consensus_vote": re.compile(r"\b(swarm|consensus|vote|voting|ensemble|collective)\b", re.I),
    "oeis_form_router": re.compile(r"\b(rout(e|ing)|mixture of experts|specialist|gating)\b", re.I),
    "oeis_calibrated_vote": re.compile(r"\b(calibrat\w*|self-model|metacognit\w*)\b", re.I),
    "oeis_novelty_archive": re.compile(r"\b(novelty|quality diversity|archive)\b", re.I),
    "oeis_prediction_error": re.compile(r"\b(prediction error|surprise|predictive coding)\b", re.I),
    "oeis_swarm_improvers": re.compile(r"\b(swarm|multi-agent|population of agents|consensus)\b", re.I),
    "frontier_extra_batch": re.compile(r"\b(open-ended|exploration|generator)\b", re.I),
    "new_data_extra_push": re.compile(r"\b(new data|frontier push|extend(ed)? terms)\b", re.I),
}


# --------------------------------------------------------------------------- blueprints

def _norm_step(step: Mapping[str, Any]) -> dict[str, Any]:
    return {"component": str(step.get("component") or ""), "n": int(step.get("n") or 1)}


def signature(steps: Iterable[Mapping[str, Any]]) -> str:
    body = json.dumps([_norm_step(s) for s in steps], sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def make_blueprint(steps: Iterable[Mapping[str, Any]], *, parent: str | None = None,
                   operator: str = "seed", evidence: Iterable[str] = ()) -> dict[str, Any]:
    st = [_norm_step(s) for s in steps]
    sig = signature(st)
    return {"id": f"bp_{sig}" if st else "bp_default", "signature": sig, "steps": st,
            "parent": parent, "operator": operator, "evidence": sorted(set(evidence))}


def expand(steps: Iterable[Mapping[str, Any]], macros: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Macro steps become their stored steps (one level; macros never nest)."""
    out: list[dict[str, Any]] = []
    for s in steps:
        s = _norm_step(s)
        m = (macros or {}).get(s["component"])
        if isinstance(m, dict):
            out.extend(_norm_step(x) for x in (m.get("steps") or []))
        else:
            out.append(s)
    return out


def validate(bp: Mapping[str, Any], macros: Mapping[str, Any] | None = None) -> tuple[bool, str]:
    raw = list(bp.get("steps") or [])
    for s in raw:
        name = str(s.get("component") or "")
        if name not in COMPONENTS and name not in (macros or {}):
            return False, f"unknown_component:{name}"
    steps = expand(raw, macros)
    for s in steps:
        if s["component"] not in COMPONENTS:
            return False, f"nested_or_unknown:{s['component']}"
        spec = COMPONENTS[s["component"]]
        if not 1 <= s["n"] <= int(spec["max_n"]):
            return False, f"size_out_of_bounds:{s['component']}={s['n']}"
    if len(steps) > MAX_STEPS:
        return False, "too_many_steps"
    if sum(s["n"] for s in steps) > MAX_TOTAL_SIZE:
        return False, "too_large"
    if sum(1 for s in steps if COMPONENTS[s["component"]]["heavy"]) > MAX_HEAVY:
        return False, "too_many_heavy"
    return True, "ok"


def self_test(bp: Mapping[str, Any], ctx: Context, macros: Mapping[str, Any] | None = None,
              *, new_only: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Fast check before a window is spent: valid, and no dead step on live state.

    Read-only: plans each step against the current state without running
    any attempt. ``new_only`` limits the dead-step rule to the steps this
    candidate adds (a kept step that is idle today does not block a child).
    """
    ok, why = validate(bp, macros)
    if not ok:
        return {"ok": False, "reason": why, "plan": []}
    steps = expand(bp.get("steps") or [], macros)
    check = expand(new_only, macros) if new_only is not None else steps
    plan = []
    for s in steps:
        spec = COMPONENTS[s["component"]]
        try:
            n_plan = int(spec["plan"](ctx, s["component"], s["n"]))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": f"plan_error:{s['component']}:{type(exc).__name__}", "plan": plan}
        plan.append({**s, "planned": n_plan})
    dead = [p["component"] for p in plan if p["planned"] <= 0 and _norm_step(p) in check]
    if dead:
        return {"ok": False, "reason": "dead_step:" + ",".join(dead), "plan": plan}
    if steps and sum(p["planned"] for p in plan) <= 0:
        return {"ok": False, "reason": "no_op_on_live_state", "plan": plan}
    return {"ok": True, "reason": "ok", "plan": plan}


def run_blueprint(bp: Mapping[str, Any], ctx: Context, macros: Mapping[str, Any] | None = None,
                  *, budget_s: float = CYCLE_BUDGET_S) -> dict[str, Any]:
    ok, why = validate(bp, macros)
    if not ok:
        return {"blueprint": bp.get("id"), "ran": [], "invalid": why}
    t0 = time.process_time()
    ran = []
    for s in expand(bp.get("steps") or [], macros):
        spent = time.process_time() - t0
        if spent >= budget_s:
            ran.append({**s, "actions": 0, "skipped": "cycle_budget"})
            continue
        spec = COMPONENTS[s["component"]]
        try:
            out = dict(spec["run"](ctx, s["component"], s["n"]) or {})
        except Exception as exc:  # noqa: BLE001
            out = {"actions": 0, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        ran.append({**s, **out})
    return {"blueprint": bp.get("id"), "ran": ran,
            "actions": sum(int(r.get("actions") or 0) for r in ran),
            "cpu_s": round(time.process_time() - t0, 3)}


# --------------------------------------------------------------------------- evidence

def load_ideas(path: Path | None = None) -> list[dict[str, Any]]:
    """Item-79 architecture ideas; a missing file is simply no evidence."""
    if path is None and os.environ.get("COLONY_ARCH_IDEAS"):
        path = Path(os.environ["COLONY_ARCH_IDEAS"])  # same override item 79 uses
    return [r for r in load_log(Path(path or IDEAS_PATH)) if r.get("event") == "architecture_idea"]


def _texts(rows: Iterable[Any]) -> list[str]:
    out = []
    for r in rows:
        if isinstance(r, Mapping):
            out.append(" ".join(str(v) for v in r.values() if isinstance(v, (str, int, float)))[:2000])
    return out


def evidence(ideas: list[dict[str, Any]] | None = None, cards: list[Any] | None = None,
             lessons: list[Any] | None = None) -> dict[str, dict[str, Any]]:
    """Per component: supporting papers (distinct arXiv ids), cards and lessons."""
    if ideas is None:
        ideas = load_ideas()
    if cards is None:
        try:
            from colony.research_desk import load_cards
            cards = list(load_cards() or [])
        except Exception:
            cards = []
    if lessons is None:
        try:
            from colony.lessons import load_lessons
            lessons = list(load_lessons(limit=200) or [])
        except Exception:
            lessons = []
    out: dict[str, dict[str, Any]] = {}
    per_idea: dict[str, set[str]] = {}
    for r in ideas:
        if r.get("idea") and r.get("arxiv_id"):
            per_idea.setdefault(str(r["idea"]), set()).add(str(r["arxiv_id"]))
    order = sorted(per_idea, key=lambda k: (-len(per_idea[k]), k))
    ranks = {k: i for i, k in enumerate(order)}
    for name, spec in COMPONENTS.items():
        papers = sorted({str(r.get("arxiv_id")) for r in ideas
                         if r.get("idea") in spec["ideas"] and r.get("arxiv_id")})
        pat = _EVIDENCE_PATTERNS.get(name)
        n_cards = sum(1 for t in _texts(cards) if pat and pat.search(t))
        n_lessons = sum(1 for t in _texts(lessons) if pat and pat.search(t))
        rank = min((ranks[i] for i in spec["ideas"] if i in ranks), default=None)
        # Papers dominate (top-ranked research-desk ideas seed the first
        # blueprints); cards and lessons only break ties.
        boost = (1.0 + 0.5 * min(16, len(papers)) + (1.5 / (1 + rank) if rank is not None else 0.0)
                 + 0.05 * min(5, n_cards) + 0.02 * min(5, n_lessons))
        out[name] = {"papers": papers[:8], "n_papers": len(papers), "idea_rank": rank,
                     "cards": n_cards, "lessons": n_lessons, "boost": round(boost, 4)}
    return out


# --------------------------------------------------------------------------- generator

def _comp_weight(name: str, stats: Mapping[str, Any], ev: Mapping[str, Any], macros: Mapping[str, Any],
                 losses: Mapping[str, int] | None = None) -> float:
    if name in macros:
        parts = expand([{"component": name}], macros)
        ws = [_comp_weight(p["component"], stats, ev, {}, losses) for p in parts]
        return (sum(ws) / len(ws) if ws else 0.5) * 1.1
    s = stats.get(name) or {}
    kept = float(s.get("kept") or 0)
    tried = float(s.get("tried") or 0)
    rate = (kept + 1.0) / (tried + 2.0)
    w = rate * float((ev.get(name) or {}).get("boost") or 1.0)
    # Item 85: a newly added component sharing an established one's evidence starts just behind it.
    w *= float((COMPONENTS.get(name) or {}).get("prior", 1.0))
    if losses:
        # Item 89: components whose blueprints really lost (reverted) are weighted down.
        from colony.failure_modes import component_penalty
        w *= component_penalty(name, losses)
    return w


WIDE_OPERATORS = ("replace", "pair", "jump")
# Item 87: prior factor per mutation operator; the learned factor multiplies it.
OPERATOR_PRIOR = {"add": 1.0, "use_macro": 1.0, "resize": 0.9, "remove": 0.5, "swap": 0.6,
                  "crossover": 1.0, "replace": 0.8, "pair": 0.7, "jump": 0.6,
                  # Item 92: structural moves (order and grouping of steps, not sizes or knobs)
                  "insert_front": 0.9, "move": 0.7, "merge": 0.6, "split": 0.6, "inline_macro": 0.7}
STRUCTURAL_OPERATORS = ("insert_front", "move", "merge", "split", "inline_macro")


def operator_stats_from_log(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Per-operator tried/kept/reverted counts rebuilt from the append-only blueprint log."""
    opened: dict[str, str] = {}
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        ev, bid = r.get("event"), str(r.get("blueprint") or "")
        if ev == "blueprint_trial_open":
            opened[bid] = str(r.get("operator") or "")
        elif ev in ("blueprint_trial_close", "blueprint_trial_void"):
            op = str(r.get("operator") or opened.get(bid) or "")
            if not op:
                continue
            s = out.setdefault(op, {"tried": 0, "kept": 0, "reverted": 0})
            outcome = r.get("outcome")
            if outcome in ("kept", "reverted"):  # inconclusive / voided: no evidence either way
                s["tried"] += 1
                s[outcome] += 1
    return out


def operator_factor(op: str, op_stats: Mapping[str, Any] | None) -> float:
    """Prior x learned keep rate. Laplace (kept+1)/(tried+2), scaled so an unseen operator is 1.0."""
    prior = float(OPERATOR_PRIOR.get(op, 0.5))
    s = (op_stats or {}).get(op) or {}
    kept, tried = float(s.get("kept") or 0), float(s.get("tried") or 0)
    return prior * ((kept + 1.0) / (tried + 2.0)) / 0.5


def candidates(state: Mapping[str, Any], ev: Mapping[str, Any]) -> list[dict[str, Any]]:
    """All legal one-move children of the active blueprint, best first."""
    active = state.get("active") or DEFAULT_BLUEPRINT
    steps = [_norm_step(s) for s in active.get("steps") or []]
    macros = dict(state.get("macros") or {})
    stats = state.get("component_stats") or {}
    tried = state.get("tried") or {}
    parent = active.get("id") or "bp_default"
    raw: list[tuple[float, dict[str, Any], list[dict[str, Any]]]] = []
    seen_sig: set[str] = set()
    try:
        from colony.failure_modes import component_losses, live as _fm_live
        losses = component_losses() if _fm_live() else {}
    except Exception:  # noqa: BLE001
        losses = {}

    op_stats = state.get("operator_stats") or {}
    try:  # item 102: learn from this colony's own kept / reverted blueprints
        from colony import self_build_lessons as _sbl
        _les = _sbl.lessons() if _sbl.enabled() else None
    except Exception:  # noqa: BLE001
        _sbl, _les = None, None

    def add(new_steps: list[dict[str, Any]], operator: str, added: list[dict[str, Any]], factor: float = 1.0):
        bp = make_blueprint(new_steps, parent=parent, operator=operator,
                            evidence=[a["component"] for a in added])
        if bp["signature"] in tried or bp["signature"] == signature(steps):
            return
        if (operator in WIDE_OPERATORS or operator in STRUCTURAL_OPERATORS) and bp["signature"] in seen_sig:
            return  # a wide move that repeats an existing child adds nothing
        ok, _ = validate(bp, macros)
        if not ok:
            return
        if _les is not None and _sbl.blocked(added, _les, macros):
            return  # item 102: never re-add a component whose own blueprint was reverted
        seen_sig.add(bp["signature"])
        # Item 87: operator prior x keep rate learned from past kept / reverted trials.
        w = factor * operator_factor(operator, op_stats) / max(1e-9, float(OPERATOR_PRIOR.get(operator, 0.5)))
        cw = [_comp_weight(a["component"], stats, ev, macros, losses) for a in added]
        if _les is not None:
            cw = [x * _sbl.desk_factor(a["component"], _les, COMPONENTS, macros) for x, a in zip(cw, added)]
        if operator == "pair" and cw:
            w *= min(cw)  # a pair ranks like its weaker half: it never rides on its best component
        else:
            for x in cw:
                w *= x
        raw.append((w, bp, added))

    names = sorted(COMPONENTS) + sorted(macros)
    for name in names:
        max_n = 1 if name in macros else int(COMPONENTS[name]["max_n"])
        for n in range(1, min(2, max_n) + 1):
            step = {"component": name, "n": n}
            add(steps + [step], "add" if name in COMPONENTS else "use_macro", [step], 1.0 / n)
    for i, s in enumerate(steps):
        if s["component"] in COMPONENTS:
            for d in (1, -1):
                n = s["n"] + d
                if 1 <= n <= int(COMPONENTS[s["component"]]["max_n"]):
                    new = [dict(x) for x in steps]
                    new[i] = {"component": s["component"], "n": n}
                    add(new, "resize", [new[i]], OPERATOR_PRIOR["resize"])
        add(steps[:i] + steps[i + 1:], "remove", [], OPERATOR_PRIOR["remove"])
        if i + 1 < len(steps):
            new = [dict(x) for x in steps]
            new[i], new[i + 1] = new[i + 1], new[i]
            add(new, "swap", [], OPERATOR_PRIOR["swap"])
    # Item 87: wider moves. replace = swap one step for a component not in the blueprint;
    # jump = resize by 2; pair = add two components from different desks in one move.
    present = {s["component"] for s in steps}
    for i, s in enumerate(steps):
        if s["component"] not in COMPONENTS:
            continue
        for name in sorted(COMPONENTS):
            if name in present:
                continue
            new = [dict(x) for x in steps]
            new[i] = {"component": name, "n": min(s["n"], int(COMPONENTS[name]["max_n"]))}
            add(new, "replace", [new[i]], OPERATOR_PRIOR["replace"])
        for d in (2, -2):
            n = s["n"] + d
            if 1 <= n <= int(COMPONENTS[s["component"]]["max_n"]):
                new = [dict(x) for x in steps]
                new[i] = {"component": s["component"], "n": n}
                add(new, "jump", [new[i]], OPERATOR_PRIOR["jump"])
    # Item 92: structural moves. Steps run in order and share the cycle's attempted set, so
    # position and grouping change which targets each step gets. insert_front = a new block
    # ahead of the others; move = non-adjacent reorder (adjacent is swap); merge = two adjacent
    # passes of one component become one; split = one pass becomes two; inline_macro = a macro
    # step is replaced by its parts so each becomes individually mutable.
    if steps:
        for name in sorted(COMPONENTS):
            step = {"component": name, "n": 1}
            add([step] + steps, "insert_front", [step], OPERATOR_PRIOR["insert_front"])
    for i in range(len(steps)):
        for j in (0, len(steps) - 1):
            if abs(i - j) >= 2:
                new = [dict(x) for x in steps]
                st_i = new.pop(i)
                new.insert(j, st_i)
                add(new, "move", [], OPERATOR_PRIOR["move"])
    for i in range(len(steps) - 1):
        a, b = steps[i], steps[i + 1]
        if a["component"] == b["component"] and a["component"] in COMPONENTS:
            n = a["n"] + b["n"]
            if n <= int(COMPONENTS[a["component"]]["max_n"]):
                merged = {"component": a["component"], "n": n}
                add(steps[:i] + [merged] + steps[i + 2:], "merge", [merged], OPERATOR_PRIOR["merge"])
    for i, s in enumerate(steps):
        if s["component"] in COMPONENTS and s["n"] >= 2:
            parts = [{"component": s["component"], "n": s["n"] - 1}, {"component": s["component"], "n": 1}]
            add(steps[:i] + parts + steps[i + 1:], "split", [], OPERATOR_PRIOR["split"])
        elif s["component"] in macros:
            inner = [_norm_step(x) for x in (macros[s["component"]].get("steps") or [])]
            if inner:
                add(steps[:i] + inner + steps[i + 1:], "inline_macro", [], OPERATOR_PRIOR["inline_macro"])
    comps = [n for n in sorted(COMPONENTS) if n not in present]
    for a_i, a_name in enumerate(comps):
        for b_name in comps[a_i + 1:]:
            if COMPONENTS[a_name].get("plan") is COMPONENTS[b_name].get("plan"):
                continue  # same desk twice is a resize, not a pair
            pair = [{"component": a_name, "n": 1}, {"component": b_name, "n": 1}]
            add(steps + pair, "pair", pair, OPERATOR_PRIOR["pair"])
    for sig, rec in sorted(tried.items()):
        if isinstance(rec, dict) and rec.get("outcome") == "kept":
            extra = [_norm_step(x) for x in rec.get("steps") or [] if _norm_step(x) not in steps]
            if extra:
                add(steps + extra, "crossover", extra, 1.0)
    raw.sort(key=lambda t: (-t[0], t[1]["signature"]))
    out = []
    for w, bp, added in raw:
        bp = dict(bp)
        bp["weight"] = round(w, 6)
        bp["added"] = added
        bp["evidence_detail"] = {a["component"]: ev.get(a["component"]) for a in added
                                 if a["component"] in ev}
        out.append(bp)
    return out


def propose(state: Mapping[str, Any], ctx: Context, ev: Mapping[str, Any] | None = None,
            limit: int = 40) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Best child that passes the fast self-test, plus the rejected ones (reasons)."""
    ev = ev if ev is not None else evidence()
    macros = state.get("macros") or {}
    rejected = []
    for bp in candidates(state, ev)[:limit]:
        test = self_test(bp, ctx, macros, new_only=bp.get("added") or [])
        if test["ok"]:
            bp = dict(bp)
            bp["self_test"] = test
            return bp, rejected
        rejected.append({"id": bp["id"], "operator": bp["operator"], "reason": test["reason"]})
    return None, rejected


# --------------------------------------------------------------------------- twin scoring

def _paired_rows(board: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    try:
        from colony.twin import paired_history
        return paired_history(list((board or {}).get("history") or []))
    except Exception:
        return [r for r in (board or {}).get("history") or [] if isinstance(r, dict) and r.get("paired")]


def load_board() -> dict[str, Any]:
    try:
        from colony import twin as _tw
        return _load_json(_tw.SCOREBOARD_PATH, {}) or {}
    except Exception:
        return {}


def _diff(row: Mapping[str, Any]) -> tuple[float, float]:
    t, c = row.get("treatment") or {}, row.get("control") or {}

    def g(d: Mapping[str, Any], k: str) -> float:
        try:
            return float(d.get(k) or 0)
        except (TypeError, ValueError):
            return 0.0
    return (g(t, "oracle_passes") - g(c, "oracle_passes"),
            g(t, "verified_depth_sum") - g(c, "verified_depth_sum"))


def window_rows(rows: list[dict[str, Any]]) -> int:
    try:
        per = int((rows[-1] if rows else {}).get("cycles_this_run") or 3)
    except (TypeError, ValueError):
        per = 3
    return max(1, -(-WINDOW_CYCLES // max(1, per)))


def gain(rows: list[dict[str, Any]], start: int, end: int) -> tuple[float, float] | None:
    """Treatment-minus-control gain from paired row ``start`` to row ``end``."""
    if start < 0 or end >= len(rows) or end <= start:
        return None
    a, b = _diff(rows[start]), _diff(rows[end])
    return (b[0] - a[0], b[1] - a[1])


def decide(trial_gain: tuple[float, float] | None, baseline_gain: tuple[float, float] | None) -> dict[str, Any]:
    """Keep only when strictly better than baseline AND than the twin."""
    if trial_gain is None:
        return {"keep": False, "reason": "no_paired_window"}
    base = baseline_gain if baseline_gain is not None else (0.0, 0.0)
    better_than_baseline = tuple(trial_gain) > tuple(base)
    better_than_twin = tuple(trial_gain) > (0.0, 0.0)
    keep = bool(better_than_baseline and better_than_twin)
    reason = "kept" if keep else ("not_better_than_baseline" if not better_than_baseline
                                  else "not_better_than_twin")
    return {"keep": keep, "reason": reason, "trial_gain": list(trial_gain), "baseline_gain": list(base),
            "better_than_baseline": better_than_baseline, "better_than_twin": better_than_twin}


# --------------------------------------------------------------------------- self-heal coupling

def _self_heal_state() -> dict[str, Any]:
    try:
        from colony import self_heal as _sh
        return _sh.load_state() or {}
    except Exception:
        return {}


def blocks_self_heal(state: Mapping[str, Any] | None = None) -> bool:
    """True while a blueprint trial is open (self-heal waits so neither is miscredited)."""
    if not self_mod_ok():
        return False
    st = state if state is not None else load_state()
    return bool(st.get("trial"))


def _heal_had_turn(heal: Mapping[str, Any], turn: Mapping[str, Any]) -> bool:
    """True once self-heal ran its proposer in a cycle after ``turn`` (or holds a trial)."""
    if heal.get("trial") or heal.get("build_turn"):
        return True  # holding a trial, or itself waiting for self-build: no deadlock
    last = str(heal.get("last_propose_cycle") or "")
    return bool(last) and last > str(turn.get("cycle_id") or "")


def build_turn_pending(heal_state: Mapping[str, Any], state: Mapping[str, Any] | None = None) -> bool:
    """Item 84: after a self-heal trial ends, self-build proposes before self-heal opens another."""
    if not self_mod_ok():
        return False
    turn = heal_state.get("build_turn")
    if not isinstance(turn, dict):
        return False
    st = state if state is not None else load_state()
    last = str(st.get("last_propose_cycle") or "")
    if st.get("trial") or (last and last >= str(turn.get("cycle_id") or "")):
        return False
    return True


def _excluded_targets(heal: Mapping[str, Any]) -> set[str]:
    out = set(str(x) for x in (heal.get("compute_bound_targets") or {}))
    trial = heal.get("trial")
    if isinstance(trial, dict):
        out.update(str(x) for x in trial.get("predicted_targets") or [])
    return out


# --------------------------------------------------------------------------- cycle

def _bump(stats: dict[str, Any], names: Iterable[str], key: str) -> None:
    for name in set(names):
        s = stats.setdefault(name, {"tried": 0, "kept": 0, "reverted": 0, "inconclusive": 0})
        s[key] = int(s.get(key) or 0) + 1


def code_fingerprint() -> str:
    """Digest of running behavior code (same narrowed digest self-heal voids on)."""
    try:
        from colony.self_heal import _colony_file_digest
        return str(_colony_file_digest())
    except Exception:  # noqa: BLE001
        return ""


def _void(st: dict[str, Any], trial: dict[str, Any], cycle_id: str, reason: str, *, write: bool,
          log_path: Path | None, fp: str = "") -> dict[str, Any]:
    """Item 84: end a confounded trial with no credit; the active blueprint is unchanged."""
    bp = trial.get("blueprint") or {}
    st["trial"] = None
    st["voided_count"] = int(st.get("voided_count") or 0) + 1
    st["heal_turn"] = {"cycle_id": cycle_id, "cycle_index": st.get("cycle_index")}
    row = {"event": "blueprint_trial_void", "cycle_id": cycle_id, "outcome": "voided", "reason": reason,
           "blueprint": bp.get("id"), "steps": bp.get("steps"), "old_code_fp": trial.get("code_fp"),
           "new_code_fp": fp, "active_after": (st.get("active") or {}).get("id"),
           "authorized": False, "human_signoff_required": False}
    if write:
        append_log(row, log_path)
        _log_failure(row, bp, st)
    return row


def _log_failure(row: Mapping[str, Any], bp: Mapping[str, Any], st: Mapping[str, Any]) -> None:
    """Item 89: exact failure mode of a non-kept blueprint trial (append-only)."""
    try:
        from colony.failure_modes import log_blueprint
        names = [s["component"] for s in expand(bp.get("added") or bp.get("steps") or [], st.get("macros"))]
        log_blueprint(row, components=names)
    except Exception:  # noqa: BLE001
        pass


def _overlap_flags(rows: list[dict[str, Any]], a: int, b: int, exclude_id: str | None) -> list[dict[str, Any]] | None:
    """Item 104 (flag only): other experiments that shared time with paired rows a..b.

    The keep / revert verdict is NOT changed by this; it records when a window or its baseline
    was shared with another trial so a confounded verdict is visible in the log."""
    try:
        from colony.experiment_reservation import enabled, overlapping, trial_intervals
        if not enabled() or a < 0 or b <= a or a >= len(rows):
            return None
        end = rows[b].get("ts") if b < len(rows) else None
        return overlapping(rows[a].get("ts"), end, trial_intervals(), exclude_id=exclude_id)
    except Exception:  # noqa: BLE001
        return None


def _close(st: dict[str, Any], board: Mapping[str, Any], cycle_id: str, *, write: bool,
           log_path: Path | None) -> dict[str, Any] | None:
    trial = st.get("trial")
    if not isinstance(trial, dict):
        return None
    fp = code_fingerprint()
    if fp and not trial.get("code_fp") and not trial.get("opened_cycle_id"):
        trial["code_fp"] = fp  # hand-built trial dict (no open record): start tracking now
    if fp and trial.get("code_fp") != fp:
        # a code change landed inside the window (or a pre-item-84 trial with no fingerprint)
        return _void(st, trial, cycle_id, "code_changed_in_window" if trial.get("code_fp") else
                     "no_code_fingerprint_at_open", write=write, log_path=log_path, fp=fp)
    age = int(st["cycle_index"]) - int(trial.get("opened_cycle_index") or 0)
    rows = _paired_rows(board)
    w = int(trial.get("window_rows") or window_rows(rows))
    start = int(trial.get("open_row") if trial.get("open_row") is not None else len(rows) - 1)
    if age < WINDOW_CYCLES:
        return None
    if len(rows) - 1 < start + w:
        if age < TRIAL_MAX_CYCLES:
            return None
        verdict = {"keep": False, "reason": "inconclusive_no_paired_window",
                   "time_limit_cycles": TRIAL_MAX_CYCLES}
        outcome = "inconclusive"
    else:
        verdict = decide(gain(rows, start, start + w),
                         tuple(trial["baseline_gain"]) if trial.get("baseline_gain") else None)
        outcome = "kept" if verdict["keep"] else "reverted"
    bp = trial.get("blueprint") or {}
    names = [s["component"] for s in expand(bp.get("added") or bp.get("steps") or [], st.get("macros"))]
    stats = st.setdefault("component_stats", {})
    _bump(stats, names, outcome if outcome != "kept" else "kept")
    if outcome in ("kept", "reverted") and bp.get("operator"):
        ops = st.setdefault("operator_stats", {}).setdefault(str(bp["operator"]),
                                                            {"tried": 0, "kept": 0, "reverted": 0})
        ops["tried"] = int(ops.get("tried") or 0) + 1
        ops[outcome] = int(ops.get(outcome) or 0) + 1
    if outcome == "kept":
        st["active"] = {k: bp.get(k) for k in ("id", "signature", "steps", "parent", "operator")}
        st["kept_count"] = int(st.get("kept_count") or 0) + 1
        raw = bp.get("steps") or []
        if len(expand(raw, st.get("macros"))) >= 2 and len(st.get("macros") or {}) < MAX_MACROS:
            name = f"macro_{bp.get('signature')}"[:22]
            st.setdefault("macros", {})[name] = {"steps": expand(raw, st.get("macros")),
                                                 "from": bp.get("id"), "cycle_id": cycle_id}
    elif outcome == "reverted":
        st["reverted_count"] = int(st.get("reverted_count") or 0) + 1
    else:
        st["inconclusive_count"] = int(st.get("inconclusive_count") or 0) + 1
    st.setdefault("tried", {})[bp.get("signature") or ""] = {
        "outcome": outcome, "steps": bp.get("steps"), "id": bp.get("id"), "cycle_id": cycle_id}
    st["trial"] = None
    st["heal_turn"] = {"cycle_id": cycle_id, "cycle_index": st.get("cycle_index")}
    row = {"event": "blueprint_trial_close", "cycle_id": cycle_id, "outcome": outcome,
           "blueprint": bp.get("id"), "steps": bp.get("steps"), "parent": bp.get("parent"),
           "operator": bp.get("operator"), "active_after": (st.get("active") or {}).get("id"),
           "verdict": verdict, "authorized": False, "human_signoff_required": False}
    flags = _overlap_flags(rows, start, start + w, bp.get("id"))
    if flags is not None:
        row["window_overlaps"] = flags
        if trial.get("baseline_overlaps") is not None:
            row["baseline_overlaps"] = trial.get("baseline_overlaps")
    if write:
        append_log(row, log_path)
        if outcome != "kept":
            _log_failure(row, bp, st)
    return row


def run_cycle(cycle_id: str = "", *, ctx: Context | None = None, board: Mapping[str, Any] | None = None,
              heal: Mapping[str, Any] | None = None, ev: Mapping[str, Any] | None = None,
              state_path: Path | None = None, log_path: Path | None = None,
              write: bool = True, execute: bool = True) -> dict[str, Any]:
    """One self-build turn: close a finished trial, run the blueprint, maybe open a trial.

    ``write=False, execute=False`` is a read-only dry run (``python -m colony self-build``).
    """
    if not self_mod_ok():
        return {"skipped": "control_arm_or_self_mod_off"}
    st = load_state(state_path)
    heal = heal if heal is not None else _self_heal_state()
    ctx = ctx or Context(cycle_id, exclude_ids=_excluded_targets(heal))
    board = board if board is not None else load_board()
    st["cycle_index"] = int(st.get("cycle_index") or 0) + 1
    if "operator_stats" not in st:  # item 87: learn operator weights from the whole history once
        try:
            st["operator_stats"] = operator_stats_from_log(load_log(log_path))
        except Exception:  # noqa: BLE001
            st["operator_stats"] = {}
    closed = _close(st, board, cycle_id, write=write, log_path=log_path)
    trial = st.get("trial")
    current = (trial or {}).get("blueprint") if isinstance(trial, dict) else st.get("active")
    run = None
    if execute and current and current.get("steps"):
        run = run_blueprint(current, ctx, st.get("macros"))
        st["last_run"] = {"cycle_id": cycle_id, **run}
    opened = None
    rejected: list[dict[str, Any]] = []
    proposal = None
    if not st.get("trial") and st.get("heal_turn") and _heal_had_turn(heal, st["heal_turn"]):
        st["heal_turn"] = None
    reserve = None
    if not st.get("trial") and not heal.get("trial") and not st.get("heal_turn"):
        # Item 104: one exclusive experiment reservation (also a Hive rule trial; fails closed).
        try:
            from colony.experiment_reservation import check as _reserve_check
            reserve = _reserve_check("self_build", states={"self_build": st, "self_heal": heal})
        except Exception as exc:  # noqa: BLE001
            reserve = {"ok": False, "reason": "reservation_unreadable", "detail": type(exc).__name__}
    if not st.get("trial"):
        if heal.get("trial"):
            st["last_skip"] = {"cycle_id": cycle_id, "reason": "self_heal_trial_open"}
        elif reserve is not None and not reserve.get("ok"):
            st["last_skip"] = {"cycle_id": cycle_id, "reason": str(reserve.get("reason"))}
        elif st.get("heal_turn"):
            # Item 84: after a blueprint trial ends, self-heal gets the next turn first.
            st["last_skip"] = {"cycle_id": cycle_id, "reason": "self_heal_turn"}
        else:
            st["last_propose_cycle"] = cycle_id
            proposal, rejected = propose(st, ctx, ev)
            if write and rejected:
                try:  # item 89: why each candidate was rejected
                    from colony.failure_modes import log_rejections
                    log_rejections(cycle_id, rejected)
                except Exception:  # noqa: BLE001
                    pass
            if proposal is None:
                st["last_skip"] = {"cycle_id": cycle_id, "reason": "no_candidate_passed_self_test",
                                   "rejected": rejected[:12]}
            else:
                rows = _paired_rows(board)
                w = window_rows(rows)
                open_row = len(rows) - 1
                base = gain(rows, open_row - w, open_row)
                opened = {"blueprint": proposal, "opened_cycle_id": cycle_id, "code_fp": code_fingerprint(),
                          "opened_cycle_index": st["cycle_index"], "open_row": open_row,
                          "window_rows": w, "baseline_gain": list(base) if base else None}
                bflags = _overlap_flags(rows, open_row - w, open_row, proposal.get("id"))
                if bflags is not None:
                    opened["baseline_overlaps"] = bflags
                if execute:
                    st["trial"] = opened
                    _bump(st.setdefault("component_stats", {}),
                          [s["component"] for s in expand(proposal.get("added") or [], st.get("macros"))],
                          "tried")
                    st["last_skip"] = None
                    if write:
                        append_log({"event": "blueprint_trial_open", "cycle_id": cycle_id,
                                    "blueprint": proposal["id"], "steps": proposal["steps"],
                                    "parent": proposal.get("parent"), "operator": proposal.get("operator"),
                                    "added": proposal.get("added"), "weight": proposal.get("weight"),
                                    "evidence": proposal.get("evidence_detail"),
                                    "self_test": proposal.get("self_test"),
                                    "baseline_gain": opened["baseline_gain"], "window_rows": w,
                                    **({"baseline_overlaps": opened["baseline_overlaps"]}
                                       if "baseline_overlaps" in opened else {}),
                                    "authorized": False, "human_signoff_required": False}, log_path)
    if write:
        save_state(st, state_path)
    return {"ok": True, "cycle_id": cycle_id, "closed": closed, "run": run,
            "opened": opened, "proposal": proposal, "rejected": rejected,
            "active": (st.get("active") or {}).get("id"), "trial": bool(st.get("trial")),
            "last_skip": st.get("last_skip")}


def dry_run(cycle_id: str = "dry_run") -> dict[str, Any]:
    """Read-only: what the generator would try now, and why others were rejected."""
    heal = _self_heal_state()
    ctx = Context(cycle_id, exclude_ids=_excluded_targets(heal))
    st = load_state()
    ev = evidence()
    cands = candidates(st, ev)
    tested = []
    for bp in cands[:20]:
        t = self_test(bp, ctx, st.get("macros"), new_only=bp.get("added") or [])
        tested.append({"id": bp["id"], "operator": bp["operator"], "steps": bp["steps"],
                       "weight": bp["weight"], "self_test": t["reason"], "plan": t.get("plan")})
    return {"active": (st.get("active") or {}).get("id"), "trial_open": bool(st.get("trial")),
            "self_heal_trial_open": bool(heal.get("trial")),
            "excluded_targets": sorted(ctx.exclude_ids),
            "free_authored_slots": ctx.free_authored_slots(),
            "evidence": {k: {kk: v[kk] for kk in ("n_papers", "idea_rank", "cards", "lessons", "boost")}
                         for k, v in ev.items()},
            "candidates": tested}


def format_visibility(state: Mapping[str, Any] | None = None) -> str:
    st = state if state is not None else load_state()
    trial = st.get("trial")
    t = (trial or {}).get("blueprint", {}).get("id") if isinstance(trial, dict) else None
    return (f"self-build: active {(st.get('active') or {}).get('id')}; trial {t or 'none'}; "
            f"kept {st.get('kept_count', 0)}, reverted {st.get('reverted_count', 0)}, "
            f"inconclusive {st.get('inconclusive_count', 0)}; macros {len(st.get('macros') or {})}")


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(dry_run(), indent=1, default=str))
