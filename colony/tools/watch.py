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
# Item 116: crystallized.jsonl is append-only (crystallize() appends). downscale()
# used to rewrite it in place; its compacted view now goes to this derived file,
# which is a regenerated snapshot, not a log.
COMPACT = ROOT / "data" / "commons" / "crystallized_compact.jsonl"
WATCH_EXCHANGE = ROOT / "data" / "commons" / "exchange_watch.jsonl"


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


def replay(source: str = "one-mind") -> dict:
    """NREM: re-score crystallized fingerprints in order. Mark reactivated."""
    reactivated = []
    holes = []
    try:
        from colony.tools.crystallize import retrieve
        if not STORE.exists():
            return {"reactivated": [], "holes": []}
        for line in STORE.read_text(encoding="utf-8").splitlines()[-64:]:
            try:
                rec = json.loads(line)
                fp = rec.get("fingerprint")
                if not fp:
                    continue
                if retrieve(fp, rec.get("source") or source):
                    rec["reactivated"] = True
                    reactivated.append(rec)
                else:
                    holes.append(fp)
            except Exception:
                continue
        return {"reactivated": reactivated, "holes": holes}
    except Exception:
        return {"reactivated": [], "holes": []}


def integrate(source: str, reactivated: list) -> int:
    """Raise rank when the other lineage dreamed a fingerprint we hold.

    Agreement is a prior, not a keep. Fail-open.
    """
    try:
        from colony.tools.symbiotic_exchange import foreign_fingerprints
        foreign = set(foreign_fingerprints(source, limit=200))
        n = 0
        for rec in reactivated:
            fp = str(rec.get("fingerprint", ""))
            if fp and fp in foreign:
                rec["agreed"] = True
                n += 1
        return n
    except Exception:
        return 0


def downscale(reactivated: list, max_keep: int = 64) -> int:
    """REM/SHY: keep only what replay reactivated. Weak die. Fail-open.

    Item 116: writes the compacted view to the derived COMPACT file; the
    append-only crystallized.jsonl is never rewritten.
    """
    try:
        if not reactivated:
            return 0
        kept = reactivated[-max_keep:]
        COMPACT.parent.mkdir(parents=True, exist_ok=True)
        tmp = COMPACT.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(json.dumps(r) + "\n" for r in kept), encoding="utf-8")
        tmp.replace(COMPACT)
        return len(kept)
    except Exception:
        return 0


def dream(source: str = "one-mind") -> int:
    """Replay then downscale. Returns count kept."""
    result = replay(source)
    return downscale(result["reactivated"])


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


def _key(rec: dict) -> str:
    if rec.get("event_id"):
        return "id:" + str(rec["event_id"])
    return "st:" + json.dumps({k: rec.get(k) for k in ("source", "lineage", "fingerprint", "kind", "outcome")
                               if k in rec}, sort_keys=True)


def fold_watch_receipts(src: Path | None = None, dest: Path | None = None) -> int:
    """Item 116: append watch-job receipts not yet in exchange.jsonl (run by the evolve job,
    the single writer of exchange.jsonl). Append-only on both files; returns rows added."""
    src = Path(src or WATCH_EXCHANGE)
    dest = Path(dest or EXCHANGE)
    if not src.exists():
        return 0
    seen = set()
    if dest.exists():
        for line in dest.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(_key(json.loads(line)))
            except Exception:
                continue
    add = []
    for line in src.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        k = _key(rec)
        if k in seen:
            continue
        seen.add(k)
        add.append(json.dumps(rec) + "\n")
    if add:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("a", encoding="utf-8") as f:
            f.writelines(add)
    return len(add)


def run(source: str = "one-mind") -> dict:
    report = reload_check(source)
    report["foreign"] = listen(source)
    result = replay(source)
    report["reactivated"] = len(result["reactivated"])
    report["holes"] = len(result["holes"])
    report["agreed"] = integrate(source, result["reactivated"])
    report["kept"] = downscale(result["reactivated"])
    echo(source, report)
    return report


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--fold":
        try:
            from colony.external_priors import enabled as _ext_on
            on = _ext_on()
        except Exception:  # noqa: BLE001
            on = True
        print(json.dumps({"folded": fold_watch_receipts() if on else 0, "external_priors": on}))
        raise SystemExit(0)
    src = sys.argv[1] if len(sys.argv) > 1 else "one-mind"
    print(json.dumps(run(src)))
