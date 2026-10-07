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
    "schema_drift", "self_repair",
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


def _lessons_with_guides(*, lookback: int = 40) -> list[dict[str, Any]]:
    """Recent lessons plus ALL active human_guide rows (guides must not drown under kills)."""
    recent = load_lessons(limit=lookback)
    by_id = {e.get("id"): e for e in recent if e.get("id")}
    for e in load_lessons(limit=400):
        if (e.get("type") == "human_guide" or e.get("decision") == "guide") and not e.get("expired"):
            by_id[e.get("id") or id(e)] = e
    return list(by_id.values())


def skill_bias_from_lessons(*, lookback: int = 40) -> dict[str, float]:
    """Aggregate skill biases from recent lessons; human_guide always included as prior."""
    lessons = _lessons_with_guides(lookback=lookback)
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
    """Soft-nudge genome trait files from skill_bias + human_guide genome_prior."""
    root = root or ROOT
    bias = skill_bias_from_lessons()
    # Fold explicit genome_prior from durable human_guide lessons (teaching priors).
    for e in _lessons_with_guides(lookback=40):
        if e.get("type") != "human_guide" and e.get("decision") != "guide":
            continue
        for trait, delta in (e.get("genome_prior") or {}).items():
            try:
                bias[str(trait)] = round(
                    max(-0.2, min(0.2, float(bias.get(str(trait)) or 0.0) + 1.5 * float(delta))),
                    4,
                )
            except (TypeError, ValueError):
                continue
    if not bias:
        return 0
    trait_map = {
        "gather": "gather",
        "build": "build",
        "communicate": "reply",
        "reply": "reply",
        "improve": "explore",
        "explore": "explore",
        "emergence": "explore",
        "oracle": "explore",
        "hard_tier": "explore",
        "novelty": "explore",
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
            trait = trait_map.get(sk_base) or (sk_base if sk_base in traits else None)
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
    """Surface human_guide priors first, then recent outcome lessons."""
    guides = [
        e for e in load_lessons(limit=400)
        if (e.get("type") == "human_guide" or e.get("decision") == "guide") and not e.get("expired")
    ]
    recent = load_lessons(limit=max(limit * 3, 12))
    # Prefer guides, then non-guide recent, de-dupe by id
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for e in list(guides[-limit:]) + list(recent[-limit:]):
        eid = str(e.get("id") or "")
        if eid and eid in seen:
            continue
        if eid:
            seen.add(eid)
        ordered.append(e)
        if len(ordered) >= limit:
            break
    if not ordered:
        return "(no lessons yet)"
    parts = []
    for e in ordered:
        parts.append(
            f"[{e.get('type') or e.get('decision')}/{e.get('family')}] "
            f"{e.get('mutation') or e.get('check')}: {(e.get('what') or '')[:60]}"
        )
    return " | ".join(parts)


def catalog_hints_from_lessons(*, lookback: int = 40) -> list[dict[str, Any]]:
    """Recent catalog_hint payloads; human_guide hints always eligible as priors."""
    out: list[dict[str, Any]] = []
    for e in _lessons_with_guides(lookback=lookback):
        hint = e.get("catalog_hint") or {}
        if hint.get("add_mutation") or hint.get("prefer") or hint.get("seek"):
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




def guide_process_spam_avoided() -> bool:
    """True when an active human_guide prefers real fitness over process spam."""
    for e in _lessons_with_guides(lookback=40):
        if e.get("type") != "human_guide" and e.get("decision") != "guide":
            continue
        hint = e.get("catalog_hint") or {}
        avoid = [str(x).lower() for x in (hint.get("avoid") or [])]
        tags = [str(x).lower() for x in (e.get("tags") or [])]
        prefer = [str(x).lower() for x in (hint.get("prefer") or [])]
        if any(a in ("process_spam", "multihop_debate_patch") for a in avoid):
            return True
        if "become" in tags and any(p in prefer for p in ("novelty", "citation_reuse", "bench_delta", "lesson_uptake")):
            return True
    return False



KILL_COOLDOWN_THRESHOLD = 3  # repeated Oracle kills → drop theme, seek elsewhere


def theme_key(text: str) -> str:
    """Normalize a mutation/theme from title, mutation field, or action string."""
    import re
    s = (text or "").strip().lower()
    if not s:
        return ""
    m = re.search(r"`([a-z][a-z0-9_]{2,})`", s)
    if m:
        return m.group(1)
    m = re.search(r"(?:seek_enable|enable):([a-z][a-z0-9_]{2,})", s)
    if m:
        return m.group(1)
    m = re.match(r"^([a-z][a-z0-9_]{2,})$", s)
    if m:
        return m.group(1)
    # Prefer known-looking snake tokens over stopwords
    _STOP = {
        "seek", "citing", "from", "papers", "lessons", "oracle", "kill", "fail",
        "keep", "cycle", "new", "the", "and", "for", "with", "that", "this",
    }
    for tok in re.findall(r"\b([a-z][a-z0-9_]{3,})\b", s):
        if tok not in _STOP and "_" in tok:
            return tok
    return s[:48]


def oracle_kill_theme_counts(*, lookback: int = 400) -> dict[str, int]:
    """Count Oracle kills per theme (guides teach: drop after repeats)."""
    counts: dict[str, int] = {}
    for e in load_lessons(limit=lookback, include_expired=True):
        if e.get("type") != "oracle_kill":
            continue
        theme = theme_key(e.get("mutation") or "") or theme_key(e.get("what") or "")
        if theme:
            counts[theme] = counts.get(theme, 0) + 1
    return counts


def guide_avoid_themes() -> set[str]:
    """Themes human_guides explicitly mark avoid / drop_theme."""
    out: set[str] = set()
    for e in _lessons_with_guides(lookback=40):
        if e.get("type") != "human_guide" and e.get("decision") != "guide":
            continue
        h = e.get("catalog_hint") or {}
        for key in ("avoid", "drop_theme", "blocked_theme"):
            for a in (h.get(key) or []):
                t = theme_key(str(a))
                # Skip meta avoid labels that are not mutations
                if t and t not in {
                    "process_spam", "multihop_debate_patch", "prefer", "novelty",
                    "citation_reuse", "lesson_uptake", "bench_delta",
                }:
                    out.add(t)
    return out


def blocked_themes(*, threshold: int = KILL_COOLDOWN_THRESHOLD) -> dict[str, str]:
    """theme -> reason. kill_cooldown:N or guide_avoid. Spark/seek must respect."""
    out: dict[str, str] = {}
    for theme, n in oracle_kill_theme_counts().items():
        if n >= threshold:
            out[theme] = f"kill_cooldown:{n}"
    for theme in guide_avoid_themes():
        out.setdefault(theme, "guide_avoid")
    return out


def theme_is_blocked(theme: str, *, threshold: int = KILL_COOLDOWN_THRESHOLD) -> bool:
    t = theme_key(theme)
    return bool(t) and t in blocked_themes(threshold=threshold)


def next_unblocked_mutation(
    candidates: list[str],
    *,
    threshold: int = KILL_COOLDOWN_THRESHOLD,
) -> str:
    """First candidate not under kill cooldown / guide avoid; else empty."""
    blocked = blocked_themes(threshold=threshold)
    for c in candidates:
        t = theme_key(c)
        if t and t not in blocked:
            return t
    return ""


def seek_proposal_from_guides(*, cycle_id: str = "") -> tuple[str, str, str] | None:
    """Build one seek-oriented improvement from guides + papers/ledger themes (not process spam).

    Respects kill cooldown / guide avoid: never re-propose a repeatedly Oracle-killed theme.
    """
    if not guide_process_spam_avoided():
        return None
    theme_title = ""
    theme_url = ""
    try:
        from colony.conjecture_desk import _load_paper_themes
        themes = _load_paper_themes() or []
        if themes:
            # Prefer a paper theme whose title token is not a cooled mutation name
            t0 = themes[0]
            for t in themes:
                # rotate off first if we already looped on it with a blocked mut
                t0 = t
                break
            theme_title = (t0.get("title") or "paper theme")[:90]
            theme_url = (t0.get("url") or t0.get("arxiv_id") or "")[:120]
    except Exception:
        pass
    candidates: list[str] = []
    # Prefer explicit add_mutation from seek/become/drop guides (newest guides last in file → later wins preference via reverse)
    guide_rows = [e for e in _lessons_with_guides(lookback=40) if e.get("type") == "human_guide"]
    # Prefer guides tagged kill_cooldown / drop / seek (drop guide should outrank stale add_mutation)
    def _guide_rank(e: dict) -> int:
        tags = {str(x).lower() for x in (e.get("tags") or [])}
        score = 0
        if "kill_cooldown" in tags or "drop" in tags:
            score += 3
        if "seek" in tags or "become" in tags or "extend" in tags:
            score += 1
        return score
    guide_rows = sorted(guide_rows, key=_guide_rank, reverse=True)
    for e in guide_rows:
        h = e.get("catalog_hint") or {}
        if h.get("add_mutation"):
            candidates.append(str(h["add_mutation"]))
    # Fallbacks from mutation catalog (skip easy_pad noise)
    try:
        from colony.conjecture_mutations import MUTATION_SNIPPETS
        for name, kind, _snip in MUTATION_SNIPPETS:
            if str(kind).startswith("easy") or str(name).startswith("easy_pad"):
                continue
            candidates.append(str(name))
    except Exception:
        pass
    candidates.append("stem_easy_pad_units")
    # Dedup preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        t = theme_key(c) or c
        if t in seen:
            continue
        seen.add(t)
        ordered.append(c)
    mut = next_unblocked_mutation(ordered)
    if not mut:
        mut = theme_key(ordered[-1]) if ordered else "binomial_hockey_deep"
    if not mut:
        mut = "binomial_hockey_deep"
    cooled = blocked_themes()
    title = f"Seek+enable `{mut}` from papers/lessons"
    if theme_title:
        title = f"Seek `{mut}` citing {theme_title[:50]}"
    hyp = (
        f"SEEK INFORMATION prior: gather from ledger/papers before proposing. "
        f"Target mutation `{mut}`. Source={theme_url or 'papers.jsonl/lessons'}. "
        f"Raise novelty/citation_reuse/lesson_uptake — not process spam. "
        f"Cooled themes skipped={sorted(cooled)[:6]}. cycle={cycle_id}."
    )
    action = f"seek_enable:{mut}"
    return title, hyp, action

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
