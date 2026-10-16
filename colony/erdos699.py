"""Erdős Problem #699 dedicated frontier target — bounded evidence, not proof.

Checks, for every n in a range: for all 1 <= i < j <= n/2, some prime p >= i (main) divides
gcd(C(n,i), C(n,j)); and lists every exception of the strict version (p > i).

Two independent C checkers live in society/benchmarks/frontier/erdos699/:
  fast699.c  — prime-free-window reduction (i <= n - prevprime(n)) + Kummer/Lucas + CRT enumeration;
  brute699.c — 'full' mode: no reduction at all (all pairs); 'lite' mode: direct Kummer over every j.

Progress is stored as one JSON file per checked interval under society/systems/erdos699/ranges/,
so parallel CI shards never edit the same file. `status` merges them into a verified-up-to bound.
A counterexample (or a new strict exception with i >= 4) is re-checked with the brute checker and
flagged for HUMAN REVIEW. It is never claimed automatically.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "society" / "benchmarks" / "frontier" / "erdos699"
TARGET = SRC / "target.json"
STATE = ROOT / "society" / "systems" / "erdos699"
RANGES = STATE / "ranges"
STATUS = STATE / "status.json"
REVIEW = STATE / "review.jsonl"
BIN = Path(os.environ.get("ERDOS699_BIN", "/tmp/erdos699-bin"))
LABEL = "bounded evidence, not proof"
START = 4
KNOWN_STRICT = {(10, 3, 5), (16, 2, 6), (28, 3, 14), (28, 5, 14), (244, 3, 122), (512, 2, 147),
                (2048, 2, 713), (2188, 3, 1094), (1594324, 3, 797162)}
CHUNK = 1_000_000


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build() -> dict[str, str]:
    BIN.mkdir(parents=True, exist_ok=True)
    out = {}
    for name in ("fast699", "brute699"):
        exe = BIN / name
        subprocess.run(["gcc", "-O2", "-o", str(exe), str(SRC / f"{name}.c"), "-lm"], check=True)
        out[name] = str(exe)
    return out


def parse(text: str) -> dict:
    strict, main, summary = [], [], ""
    for line in text.splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "STRICT":
            strict.append(tuple(int(x) for x in p[1:4]))
        elif p[0] == "MAIN":
            main.append(tuple(int(x) for x in p[1:4]))
        elif p[0] == "SUMMARY":
            summary = line
    return {"strict": strict, "main": main, "summary": summary}


def run_bin(args: list[str]) -> dict:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{args} failed: {r.stderr.strip()}")
    return parse(r.stdout)


def selftest() -> dict:
    """Gate: reproduce the known strict exceptions <= 3000, zero main <= 10^6, fast == brute(full) <= 3000."""
    b = build()
    small = run_bin([b["fast699"], "4", "3000"])
    want = sorted(t for t in KNOWN_STRICT if t[0] <= 3000)
    ok_small = sorted(small["strict"]) == want and not small["main"]
    brute = run_bin([b["brute699"], "full", "4", "3000"])
    ok_brute = sorted(brute["strict"]) == sorted(small["strict"]) and brute["main"] == small["main"]
    big = run_bin([b["fast699"], "4", "1000000"])
    ok_big = not big["main"] and sorted(big["strict"]) == want
    res = {"ok": ok_small and ok_brute and ok_big, "reproduced_strict": [list(t) for t in small["strict"]],
           "brute_agrees_le_3000": ok_brute, "main_le_1e6": len(big["main"]), "ts": _utc()}
    return res


def _review(hit: tuple, kind: str, brute_bin: str) -> dict:
    n = hit[0]
    chk = run_bin([brute_bin, "lite", str(n), str(n)])
    row = {"ts": _utc(), "kind": kind, "hit": list(hit), "brute_lite_main": [list(t) for t in chk["main"]],
           "brute_lite_strict": [list(t) for t in chk["strict"]], "status": "human_review",
           "label": LABEL, "claimed": False}
    STATE.mkdir(parents=True, exist_ok=True)
    with REVIEW.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def _chunk(fast: str, lo: int, hi: int) -> dict:
    t = time.time()
    r = run_bin([fast, str(lo), str(hi)])
    r["seconds"] = round(time.time() - t, 2)
    r["lo"], r["hi"] = lo, hi
    return r


def run_range(lo: int, hi: int, budget_s: float, jobs: int | None = None, tag: str = "") -> dict:
    """Check [lo,hi] in CHUNK pieces in order, in parallel, until done or budget spent.
    Writes one ranges/<lo>_<hi>.json for the contiguous prefix actually completed."""
    b = build()
    jobs = jobs or os.cpu_count() or 2
    t0 = time.time()
    pieces = [(a, min(a + CHUNK - 1, hi)) for a in range(lo, hi + 1, CHUNK)]
    done: dict[int, dict] = {}
    with cf.ThreadPoolExecutor(jobs) as ex:
        futs = {}
        it = iter(pieces)
        for _ in range(jobs):
            p = next(it, None)
            if p:
                futs[ex.submit(_chunk, b["fast699"], *p)] = p
        while futs:
            fin, _ = cf.wait(futs, return_when=cf.FIRST_COMPLETED)
            for f in fin:
                p = futs.pop(f)
                done[p[0]] = f.result()
                if time.time() - t0 < budget_s:
                    q = next(it, None)
                    if q:
                        futs[ex.submit(_chunk, b["fast699"], *q)] = q
    prefix_hi, secs, strict, main = lo - 1, 0.0, [], []
    for a, _ in pieces:
        if a not in done:
            break
        r = done[a]
        prefix_hi, secs = r["hi"], secs + r["seconds"]
        strict += r["strict"]
        main += r["main"]
    reviews = [_review(h, "main_counterexample", b["brute699"]) for h in main]
    reviews += [_review(h, "new_strict_exception_i_ge_4", b["brute699"]) for h in strict
                if h[1] >= 4 and h not in KNOWN_STRICT]
    rec = {"target": "erdos_699", "lo": lo, "hi": prefix_hi, "complete": prefix_hi == hi, "requested_hi": hi,
           "cpu_seconds": round(secs, 1), "wall_seconds": round(time.time() - t0, 1), "jobs": jobs,
           "main_counterexamples": [list(t) for t in main], "strict_exceptions": [list(t) for t in strict],
           "reviews": len(reviews), "checker": "fast699.c", "label": LABEL, "proof": False, "ts": _utc(), "tag": tag}
    if prefix_hi >= lo:
        RANGES.mkdir(parents=True, exist_ok=True)
        (RANGES / f"{lo:013d}_{prefix_hi:013d}.json").write_text(json.dumps(rec, indent=1) + "\n")
    return rec


def intervals() -> list[tuple[int, int]]:
    iv = []
    for p in sorted(RANGES.glob("*.json")) if RANGES.exists() else []:
        r = json.loads(p.read_text())
        if r["hi"] >= r["lo"]:
            iv.append((r["lo"], r["hi"]))
    iv.sort()
    merged: list[list[int]] = []
    for a, b in iv:
        if merged and a <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [tuple(m) for m in merged]


def verified_up_to() -> int:
    iv = intervals()
    return iv[0][1] if iv and iv[0][0] <= START else START - 1


def gaps(lo: int, hi: int) -> list[tuple[int, int]]:
    out, cur = [], lo
    for a, b in intervals():
        if b < cur:
            continue
        if a > hi:
            break
        if a > cur:
            out.append((cur, min(a - 1, hi)))
        cur = max(cur, b + 1)
    if cur <= hi:
        out.append((cur, hi))
    return out


def plan(lo: int, hi: int, shards: int) -> list[dict]:
    """Split the still-unverified parts of [lo,hi] into ~`shards` pieces of roughly equal cost (~ n^0.15 per n)."""
    todo = gaps(lo, hi)
    total = sum(b - a + 1 for a, b in todo)
    if not total:
        return []
    per = max(CHUNK, -(-total // shards))
    per = -(-per // CHUNK) * CHUNK
    out = []
    for a, b in todo:
        x = a
        while x <= b:
            y = min(b, x + per - 1)
            out.append({"lo": x, "hi": y})
            x = y + 1
    return out


def status(write: bool = True) -> dict:
    rows = [json.loads(p.read_text()) for p in sorted(RANGES.glob("*.json"))] if RANGES.exists() else []
    strict = sorted({tuple(t) for r in rows for t in r["strict_exceptions"]})
    main = sorted({tuple(t) for r in rows for t in r["main_counterexamples"]})
    reviews = [json.loads(x) for x in REVIEW.read_text().splitlines()] if REVIEW.exists() else []
    s = {"target": "erdos_699", "verified_up_to": verified_up_to(), "intervals": intervals(),
         "main_counterexamples": [list(t) for t in main], "strict_exceptions": [list(t) for t in strict],
         "new_strict_i_ge_4": [list(t) for t in strict if t[1] >= 4 and t not in KNOWN_STRICT],
         "human_review_pending": len(reviews),
         "cpu_seconds": round(sum(r["cpu_seconds"] for r in rows), 1),
         "status": "human_review" if (main or reviews) else "open",
         "label": LABEL, "proof": False, "ts": _utc()}
    if write:
        STATE.mkdir(parents=True, exist_ok=True)
        STATUS.write_text(json.dumps(s, indent=1) + "\n")
    return s


def main() -> None:
    ap = argparse.ArgumentParser(prog="colony.erdos699")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    p = sub.add_parser("plan")
    p.add_argument("--lo", type=int, required=True)
    p.add_argument("--hi", type=int, required=True)
    p.add_argument("--shards", type=int, default=20)
    r = sub.add_parser("run")
    r.add_argument("--lo", type=int, required=True)
    r.add_argument("--hi", type=int, required=True)
    r.add_argument("--budget", type=float, default=3600)
    r.add_argument("--jobs", type=int, default=0)
    r.add_argument("--tag", default="")
    sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "selftest":
        res = selftest()
        print(json.dumps(res))
        raise SystemExit(0 if res["ok"] else 1)
    if a.cmd == "plan":
        print(json.dumps(plan(a.lo, a.hi, a.shards)))
    elif a.cmd == "run":
        rec = run_range(a.lo, a.hi, a.budget, a.jobs or None, a.tag)
        print(json.dumps({k: v for k, v in rec.items() if k != "strict_exceptions"} | {"n_strict": len(rec["strict_exceptions"])}))
        if rec["main_counterexamples"]:
            raise SystemExit(3)
    else:
        print(json.dumps(status()))


if __name__ == "__main__":
    main()
