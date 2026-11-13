"""Research desk: public-text method cards mapped to the closed legal op set.

Phase 2. Reads public scholarly text (arXiv Atom abstracts, query only)
about self-improvement, recursive self-improvement, and learning
methods. Network is allowed in Actions and is fail-soft. Raw responses
and extracted cards are cached append-only under ``data/commons/``.
Parsing is deterministic: a fixed lexicon of phrases maps to a plain-
English method plus a *legal* Hive op (``set_knob`` on bounded
colony-wide policy knobs, ``add_family_rotation``, ``reorder_desk``).
Nothing fetched is ever executed. No paid or neural model.

Disabled on the control arm. Does not loosen the Oracle, the P≥0.70
gate, the 150 cap, Wilson 700‰, or Athanor math.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

PREFIX = "mc_"
# Public arXiv API (HTTPS). The existing gather desk uses the same host.
ARXIV_API = "https://export.arxiv.org/api/query"
QUERY = (
    'ti:"recursive self-improvement" OR ti:"self-improvement" OR '
    'abs:"curriculum learning" OR abs:"learning from failure" OR '
    'abs:"experience replay" OR abs:"exploration exploitation"'
)
MAX_RESULTS = 8
ABSTRACT_CHARS = 2000
CACHE_NAME = "research_desk.jsonl"
CARDS_NAME = "method_cards.jsonl"

# Closed mapping: phrase → (plain-English method, legal action template).
# First matching rule wins per abstract (deterministic order). Actions
# are validated against Hive's closed op set before a card is accepted.
# New bounded knobs (desk_budget, curriculum_pace, retry_policy_cycles,
# routing_explore_weight) are the careful extension of what set_knob
# may legally target; no new op name is introduced, and no invariant
# knob is reachable.
_RULES: tuple[tuple[re.Pattern[str], str, dict[str, Any]], ...] = (
    (
        re.compile(r"curriculum learning|easy[- ]to[- ]hard|staged training|from simple to (complex|hard)", re.I),
        "Practice easier cases before harder ones (curriculum).",
        {"op": "set_knob", "name": "curriculum_pace", "direction": "up"},
    ),
    (
        re.compile(r"experience replay|replay (of )?(failed|failures|errors)|re-?try failed|learn(?:ing)? from fail", re.I),
        "Replay failed attempts before giving up, so the colony learns from its own misses.",
        {"op": "set_knob", "name": "retry_policy_cycles", "direction": "up"},
    ),
    (
        re.compile(r"exploration[- ]exploitation|epsilon-greedy|explore more|exploration bonus", re.I),
        "Spend a bounded share of attention on less-used desks and targets.",
        {"op": "set_knob", "name": "routing_explore_weight", "direction": "up"},
    ),
    (
        re.compile(r"compute budget|resource allocation|attention budget|time budget", re.I),
        "Bound how much work one desk may do in a cycle.",
        {"op": "set_knob", "name": "desk_budget", "direction": "up"},
    ),
    (
        re.compile(r"diversif(?:y|ication)|rotate (?:the )?famil|family rotation|avoid(?:ing)? (?:premature )?convergence", re.I),
        "Rotate which claim family is attempted so search does not stick on one shape.",
        {"op": "add_family_rotation", "family": "algebraic"},
    ),
    (
        re.compile(r"task (?:order|ordering|sequence)|reorder(?:ing)? (?:the )?desk|priority queue|schedule (?:the )?desk", re.I),
        "Reorder desks so research and improvement run before spent catalogs.",
        {"op": "reorder_desk", "order": ["research", "improve", "conjecture", "hunt"]},
    ),
)


def _repo() -> Path:
    return Path(__file__).resolve().parent.parent


def cache_path() -> Path:
    return Path(os.environ.get("COLONY_RESEARCH_CACHE") or (
        _repo() / "data" / "commons" / CACHE_NAME
    ))


def cards_path() -> Path:
    return Path(os.environ.get("COLONY_METHOD_CARDS") or (
        _repo() / "data" / "commons" / CARDS_NAME
    ))


def self_mod_ok() -> bool:
    try:
        from colony.arm import self_mod_enabled
        return bool(self_mod_enabled())
    except Exception:
        return True


def _pytest_would_write_repo(path: Path) -> bool:
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    try:
        real = _repo().resolve()
        resolved = path.resolve()
        return real in resolved.parents or resolved.parent == real
    except Exception:
        return True


def _strip_xml(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = (text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
                .replace("&quot;", '"').replace("&apos;", "'").replace("&#10;", " "))
    return re.sub(r"\s+", " ", text).strip()


def parse_atom(body: str) -> list[dict[str, Any]]:
    """Deterministic Atom parse. Text only; never executes payload content."""
    hits: list[dict[str, Any]] = []
    if not body or not body.strip():
        return hits
    # Prefer the stdlib XML parser; fall back to a split if the body is messy.
    entries: list[str] = []
    try:
        root = ET.fromstring(body)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        nodes = root.findall("a:entry", ns) or root.findall("entry")
        for node in nodes:
            def _t(tag: str) -> str:
                el = node.find(f"a:{tag}", ns)
                if el is None:
                    el = node.find(tag)
                return _strip_xml(el.text or "") if el is not None else ""
            title = _t("title")
            summary = _t("summary")
            entry_id = _t("id")
            published = _t("published")
            arxiv_id = ""
            if "arxiv.org" in entry_id:
                arxiv_id = re.sub(r"v\d+$", "", entry_id.rstrip("/").split("/")[-1])
            if not title and not summary:
                continue
            hits.append({
                "title": title[:300],
                "abstract": summary[:ABSTRACT_CHARS],
                "url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else entry_id,
                "arxiv_id": arxiv_id,
                "year": int(published[:4]) if published[:4].isdigit() else None,
                "source": "arxiv",
            })
        if hits:
            return hits
    except ET.ParseError:
        pass
    for ent in re.split(r"<entry>", body)[1:]:
        title_m = re.search(r"<title>(.*?)</title>", ent, re.S)
        summary_m = re.search(r"<summary>(.*?)</summary>", ent, re.S)
        id_m = re.search(r"<id>(.*?)</id>", ent, re.S)
        published_m = re.search(r"<published>(\d{4})", ent)
        title = _strip_xml(title_m.group(1) if title_m else "")[:300]
        abstract = _strip_xml(summary_m.group(1) if summary_m else "")[:ABSTRACT_CHARS]
        entry_id = _strip_xml(id_m.group(1) if id_m else "")
        arxiv_id = ""
        if "arxiv.org" in entry_id:
            arxiv_id = re.sub(r"v\d+$", "", entry_id.rstrip("/").split("/")[-1])
        if not title and not abstract:
            continue
        hits.append({
            "title": title,
            "abstract": abstract,
            "url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else entry_id,
            "arxiv_id": arxiv_id,
            "year": int(published_m.group(1)) if published_m else None,
            "source": "arxiv",
        })
    return hits


def _card_id(arxiv_id: str, method: str, op: dict[str, Any]) -> str:
    blob = json.dumps({"a": arxiv_id, "m": method, "o": op}, sort_keys=True, separators=(",", ":"))
    return PREFIX + hashlib.sha256(blob.encode()).hexdigest()[:12]


def _validate_action(action: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """Accept only actions Hive's closed op set would accept."""
    try:
        from hive import ops as HO
        v = HO.validate(dict(action))
        payload = dict(getattr(v, "payload", None) or action)
        reason = str(getattr(v, "reason", "") or "")
        return bool(getattr(v, "ok", False)), reason, payload
    except Exception as exc:  # noqa: BLE001
        # Without Hive, still refuse anything that is not in the local closed set.
        op = str(action.get("op") or "")
        if op not in ("set_knob", "add_family_rotation", "reorder_desk"):
            return False, f"hive_unavailable:{type(exc).__name__}", dict(action)
        if op == "set_knob":
            name = str(action.get("name") or "")
            if name not in POLICY_KNOBS:
                return False, "unknown_or_invariant_knob", dict(action)
        return True, "", dict(action)


