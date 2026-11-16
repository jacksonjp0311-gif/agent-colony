"""Item 104: frozen-workload A/B of the new-data work allocation, equal CPU and wall budgets.

A (baseline) = the allocation policy ``colony.new_data.run_cycle`` uses today, emulated on a
frozen in-memory workload: rank by learned terms per CPU-second (b-file-length weighted) plus
the UCB bonus; push each target once with min(per-target budget, what is left), halving N until
the learned cost estimate fits (``_calibrate`` probe first) else ``intractable`` for good; a
verified push marks the target done (one claim per b-file version); at most 4 pushes a cycle;
only CPU (process_time) is checked; an unverified push stays open and is retried.

B (treatment) = ``colony.work_scheduler.Scheduler`` (aging + oldest-first, bounded exploration,
two-part smoothed cost hypothesis, bounded chunks, resumable cursor, CPU + wall budgets).

Both run the colony's REAL arithmetic (``colony.new_data.MENU`` method A / method B, verified two
ways) on the same frozen targets with the same per-cycle CPU and wall budgets. No network, no
claims written, nothing in society/ or data/ touched.

Adversarial cases in the workload: a cheap huge "hog", a "giant" whose span does not fit one
per-target budget, a cost "cliff" (method B 30x slower past a point), a "poison" target (method
B wrong at one unit), a duplicate admission, two late arrivals, a "wall" target (I/O-like sleep:
wall time with no CPU), plus a crash between accept and checkpoint (treatment only).

    python scripts/item104_sched_ab.py [--cycles 15] [--cpu 0.6] [--wall 0.8] [--reps 3] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from colony.new_data import MENU  # noqa: E402
from colony import work_scheduler as W  # noqa: E402

# name, menu key, frontier f (last "published" index), span G, admit cycle, special
WORKLOAD = [
    ("hog", "col_steps", 20000, 300000, 0, None),
    ("col_max", "col_max", 30000, 3000, 0, None),
    ("col_odd", "col_odd", 30000, 3000, 0, None),
    ("gb_min", "gb_min", 30000, 3000, 0, None),
    ("gb_close", "gb_close", 20000, 2000, 0, None),
    ("giant", "gb_u_odd", 6000, 1500, 0, None),
    ("cliff", "col_stop", 30000, 3000, 0, "cliff"),
    ("poison", "col_even", 30000, 3000, 0, "poison"),
    ("dup_col_max", "col_max", 30000, 3000, 2, "dup"),
    ("late_gbcls", "gb_min_cls4_1", 10000, 2000, 4, None),
    ("late_colmax2", "col_max", 60000, 2000, 4, "alias"),
    ("wall", "gb_close", 30000, 2000, 0, "wall"),
]
CLIFF_AT, CLIFF_X = 1000, 30
POISON_AT = 700
WALL_SLEEP = 0.25


def _fns(key: str, special: str | None, f: int) -> tuple[Callable, Callable]:
    a, b = MENU[key]["a"], MENU[key]["b"]
    if special == "cliff":
        def b2(ns):
            out = b(ns)
            slow = [n for n in ns if n > f + CLIFF_AT]
            for _ in range(CLIFF_X - 1):
                if slow:
                    b(slow)
            return out
        return a, b2
    if special == "poison":
        def b3(ns):
            return [v + 1 if n == f + POISON_AT else v for n, v in zip(ns, b(ns))]
        return a, b3
    if special == "wall":
        def a2(N):
            time.sleep(WALL_SLEEP)
            return a(N)
        return a2, b
    return a, b


def _target(name: str, key: str, special: str | None) -> str:
    # dup = the same question as col_max (same strict key); alias = same sequence, other range
    return "col_max" if special == "dup" else name


def truth(key: str, ns: list[int]) -> list[int]:
    return [int(x) for x in MENU[key]["b"](ns)]


# --------------------------------------------------------------------------- A: baseline emulation
def run_baseline(cycles: int, cpu_budget: float, wall_budget: float) -> dict[str, Any]:
    target_budget = cpu_budget * 0.5          # TARGET_BUDGET_S / CYCLE_BUDGET_S = 20 / 40
    stop_left = cpu_budget * 0.05             # "left < 2" of 40
    push_per_cycle = 4
    ents: dict[str, dict[str, Any]] = {}
    results = W.Results()
    log = {"overrun_cpu": 0, "overrun_wall": 0, "overhead": 0.0, "work_cpu": 0.0, "work_wall": 0.0}
    for cyc in range(cycles):
        t_c, t_w = time.process_time(), time.perf_counter()
        for name, key, f, g, adm, sp in WORKLOAD:
            tgt = _target(name, key, sp)
            if adm == cyc and tgt not in ents:
                a, b = _fns(key, sp, f)
                ents[tgt] = {"name": tgt, "key": key, "f": f, "goal": f + g, "a": a, "b": b, "admit": adm,
                             "stats": {"tries": 0, "beyond": 0, "cpu_s": 0.0}, "status": "open",
                             "first": None, "done": None, "accepted": 0}
            elif adm == cyc and tgt in ents:
                log["dup_admissions"] = log.get("dup_admissions", 0) + 1
        o0 = time.process_time()
        live = [e for e in ents.values() if e["status"] == "open"]
        total = sum(e["stats"]["tries"] for e in live)

        def score(e):
            s = e["stats"]
            ev = (s["beyond"] + 1.0) / (s["cpu_s"] + 1.0) * (1.0 / (1.0 + e["f"] / 50.0))
            return ev + math.sqrt(2 * math.log(total + 2) / (s["tries"] + 1))
        live.sort(key=lambda e: -score(e))
        log["overhead"] += time.process_time() - o0
        pushed = 0
        for e in live:
            left = cpu_budget - (time.process_time() - t_c)
            if left < stop_left:
                break
            budget = min(target_budget, left)
            c0, w0 = time.process_time(), time.perf_counter()
            r = _baseline_push(e, budget)
            dc, dw = time.process_time() - c0, time.perf_counter() - w0
            log["work_cpu"] += dc
            log["work_wall"] += dw
            e["stats"]["tries"] += 1
            e["stats"]["cpu_s"] += dc
            if e["first"] is None:
                e["first"] = cyc
            if r["status"] == "intractable":
                e["status"] = "intractable"
            elif r["status"] == "new":
                acc = results.accept(W.Job("terms", e["name"], "A/B", e["f"] + 1, e["goal"], 0), r["values"])
                e["accepted"] += acc["accepted"]
                e["stats"]["beyond"] += len(r["values"])
                e["status"] = "done"          # one claim per published frontier version
                e["done"] = cyc
                e["reached_goal"] = max(r["values"]) + 1 >= e["goal"]
            pushed += 1
            if pushed >= push_per_cycle:
                break
        uc, uw = time.process_time() - t_c, time.perf_counter() - t_w
        log["overrun_cpu"] += int(uc > cpu_budget)
        log["overrun_wall"] += int(uw > wall_budget)
    return {"ents": ents, "results": results, "log": log}


def _baseline_push(e: dict[str, Any], budget: float) -> dict[str, Any]:
    f, goal = e["f"], e["goal"]
    if "cost" not in e:                       # _calibrate: method A at min(f, 5000), B on 21 points
        n = min(f, 5000)
        t = time.process_time()
        e["a"](n)
        ta = time.process_time() - t
        t = time.process_time()
        e["b"](list(range(max(1, n - 20), n + 1)))
        tb = (time.process_time() - t) / 21
        e["cost"] = {"N": n, "cpu_s": max(ta, 1e-4), "b_per_term_s": tb}

    def est(N):
        c = e["cost"]
        return float(c["cpu_s"]) * (N / c["N"]) ** 1.2 + float(c.get("b_per_term_s") or 0.0) * (N - f)
    N = goal - 1
    while N > f + 10 and est(N) > budget:
        N = f + (N - f) // 2
    if est(N) > budget:
        return {"status": "intractable"}
    t0 = time.process_time()
    va = e["a"](N)
    e["cost"] = {"N": N, "cpu_s": max(time.process_time() - t0, 1e-4),
                 "b_per_term_s": e["cost"].get("b_per_term_s")}
    ns = list(range(f + 1, N + 1))
    vb = e["b"](ns)
    vals = [va[n - 1] for n in ns]
    if [int(x) for x in vals] != [int(x) for x in vb]:
        return {"status": "unverified"}
    return {"status": "new", "values": {n: int(v) for n, v in zip(ns, vals)}}


# --------------------------------------------------------------------------- B: scheduler
def run_treatment(cycles: int, cpu_budget: float, wall_budget: float, *, crash: bool = True,
                  order: list[int] | None = None, chunk_share: float = W.CHUNK_SHARE) -> dict[str, Any]:
    fns: dict[str, tuple[Callable, Callable, str]] = {}

    def runner(job: W.Job, lo: int, hi: int) -> dict[str, Any]:
        a, b, _key = fns[job.target]
        c0, w0 = time.process_time(), time.perf_counter()
        va = a(hi - 1)
        pre, pre_w = time.process_time() - c0, time.perf_counter() - w0
        ns = list(range(lo, hi))
        vb = b(ns)
        vals = [int(va[n - 1]) for n in ns]
        ok = vals == [int(x) for x in vb]
        return {"verified": ok, "values": dict(zip(ns, vals)) if ok else {}, "why": "" if ok else "method_b_disagrees",
                "parts": {"prefix_s": pre, "prefix_wall_s": pre_w}}
    s = W.Scheduler(runner, chunk_share=chunk_share)
    admit_cycle: dict[str, int] = {}
    wl = [WORKLOAD[i] for i in (order or range(len(WORKLOAD)))]
    dup = 0
    for cyc in range(cycles):
        for name, key, f, g, adm, sp in wl:
            if adm != cyc:
                continue
            tgt = _target(name, key, sp)
            if tgt in fns:
                dup += 1
            a, b = _fns(key, sp, f)
            fns.setdefault(tgt, (a, b, key))
            j = s.admit(key, tgt, "A/B", f + 1, f + g + 1)   # work type = the algorithm (menu key)
            admit_cycle.setdefault(j.id, cyc)
            if crash and name == "col_odd" and cyc == 0:
                s.crash_after_accept.add((j.id, f + 1))
        s.run_cycle(cpu_budget, wall_budget, cycle=cyc)
    return {"sched": s, "admit": admit_cycle, "fns": fns, "dup_admissions": dup}


# --------------------------------------------------------------------------- metrics
def _summ(xs: list[float]) -> dict[str, Any]:
    return {"mean": round(statistics.mean(xs), 2) if xs else None, "max": max(xs) if xs else None, "n": len(xs)}


def metrics_baseline(out: dict[str, Any], cycles: int) -> dict[str, Any]:
    ents, res, log = out["ents"], out["results"], out["log"]
    honest = [e for e in ents.values() if e["name"] != "poison"]
    goal_units = sum(e["goal"] - e["f"] - 1 for e in honest)
    wrong = _wrong(res.values, {e["name"]: e["key"] for e in ents.values()})
    waits = [e["first"] - e["admit"] for e in honest if e["first"] is not None]
    lat = [e["done"] - e["admit"] for e in honest if e.get("reached_goal")]
    return {
        "verified_units": len(res.values), "coverage_targets": f"{sum(1 for e in honest if e['accepted'])}/{len(honest)}",
        "coverage_units": round(len(res.values) / goal_units, 4),
        "targets_completed_to_goal": sum(1 for e in honest if e.get("reached_goal")),
        "targets_done_partial": sum(1 for e in honest if e["status"] == "done" and not e.get("reached_goal")),
        "intractable": sorted(e["name"] for e in ents.values() if e["status"] == "intractable"),
        "poison_accepted_units": sum(1 for k in res.values if k.split("|")[1] == "poison"),
        "poison_retries": ents.get("poison", {}).get("stats", {}).get("tries"),
        "wait_cycles": _summ(waits), "never_served": sum(1 for e in honest if e["first"] is None),
        "latency_cycles_to_goal": _summ(lat),
        "overhead_share": round(log["overhead"] / max(log["overhead"] + log["work_cpu"], 1e-9), 5),
        "cycle_overruns_cpu": log["overrun_cpu"], "cycle_overruns_wall": log["overrun_wall"],
        "work_cpu_s": round(log["work_cpu"], 3), "work_wall_s": round(log["work_wall"], 3),
        "wrong_accepted": wrong, "duplicates_skipped": res.duplicates, "conflicts": res.conflicts,
        "useful_units_per_cpu_s": round(len(res.values) / max(log["work_cpu"], 1e-9), 1),
        "per_target_units": _per_target(res.values),
        "verified_units_excluding_hog": sum(v for t, v in _per_target(res.values).items() if t != "hog"),
    }


def metrics_treatment(out: dict[str, Any], cycles: int) -> dict[str, Any]:
    s: W.Scheduler = out["sched"]
    honest = [j for j in s.jobs if j.target != "poison"]
    goal_units = sum(j.goal - (j.goal - (j.goal - j.cursor)) for j in [])  # placeholder (overwritten)
    goal_units = 0
    for name, key, f, g, adm, sp in WORKLOAD:
        if sp not in ("dup", "poison"):
            goal_units += g
    per = {}
    for k in s.results.values:
        t = k.split("|")[1]
        per[t] = per.get(t, 0) + 1
    waits = [j.first_served_tick - out["admit"][j.id] for j in honest if j.first_served_tick is not None]
    lat = [j.done_tick - out["admit"][j.id] for j in honest if j.done_tick is not None]
    wrong = _wrong(s.results.values, {t: v[2] for t, v in out["fns"].items()})
    return {
        "verified_units": len(s.results.values),
        "coverage_targets": f"{sum(1 for j in honest if per.get(j.target))}/{len(honest)}",
        "coverage_units": round(len(s.results.values) / goal_units, 4),
        "targets_completed_to_goal": sum(1 for j in honest if j.status == "done"),
        "quarantined": sorted(f"{j.target}:{j.why}" for j in s.jobs if j.status == "quarantined"),
        "over_budget": sorted(j.target for j in s.jobs if j.status == "over_budget"),
        "poison_accepted_units": per.get("poison", 0),
        "wait_cycles": _summ(waits), "never_served": sum(1 for j in honest if j.first_served_tick is None),
        "latency_cycles_to_goal": _summ(lat),
        "overhead_share": round(s.overhead_cpu / max(s.overhead_cpu + s.work_cpu, 1e-9), 5),
        "cycle_overruns_cpu": s.cycle_overruns_cpu, "cycle_overruns_wall": s.cycle_overruns_wall,
        "chunk_overruns": s.chunk_overruns,
        "work_cpu_s": round(s.work_cpu, 3), "work_wall_s": round(s.work_wall, 3),
        "wrong_accepted": wrong, "duplicates_skipped": s.results.duplicates, "conflicts": s.results.conflicts,
        "crash_recovered": any(r.get("crashed_before_checkpoint") for r in s.receipts),
        "chunks": sum(1 for r in s.receipts if "units" in r),
        "dup_admissions_merged": out["dup_admissions"],
        "useful_units_per_cpu_s": round(len(s.results.values) / max(s.work_cpu, 1e-9), 1),
        "retracted_units": s.results.retracted,
        "per_target_units": _per_target(s.results.values),
        "verified_units_excluding_hog": sum(v for t, v in _per_target(s.results.values).items() if t != "hog"),
        "cost_hypothesis": s.cost.report(),
        "picks_by_reason": {w: sum(1 for r in s.receipts if r.get("why") == w) for w in ("aging", "explore", "value")},
    }


def _per_target(values: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for k in values:
        t = k.split("|")[1]
        out[t] = out.get(t, 0) + 1
    return dict(sorted(out.items()))


def _wrong(values: dict[str, int], keys: dict[str, str]) -> int:
    """Accepted units that differ from an independent clean recomputation (method B, unwrapped)."""
    by: dict[str, list[tuple[int, int]]] = {}
    for k, v in values.items():
        _wt, tgt, _tag, n = k.split("|")
        by.setdefault(tgt, []).append((int(n), v))
    bad = 0
    for tgt, pairs in by.items():
        pairs.sort()
        ns = [n for n, _ in pairs]
        tv = truth(keys[tgt], ns)
        bad += sum(1 for (n, v), t in zip(pairs, tv) if v != t)
    return bad


def invariance(cycles: int, cpu: float, wall: float) -> dict[str, Any]:
    """Same frozen targets under different schedules: accepted values must agree on every common unit."""
    runs = [run_treatment(cycles, cpu, wall, crash=False),
            run_treatment(cycles, cpu * 0.5, wall * 0.5, crash=True, order=list(reversed(range(len(WORKLOAD))))),
            run_treatment(cycles, cpu, wall, crash=False, chunk_share=0.2)]
    vals = [r["sched"].results.values for r in runs]
    common = set(vals[0]) & set(vals[1]) & set(vals[2])
    disagree = sum(1 for k in common if len({v[k] for v in vals}) > 1)
    return {"schedules": 3, "common_units": len(common), "disagreements_on_common_units": disagree,
            "digests_on_common": sorted({W.digest({k: v[k] for k in common}) for v in vals})}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=15)
    ap.add_argument("--cpu", type=float, default=0.6)
    ap.add_argument("--wall", type=float, default=0.8)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    reps = []
    for i in range(a.reps):
        if i % 2 == 0:
            A = metrics_baseline(run_baseline(a.cycles, a.cpu, a.wall), a.cycles)
            B = metrics_treatment(run_treatment(a.cycles, a.cpu, a.wall), a.cycles)
        else:
            B = metrics_treatment(run_treatment(a.cycles, a.cpu, a.wall), a.cycles)
            A = metrics_baseline(run_baseline(a.cycles, a.cpu, a.wall), a.cycles)
        reps.append({"A_baseline": A, "B_scheduler": B})
    out = {"budgets": {"cycles": a.cycles, "cpu_s_per_cycle": a.cpu, "wall_s_per_cycle": a.wall},
           "reps": reps, "invariance": invariance(a.cycles, a.cpu, a.wall)}
    print(json.dumps(out, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
