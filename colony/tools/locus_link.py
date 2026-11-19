"""Thin link to Locus. Fail-open. A number, not an order.

If Locus is not on the path, return empty. Never decide.
"""
from __future__ import annotations


def ask_locus(query: str = "", guide: str = "") -> dict:
    try:
        from colony.tools.handoff import ask
        return ask(query, guide)
    except Exception:
        return {"source": "locus", "available": False, "query_hits": 0, "off_target": 0}
