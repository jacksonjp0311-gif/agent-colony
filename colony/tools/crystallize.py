"""Crystallize a verified keep into Bitwork.

On a durable keep, append a prototype for the fingerprint so later
queries can retrieve it. Fail-open. Lineage-preserving.
"""
from __future__ import annotations

def crystallize(fingerprint: str, source: str = "colony", category: str = "kept") -> bool:
    if not fingerprint:
        return False
    try:
        from hive.bitwork import Router
        router = Router()
        text = f"kept {fingerprint} from {source}"
        router.learn(
            text=text,
            category=category,
            action_key=fingerprint,
            positive=True,
            source_id=source,
            proto_key=f"{source}:{fingerprint}",
        )
        return True
    except Exception:
        return False
