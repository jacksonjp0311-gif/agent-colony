"""Item 100: break treatment vs control fitness into its weighted components (read-only).

aggregate = sum(weight_i * term_i) (colony/fitness.py compute_fitness). For the last N rows of
each arm's fitness history this prints each term's mean, the weighted contribution and the
treatment - control gap, sorted by gap, so the biggest drag is the first negative line. It also
shows that Oracle passes are not a fitness term at all (only the sieve kill-rate term is).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = {"tribute_quality": 0.18, "gather_coverage": 0.14, "build_reuse": 0.14, "comm_reply_rate": 0.11,
           "reply_quality": 0.06, "commons_signal": 0.04, "prize_boost": 0.16, "kill_rate_term": 0.07,
           "novelty": 0.05, "lesson_uptake": 0.05}
ARMS = {"treatment": ROOT / "society/systems/fitness_history.jsonl",
        "control": ROOT / "control/society/systems/fitness_history.jsonl"}


def tail(path: Path, n: int) -> list[dict]:
    rows = []
    try:
        for ln in path.read_text(encoding="utf-8").splitlines()[-n:]:
            try:
                rows.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return rows


def means(rows: list[dict]) -> dict[str, float]:
    keys = list(WEIGHTS) + ["aggregate"]
    return {k: sum(float(r.get(k) or 0.0) for r in rows) / max(1, len(rows)) for k in keys}


def decompose(n: int = 30) -> dict:
    m = {arm: means(tail(p, n)) for arm, p in ARMS.items()}
    lines = []
    for k, w in WEIGHTS.items():
        t, c = m["treatment"][k], m["control"][k]
        lines.append({"term": k, "weight": w, "treatment": round(t, 4), "control": round(c, 4),
                      "weighted_gap": round(w * (t - c), 4)})
    lines.sort(key=lambda r: r["weighted_gap"])
    return {"n": n, "aggregate": {a: round(v["aggregate"], 4) for a, v in m.items()}, "terms": lines,
            "biggest_drag": lines[0]["term"] if lines and lines[0]["weighted_gap"] < 0 else None}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=30)
    d = decompose(ap.parse_args().n)
    print(f"last {d['n']} rows: aggregate treatment {d['aggregate']['treatment']} vs control {d['aggregate']['control']}")
    for r in d["terms"]:
        print(f"{r['term']:<16} w={r['weight']:<5} T={r['treatment']:<7} C={r['control']:<7} weighted gap={r['weighted_gap']:+.4f}")
    print(f"biggest drag: {d['biggest_drag']}")
    print("note: Oracle passes are not a fitness term; only kill_rate_term (the sieve) sees the Oracle.")
