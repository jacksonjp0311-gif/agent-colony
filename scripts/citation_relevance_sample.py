"""Before/after citation relevance on a fixed sample (evidence/2026-10-16-citations/).

BEFORE = every (target, paper) citation the colony actually wrote into the ledger with the old
keyword-overlap picker ("Feed cite: ... `id`"). AFTER = for the same targets, the paper the new
relevance-checked picker would cite from the same feed cache (or no citation).
Relevance ground truth = manual labels in evidence/2026-10-16-citations/labels.json (a reader
judged title+abstract: does the source concern the claim's mathematical objects?). The labels
were written from the titles/abstracts, not from the checker's output.

    PYTHONPATH=. python3 scripts/citation_relevance_sample.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from colony.citations import assess_paper
from colony.feeds import _pick, load_items

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evidence" / "2026-10-16-citations"


def before_pairs() -> list[tuple[str, str]]:
    seen: dict[tuple[str, str], None] = {}
    for ln in (ROOT / "data" / "ledger.jsonl").open(encoding="utf-8"):
        if "Feed cite" not in ln:
            continue
        t = json.dumps(json.loads(ln))
        m = re.search(r"`([a-z0-9_]+)` citing", t)
        f = re.search(r"Feed cite: \w+ `([^`]+)`", t)
        if m and f:
            seen[(m.group(1), f.group(1))] = None
    return list(seen)


def after_pick(target: str, papers: list[dict], salt: str) -> tuple[str | None, str]:
    judged = [(len(c["matched"]), e, c) for e in papers for c in [assess_paper(target, e)] if c["relevant"]]
    if not judged:
        return None, "no feed paper states the claim's key objects"
    best = max(n for n, _, _ in judged)
    e, c = _pick([(e, c) for n, e, c in judged if n == best], salt)
    return e["id"], c["reason"]


def main() -> None:
    items = {e["id"]: e for e in load_items(limit=100000)}
    papers = [e for e in items.values() if e.get("kind") == "paper" and e.get("title")]
    labels = json.loads((OUT / "labels.json").read_text())["labels"]
    rows = []
    for i, (tg, fid) in enumerate(before_pairs()):
        afid, reason = after_pick(tg, papers, f"s{i}")
        rows.append({"target": tg, "before": fid, "before_title": items.get(fid, {}).get("title"),
                     "before_label": labels.get(f"{tg}|{fid}"),
                     "after": afid, "after_title": items.get(afid, {}).get("title") if afid else None,
                     "after_reason": reason, "after_label": labels.get(f"{tg}|{afid}") if afid else None})
    b = [r["before_label"] for r in rows if r["before_label"] is not None]
    a = [r["after_label"] for r in rows if r["after"] and r["after_label"] is not None]
    summary = {
        "n_targets": len(rows),
        "before_cited": len(rows), "before_relevant": sum(b), "before_share_relevant": round(sum(b) / len(b), 3) if b else None,
        "after_cited": sum(1 for r in rows if r["after"]), "after_relevant": sum(a),
        "after_share_relevant": round(sum(a) / len(a), 3) if a else None,
        "after_uncited": sum(1 for r in rows if not r["after"]),
        "unlabelled": sum(1 for r in rows if r["before_label"] is None or (r["after"] and r["after_label"] is None)),
    }
    # Checker agreement with the manual labels over every labelled (target, paper) pair.
    tp = fp = fn = tn = 0
    for key, lab in labels.items():
        tg, fid = key.split("|", 1)
        if fid not in items:
            continue
        pred = assess_paper(tg, items[fid])["relevant"]
        tp += pred and lab == 1; fp += pred and lab == 0; fn += (not pred) and lab == 1; tn += (not pred) and lab == 0
    summary["checker_vs_labels"] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                                    "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                                    "recall": round(tp / (tp + fn), 3) if tp + fn else None}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sample.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
