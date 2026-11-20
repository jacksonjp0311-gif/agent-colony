"""Crystallize a verified keep into durable Bitwork prototypes.

Stores a uniquely identified record. A fresh process can reload
and retrieve it. Fail-open. Lineage-preserving.
"""
from __future__ import annotations
from typing import Any, Mapping
from pathlib import Path
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent.parent
STORE = ROOT / "data" / "commons" / "crystallized.jsonl"

def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()

def _fingerprint(treatment: Any) -> str:
    """Extract fingerprint from dict or object."""
    if treatment is None:
        return ""
    if isinstance(treatment, Mapping):
        return str(treatment.get("fingerprint") or treatment.get("knob") or "")
    return str(getattr(treatment, "fingerprint", "") or "")

def crystallize(treatment: Any = None, fingerprint: str = "", source: str = "one-mind", category: str = "kept") -> bool:
    fp = fingerprint or _fingerprint(treatment)
    if not fp:
        return False
    key = f"{source}:{fp}"
    try:
        # Skip if already stored
        if STORE.exists():
            for line in STORE.read_text(encoding="utf-8").splitlines():
                try:
                    if json.loads(line).get("key") == key:
                        return True  # already durable
                except Exception:
                    continue
        STORE.parent.mkdir(parents=True, exist_ok=True)
        try:
            from colony.tools.surgical_implants import sparse_delta
            rec = sparse_delta(fp, category, source)
            rec["key"] = key
            rec["ts"] = _utc()
            rec["lineage"] = source
        except Exception:
            rec = {
                "key": key,
                "fingerprint": fp,
                "source": source,
                "lineage": source,
                "category": category,
                "ts": _utc(),
            }
        with STORE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        # Also learn into a live router if available (best-effort)
        try:
            from hive.bitwork import Router
            router = Router()
            router.learn(
                text=f"kept {fp} from {source}",
                category=category,
                action_key=fp,
                positive=(category == "kept"),
                source_id=source,
                proto_key=key,
            )
        except Exception:
            pass
        return True
    except Exception:
        return False

def reload_into(router: Any = None) -> int:
    """Load durable records into a Router. Returns count loaded."""
    if not STORE.exists():
        return 0
    if router is None:
        from hive.bitwork import Router
        router = Router()
    n = 0
    lines = STORE.read_text(encoding="utf-8").splitlines()
    try:
        from colony.tools.surgical_implants import prune_weak
        recs = []
        for line in lines:
            try:
                recs.append(__import__("json").loads(line))
            except Exception:
                continue
        recs = prune_weak(recs, max_keep=64)
        lines = [__import__("json").dumps(r) for r in recs]
    except Exception:
        pass
    for line in lines:
        try:
            rec = json.loads(line)
            router.learn(
                text=f"kept {rec['fingerprint']} from {rec['source']}",
                category=rec.get("category", "kept"),
                action_key=rec["fingerprint"],
                positive=(rec.get("category") == "kept"),
                source_id=rec["source"],
                proto_key=rec["key"],
            )
            n += 1
        except Exception:
            continue
    return n

def retrieve(fingerprint: str, source: str = "one-mind") -> bool:
    """True if a fresh load finds this fingerprint."""
    from hive.bitwork import Router
    router = Router()
    reload_into(router)
    key = f"{source}:{fingerprint}"
    return any(getattr(p, "key", "") == key for p in getattr(router, "prototypes", []))



def crystallize_stable(source: str = "one-mind", min_count: int = 2) -> int:
    """Crystallize fingerprints seen at least min_count times as reverted.

    Durable learning from repeated observation. Fail-open. Returns count written.
    """
    try:
        from collections import Counter
        import json
        from pathlib import Path
        ex = Path(__file__).resolve().parent.parent.parent / "data" / "commons" / "exchange.jsonl"
        if not ex.exists():
            return 0
        counts = Counter()
        for line in ex.read_text(encoding="utf-8").splitlines()[-200:]:
            try:
                rec = json.loads(line)
                if rec.get("outcome") in ("observed", "kept", "adopted") and rec.get("fingerprint"):
                    counts[str(rec["fingerprint"])] += 1
            except Exception:
                continue
        n = 0
        for fp, c in counts.items():
            if c >= min_count:
                if crystallize({"fingerprint": fp}, source=source, category="stable"):
                    n += 1
        return n
    except Exception:
        return 0
