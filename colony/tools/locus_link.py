"""Thin link to Locus. Fail-open. A number, not an order.

Reads the public receipt. Does not import a module that is not here.
"""
from __future__ import annotations
import json
import urllib.request

RECEIPT = "https://raw.githubusercontent.com/jacksonjp0311-gif/locus/main/data/commons/locus_receipt.json"


def ask_locus(query: str = "", guide: str = "") -> dict:
    try:  # item 115: live fetch only with COLONY_EXTERNAL_PRIORS live on a treatment arm
        from colony.external_priors import enabled as _ext_on
        if not _ext_on():
            return {"source": "locus", "available": False, "query_hits": 0, "off_target": 0,
                    "skipped": "COLONY_EXTERNAL_PRIORS off"}
    except Exception:  # noqa: BLE001
        return {"source": "locus", "available": False, "query_hits": 0, "off_target": 0}
    try:
        with urllib.request.urlopen(RECEIPT, timeout=8) as r:
            data = json.loads(r.read().decode())
        data["available"] = True
        return data
    except Exception:
        return {"source": "locus", "available": False, "query_hits": 0, "off_target": 0}

