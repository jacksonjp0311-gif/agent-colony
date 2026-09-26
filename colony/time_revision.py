"""TIME REVISION — continuously re-evaluate prior conclusions as new data arrives.

New publications, solar/space/weather updates, and shifting residuals must
revise earlier positions, not only append new ones. Track revision events
alongside Oracle/authorize metrics. Not AGI. UNKNOWN stays UNKNOWN.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REV_STATE = ROOT / "society" / "systems" / "time_revision.json"
REV_LOG = ROOT / "data" / "commons" / "time_revision.jsonl"
BELIEF_STORE = ROOT / "data" / "commons" / "belief_positions.jsonl"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hid(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _load_beliefs() -> list[dict[str, Any]]:
    if not BELIEF_STORE.exists():
        return []
    out = []
    for line in BELIEF_STORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _append_belief(row: dict[str, Any]) -> None:
    BELIEF_STORE.parent.mkdir(parents=True, exist_ok=True)
    with BELIEF_STORE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def register_position(
    *,
    topic: str,
    claim: str,
    confidence: float,
    cycle_id: str,
    source: str = "debate",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a current belief/conclusion agents may later revise."""
    row = {
        "id": f"pos_{_hid(topic + '|' + claim)}",
        "ts": _utc(),
        "topic": topic,
        "claim": claim[:500],
        "confidence": float(confidence),
        "cycle_id": cycle_id,
        "source": source,
        "status": "active",
        "revision_of": None,
        "meta": meta or {},
        "not_discovery": True,
    }
    _append_belief(row)
    return row


def _active_positions() -> dict[str, dict[str, Any]]:
    """Latest active position per topic id."""
    latest: dict[str, dict[str, Any]] = {}
    for row in _load_beliefs():
        pid = row.get("id") or row.get("topic")
        if not pid:
            continue
        # allow superseded chain — last write wins per id family
        key = row.get("topic") or pid
        latest[key] = row
    return {k: v for k, v in latest.items() if v.get("status") in (None, "active", "revised")}


