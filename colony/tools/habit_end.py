"""End-of-cycle habit. Score is a delta, not a window.

Pattern: count receipts now, subtract the cursor, propose the delta.
A quiet cycle can score 0 and refuse. A productive cycle can keep.
Fail-open.
"""
from __future__ import annotations


def apply(lineage: str = "colony") -> dict:
    try:
        from colony.tools.genome import load, save, propose
        from colony.tools.feedback import last

        g = load()
        before = int(g.get("receipts_seen") or 0)
        rows = last(lineage, n=500)
        after = len(rows)
        delta = float(max(0, after - before))
        prior = float(g.get("last_score") or 0)
        g = dict(g)
        g["receipts_seen"] = after
        save(g)
        return propose("last_score", delta, delta, prior)
    except Exception as exc:
        return {"kept": False, "reason": "fail-open", "error": str(exc)}


if __name__ == "__main__":
    import json
    print(json.dumps(apply("colony")))
