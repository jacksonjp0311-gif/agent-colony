"""Watch — the between-time swarm.

Runs when evolve finishes. Does not propose. Does not keep.
Reloads memory, dreams, listens, writes one receipt.
Fail-open.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STORE = ROOT / "data" / "commons" / "crystallized.jsonl"
EXCHANGE = ROOT / "data" / "commons" / "exchange.jsonl"


def reload_check(source: str = "one-mind") -> dict:
    """How many crystallized fingerprints a fresh process can retrieve."""
    try:
        from colony.tools.crystallize import retrieve
        if not STORE.exists():
            return {"checked": 0, "holes": 0}
        holes = 0
        checked = 0
        for line in STORE.read_text(encoding="utf-8").splitlines()[-64:]:
            try:
                rec = json.loads(line)
                fp = rec.get("fingerprint")
                if not fp:
                    continue
                checked += 1
                if not retrieve(fp, rec.get("source") or source):
                    holes += 1
            except Exception:
                continue
        return {"checked": checked, "holes": holes}
    except Exception:
        return {"checked": 0, "holes": 0}


def listen(source: str = "one-mind") -> int:
    """Pull the other lineage and count foreign fingerprints."""
    try:
        from colony.tools.reciprocal_exchange import merge_remote
        from colony.tools.symbiotic_exchange import foreign_fingerprints
        merge_remote(source)
        return len(foreign_fingerprints(source, limit=200))
    except Exception:
        return 0


def dream(source: str = "one-mind") -> int:
    """Prune by use. Returns count kept. Fail-open."""
    try:
        if not STORE.exists():
            return 0
        from colony.tools.surgical_implants import prune_weak
        recs = []
        for line in STORE.read_text(encoding="utf-8").splitlines():
            try:
                recs.append(json.loads(line))
            except Exception:
                continue
        kept = prune_weak(recs, max_keep=64)
        STORE.write_text("".join(json.dumps(r) + "\n" for r in kept), encoding="utf-8")
        return len(kept)
    except Exception:
        return 0


def echo(source: str, report: dict) -> None:
    """One receipt the other lineage can read. Dream talks."""
    try:
        from colony.tools.symbiotic_exchange import append_receipt
        other = "colony" if source == "one-mind" else "one-mind"
        append_receipt(
            source,
            "dream",
            f"dream:{other}:{report.get('checked', 0)}",
            "observed",
            {**report, "to": other, "from": source},
        )
    except Exception:
        pass


def run(source: str = "one-mind") -> dict:
    report = reload_check(source)
    report["foreign"] = listen(source)
    report["kept"] = dream(source)
    echo(source, report)
    return report


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "one-mind"
    print(json.dumps(run(src)))
