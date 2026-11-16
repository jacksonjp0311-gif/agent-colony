"""Item 104: a native, bounded scheduler for the colony's new-data work allocation.

Why: ``colony.new_data`` / ``colony.sparse`` rank targets by learned terms-per-CPU-second plus an
unbounded UCB bonus, push each target ONCE with whatever fits in the per-target budget, and then
mark it done (one claim per b-file version) or intractable for good. Only CPU (process_time) is
budgeted; wall time is not measured. A big target that does not fit in one push is never
resumed, and nothing bounds how long an item can wait behind a cheap one.

This module is a small, deterministic scheduling layer (no LLM, no new dependency). The ideas
are general scheduling practice; the aging rule follows the *idea* of the Apache-2.0 Superfluid
scheduler (``starved_after``: a queued item counts a starved tick only when a YOUNGER item was
served instead; at the bound it is served first, oldest first). No Superfluid code is used,
copied or run, and none of its KV-cache / fleet machinery applies here.

1. Aging + oldest-first tie-break: a job passed over by a younger job ``AGE_BOUND`` times is
   served next; ties (equal value) go to the oldest admission. Bounded exploration: at most
   ``EXPLORE_SHARE`` of a cycle's CPU budget goes to never-served jobs ahead of value order.
2. Per-work-type smoothed cost (EWMA of CPU and wall seconds per unit) is a HYPOTHESIS: every
   chunk logs the smoothed prediction and the per-job last-measured prediction against the
   actual cost; the smoothed model drives chunk sizing only once it has ``HYP_MIN_SAMPLES``
   chunks of that type and a lower mean |log error| than the per-job model. Until then the
   larger (safer) of the two predictions sizes the chunk.
3. Bounded chunks with safe checkpoints: a job is a half-open unit range [cursor, goal). Each
   pick runs ONE chunk sized to fit the remaining CPU *and* wall budget; a chunk that would not
   fit is not started. Results are accepted (strict reuse key = work type, target, method tag,
   unit index) and the receipt written BEFORE the cursor moves, so a crash between the two
   recomputes the chunk and the re-accepted values are deduplicated, never counted twice. A
   recomputed value that disagrees with an accepted one is a conflict: nothing is accepted and
   the job is quarantined.
4. CPU (``time.process_time``) and wall (``time.perf_counter``) are both measured per chunk
   and per cycle; overruns of either are counted, never hidden.
5. Scheduling receipts (``data/commons/work_receipts.jsonl``) are separate from math findings
   (``society/frontier/claims.json`` is untouched by this module).

Switch ``COLONY_WORK_SCHED`` = shadow (default) | off. Always off on the control arm. In shadow
the new-data stage reports what the scheduler sees (eligible / resumable / parked targets) next to
its own summary; it changes no allocation and writes no claim. A live mode needs new_data's claim
record to accept chunked k-ranges first (not done in item 104); the frozen-workload A/B
(scripts/item104_sched_ab.py) is the evidence for or against doing that.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parent.parent
RECEIPTS = ROOT / "data" / "commons" / "work_receipts.jsonl"
MODES = ("shadow", "off")   # live (claims per chunk) is not wired yet: see the item-104 notes

AGE_BOUND = 3            # picks passed over by a younger job before it is served first
EXPLORE_SHARE = 0.20     # max share of a cycle's CPU budget spent on never-served jobs first
CHUNK_SHARE = 0.5        # a chunk may plan at most this share of what is left of the cycle
MIN_CHUNK_UNITS = 8
MAX_CHUNK_UNITS = 4000
EWMA_ALPHA = 0.3
HYP_MIN_SAMPLES = 6
SAFETY = 1.25            # planned cost * SAFETY must fit (one chunk may still overrun; counted)


def mode() -> str:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return "off"
    except Exception:  # noqa: BLE001
        return "off"
    v = (os.environ.get("COLONY_WORK_SCHED") or "shadow").strip().lower()
    return v if v in MODES else "shadow"


# --------------------------------------------------------------------------- jobs and keys
def reuse_key(work_type: str, target: str, method_tag: str, unit: int) -> str:
    """Strict reuse key of ONE verified unit (a term index): same key = same question."""
    return f"{work_type}|{target}|{method_tag}|{int(unit)}"


@dataclass
class Job:
    work_type: str
    target: str
    method_tag: str
    cursor: int                  # next unit to compute (inclusive)
    goal: int                    # end (exclusive)
    admitted: int                # admission sequence: lower = older
    value: float = 1.0           # caller's value per unit (ordering only)
    starved: int = 0
    served: int = 0
    first_served_tick: int | None = None
    done_tick: int | None = None
    status: str = "open"         # open | done | quarantined
    k_cpu: dict[str, float] | None = None   # per-job last measured cost coefficients (baseline estimator)
    k_wall: dict[str, float] | None = None
    why: str = ""

    @property
    def id(self) -> str:
        return f"{self.work_type}|{self.target}|{self.method_tag}"


# --------------------------------------------------------------------------- cost hypothesis
PREFIX_EXP = 1.2   # same exponent new_data.estimate_cost scales its prefix cost with


def _pred(k: Mapping[str, float] | None, lo: int, hi: int) -> float | None:
    """Two-part cost: a prefix part (method A sieves / iterates up to ``hi``) + a per-unit part."""
    if not k:
        return None
    return float(k.get("prefix", 0.0)) * max(hi, 1) ** PREFIX_EXP + float(k.get("unit", 0.0)) * max(hi - lo, 0)


@dataclass
class CostModel:
    """Per-work-type EWMA of the two cost coefficients (CPU and wall), with a logged test of
    whether the smoothed per-type model predicts chunk cost better than the per-job last one."""
    cpu: dict[str, dict[str, float]] = field(default_factory=dict)
    wall: dict[str, dict[str, float]] = field(default_factory=dict)
    n: dict[str, int] = field(default_factory=dict)
    err_smooth: dict[str, list[float]] = field(default_factory=dict)
    err_job: dict[str, list[float]] = field(default_factory=dict)

    def smoothed_accepted(self, wt: str) -> bool:
        es, ej = self.err_smooth.get(wt) or [], self.err_job.get(wt) or []
        if min(len(es), len(ej)) < HYP_MIN_SAMPLES:
            return False
        return sum(es) / len(es) < sum(ej) / len(ej)

    def predict(self, job: "Job", lo: int, hi: int) -> tuple[float | None, float | None, str]:
        """(cpu s, wall s, estimator) for the chunk [lo, hi) of ``job``."""
        s_c, s_w = _pred(self.cpu.get(job.work_type), lo, hi), _pred(self.wall.get(job.work_type), lo, hi)
        j_c, j_w = _pred(job.k_cpu, lo, hi), _pred(job.k_wall, lo, hi)
        if s_c is None and j_c is None:
            return None, None, "none"
        if self.smoothed_accepted(job.work_type) and s_c is not None:
            return s_c, (s_w if s_w is not None else s_c), "smoothed"
        cs = [x for x in (s_c, j_c) if x is not None]
        ws = [x for x in (s_w, j_w) if x is not None]
        return max(cs), (max(ws) if ws else max(cs)), "conservative_max"

    @staticmethod
    def _coeffs(total: float, parts: Mapping[str, Any] | None, lo: int, hi: int) -> dict[str, float]:
        units = max(1, hi - lo)
        if parts and parts.get("prefix_s") is not None:
            pre = max(float(parts.get("prefix_s") or 0.0), 0.0)
            rest = max(total - pre, 0.0)
            return {"prefix": pre / max(hi, 1) ** PREFIX_EXP, "unit": rest / units}
        return {"prefix": 0.0, "unit": max(total, 1e-7) / units}

    @staticmethod
    def _ewma(old: dict[str, float] | None, new: dict[str, float]) -> dict[str, float]:
        if not old:
            return dict(new)
        return {k: (1 - EWMA_ALPHA) * float(old.get(k, 0.0)) + EWMA_ALPHA * float(new[k]) for k in new}

    def observe(self, job: "Job", lo: int, hi: int, cpu_s: float, wall_s: float,
                parts: Mapping[str, Any] | None = None) -> dict[str, Any]:
        wt = job.work_type
        actual = max(cpu_s, 1e-6)
        rec: dict[str, Any] = {}
        for name, k, store in (("smoothed", self.cpu.get(wt), self.err_smooth),
                               ("job_last", job.k_cpu, self.err_job)):
            pred = _pred(k, lo, hi)
            if pred is not None:
                e = abs(math.log(max(pred, 1e-9) / actual))
                store.setdefault(wt, []).append(round(e, 4))
                store[wt] = store[wt][-200:]
                rec[f"err_{name}"] = round(e, 4)
        kc = self._coeffs(cpu_s, parts, lo, hi)
        wparts = None
        if parts and parts.get("prefix_wall_s") is not None:
            wparts = {"prefix_s": parts.get("prefix_wall_s")}
        kw = self._coeffs(wall_s, wparts, lo, hi)
        self.cpu[wt] = self._ewma(self.cpu.get(wt), kc)
        self.wall[wt] = self._ewma(self.wall.get(wt), kw)
        self.n[wt] = self.n.get(wt, 0) + 1
        job.k_cpu, job.k_wall = kc, kw
        return rec

    def report(self) -> dict[str, Any]:
        out = {}
        for wt in sorted(set(self.err_smooth) | set(self.err_job) | set(self.n)):
            es, ej = self.err_smooth.get(wt) or [], self.err_job.get(wt) or []
            out[wt] = {"chunks": self.n.get(wt, 0),
                       "mean_abs_log_err_smoothed": round(sum(es) / len(es), 4) if es else None,
                       "mean_abs_log_err_job_last": round(sum(ej) / len(ej), 4) if ej else None,
                       "smoothed_accepted": self.smoothed_accepted(wt)}
        return out


# --------------------------------------------------------------------------- results store
class Results:
    """Accepted verified units by strict reuse key. Duplicates are skipped, conflicts refused."""

    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.duplicates = 0
        self.conflicts = 0
        self.retracted = 0

    def accept(self, job: Job, values: Mapping[int, int]) -> dict[str, int]:
        keys = {n: reuse_key(job.work_type, job.target, job.method_tag, n) for n in values}
        bad = [n for n, k in keys.items() if k in self.values and self.values[k] != int(values[n])]
        if bad:
            self.conflicts += len(bad)
            return {"accepted": 0, "duplicate": 0, "conflict": len(bad)}
        new = dup = 0
        for n, k in keys.items():
            if k in self.values:
                dup += 1
            else:
                self.values[k] = int(values[n])
                new += 1
        self.duplicates += dup
        return {"accepted": new, "duplicate": dup, "conflict": 0}

    def retract(self, job: Job) -> int:
        """A target whose methods disagreed anywhere is unverified as a whole (the same rule
        new_data applies to a push): its earlier accepted units are withdrawn, not kept."""
        pre = f"{job.work_type}|{job.target}|{job.method_tag}|"
        gone = [k for k in self.values if k.startswith(pre)]
        for k in gone:
            del self.values[k]
        self.retracted += len(gone)
        return len(gone)


# --------------------------------------------------------------------------- scheduler
Runner = Callable[[Job, int, int], Mapping[str, Any]]


class Scheduler:
    """Bounded chunk scheduler. ``runner(job, lo, hi)`` computes units [lo, hi) by two methods
    and returns ``{"verified": bool, "values": {unit: value}}`` (values only if both agree)."""

    def __init__(self, runner: Runner, *, receipts: list[dict[str, Any]] | None = None,
                 age_bound: int = AGE_BOUND, explore_share: float = EXPLORE_SHARE,
                 chunk_share: float = CHUNK_SHARE, clock_cpu: Callable[[], float] = time.process_time,
                 clock_wall: Callable[[], float] = time.perf_counter) -> None:
        self.runner = runner
        self.jobs: list[Job] = []
        self.cost = CostModel()
        self.results = Results()
        self.receipts = receipts if receipts is not None else []
        self.age_bound, self.explore_share, self.chunk_share = age_bound, explore_share, chunk_share
        self.cpu, self.wall = clock_cpu, clock_wall
        self.tick = 0
        self.seq = 0
        self.overhead_cpu = 0.0
        self.work_cpu = 0.0
        self.work_wall = 0.0
        self.chunk_overruns = 0
        self.cycle_overruns_cpu = 0
        self.cycle_overruns_wall = 0
        self.crash_after_accept: set[tuple[str, int]] = set()   # test hook: (job id, chunk lo)

    # ---- admission
    def admit(self, work_type: str, target: str, method_tag: str, lo: int, goal: int,
              value: float = 1.0) -> Job:
        jid = f"{work_type}|{target}|{method_tag}"
        for j in self.jobs:   # same question twice: one job (the strict key dedupes units anyway)
            if j.id == jid:
                j.goal = max(j.goal, int(goal))
                if j.status == "done" and j.cursor < j.goal:
                    j.status, j.done_tick = "open", None
                return j
        j = Job(work_type, target, method_tag, int(lo), int(goal), self.seq, float(value))
        self.seq += 1
        self.jobs.append(j)
        return j

    # ---- planning
    def _plan_units(self, job: Job, cpu_left: float, wall_left: float) -> tuple[int, float, float, str]:
        """Largest chunk whose predicted CPU and wall cost (x SAFETY) fit ``chunk_share`` of what is left."""
        room = self.chunk_share * min(cpu_left, wall_left)
        remaining = job.goal - job.cursor
        lo = job.cursor
        c, w, which = self.cost.predict(job, lo, lo + min(remaining, MIN_CHUNK_UNITS))
        if c is None:   # never measured: a minimal probe chunk (still must leave budget)
            return (min(remaining, MIN_CHUNK_UNITS), 0.0, 0.0, "probe") if room > 0 else (0, 0.0, 0.0, "probe")

        def fits(u: int) -> tuple[bool, float, float]:
            pc, pw, _ = self.cost.predict(job, lo, lo + u)
            pc, pw = float(pc or 0.0), float(pw if pw is not None else pc or 0.0)
            return max(pc, pw) * SAFETY <= room, pc, pw
        u_min = min(remaining, MIN_CHUNK_UNITS)
        ok, pc, pw = fits(u_min)
        if not ok:
            return 0, 0.0, 0.0, which
        best = (u_min, pc, pw)
        hi_u = min(remaining, MAX_CHUNK_UNITS)
        lo_u = u_min
        while lo_u < hi_u:      # binary search on units (cost is monotone in units)
            mid = (lo_u + hi_u + 1) // 2
            ok, pc, pw = fits(mid)
            if ok:
                lo_u, best = mid, (mid, pc, pw)
            else:
                hi_u = mid - 1
        return best[0], best[1], best[2], which

    def _rank_value(self, job: Job) -> float:
        hi = min(job.goal, job.cursor + MIN_CHUNK_UNITS)
        c, _w, _ = self.cost.predict(job, job.cursor, hi)
        return job.value * (hi - job.cursor) / max(c or 1e-6, 1e-9)

    def _pick(self, cands: list[Job], explore_left: float) -> tuple[Job, str]:
        starving = [j for j in cands if j.starved >= self.age_bound]
        if starving:
            return min(starving, key=lambda j: j.admitted), "aging"
        fresh = [j for j in cands if j.served == 0]
        if fresh and explore_left > 0:
            return min(fresh, key=lambda j: j.admitted), "explore"
        return min(cands, key=lambda j: (-self._rank_value(j), j.admitted)), "value"

    # ---- one cycle
    def run_cycle(self, cpu_budget: float, wall_budget: float, cycle: int = 0,
                  max_picks: int = 1000) -> dict[str, Any]:
        t_cpu0, t_wall0 = self.cpu(), self.wall()
        explore_left = self.explore_share * cpu_budget
        # A measured job whose smallest chunk cannot fit even a fresh cycle is parked as
        # over_budget (visible, re-checked every cycle: it reopens if its cost estimate drops).
        o0 = self.cpu()
        for j in self.jobs:
            if j.status not in ("open", "over_budget") or j.k_cpu is None:
                continue
            fits = self._plan_units(j, cpu_budget, wall_budget)[0] > 0
            if j.status == "open" and not fits:
                j.status, j.why = "over_budget", "min_chunk_over_cycle_budget"
                self.receipts.append({"cycle": cycle, "job": j.id, "event": "parked_over_budget",
                                      "cursor": j.cursor})
            elif j.status == "over_budget" and fits:
                j.status, j.why = "open", ""
                self.receipts.append({"cycle": cycle, "job": j.id, "event": "reopened", "cursor": j.cursor})
        self.overhead_cpu += self.cpu() - o0
        picks: list[dict[str, Any]] = []
        skipped: set[str] = set()
        for _ in range(max_picks):
            o0 = self.cpu()
            used_cpu, used_wall = self.cpu() - t_cpu0, self.wall() - t_wall0
            cpu_left, wall_left = cpu_budget - used_cpu, wall_budget - used_wall
            cands = []
            plans = {}
            for j in self.jobs:
                if j.status != "open" or j.id in skipped:
                    continue
                p = self._plan_units(j, cpu_left, wall_left)
                if p[0] > 0:
                    cands.append(j)
                    plans[j.id] = p
            if not cands:
                self.overhead_cpu += self.cpu() - o0
                break
            job, why = self._pick(cands, explore_left)
            units, pc, pw, which = plans[job.id]
            lo, hi = job.cursor, job.cursor + units
            self.overhead_cpu += self.cpu() - o0
            c0, w0 = self.cpu(), self.wall()
            try:
                out = dict(self.runner(job, lo, hi) or {})
            except MemoryError:
                out = {"verified": False, "why": "memory"}
            except Exception as exc:  # noqa: BLE001
                out = {"verified": False, "why": f"error:{type(exc).__name__}"}
            dc, dw = self.cpu() - c0, self.wall() - w0
            o1 = self.cpu()
            self.work_cpu += dc
            self.work_wall += dw
            self.tick += 1
            room = self.chunk_share * min(cpu_left, wall_left)
            over = dc > room or dw > room
            self.chunk_overruns += int(over)
            hyp = self.cost.observe(job, lo, hi, dc, dw, out.get("parts"))
            if job.first_served_tick is None:
                job.first_served_tick = cycle
            job.served += 1
            # aging: older jobs that waited while this (younger) one ran count one starved tick
            for j in cands:
                if j is not job and j.admitted < job.admitted:
                    j.starved += 1
            job.starved = 0
            if why == "explore":
                explore_left -= dc
            rec = {"cycle": cycle, "job": job.id, "lo": lo, "hi": hi, "units": units, "why": why,
                   "estimator": which, "pred_cpu_s": round(pc, 6), "pred_wall_s": round(pw, 6),
                   "cpu_s": round(dc, 6), "wall_s": round(dw, 6), "overrun": bool(over), **hyp}
            if out.get("verified"):
                vals = {int(k): int(v) for k, v in (out.get("values") or {}).items()}
                acc = self.results.accept(job, vals)
                rec.update(acc)
                if acc["conflict"]:
                    job.status, job.why = "quarantined", "conflict_with_accepted_value"
                    rec["retracted"] = self.results.retract(job)
                elif (job.id, lo) in self.crash_after_accept:
                    # test hook: accepted + receipt written, then the process "dies" before the cursor moves
                    self.crash_after_accept.discard((job.id, lo))
                    rec["crashed_before_checkpoint"] = True
                    self.receipts.append(rec)
                    self.overhead_cpu += self.cpu() - o1
                    picks.append(rec)
                    continue
                else:
                    job.cursor = hi
                    if job.cursor >= job.goal:
                        job.status, job.done_tick = "done", cycle
            else:
                job.status, job.why = "quarantined", str(out.get("why") or "unverified")
                rec["verified"] = False
                rec["retracted"] = self.results.retract(job)
            rec["cursor_after"] = job.cursor
            self.receipts.append(rec)
            picks.append(rec)
            self.overhead_cpu += self.cpu() - o1
        used_cpu, used_wall = self.cpu() - t_cpu0, self.wall() - t_wall0
        self.cycle_overruns_cpu += int(used_cpu > cpu_budget)
        self.cycle_overruns_wall += int(used_wall > wall_budget)
        return {"cycle": cycle, "picks": len(picks), "cpu_s": round(used_cpu, 4), "wall_s": round(used_wall, 4),
                "over_cpu": used_cpu > cpu_budget, "over_wall": used_wall > wall_budget}

    # ---- persistence (resumable cursor)
    def snapshot(self) -> dict[str, Any]:
        return {"jobs": [asdict(j) for j in self.jobs], "seq": self.seq, "tick": self.tick,
                "cost": asdict(self.cost), "results": dict(self.results.values)}

    @classmethod
    def restore(cls, snap: Mapping[str, Any], runner: Runner, **kw: Any) -> "Scheduler":
        s = cls(runner, **kw)
        s.jobs = [Job(**j) for j in snap.get("jobs") or []]
        s.seq, s.tick = int(snap.get("seq") or 0), int(snap.get("tick") or 0)
        c = snap.get("cost") or {}
        s.cost = CostModel(**{k: dict(c.get(k) or {}) for k in ("cpu", "wall", "n", "err_smooth", "err_job")})
        s.results.values = dict(snap.get("results") or {})
        return s


def append_receipts(rows: Iterable[Mapping[str, Any]], path: Path | None = None) -> int:
    """Append-only scheduling receipts (never math findings)."""
    p = Path(path or RECEIPTS)
    rows = list(rows)
    if not rows:
        return 0
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(dict(r), sort_keys=True) + "\n")
    return len(rows)


def digest(values: Mapping[str, int]) -> str:
    """Order-free digest of accepted results (schedule invariance checks)."""
    h = hashlib.sha256()
    for k in sorted(values):
        h.update(f"{k}={values[k]}\n".encode())
    return h.hexdigest()[:16]


def shadow_view(idx: Mapping[str, Any], done_fn: Callable[[Mapping[str, Any]], bool] | None = None) -> dict[str, Any]:
    """Shadow report for the live new-data stage: what the scheduler would have to work with.

    Read-only. ``eligible`` = matched, not intractable, not done for this b-file version (what
    new_data.run_cycle may push now); ``intractable`` = marked for good by the one-shot push (the
    chunked scheduler could resume these only if a chunk fits a cycle); ``done`` = one claim per
    b-file version already made."""
    if mode() == "off":
        return {"mode": "off"}
    ents = list((idx.get("entries") or {}).values()) if isinstance(idx, Mapping) else []
    sp = list((idx.get("sparse") or {}).values()) if isinstance(idx, Mapping) else []
    done = done_fn or (lambda e: bool(e.get("done_for_sha")))
    out = {"mode": mode(), "entries": len(ents),
           "eligible": sum(1 for e in ents if e.get("status") == "matched" and not e.get("intractable")
                           and not done(e)),
           "intractable": sorted(str(e.get("anum") or e.get("item")) for e in ents if e.get("intractable")),
           "done": sum(1 for e in ents if done(e)),
           "sparse_entries": len(sp),
           "sparse_eligible": sum(1 for e in sp if e.get("status") == "matched" and not e.get("claimed")
                                  and not e.get("intractable"))}
    return out
