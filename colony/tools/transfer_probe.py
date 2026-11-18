"""Transfer probe.

Pattern: same fingerprint, scored with the prior and without.
A later session continues this by reading the delta.
A hit is +60. A miss is 0. The probe does not decide.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "commons" / "transfer_probe.jsonl"


def probe(fingerprint: str, base_score: int = 100) -> dict:
    """One matched pair. Fail-open returns zeros."""
    result = {
        "fingerprint": fingerprint,
        "base": base_score,
        "with_prior": base_score,
        "without_prior": base_score,
        "delta": 0,
        "kept_hit": False,
    }
    try:
        from colony.tools.symbiotic_exchange import kept_prior
        bonus = kept_prior(fingerprint)
        result["with_prior"] = base_score + bonus
        result["delta"] = bonus
        result["kept_hit"] = bonus > 0
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")
        return result
    except Exception:
        return result


def run_known() -> list:
    """Probe a few known kept knobs and one unknown."""
    samples = [
        "park_cycles:up:10",
        "deep_digits:up:6350",
        "gf_term_cap:up:2310",
        "no_such_knob:up:1",
    ]
    return [probe(fp) for fp in samples]


if __name__ == "__main__":
    for r in run_known():
        print(json.dumps(r))
