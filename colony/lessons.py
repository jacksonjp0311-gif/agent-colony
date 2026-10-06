"""Lesson ledger — learn ONLY from kept/reverted outcomes under named checks.

Every keep/revert on bench/gather/conjecture writes a lesson into
data/commons/lessons.jsonl (+ society/systems/lesson_ledger.json).
Next cycles bias skills from that ledger. Stale easy wins expire under
harder checks. Not AGI. Not open-ended ML training.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LESSONS_JSONL = ROOT / "data" / "commons" / "lessons.jsonl"
LEDGER_SYSTEM = ROOT / "society" / "systems" / "lesson_ledger.json"
GENOMES_DIR = ROOT / "society" / "genomes"

# Easy-check lessons expire when a harder check of the same family exists newly
EASY_FAMILIES = {"easy_pad", "fft_pad", "textbook_only"}
HARD_FAMILIES = {"hard_enable", "hard_tier", "lemma_hard", "bench_hard", "derived_chain"}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Human authors allowed to write type=human_guide (agents may NOT invent guides).
HUMAN_GUIDE_AUTHORS = frozenset({
    "James Paul Jackson",
    "James Jackson",
    "jacksonjp0311-gif",
})

LESSON_TYPES = frozenset({
    "oracle_kill", "hearing_reject", "hearing_defer", "bench_regression",
    "repeat_proposal", "catalog_exhausted", "human_guide",
    "keep", "revert", "skip",
})


def write_lesson(
    *,
    decision: str,
    check: str,
    what: str,
    source: str,
    cycle_id: str = "",
    mutation: str = "",
    before_score: float | None = None,
    after_score: float | None = None,
    skill_bias: dict[str, float] | None = None,
    family: str = "",
    tags: list[str] | None = None,
    evidence: list[str] | None = None,
    lesson_type: str = "",
    catalog_hint: dict[str, Any] | None = None,
    proposal_fingerprint: str = "",
    genome_prior: dict[str, float] | None = None,
    author: str | None = None,
) -> dict[str, Any]:
    """Append one lesson. decision in {keep, revert, skip, guide, block}.

    human_guide is ONLY writable by explicit human path (author allowlist + source=human).
    Agents may read guides as teaching priors; they may not invent type=human_guide.
    Lessons remain status=candidate — durable promotion still needs authorize.
    """
    ltype = (lesson_type or decision or "skip").strip()
    if ltype == "human_guide" or decision == "guide":
        # Hard guard: reject non-human writers
        if source != "human" or (author or "") not in HUMAN_GUIDE_AUTHORS:
            raise PermissionError(
                "human_guide lessons are writable only by humans "
                f"(source=human + author in allowlist); got source={source!r} author={author!r}"
            )
        ltype = "human_guide"
        decision = "guide"
        source = "human"
        family = family or "human_teaching"

    LESSONS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    fam = family or (
        "easy_pad"
        if "easy" in (check + mutation).lower()
        else ("hard_tier" if decision == "keep" else "outcome")
    )
    entry = {
        "id": f"les_{cycle_id[-8:] if cycle_id else _utc()[-8:]}_{mutation or check}"[:48],
        "ts": _utc(),
        "cycle_id": cycle_id,
        "type": ltype if ltype in LESSON_TYPES else (decision or "skip"),
        "decision": decision,
        "check": check,
        "mutation": mutation,
        "what": what[:500],
        "source": source,
        "family": fam,
        "before_score": before_score,
        "after_score": after_score,
        "skill_bias": dict(skill_bias or {}),
        "genome_prior": dict(genome_prior or {}),
        "catalog_hint": dict(catalog_hint) if catalog_hint else {},
        "proposal_fingerprint": (proposal_fingerprint or "")[:48],
        "tags": list(tags or []),
        "evidence": list(evidence or []),
        "author": author,
        "expired": False,
        "status": "candidate",  # hard ceiling — durable accept needs authorize
    }
    with LESSONS_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    expire_stale_easy_wins()
    persist_system(cycle_id=cycle_id)
    return entry


def load_lessons(*, limit: int = 200, include_expired: bool = False) -> list[dict[str, Any]]:
    if not LESSONS_JSONL.exists():
        return []
    out: list[dict[str, Any]] = []
    for ln in LESSONS_JSONL.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if not include_expired and e.get("expired"):
            continue
        out.append(e)
    return out[-limit:]


def expire_stale_easy_wins() -> int:
    """Mark easy-family keep lessons expired once harder-family lessons exist."""
    if not LESSONS_JSONL.exists():
        return 0
    lines = LESSONS_JSONL.read_text(encoding="utf-8").splitlines()
    entries: list[dict[str, Any]] = []
    for ln in lines:
        try:
            entries.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    has_hard = any(
        (e.get("family") in HARD_FAMILIES or "hard" in str(e.get("check") or "").lower())
        and e.get("decision") == "keep"
        and not e.get("expired")
        for e in entries
    )
    if not has_hard:
        return 0
    n = 0
    for e in entries:
        if (
            e.get("family") in EASY_FAMILIES
            and e.get("decision") == "keep"
            and not e.get("expired")
        ):
            e["expired"] = True
            e["expire_reason"] = "harder_check_supersedes_easy_win"
            n += 1
    if n:
        LESSONS_JSONL.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
            encoding="utf-8",
        )
    return n


def skill_bias_from_lessons(*, lookback: int = 40) -> dict[str, float]:
    """Aggregate skill biases from recent non-expired keep/revert lessons."""
    lessons = load_lessons(limit=lookback)
    bias: dict[str, float] = {}
    weights: dict[str, float] = {}
    for e in lessons:
        sb = e.get("skill_bias") or {}
        decision = e.get("decision")
        ltype = e.get("type") or decision
        # Keeps reinforce; reverts push opposite lightly; guides teach
        sign = 1.0 if decision == "keep" else (-0.5 if decision == "revert" else 0.0)
        if ltype == "human_guide" or decision == "guide":
            sign = 1.5
        elif ltype == "oracle_kill":
            sign = -1.0 if sign == 0.0 else sign
            # Also apply skill_bias at full weight for kill teaching
            if sign == 0.0:
                sign = -0.5
        if e.get("family") in EASY_FAMILIES:
            sign *= 0.0  # SPARK: easy_pad keeps get zero genome/skill bias (die)
        for k, v in sb.items():
            weights[k] = weights.get(k, 0.0) + abs(sign) if sign != 0 else weights.get(k, 0.0) + 1.0
            bias[k] = bias.get(k, 0.0) + float(v) * (sign if sign != 0 else 1.0)
    out: dict[str, float] = {}
    for k, total in bias.items():
        w = weights.get(k) or 1.0
        out[k] = round(max(-0.2, min(0.2, total / w)), 4)
    return out


def apply_lesson_bias_to_agents(agents: dict[str, Any]) -> dict[str, float]:
    """Mutate agent skill weights in-place from lesson ledger (measured, bounded)."""
    bias = skill_bias_from_lessons()
    if not bias:
        return bias
    for role, agent in agents.items():
        if (agent or {}).get("status") == "retired":
            continue
        skills = agent.setdefault("skills", {})
        for key, delta in bias.items():
            # key forms: "gather", "role.skill", or skill name
            if "." in key:
                r, sk = key.split(".", 1)
                if r != role:
                    continue
                skills[sk] = round(max(0.05, min(0.99, float(skills.get(sk) or 0.5) + delta)), 4)
            else:
                if key in skills:
                    skills[key] = round(max(0.05, min(0.99, float(skills[key]) + delta)), 4)
    return bias


def apply_lesson_bias_to_genomes(root: Path | None = None) -> int:
    """Soft-nudge genome trait files from keep lessons (explore/gather/build)."""
    root = root or ROOT
    bias = skill_bias_from_lessons()
    if not bias:
        return 0
    trait_map = {
        "gather": "gather",
        "build": "build",
        "communicate": "reply",
        "reply": "reply",
        "improve": "explore",
        "emergence": "explore",
        "oracle": "explore",
        "hard_tier": "explore",
    }
    # SPARK: if keep lessons outweigh reverts on communicate, nudge reply trait
    n = 0
    gdir = root / "society" / "genomes"
    if not gdir.is_dir():
        return 0
    for path in gdir.glob("*.json"):
        try:
            g = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        traits = g.setdefault("traits", {})
        changed = False
        for sk, delta in bias.items():
            sk_base = sk.split(".")[-1]
            trait = trait_map.get(sk_base)
            if not trait or trait not in traits:
                continue
            traits[trait] = round(max(0.05, min(0.99, float(traits[trait]) + 0.5 * delta)), 4)
            changed = True
        if changed:
            g["lesson_bias_ts"] = _utc()
            path.write_text(json.dumps(g, indent=2) + "\n", encoding="utf-8")
            n += 1
    return n


def persist_system(*, cycle_id: str = "") -> None:
    lessons = load_lessons(limit=80, include_expired=True)
    active = [e for e in lessons if not e.get("expired")]
    keeps = sum(1 for e in active if e.get("decision") == "keep")
    reverts = sum(1 for e in active if e.get("decision") == "revert")
    payload = {
        "version": 1,
        "updated_at": _utc(),
        "updated_cycle": cycle_id,
        "n_active": len(active),
        "n_keeps": keeps,
        "n_reverts": reverts,
        "skill_bias": skill_bias_from_lessons(),
        "recent": active[-12:],
        "note": (
            "Lessons from keep/revert only. Stale easy wins expire under harder checks. "
            "Candidates until human authorize. Not AGI."
        ),
    }
    LEDGER_SYSTEM.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_SYSTEM.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def digest(*, limit: int = 5) -> str:
    active = load_lessons(limit=limit)
    if not active:
        return "(no lessons yet)"
    parts = []
    for e in active[-limit:]:
        parts.append(
            f"[{e.get('decision')}/{e.get('family')}] {e.get('mutation') or e.get('check')}: "
            f"{(e.get('what') or '')[:60]}"
        )
    return " | ".join(parts)


def catalog_hints_from_lessons(*, lookback: int = 40) -> list[dict[str, Any]]:
    """Recent catalog_hint payloads from kill/exhausted lessons (priors for desk)."""
    out: list[dict[str, Any]] = []
    for e in load_lessons(limit=lookback):
        hint = e.get("catalog_hint") or {}
        if hint.get("add_mutation"):
            out.append(dict(hint))
    return out


def proposal_fingerprint_counts(*, days: int = 14, lookback: int = 400) -> dict[str, int]:
    """Count repeat_proposal / hearing_* fingerprints (approx by recent lessons)."""
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    counts: dict[str, int] = {}
    for e in load_lessons(limit=lookback, include_expired=True):
        fp = e.get("proposal_fingerprint") or ""
        if not fp:
            continue
        ts = e.get("ts") or ""
        try:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if dt < cutoff:
                continue
        except ValueError:
            pass
        counts[fp] = counts.get(fp, 0) + 1
    return counts


def write_human_guide(
    *,
    what: str,
    author: str = "James Paul Jackson",
    mutation: str = "",
    catalog_hint: dict[str, Any] | None = None,
    skill_bias: dict[str, float] | None = None,
    genome_prior: dict[str, float] | None = None,
    cycle_id: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Explicit human path to append a human_guide lesson (teaching prior only)."""
    return write_lesson(
        decision="guide",
        check="human",
        what=what,
        source="human",
        author=author,
        mutation=mutation,
        lesson_type="human_guide",
        family="human_teaching",
        catalog_hint=catalog_hint,
        skill_bias=skill_bias,
        genome_prior=genome_prior,
        cycle_id=cycle_id,
        tags=list(tags or ["human_guide"]),
    )
