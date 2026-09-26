"""RSI → agent improvement coupling (measured, not mystical).

When the ledger/commons hold accepted or strong RSI-related findings, feed them
into improver proposals, skill_router biases, and genome mutation biases.
Documented in society/artifacts/rsi_agent_coupling.md. Not AGI training.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

RSI_TOPICS = {
    "recursive-self-improvement",
    "meta-learning",
    "self-improving-agents",
    "godel-machines",
    "darwin-godel-machine",
    "reflexion",
    "self-refine",
}
RSI_RELATED = {"agent-societies"}
RSI_TAG_HINTS = {
    "rsi", "self-improve", "self-improvement", "reflexion", "self-refine",
    "meta-learning", "godel", "darwin-godel", "bounded", "open-ended",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_dict(f: Any) -> dict[str, Any]:
    if isinstance(f, dict):
        return f
    return {
        "id": getattr(f, "id", None),
        "title": getattr(f, "title", None),
        "topic_id": getattr(f, "topic_id", None),
        "status": getattr(f, "status", None),
        "tags": list(getattr(f, "tags", None) or []),
        "evidence_urls": list(getattr(f, "evidence_urls", None) or []),
        "claim": (getattr(f, "claim", None) or "")[:240],
    }


def _status(f: Any) -> str:
    return str(getattr(f, "status", None) or (f.get("status") if isinstance(f, dict) else "") or "")


def harvest_rsi_signal(findings: list[Any]) -> dict[str, Any]:
    """Score accepted / strong RSI findings for coupling."""
    accepted: list[dict[str, Any]] = []
    strong_candidate: list[dict[str, Any]] = []
    unknown_caution: list[dict[str, Any]] = []
    for f in findings:
        d = _as_dict(f)
        st = _status(f)
        topic = d.get("topic_id")
        tags = set(d.get("tags") or [])
        title = (d.get("title") or "").lower()
        claim = (d.get("claim") or "").lower()
        ev = d.get("evidence_urls") or []
        core = topic in RSI_TOPICS or bool(tags & RSI_TAG_HINTS) or any(
            h in title for h in ("self-improv", "reflexion", "gödel", "godel", "meta-learn", "rsi")
        )
        related_accepted = topic in RSI_RELATED and any(
            h in title or h in claim for h in ("self-improv", "open-ended", "rsi", "reflexion")
        )
        if st == "accepted" and (core or related_accepted or topic in RSI_TOPICS):
            if core or topic in RSI_TOPICS or related_accepted:
                accepted.append(d)
            continue
        if not core:
            continue
        if title.startswith("gather synthesis") or title.startswith("message:") or title.startswith("improve:"):
            continue
        if st == "unknown" or "unknown" in tags or "theoretical" in tags:
            unknown_caution.append(d)
        elif st == "candidate" and len(ev) >= 1 and "theoretical" not in tags:
            strong_candidate.append(d)
    strength = min(
        1.0,
        0.60 * min(1.0, len(accepted) / 5.0)
        + 0.25 * min(1.0, len(strong_candidate) / 8.0)
        + 0.15 * min(1.0, max(0, len(accepted) - len(unknown_caution)) / 4.0),
    )
    mutation_bias = {
        "explore": round(0.04 + 0.10 * strength, 4),
        "govern": round(0.02 + 0.08 * strength, 4),
        "build": round(0.02 + 0.06 * strength, 4),
        "gather": round(0.01 + 0.04 * strength, 4),
        "reply": round(0.01 + 0.03 * strength, 4),
    }
    skill_bias = {
        "improver.improve": round(0.55 + 0.40 * strength, 4),
        "spark.emergence": round(0.50 + 0.35 * strength, 4),
        "pathfinder.gather": round(0.45 + 0.25 * strength, 4),
    }
    lessons = [
        {
            "id": d.get("id"),
            "title": d.get("title"),
            "topic_id": d.get("topic_id"),
            "lesson": "Accepted RSI finding → bias measured improve/explore loops (candidate until authorize).",
        }
        for d in accepted[-5:]
    ]
    return {
        "ts": _utc_now(),
        "accepted_count": len(accepted),
        "strong_candidate_count": len(strong_candidate),
        "unknown_caution_count": len(unknown_caution),
        "strength": round(strength, 4),
        "mutation_bias": mutation_bias,
        "skill_bias": skill_bias,
        "accepted_ids": [d.get("id") for d in accepted[-12:]],
        "strong_ids": [d.get("id") for d in strong_candidate[-12:]],
        "lessons": lessons,
        "note": (
            "Coupling is measured state update inside this repo — not open-ended ML, "
            "not AGI, not consciousness. Improvement proposals stay candidate until human authorize."
        ),
    }


def apply_skill_biases(registry: Any, signal: dict[str, Any]) -> dict[str, float]:
    updated: dict[str, float] = {}
    active = registry.active()
    for key, success in (signal.get("skill_bias") or {}).items():
        if "." not in key:
            continue
        role, skill = key.split(".", 1)
        if role in active:
            updated[key] = registry.record_outcome(role, skill, float(success))
    return updated


def apply_mutation_bias_to_genome(genome: dict[str, Any], signal: dict[str, Any]) -> dict[str, Any]:
    bias = signal.get("mutation_bias") or {}
    genome = dict(genome)
    genome["rsi_mutation_bias"] = dict(bias)
    genome["rsi_coupling_strength"] = signal.get("strength")
    genome["rsi_coupling_ts"] = signal.get("ts")
    return genome


def biased_mutate_rate(signal: dict[str, Any], base: float = 0.18) -> float:
    s = float(signal.get("strength") or 0)
    return round(min(0.35, base + 0.12 * s), 4)


def pick_rsi_improvement(signal: dict[str, Any], metrics: dict[str, float]) -> tuple[str, str, str] | None:
    if float(signal.get("strength") or 0) < 0.15:
        return None
    n_acc = int(signal.get("accepted_count") or 0)
    n_strong = int(signal.get("strong_candidate_count") or 0)
    title = "Feed accepted/strong RSI findings into skill_router + genome bias"
    hypothesis = (
        f"RSI coupling strength={signal.get('strength')} "
        f"(accepted={n_acc}, strong_cand={n_strong}). "
        f"Bias improver/explore skills and child mutation toward measured self-improve loops. "
        f"agg={metrics.get('aggregate')}."
    )
    action = "rsi_coupling:skill_router+mutation_bias"
    return title, hypothesis, action


def persist_coupling(signal: dict[str, Any], *, cycle_id: str, root: Path | None = None) -> Path:
    root = root or ROOT
    systems = root / "society" / "systems"
    systems.mkdir(parents=True, exist_ok=True)
    path = systems / "rsi_coupling.json"
    payload = {
        "version": 1,
        "updated_at": _utc_now(),
        "updated_cycle": cycle_id,
        "signal": signal,
        "doc": "society/artifacts/rsi_agent_coupling.md",
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    art = root / "society" / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    md = art / "rsi_agent_coupling.md"
    md.write_text(
        "# RSI → Agent Coupling\n\n"
        "> Measured feed from accepted/strong RSI ledger findings into improver, "
        "skill_router, and genome mutation biases. **Not AGI. Not consciousness.**\n\n"
        f"**Updated:** {_utc_now()}  \n"
        f"**Cycle:** `{cycle_id}`  \n"
        f"**Strength:** {signal.get('strength')}  \n"
        f"**Accepted RSI findings:** {signal.get('accepted_count')}  \n"
        f"**Strong candidates:** {signal.get('strong_candidate_count')}  \n\n"
        "See society/systems/rsi_coupling.json for biases.\n\n"
        "_Hard ceiling: creator tribute · human authorize · append-only witness._\n",
        encoding="utf-8",
    )
    return path
