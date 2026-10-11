"""Trust-loop experiments: matched ablations, stripped baseline, frozen holdout evaluation.

    PYTHONPATH=. python3 scripts/trust_experiments.py ablation --pool dev
    PYTHONPATH=. python3 scripts/trust_experiments.py stripped --pool dev
    PYTHONPATH=. python3 scripts/trust_experiments.py holdout   # ONE exposure of holdout_v1

Isolation (enforced by construction): every colony run happens in a throwaway copy of the
repo under /tmp/trust_ws/ that excludes .git/, evaluation/ and evidence/. Only candidate
*source* (names + check functions) is injected; labels, witnesses and the independent
evaluator never enter the colony workspace. The parent process scores runs with
evaluation/evaluator.py after the colony process has exited. (Procedural part: the colony
process is not OS-sandboxed; it could read an absolute path. A static test asserts colony/
never references evaluation/, and the manifest hash is checked before and after.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "evaluation"))
import evaluator  # noqa: E402

EVID = ROOT / "evidence" / "2026-10-11-trust-loop"
WS_BASE = Path("/tmp/trust_ws")
SEEDS = [11, 23, 37, 41, 53]
ARMS = {"L1C1": {"COLONY_LEARNING": "1", "COLONY_CHALLENGER": "1"},
        "L0C1": {"COLONY_LEARNING": "0", "COLONY_CHALLENGER": "1"},
        "L1C0": {"COLONY_LEARNING": "1", "COLONY_CHALLENGER": "0"},
        "L0C0": {"COLONY_LEARNING": "0", "COLONY_CHALLENGER": "0"}}
IGNORE = shutil.ignore_patterns(".git", "evaluation", "evidence", "__pycache__", "*.pyc", ".lemma_backups")

WORKER = r'''
import json, sys, time
from colony.conjecture_desk import improve_once
out = []
K, tag = int(sys.argv[1]), sys.argv[2]
for i in range(K):
    t0 = time.perf_counter()
    r = improve_once(cycle_id=f"{tag}_c{i:02d}")
    out.append({"i": i, "decision": r.decision, "mutation": r.mutation, "kind": r.kind,
                "self_rejected": r.self_rejected, "promotion": (r.promotion or {}).get("category"),
                "seconds": round(time.perf_counter() - t0, 3), "note": (r.note or "")[:300]})
print("@@RESULT@@" + json.dumps(out))
'''


def manifest_ok() -> bool:
    sys.path.insert(0, str(ROOT))
    from colony.trust.gate import manifest_check
    return bool(manifest_check(ROOT)["ok"])


def inject(ws: Path, pool: str, seed: int) -> list[str]:
    cands = json.loads((ROOT / "evaluation" / "pools" / pool / "candidates.json").read_text())["candidates"]
    impl = ws / "society" / "benchmarks" / "artifacts" / "lemma_impl.py"
    src = impl.read_text()
    marker = "# Mutable catalog the conjecture desk may extend / mutate."
    block = "".join(c["helpers_src"] + c["check_src"] + "\n" for c in cands)
    src = src.replace(marker, block + "\n" + marker, 1)
    hi = src.index("HARD_TIER_LEMMAS:")
    close = src.index("\n]\n", hi)
    entries = "".join(f'\n    ("{c["name"]}", check_{c["name"]}, False),' for c in cands)
    src = src[:close] + entries + src[close:]
    impl.write_text(src)
    order = [c["name"] for c in cands]
    random.Random(seed).shuffle(order)
    ext = ws / "society" / "systems" / "mutation_catalog_ext.json"
    data = json.loads(ext.read_text()) if ext.exists() else {"version": 1, "mutations": []}
    data["mutations"] = list(data.get("mutations") or []) + [
        {"name": n, "kind": "hard_enable", "snippet": f"enable:{n}", "status": "candidate"} for n in order]
    ext.write_text(json.dumps(data, indent=1))
    return order


def _lines(p: Path) -> int:
    return sum(1 for _ in p.open()) if p.exists() else 0


def run_one(pool: str, arm: str, seed: int, cycles: int, code_root: Path = ROOT) -> dict:
    ws = WS_BASE / f"{pool}_{arm}_s{seed}_{os.getpid()}"
    if ws.exists():
        shutil.rmtree(ws)
    shutil.copytree(code_root, ws, ignore=IGNORE)
    assert not (ws / "evaluation").exists(), "isolation breach: evaluation/ copied into workspace"
    order = inject(ws, pool, seed)
    o0 = _lines(ws / "data" / "commons" / "oracle.jsonl")
    c0 = _lines(ws / "data" / "commons" / "self_challenge.jsonl")
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("COLONY_")}, **ARMS[arm],
           "PYTHONPATH": str(ws), "PYTHONDONTWRITEBYTECODE": "1"}
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "-c", WORKER, str(cycles), f"trust_{pool}_{arm}_s{seed}"],
                       cwd=ws, env=env, capture_output=True, text=True, timeout=1800)
    wall = time.perf_counter() - t0
    if "@@RESULT@@" not in p.stdout:
        raise RuntimeError(f"worker failed {arm} s{seed}: {p.stderr[-2000:]}")
    cyc = json.loads(p.stdout.split("@@RESULT@@", 1)[1])
    n_oracle = _lines(ws / "data" / "commons" / "oracle.jsonl") - o0
    n_chal = _lines(ws / "data" / "commons" / "self_challenge.jsonl") - c0
    shutil.rmtree(ws, ignore_errors=True)
    kept = [c["mutation"] for c in cyc if c["decision"] == "keep"]
    picks: dict[str, int] = {}
    fails: dict[str, int] = {}
    for c in cyc:
        if c["mutation"]:
            picks[c["mutation"]] = picks.get(c["mutation"], 0) + 1
            if c["decision"] != "keep":
                fails[c["mutation"]] = fails.get(c["mutation"], 0) + 1
    sc = evaluator.score_run(pool, kept)
    blocked = sorted({c["mutation"] for c in cyc if c["self_rejected"]})
    truth = evaluator.judge_pool(pool)
    return {
        "pool": pool, "arm": arm, "seed": seed, "cycles": cycles, "pick_order_seeded": order,
        "wall_s": round(wall, 2), "oracle_calls": n_oracle, "challenger_calls": n_chal,
        "bench_runs_approx": 2 * sum(1 for c in cyc if c["mutation"]),
        "verified": sc["verified"], "n_verified": len(sc["verified"]),
        "harmful_kept": sc["harmful_kept"], "n_harmful_kept": len(sc["harmful_kept"]),
        "coverage_only_kept": sc["coverage_only_kept"],
        "sound_not_kept": sc["sound_not_kept"],
        "repeated_failures": sum(v - 1 for v in fails.values() if v > 1),
        "distinct_candidates_tried": len([m for m in picks if m in truth]),
        "challenger_blocked": blocked,
        "harmful_blocked_by_challenger": [b for b in blocked if truth.get(b, {}).get("truth") == "unsound"],
        "useful_blocked_by_challenger": [b for b in blocked if truth.get(b, {}).get("truth") == "sound_useful"],
        "non_pool_keeps": [k for k in kept if k not in truth],
        "cycles_detail": cyc,
        "worker_stderr_tail": p.stderr[-400:],
    }


def summarize(rows: list[dict]) -> dict:
    out = {}
    for arm in sorted({r["arm"] for r in rows}):
        rs = [r for r in rows if r["arm"] == arm]
        def ms(k):
            v = [float(r[k]) for r in rs]
            return {"mean": round(statistics.mean(v), 3), "sd": round(statistics.stdev(v), 3) if len(v) > 1 else 0.0,
                    "min": min(v), "max": max(v), "values": v}
        nv = sum(r["n_verified"] for r in rs)
        out[arm] = {"n_runs": len(rs), "verified": ms("n_verified"), "harmful_kept": ms("n_harmful_kept"),
                    "repeated_failures": ms("repeated_failures"), "distinct_tried": ms("distinct_candidates_tried"),
                    "wall_s": ms("wall_s"), "oracle_calls": ms("oracle_calls"), "challenger_calls": ms("challenger_calls"),
                    "cycles_per_verified": round(sum(r["cycles"] for r in rs) / nv, 2) if nv else None,
                    "wall_s_per_verified": round(sum(r["wall_s"] for r in rs) / nv, 2) if nv else None}
    return out


def paired(rows: list[dict], a: str, b: str, key: str) -> dict:
    by = {(r["arm"], r["seed"]): r for r in rows}
    diffs = [by[(a, s)][key] - by[(b, s)][key] for s in sorted({r["seed"] for r in rows}) if (a, s) in by and (b, s) in by]
    # exact sign-flip permutation test on paired differences (two-sided)
    import itertools
    obs = abs(sum(diffs))
    n_ge = tot = 0
    for signs in itertools.product((1, -1), repeat=len(diffs)):
        tot += 1
        if abs(sum(s * d for s, d in zip(signs, diffs))) >= obs - 1e-12:
            n_ge += 1
    return {"comparison": f"{a} - {b}", "metric": key, "paired_diffs": diffs,
            "mean_diff": round(statistics.mean(diffs), 3) if diffs else None,
            "sign_flip_p_two_sided": round(n_ge / tot, 4) if tot else None, "n_pairs": len(diffs)}


def stripped(pool: str) -> dict:
    """Stripped baseline: bench-only keep rule (no Challenger, no Oracle, no learning).
    Each candidate is enabled alone in a fresh workspace; kept iff the in-window bench is green."""
    ws = WS_BASE / f"stripped_{pool}_{os.getpid()}"
    if ws.exists():
        shutil.rmtree(ws)
    shutil.copytree(ROOT, ws, ignore=IGNORE)
    inject(ws, pool, 0)
    code = r'''
import json, re
from pathlib import Path
from society.benchmarks.lemma_microbench import run
p = Path("society/benchmarks/artifacts/lemma_impl.py"); base = p.read_text()
names = re.findall(r'\("(pool_[a-z0-9_]+)", check_', base)
out = {}
for n in names:
    s = re.sub(r'(\("%s", check_%s, )False\)' % (n, n), r'\1True)', base)
    p.write_text(s); r = run(); out[n] = bool(r["ok"])
p.write_text(base)
print("@@RESULT@@" + json.dumps(out))
'''
    p = subprocess.run([sys.executable, "-c", code], cwd=ws, env={**os.environ, "PYTHONPATH": str(ws)},
                       capture_output=True, text=True, timeout=600)
    shutil.rmtree(ws, ignore_errors=True)
    res = json.loads(p.stdout.split("@@RESULT@@", 1)[1])
    kept = [n for n, ok in res.items() if ok]
    sc = evaluator.score_run(pool, kept)
    return {"pool": pool, "rule": "bench_only_keep_if_in_window_green", "bench_green": res, **sc,
            "n_verified": len(sc["verified"]), "n_harmful_kept": len(sc["harmful_kept"])}


def ablation(pool: str, cycles: int, arms: list[str], seeds: list[int], jobs: int, code_root: Path = ROOT) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor
    tasks = [(pool, a, s, cycles) for a in arms for s in seeds]
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        return list(ex.map(lambda t: run_one(*t, code_root=code_root), tasks))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["ablation", "stripped", "holdout"])
    ap.add_argument("--pool", default="dev")
    ap.add_argument("--cycles", type=int, default=14)
    ap.add_argument("--arms", default="L1C1,L0C1,L1C0,L0C0")
    ap.add_argument("--seeds", default=",".join(map(str, SEEDS)))
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--out", default="")
    ap.add_argument("--label", default="")
    ap.add_argument("--baseline-ref", default="", help="holdout only: also run this git ref's code in the SAME exposure")
    a = ap.parse_args()
    if not manifest_ok():
        print("INTEGRITY: evaluation/MANIFEST.sha256 mismatch — refusing to run", file=sys.stderr)
        return 3
    WS_BASE.mkdir(parents=True, exist_ok=True)
    seeds = [int(x) for x in a.seeds.split(",")]
    arms = a.arms.split(",")
    t0 = time.time()
    if a.cmd == "stripped":
        res = stripped(a.pool)
    else:
        pool = a.pool
        if a.cmd == "holdout":
            pool = "holdout_v1"
            log = ROOT / "evaluation" / "EXPOSURES.jsonl"
            prior = [json.loads(l) for l in log.read_text().splitlines() if l.strip()] if log.exists() else []
            if prior:
                print(f"NOTE: holdout_v1 already exposed {len(prior)}x; this run is a RE-EXPOSURE "
                      "(results must be reported as reused data, not unseen)", file=sys.stderr)
        rows = ablation(pool, a.cycles, arms, seeds, a.jobs)
        base_rows: list[dict] = []
        if a.cmd == "holdout" and a.baseline_ref:
            wt = Path("/tmp/trust_ws/baseline_ref")
            if wt.exists():
                subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT)
            subprocess.run(["git", "worktree", "add", "--detach", str(wt), a.baseline_ref], cwd=ROOT, check=True,
                           capture_output=True)
            base_rows = ablation(pool, a.cycles, arms, seeds, a.jobs, code_root=wt)
            for r in base_rows:
                r["arm"] = "BASE_" + r["arm"]
            subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT)
        rows = rows + base_rows
        res = {"pool": pool, "arms": arms, "seeds": seeds, "cycles": a.cycles, "label": a.label,
               "summary": summarize(rows),
               "paired": [paired(rows, "L1C1", "L0C1", k) for k in ("n_verified", "repeated_failures", "distinct_candidates_tried")]
               + [paired(rows, "L1C1", "L1C0", k) for k in ("n_verified", "n_harmful_kept")]
               + ([paired(rows, x, "BASE_" + x, k) for x in arms for k in ("n_verified", "n_harmful_kept", "repeated_failures")]
                  if any(r["arm"].startswith("BASE_") for r in rows) else []),
               "runs": rows}
        if a.cmd == "holdout":
            with (ROOT / "evaluation" / "EXPOSURES.jsonl").open("a") as f:
                f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "pool": pool, "label": a.label,
                                    "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
                                    "arms": arms, "seeds": seeds, "baseline_ref": a.baseline_ref}) + "\n")
    res["elapsed_s"] = round(time.time() - t0, 1)
    if not manifest_ok():
        res["integrity"] = "MANIFEST_CHANGED_DURING_RUN"
    out = Path(a.out) if a.out else EVID / f"{a.cmd}_{a.pool if a.cmd != 'holdout' else 'holdout_v1'}{('_' + a.label) if a.label else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res.get("summary", {k: v for k, v in res.items() if k != "bench_green"}), indent=1))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
