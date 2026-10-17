"""Calibrate the frontier generator's fit length FIT_N on a time split of past cycle ids.

For each candidate FIT_N, run the generator from an empty state with seeds = past desk cycle
timestamps (tuning: before 2026-10-16T23:20:31Z; held-out: after), then re-test every surprise
on the farther re-test range. False-surprise rate = surprises that fail the re-test / surprises.
Choice rule (fixed before looking at held-out): the SMALLEST FIT_N whose tuning false-surprise
rate is <= TARGET (smaller fit = more candidate patterns). Held-out is reported, not used.
Writes colony/frontier_calibration.json and docs/FRONTIER_TUNING_LOG.md.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from colony import frontier_conjectures as FC  # noqa: E402

SPLIT = "2026-10-16T23:20:31Z"
GRID = (12, 16, 20, 24, 30, 40)
TARGET = 0.05
N_SEEDS = 6


def seeds() -> tuple[list[str], list[str]]:
    rows = [json.loads(l) for l in (ROOT / "society/benchmarks/conjecture_history.jsonl").read_text().splitlines()
            if l.strip()]
    ts = sorted({r["ts"] for r in rows if r.get("ts")})
    tune = [t for t in ts if t < SPLIT][-N_SEEDS:]
    held = [t for t in ts if t >= SPLIT][:N_SEEDS]
    return tune, held


def run(F: int, seed_list: list[str], T, lookup) -> dict:
    with tempfile.TemporaryDirectory() as d:
        sp = Path(d) / "s.json"
        agg = {"tested": 0, "survived": 0, "falsified": 0, "surprises": 0, "machine_checked": 0, "trivial": 0,
               "duplicate": 0}
        for sd in seed_list:
            s = FC.run_cycle(f"cal-{sd}", state_path=sp, T=T, lookup=lookup, seed=sd, F=F)
            c = s["counts"]
            for k in ("tested", "survived", "falsified", "surprises", "machine_checked", "duplicate"):
                agg[k] += c[k]
            agg["trivial"] += sum(v for k, v in c.items() if k.startswith("trivial_"))
        st = json.loads(sp.read_text())
    sur = [r for r in st["registry"].values() if r.get("unknown")]
    bad = 0
    for r in sur:
        c = {"kind": r["kind"], "params": r["params"], "_le": FC.parse(r["lhs"]),
             "_re": FC.parse(r["rhs"]) if r.get("rhs") else None}
        lo = int(r.get("retested_to") or r["range"][1])
        res = FC.test_claim(c, T, lo, FC.RETEST_CHEAP, FC.RETEST_EXP)
        if r.get("falsified_later") or (res["tested"] and not res["survived"]):
            bad += 1
    agg["false_surprises"] = bad
    agg["false_surprise_rate"] = round(bad / len(sur), 4) if sur else None
    agg["heldout_kill_rate"] = round(agg["falsified"] / agg["tested"], 4) if agg["tested"] else None
    agg["brier"] = round(st["predictions"]["brier_sum"] / st["predictions"]["n"], 4) if st["predictions"]["n"] else None
    return agg


def main() -> None:
    T = FC.tables()
    lookup = FC.default_lookup()
    tune, held = seeds()
    res = {F: {"tuning": run(F, tune, T, lookup)} for F in GRID}
    ok = [F for F in GRID if (res[F]["tuning"]["false_surprise_rate"] or 0) <= TARGET
          and res[F]["tuning"]["surprises"] > 0]
    pick = ok[0] if ok else max(GRID)
    res[pick]["held_out"] = run(pick, held, T, lookup)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cal = {"version": 1, "calibrated_at": ts, "FIT_N": pick, "target_false_surprise_rate": TARGET, "split": SPLIT,
           "oeis_index": "available" if lookup else "absent", "seeds": {"tuning": tune, "held_out": held},
           "grid": {str(F): v for F, v in res.items()}}
    (ROOT / "colony/frontier_calibration.json").write_text(json.dumps(cal, indent=1) + "\n", encoding="utf-8")
    lines = ["# Frontier conjecture generator — tuning log", "",
             f"Calibrated {ts} by `evals/frontier/calibrate.py`. Seeds = past desk cycle timestamps; tuning before "
             f"{SPLIT}, held-out after. Rule fixed in advance: smallest FIT_N with tuning false-surprise rate <= "
             f"{TARGET} (a surprise that fails the farther re-test is a false surprise). OEIS index: {cal['oeis_index']}.",
             "", "| FIT_N | split | tested | survived | held-out kills | surprises | false surprises | machine-checked | trivial dropped | Brier |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for F, v in res.items():
        for sp_, a in v.items():
            lines.append(f"| {F} | {sp_} | {a['tested']} | {a['survived']} | {a['falsified']} | {a['surprises']} | "
                         f"{a['false_surprises']} ({a['false_surprise_rate']}) | {a['machine_checked']} | {a['trivial']} | {a['brier']} |")
    lines += ["", f"Chosen FIT_N = {pick}.", ""]
    (ROOT / "docs/FRONTIER_TUNING_LOG.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