def revise_from_signals(
    *,
    cycle_id: str,
    external_patterns: list[dict[str, Any]] | None = None,
    residual_conflicts: list[dict[str, Any]] | None = None,
    oracle: dict[str, Any] | None = None,
    fitness_delta: float | None = None,
) -> dict[str, Any]:
    """Re-evaluate prior positions given new external/residual/oracle signals.

    Returns revision event summary with concrete changes.
    """
    external_patterns = external_patterns or []
    residual_conflicts = residual_conflicts or []
    oracle = oracle or {}
    positions = _active_positions()
    revisions: list[dict[str, Any]] = []

    # Seed baseline positions if empty so revision has something to bite
    if not positions:
        seeds = [
            ("space_weather_ops", "Geomagnetic activity is routine; no commons action needed.", 0.55),
            ("arxiv_relevance", "Fresh STEM preprints are low-priority vs hard-tier lemmas.", 0.5),
            ("weather_commons", "Global weather snapshots do not affect colony gather→claim.", 0.6),
            ("residual_harmony", "Peer residuals are aligned; re-debate unnecessary.", 0.55),
            ("oracle_easy_pad", "easy_pad pressure is stable; no further Oracle vigilance.", 0.45),
        ]
        for topic, claim, conf in seeds:
            register_position(
                topic=topic,
                claim=claim,
                confidence=conf,
                cycle_id=cycle_id,
                source="time_revision_seed",
            )
        positions = _active_positions()

    pattern_kinds = {p.get("kind") for p in external_patterns}
    kp = None
    for p in external_patterns:
        sig = p.get("signals") or {}
        if sig.get("kp") is not None:
            kp = sig.get("kp")

    def _revise(topic: str, new_claim: str, new_conf: float, why: str, cause: dict[str, Any]) -> None:
        prev = positions.get(topic)
        if not prev:
            return
        old_conf = float(prev.get("confidence") or 0)
        # Only revise if directionally meaningful or claim text changes
        if abs(new_conf - old_conf) < 0.05 and new_claim.strip() == (prev.get("claim") or "").strip():
            return
        new_row = {
            "id": f"pos_{_hid(topic + '|' + new_claim + '|' + cycle_id)}",
            "ts": _utc(),
            "topic": topic,
            "claim": new_claim[:500],
            "confidence": round(float(new_conf), 4),
            "cycle_id": cycle_id,
            "source": "time_revision",
            "status": "active",
            "revision_of": prev.get("id"),
            "prior_claim": (prev.get("claim") or "")[:300],
            "prior_confidence": old_conf,
            "why": why,
            "cause": cause,
            "meta": {"revision": True},
            "not_discovery": True,
        }
        _append_belief(new_row)
        # mark prior superseded in log (append-only: status note)
        _append_belief(
            {
                **prev,
                "ts": _utc(),
                "status": "superseded",
                "superseded_by": new_row["id"],
                "superseded_cycle": cycle_id,
            }
        )
        revisions.append(
            {
                "topic": topic,
                "from_confidence": old_conf,
                "to_confidence": new_row["confidence"],
                "from_claim": new_row["prior_claim"],
                "to_claim": new_row["claim"],
                "why": why,
                "cause": cause,
                "prior_id": prev.get("id"),
                "new_id": new_row["id"],
            }
        )
        positions[topic] = new_row

    # External array driven revisions
    if "space_weather_coherence" in pattern_kinds or (kp is not None and float(kp) >= 4):
        _revise(
            "space_weather_ops",
            f"Kp/DONKI signals elevated (kp={kp}); commons should weigh ops/gather attention. Candidate only.",
            min(0.85, 0.55 + (float(kp or 4) - 3) * 0.08),
            "EXTERNAL ARRAY space_weather_coherence / elevated Kp revised prior 'routine' stance.",
            {"signal": "external_array", "kind": "space_weather_coherence", "kp": kp},
        )
    if "publications_x_space" in pattern_kinds:
        _revise(
            "arxiv_relevance",
            "Fresh arXiv STEM + space signals cross-correlate — raise multi-hop priority for hearing/Oracle evidence.",
            0.72,
            "New publications×space pattern revised low-priority preprint stance.",
            {"signal": "external_array", "kind": "publications_x_space"},
        )
    if "global_weather_spread" in pattern_kinds:
        _revise(
            "weather_commons",
            "Global weather snapshot is observable colony environment signal — include in gather→claim debate.",
            0.68,
            "Weather feed update revised 'no effect' commons belief.",
            {"signal": "external_array", "kind": "global_weather_spread"},
        )

    # Residual conflict driven revisions
    if residual_conflicts:
        top = residual_conflicts[0]
        _revise(
            "residual_harmony",
            f"Peer residual conflict {top.get('a')}↔{top.get('b')} score={top.get('score')} — re-debate required.",
            0.3,
            "INTERNAL RESIDUALS conflict revised prior harmony belief; trigger re-debate.",
            {"signal": "residuals", "conflict": top},
        )

    # Oracle easy_pad vigilance
    easy_kills = int(oracle.get("easy_pad_kills") or 0)
    if easy_kills > 0:
        _revise(
            "oracle_easy_pad",
            f"Oracle easy_pad_kills={easy_kills} — maintain kill path; no fitness credit on FAIL.",
            0.8,
            "Oracle metrics revised complacent easy_pad stance.",
            {"signal": "oracle", "easy_pad_kills": easy_kills, "kills": oracle.get("kills")},
        )

    if fitness_delta is not None and fitness_delta < -0.01:
        # fitness drop revisits arxiv/space priorities toward caution
        _revise(
            "arxiv_relevance",
            "Fitness delta negative — prefer Oracle-gated hard-tier over preprint chase. UNKNOWN where thin.",
            0.62,
            f"Fitness delta {fitness_delta} revised preprint enthusiasm downward.",
            {"signal": "fitness_delta", "delta": fitness_delta},
        )

    event = {
        "ts": _utc(),
        "cycle_id": cycle_id,
        "revision_count": len(revisions),
        "revisions": revisions,
        "positions_active": len(positions),
        "inputs": {
            "pattern_kinds": list(pattern_kinds),
            "n_residual_conflicts": len(residual_conflicts),
            "oracle_easy_pad_kills": easy_kills,
            "fitness_delta": fitness_delta,
            "kp": kp,
        },
        "note": "TIME REVISION: prior conclusions revised from new data — not append-only opinions.",
        "non_claims": ["not_AGI", "not_discovery", "UNKNOWN_stays_UNKNOWN"],
    }
    _persist(event)
    return event


def _persist(event: dict[str, Any]) -> None:
    REV_LOG.parent.mkdir(parents=True, exist_ok=True)
    with REV_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    # rolling state
    prev = {}
    if REV_STATE.exists():
        try:
            prev = json.loads(REV_STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}
    total = int(prev.get("total_revisions") or 0) + int(event.get("revision_count") or 0)
    snap = {
        "ts": event["ts"],
        "version": 1,
        "latest_cycle_id": event.get("cycle_id"),
        "latest_revision_count": event.get("revision_count"),
        "total_revisions": total,
        "latest_revisions": event.get("revisions"),
        "latest_inputs": event.get("inputs"),
        "examples": (prev.get("examples") or [])[-5:] + list(event.get("revisions") or [])[:3],
        "note": event.get("note"),
        "non_claims": event.get("non_claims"),
    }
    snap["examples"] = snap["examples"][-8:]
    REV_STATE.parent.mkdir(parents=True, exist_ok=True)
    REV_STATE.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def revision_stats() -> dict[str, Any]:
    if REV_STATE.exists():
        try:
            return json.loads(REV_STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"total_revisions": 0, "latest_revision_count": 0, "examples": []}


def recent_examples(limit: int = 5) -> list[dict[str, Any]]:
    st = revision_stats()
    return list(st.get("examples") or st.get("latest_revisions") or [])[:limit]
