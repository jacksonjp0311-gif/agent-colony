"""Run all colony benchmarks; write latest.json + history.jsonl + WITNESS_BENCH.md."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from society.benchmarks.fft_microbench import run as run_fft
from society.benchmarks.fft_stress_microbench import run as run_fft_stress
from society.benchmarks.autodiff_microbench import run as run_autodiff
from society.benchmarks.lemma_microbench import run as run_lemma

ROOT = Path(__file__).resolve().parent


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> dict:
    results = [run_fft(), run_fft_stress(), run_autodiff(), run_lemma()]
    scores = [float(r.get("score") or 0.0) for r in results]
    agg = round(sum(scores) / max(len(scores), 1), 4)
    ok_all = all(bool(r.get("ok")) for r in results)
    payload = {
        "ts": _utc(),
        "ok_all": ok_all,
        "aggregate_score": agg,
        "benches": results,
        "note": "Prize fitness must read these scores — institution names do not count.",
    }
    latest = ROOT / "latest.json"
    prev = None
    if latest.exists():
        try:
            prev = json.loads(latest.read_text())
        except Exception:
            prev = None
    latest.write_text(json.dumps(payload, indent=2) + "\n")
    with (ROOT / "history.jsonl").open("a") as f:
        f.write(json.dumps(payload) + "\n")
    delta = None
    if prev and isinstance(prev.get("aggregate_score"), (int, float)):
        delta = round(agg - float(prev["aggregate_score"]), 4)
    lines = [
        f"# Benchmark witness — {payload['ts']}",
        "",
        f"- ok_all: `{ok_all}`",
        f"- aggregate_score: `{agg}`",
        f"- delta_vs_previous: `{delta}`",
        "",
    ]
    for r in results:
        lines.append(
            f"- `{r.get('bench')}` ok={r.get('ok')} score={r.get('score')} "
            f"err={r.get('max_abs_err')} s={r.get('seconds')} impl={r.get('impl_id')}"
        )
    lines.append("")
    (ROOT / "WITNESS_BENCH.md").write_text("\n".join(lines) + "\n")
    return payload


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
