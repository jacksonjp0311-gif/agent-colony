"""End-of-cycle habit. Score is what the cycle proposed.

Pattern: read new exchange rows since the cursor.
Score is the mean bias of those rows.
A quiet cycle scores 0 and refuses.
A cycle that proposes more than the prior can keep.
Fail-open.
"""
from __future__ import annotations
import json
from pathlib import Path


def _rows(path: Path) -> list:
    out = []
    try:
        if not path.exists():
            return out
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return out
    return out


def apply(lineage: str = "colony") -> dict:
    try:
        from colony.tools.genome import load, save, propose

        root = Path(__file__).resolve().parent.parent.parent
        exchange = root / "data" / "commons" / "exchange.jsonl"
        g = load()
        before = int(g.get("exchange_seen") or 0)
        rows = _rows(exchange)
        after = len(rows)
        new = rows[before:after] if before < after else []
        biases = []
        for r in new:
            if r.get("source") not in ("", lineage) and r.get("lineage") != lineage:
                continue
            b = (r.get("extra") or {}).get("bias_delta")
            if isinstance(b, (int, float)):
                biases.append(float(b))
        score = round(sum(biases) / len(biases), 3) if biases else 0.0
        prior = float(g.get("last_score") or 0)
        g = dict(g)
        g["exchange_seen"] = after
        g["last_bias_n"] = len(biases)
        save(g)
        kept = score > prior
        try:
            from colony.tools.seeded import record
            record(prior, score, kept, "colony")
        except Exception:
            pass
        out = propose("last_score", score, score, prior)
        try:
            from colony.tools.seeded import replay
            replay(lineage)
        except Exception:
            pass
        return out
    except Exception as exc:
        return {"kept": False, "reason": "fail-open", "error": str(exc)}


if __name__ == "__main__":
    print(json.dumps(apply("colony")))
