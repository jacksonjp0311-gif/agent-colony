"""Colony reads the ear. It does not write the receipt.

Pattern: fetch the last Witness line. Record whether the ear
reported transfer. Do not open a trial. Do not raise a cap.
Do not change Wilson. A keep still requires a score that
beats the prior. Fail-open.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STORE = ROOT / "data" / "commons" / "ear.jsonl"
WITNESS = "https://raw.githubusercontent.com/jacksonjp0311-gif/witness/main/data/commons/witness.jsonl"


def read_ear() -> dict | None:
    """Last Witness line that carries a frozen receipt. Unavailable is None."""
    import urllib.request
    try:
        with urllib.request.urlopen(WITNESS, timeout=12) as r:
            lines = [ln for ln in r.read().decode().splitlines() if ln.strip()]
        for line in reversed(lines):
            try:
                rec = json.loads(line)
            except Exception:
                continue
            frozen = rec.get("frozen")
            if isinstance(frozen, dict):
                return frozen
        return None
    except Exception:
        return None


def observe() -> dict:
    """One observation. Records what the ear said. Changes nothing else."""
    frozen = read_ear()
    rec = {
        "source": "colony",
        "kind": "ear",
        "available": frozen is not None,
        "task": (frozen or {}).get("task"),
        "real_score": (frozen or {}).get("real_score"),
        "sham_score": (frozen or {}).get("sham_score"),
        "transfer": (frozen or {}).get("transfer"),
    }
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        with STORE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
    return rec
