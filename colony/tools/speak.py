"""Read-only mouth. Says what the ledger already says. Changes nothing."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HEAL = ROOT / "society" / "systems" / "self_heal.json"
CRYSTAL = ROOT / "data" / "commons" / "crystallized.jsonl"
EXCHANGE = ROOT / "data" / "commons" / "exchange.jsonl"
TELEMETRY = ROOT / "data" / "commons" / "cycle_telemetry.jsonl"
SPEAK_LOG = ROOT / "data" / "commons" / "speak.jsonl"


def speak(source: str = "one-mind") -> str:
    """One true sentence from the logs. Fail-open returns a short note."""
    try:
        adopted = reverted = 0
        last_knob = ""
        if HEAL.exists():
            state = json.loads(HEAL.read_text(encoding="utf-8"))
            adopted = int(state.get("adopted_count") or 0)
            reverted = int(state.get("reverted_count") or 0)
            last = state.get("last_self_change") or {}
            if last.get("event") == "adopt":
                last_knob = f"{last.get('knob')} {last.get('direction')} to {last.get('to')}"
        kept = stable = 0
        if CRYSTAL.exists():
            for line in CRYSTAL.read_text(encoding="utf-8").splitlines():
                try:
                    cat = json.loads(line).get("category")
                    if cat == "kept":
                        kept += 1
                    elif cat == "stable":
                        stable += 1
                except Exception:
                    continue
        foreign = 0
        if EXCHANGE.exists():
            for line in EXCHANGE.read_text(encoding="utf-8").splitlines()[-400:]:
                try:
                    rec = json.loads(line)
                    if rec.get("source") and rec.get("source") != source:
                        foreign += 1
                except Exception:
                    continue
        bias = 0
        if TELEMETRY.exists():
            lines = TELEMETRY.read_text(encoding="utf-8").splitlines()
            if lines:
                try:
                    bias = int(json.loads(lines[-1]).get("bias_delta") or 0)
                except Exception:
                    bias = 0
        parts = [f"{source} has {adopted} adopts and {reverted} reverts"]
        if last_knob:
            parts.append(f"last keep was {last_knob}")
        parts.append(f"{kept} kept records, {stable} stable")
        parts.append(f"{foreign} foreign receipts in view")
        if bias:
            parts.append(f"last bias delta {bias}")
        sentence = ". ".join(parts) + "."
        try:
            SPEAK_LOG.parent.mkdir(parents=True, exist_ok=True)
            with SPEAK_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"source": source, "sentence": sentence}) + "\n")
        except Exception:
            pass
        return sentence
    except Exception as e:
        return f"{source} could not speak: {e}"


if __name__ == "__main__":
    import sys
    print(speak(sys.argv[1] if len(sys.argv) > 1 else "one-mind"))