# The four policy knobs this desk adds, plus any existing legal names a
# rule may target. Invariant names are never listed here.
POLICY_KNOBS = (
    "desk_budget",
    "curriculum_pace",
    "retry_policy_cycles",
    "routing_explore_weight",
)


def extract_cards(hit: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply the lexicon in order; at most one card per rule per abstract."""
    text = f"{hit.get('title') or ''} {hit.get('abstract') or ''}"
    if not text.strip():
        return []
    out: list[dict[str, Any]] = []
    seen_ops: set[str] = set()
    for pattern, method, action in _RULES:
        if not pattern.search(text):
            continue
        ok, reason, payload = _validate_action(action)
        if not ok:
            continue
        # Store the legal *template* (op + name/direction/family/order), not a
        # resolved knob value that would move with the live setting and
        # change the card id.
        stored = {"op": str(action.get("op") or payload.get("op") or "")}
        for k in ("name", "direction", "family", "order"):
            if k in action:
                stored[k] = action[k]
            elif k in (payload or {}):
                stored[k] = payload[k]
        if "value" in action:
            stored["value"] = action["value"]
        if not stored.get("op"):
            continue
        key = json.dumps(stored, sort_keys=True)
        if key in seen_ops:
            continue
        seen_ops.add(key)
        evidence_m = pattern.search(text)
        evidence = evidence_m.group(0) if evidence_m else ""
        card = {
            "id": _card_id(str(hit.get("arxiv_id") or ""), method, stored),
            "method": method,
            "op": stored,
            "evidence": evidence[:160],
            "source": {
                "arxiv_id": hit.get("arxiv_id") or "",
                "title": hit.get("title") or "",
                "url": hit.get("url") or "",
                "year": hit.get("year"),
                "source": hit.get("source") or "arxiv",
            },
        }
        out.append(card)
    return out


def _append(path: Path, row: dict[str, Any]) -> None:
    if _pytest_would_write_repo(path):
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    except Exception:
        pass


def known_card_ids(path: Path | None = None) -> set[str]:
    ids: set[str] = set()
    p = path if path is not None else cards_path()
    try:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("id"):
                    ids.add(str(row["id"]))
    except Exception:
        pass
    return ids


def _desk_budget() -> int:
    try:
        from colony.self_heal import current_knob
        return max(1, min(6, int(current_knob("desk_budget"))))
    except Exception:
        return 2


def run_desk(
    cycle_id: str = "",
    *,
    body: str | None = None,
    fetch: Callable[[], str] | None = None,
    write: bool = True,
    query: str = QUERY,
) -> dict[str, Any]:
    """Fetch (or accept a body), extract cards, append new ones. Control is a no-op."""
    report: dict[str, Any] = {
        "ran": False, "cards": [], "n_hits": 0, "n_new": 0, "reason": "",
        "query": query,
    }
    if not self_mod_ok():
        report["reason"] = "control_frozen"
        return report
    raw = body
    if raw is None:
        if fetch is not None:
            try:
                raw = fetch()
            except Exception as exc:  # noqa: BLE001
                report["reason"] = f"fetch_error:{type(exc).__name__}"
                return report
        else:
            raw = _default_fetch(query)
    if not raw:
        report["reason"] = "empty_fetch"
        report["ran"] = True
        return report
    if write:
        _append(cache_path(), {
            "event": "fetch",
            "cycle_id": cycle_id,
            "query": query,
            "sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "n_chars": len(raw),
            # Store the body so a later cycle can replay without a refetch.
            # Text only; never executed.
            "body": raw[:200_000],
        })
    hits = parse_atom(raw)
    report["n_hits"] = len(hits)
    seen = known_card_ids()
    budget = _desk_budget()
    new_cards: list[dict[str, Any]] = []
    for hit in hits:
        for card in extract_cards(hit):
            if card["id"] in seen:
                continue
            card = dict(card)
            card["cycle_id"] = cycle_id
            card["query"] = query
            if write:
                _append(cards_path(), card)
            seen.add(card["id"])
            new_cards.append(card)
            if len(new_cards) >= budget:
                break
        if len(new_cards) >= budget:
            break
    report["ran"] = True
    report["cards"] = new_cards
    report["n_new"] = len(new_cards)
    report["reason"] = "ok" if new_cards else "no_new_cards"
    report["budget"] = budget
    return report


def _default_fetch(query: str) -> str:
    """Polite arXiv GET; fail-soft. Reuses research_gather's HTTP helper when present."""
    params = urlencode({
        "search_query": query,
        "start": 0,
        "max_results": MAX_RESULTS,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    url = f"{ARXIV_API}?{params}"
    try:
        from colony.research_gather import _http_get
        ok, body = _http_get(url, accept="application/atom+xml")
        return body if ok else ""
    except Exception:
        pass
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"Accept": "application/atom+xml", "User-Agent": "agent-colony-research-desk/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 — public arXiv API
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def load_cards(limit: int = 200) -> list[dict[str, Any]]:
    """Recent method cards, oldest first, from the append-only log."""
    path = cards_path()
    rows: list[dict[str, Any]] = []
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("id") and row.get("op"):
                    rows.append(row)
    except Exception:
        return []
    return rows[-max(1, int(limit)):]


def run_cycle(cycle_id: str = "", **kwargs: Any) -> dict[str, Any]:
    """Society-stage entry point. Fail-soft; never raises into the cycle."""
    try:
        return run_desk(cycle_id, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"ran": False, "cards": [], "n_hits": 0, "n_new": 0,
                "reason": f"error:{type(exc).__name__}"}
