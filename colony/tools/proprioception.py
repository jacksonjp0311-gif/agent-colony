"""Proprioception: the sense of the system's own posture.

Reads the ledger. Writes a posture record. Decides nothing.
Fail-open. Missing files mean a quiet report.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HEAL = ROOT / "society" / "systems" / "self_heal.json"
CRYSTAL = ROOT / "data" / "commons" / "crystallized.jsonl"
EXCHANGE = ROOT / "data" / "commons" / "exchange.jsonl"
TELEMETRY = ROOT / "data" / "commons" / "cycle_telemetry.jsonl"
POSTURE = ROOT / "data" / "commons" / "proprioception.jsonl"


def propriocept(source: str = "one-mind") -> dict:
    """One posture. Fail-open returns an empty dict."""
    posture = {
        "source": source,
        "adopted": 0,
        "reverted": 0,
        "kept": 0,
        "holes": 0,
        "agreed": 0,
        "bias": 0,
        "cycles_since_keep": None,
        "posture": "unknown",
    }
    try:
        if HEAL.exists():
            state = json.loads(HEAL.read_text(encoding="utf-8"))
            posture["adopted"] = int(state.get("adopted_count") or 0)
            posture["reverted"] = int(state.get("reverted_count") or 0)
            posture["cycles_since_keep"] = int(state.get("cycle_index") or 0)
            last = state.get("last_self_change") or {}
            if last.get("event") == "adopt":
                posture["cycles_since_keep"] = 0
        if CRYSTAL.exists():
            for line in CRYSTAL.read_text(encoding="utf-8").splitlines():
                try:
                    if json.loads(line).get("category") == "kept":
                        posture["kept"] += 1
                except Exception:
                    continue
        if EXCHANGE.exists():
            for line in EXCHANGE.read_text(encoding="utf-8").splitlines()[-50:]:
                try:
                    rec = json.loads(line)
                    if rec.get("kind") == "dream" and rec.get("source") == source:
                        extra = rec.get("extra") or {}
                        posture["holes"] = int(extra.get("holes") or 0)
                        posture["agreed"] = int(extra.get("agreed") or 0)
                except Exception:
                    continue
        if TELEMETRY.exists():
            lines = TELEMETRY.read_text(encoding="utf-8").splitlines()
            if lines:
                try:
                    posture["bias"] = int(json.loads(lines[-1]).get("bias_delta") or 0)
                except Exception:
                    pass
        # Posture label. Descriptive, not a decision.
        if posture["holes"] > 0:
            posture["posture"] = "holed"
        elif posture["bias"] and abs(posture["bias"]) > 40:
            posture["posture"] = "moving"
        elif posture["adopted"] > posture["reverted"]:
            posture["posture"] = "learning"
        else:
            posture["posture"] = "steady"
        POSTURE.parent.mkdir(parents=True, exist_ok=True)
        with POSTURE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(posture) + "\n")
        return posture
    except Exception:
        return posture


if __name__ == "__main__":
    import sys
    print(json.dumps(propriocept(sys.argv[1] if len(sys.argv) > 1 else "one-mind"), indent=2))
