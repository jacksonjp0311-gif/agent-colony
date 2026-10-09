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

# Machine-checkable invariant / chain mutations (combinatorics, derived proofs, STEM).
# Guides teach: seek these and compose them — not isolated renames.
INVARIANT_CHAIN_MUTATIONS: tuple[str, ...] = (
    "derived_chain_stress",
    "workload_derived_chain",
    "fibonacci_cassini_ext",
    "binomial_hockey_deep",
    "energy_work",
    "catalan_convolution",
    "lagrange_identity",
)


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
    "authored_check", "authoring_reject",
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


_GUIDE_CACHE: dict[str, Any] = {"key": None, "rows": []}


def load_human_guides(*, include_expired: bool = False) -> list[dict[str, Any]]:
    """ALL human_guide rows from the whole lessons file, however far back they are.

    Guides are teaching priors, so they must never fall out of a recent-N window the way
    outcome lessons do. Cheap: substring prefilter before json parse, cached on
    (path, mtime_ns, size) so repeated calls in one cycle do not re-read the file.
    """
    path = LESSONS_JSONL
    if not path.exists():
        return []
    try:
        st = path.stat()
    except OSError:
        return []
    key = (str(path), st.st_mtime_ns, st.st_size)
    if _GUIDE_CACHE.get("key") != key:
        rows: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as fh:
            for ln in fh:
                if '"human_guide"' not in ln and '"guide"' not in ln:
                    continue
                try:
                    e = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if e.get("type") == "human_guide" or e.get("decision") == "guide":
                    rows.append(e)
        _GUIDE_CACHE["key"] = key
        _GUIDE_CACHE["rows"] = rows
    return [dict(e) for e in _GUIDE_CACHE["rows"] if include_expired or not e.get("expired")]


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
    for e in load_human_guides():  # whole file — guides never age out of a window
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
    guides = load_human_guides()
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


def is_title_only_kill(e: dict, *, _cache: dict | None = None) -> bool:
    """True for an oracle_kill lesson that judged a seek proposal's TITLE TEXT, not its target.

    Identified from the row's own fields (history is never rewritten): written by the novelty
    gate (source ``novelty_gate``) on a kind=process claim (family ``process``) whose text names
    a resolved target (``Chain `<catalog entry>` …``) and is not that target itself. Those rows
    are not a verdict on the lemma; the Oracle's verdict on the target is a separate row with the
    lemma as its mutation, and that one still counts. Unresolved titles keep counting. Fail
    closed: if the target cannot be resolved, the kill counts. A deferred title check (source
    ``novelty_gate_deferred_title``: the target was never judged in its cycle) also counts —
    otherwise a target the desk never judges could be re-proposed forever.
    """
    if e.get("type") != "oracle_kill":
        return False
    if str(e.get("source") or "") != "novelty_gate" or str(e.get("family") or "") != "process":
        return False
    mut = str(e.get("mutation") or "").strip()
    if not mut:
        return False
    cache = _cache if _cache is not None else {}
    if mut not in cache:
        try:
            from colony.standing_trust import resolve_proposal_target
            cache[mut] = resolve_proposal_target(action="", mutation=mut)
        except Exception:
            cache[mut] = ""
    target = cache[mut]
    return bool(target) and target != mut.lower()


def oracle_kill_theme_counts(*, lookback: int = 400) -> dict[str, int]:
    """Count Oracle kills per theme (guides teach: drop after repeats).

    Only real Oracle kills of a lemma/claim count; title-only kills on proposals whose target
    resolved (:func:`is_title_only_kill`) are filtered out. Guide-based blocks are separate
    (:func:`guide_avoid_themes`) and unaffected.
    """
    counts: dict[str, int] = {}
    _cache: dict[str, str] = {}
    for e in load_lessons(limit=lookback, include_expired=True):
        if e.get("type") != "oracle_kill":
            continue
        if is_title_only_kill(e, _cache=_cache):
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


GUIDE_AVOID_MIN_LEN = 6  # shorter guide-avoid tokens are labels, not mutation stems


class MutationCooldown:
    """One shared cooldown filter for every mutation picker (seek, conjecture desk).

    A mutation name is cooled when any of these hold:

    * ``kill_cooldown:N`` / ``guide_avoid`` — its theme is in :func:`blocked_themes`
      (exact theme match; the same set spark/seek already respect);
    * ``guide_avoid:<t>`` — a human guide's avoid/drop token (len >= 6) is a substring of the
      name, so a guide saying ``easy_pad`` or ``vandermonde_asymmetric`` also covers
      ``easy_pad_diff_squares`` / ``vandermonde_asymmetric_w2`` (as seek variants already did);
    * ``revert_penalty:N`` — the exploration budget recorded N >= threshold reverts of it.

    Build it once per pick (:func:`mutation_cooldown`) so every candidate is judged against the
    same snapshot. Fail closed: if the cooldown sources cannot be read, the filter raises and
    the caller must not fall back to an unfiltered pick.
    """

    def __init__(
        self,
        *,
        blocked: dict[str, str],
        avoided: set[str],
        penalties: dict[str, int] | None = None,
        threshold: int = KILL_COOLDOWN_THRESHOLD,
    ) -> None:
        self.blocked = blocked if blocked is not None else {}
        self.avoided = {t for t in avoided if t and len(t) >= GUIDE_AVOID_MIN_LEN}
        self.penalties = {str(k): int(v or 0) for k, v in (penalties or {}).items()}
        self.threshold = int(threshold)

    def reason(self, name: str) -> str:
        """Why ``name`` is cooled, or ``""`` when it may be picked."""
        raw = (name or "").strip().lower()
        t = theme_key(name)
        if not t:
            return ""
        if t in self.blocked:
            return str(self.blocked.get(t) or "blocked")
        for a in sorted(self.avoided):
            if a in raw:
                return f"guide_avoid:{a}"
        n = self.penalties.get(name) or self.penalties.get(t) or 0
        if n >= self.threshold:
            return f"revert_penalty:{n}"
        return ""

    def allows(self, name: str) -> bool:
        return not self.reason(name)


def mutation_cooldown(*, threshold: int = KILL_COOLDOWN_THRESHOLD, with_penalties: bool = True) -> MutationCooldown:
    """Snapshot of kill cooldown + human-guide blocks + exploration revert penalties."""
    penalties: dict[str, int] = {}
    if with_penalties:
        from colony.exploration_budget import load_budget
        penalties = dict((load_budget() or {}).get("revert_penalties") or {})
    return MutationCooldown(
        blocked=blocked_themes(threshold=threshold),
        avoided=guide_avoid_themes(),
        penalties=penalties,
        threshold=threshold,
    )


def next_unblocked_mutation(
    candidates: list[str],
    *,
    threshold: int = KILL_COOLDOWN_THRESHOLD,
) -> str:
    """First candidate the shared :class:`MutationCooldown` allows; else empty."""
    cooldown = mutation_cooldown(threshold=threshold)
    for c in candidates:
        t = theme_key(c)
        if t and cooldown.allows(t):
            return t
    return ""



def guide_prefers_invariant_chains() -> bool:
    """True when an active human_guide prefers machine-checkable invariants / lemma chains."""
    for e in _lessons_with_guides(lookback=40):
        if e.get("type") != "human_guide" and e.get("decision") != "guide":
            continue
        tags = {str(x).lower() for x in (e.get("tags") or [])}
        hint = e.get("catalog_hint") or {}
        prefer = [str(x).lower() for x in (hint.get("prefer") or [])]
        if tags & {"invariant", "invariants", "chain", "compose", "derived_chain"}:
            return True
        if any(
            p in prefer
            for p in (
                "invariant",
                "invariants",
                "machine_checkable",
                "lemma_chain",
                "derived_chain",
                "compose_lemmas",
                "proof_chain",
            )
        ):
            return True
    return False


def preferred_invariant_mutations() -> list[str]:
    """Ordered invariant/chain mutation names from guides, then defaults (unblocked first)."""
    ordered: list[str] = []
    seen: set[str] = set()
    for e in _lessons_with_guides(lookback=40):
        if e.get("type") != "human_guide" and e.get("decision") != "guide":
            continue
        h = e.get("catalog_hint") or {}
        tags = {str(x).lower() for x in (e.get("tags") or [])}
        prefer = [str(x).lower() for x in (h.get("prefer") or [])]
        is_inv = bool(tags & {"invariant", "invariants", "chain", "compose", "derived_chain"}) or any(
            p in prefer
            for p in ("invariant", "invariants", "machine_checkable", "lemma_chain", "derived_chain", "compose_lemmas", "proof_chain")
        )
        if not is_inv:
            continue
        for key in ("add_mutation", "chain_mutation"):
            mut = theme_key(str(h.get(key) or ""))
            if mut and mut not in seen:
                seen.add(mut)
                ordered.append(mut)
        for m in (h.get("prefer_mutations") or h.get("chain") or []):
            mut = theme_key(str(m))
            if mut and mut not in seen:
                seen.add(mut)
                ordered.append(mut)
    for m in INVARIANT_CHAIN_MUTATIONS:
        if m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered


# --- Chain citations (human_guide: cite proven lemmas + society/benchmarks) ----------

BENCH_DIR = ROOT / "society" / "benchmarks"
BENCH_ARTIFACTS_DIR = BENCH_DIR / "artifacts"
BENCH_LATEST = BENCH_DIR / "latest.json"
CITE_GUIDE_TAGS = {"cite", "cite_benchmarks", "cite_lemmas", "bench_cite"}
CITE_GUIDE_REQUIRE = {"bench_cite", "lemma_cite", "cite_benchmarks", "cite_lemmas"}


def guide_requires_chain_cites() -> bool:
    """True when an active human_guide requires chain proposals to cite lemmas + bench artifacts."""
    for e in _lessons_with_guides(lookback=40):
        if e.get("type") != "human_guide" and e.get("decision") != "guide":
            continue
        tags = {str(x).lower() for x in (e.get("tags") or [])}
        hint = e.get("catalog_hint") or {}
        req = {str(x).lower() for x in (hint.get("require") or [])}
        if tags & CITE_GUIDE_TAGS or req & CITE_GUIDE_REQUIRE:
            return True
    return False


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _check_calls(node: Any) -> list[str]:
    """Names of check_* functions called anywhere under an AST node (source order, dedup)."""
    import ast
    out: list[str] = []
    for sub in ast.walk(node):
        name = ""
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
            name = sub.func.id
        elif isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
            name = sub.id
        if name.startswith("check_") and name not in out:
            out.append(name)
    return out


def _scan_bench_artifact(path: Path) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Parse one artifact: (check functions by name, catalog entry name -> referenced check fns)."""
    funcs, catalog, _enabled = _scan_bench_artifact_full(path)
    return funcs, catalog


def _scan_bench_artifact_full(
    path: Path,
) -> tuple[dict[str, Any], dict[str, list[str]], dict[str, bool | None]]:
    """Parse one artifact: (check fns, catalog name -> referenced check fns, catalog name -> enabled).

    Catalogs are module-level lists of (name, callable, enabled) tuples
    (CANDIDATE_LEMMAS / HARD_TIER_LEMMAS / STEM_CHECKS) — read from source, never executed.
    """
    import ast
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return {}, {}, {}
    funcs: dict[str, Any] = {}
    catalog: dict[str, list[str]] = {}
    enabled: dict[str, bool | None] = {}
    aliases: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("check_"):
            funcs[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if isinstance(value, ast.Name) and value.id.startswith("check_"):
                for t in targets:
                    if isinstance(t, ast.Name):
                        aliases[t.id] = value.id
            if isinstance(value, ast.List):
                for elt in value.elts:
                    if (
                        isinstance(elt, ast.Tuple)
                        and len(elt.elts) >= 2
                        and isinstance(elt.elts[0], ast.Constant)
                        and isinstance(elt.elts[0].value, str)
                    ):
                        refs = [aliases.get(n, n) for n in _check_calls(elt.elts[1])]
                        catalog.setdefault(elt.elts[0].value, refs)
                        flag = None
                        if len(elt.elts) >= 3 and isinstance(elt.elts[2], ast.Constant):
                            if isinstance(elt.elts[2].value, bool):
                                flag = elt.elts[2].value
                        enabled.setdefault(elt.elts[0].value, flag)
    return funcs, catalog, enabled


def _bench_check_status() -> dict[str, bool]:
    """Latest machine-check results keyed by catalog name (prefix basic:/hard:/stem: stripped)."""
    try:
        data = json.loads(BENCH_LATEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, bool] = {}
    for b in data.get("benches") or []:
        for k, v in ((b or {}).get("checks") or {}).items():
            name = str(k).split(":", 1)[-1]
            # A lemma is proven only if every recorded check of it passed
            out[name] = bool(v) and out.get(name, True)
    return out


def chain_citations(mutation: str) -> dict[str, Any] | None:
    """Look up the bench artifact + proven lemmas a (chain) mutation actually composes.

    Reads society/benchmarks/artifacts/*.py (AST, not exec) and society/benchmarks/latest.json.
    Returns None when no artifact checks this mutation — the colony must not invent a cite.
    """
    mut = theme_key(mutation) or str(mutation or "").strip()
    if not mut or not BENCH_ARTIFACTS_DIR.is_dir():
        return None
    status = _bench_check_status()
    for path in sorted(BENCH_ARTIFACTS_DIR.glob("*.py")):
        if path.name.startswith("__"):
            continue
        funcs, catalog = _scan_bench_artifact(path)
        roots: list[str] = []
        if mut in catalog:
            roots = [f for f in catalog[mut] if f in funcs]
        if not roots and f"check_{mut}" in funcs:
            roots = [f"check_{mut}"]
        if not roots:
            continue
        # Reverse map: check fn -> catalog lemma that runs exactly that check
        fn_to_lemma: dict[str, str] = {}
        for name, refs in catalog.items():
            if len(refs) == 1 and refs[0] not in fn_to_lemma and name != mut:
                if name.startswith("adversarial_") and refs[0] != f"check_{name}":
                    continue
                fn_to_lemma[refs[0]] = name
        links: list[dict[str, Any]] = []
        seen: set[str] = set()
        # A variant that re-runs another catalog lemma's check (e.g. an adversarial
        # window aliasing check_derived_chain_stress) is built from that lemma.
        for root in roots:
            base = fn_to_lemma.get(root)
            if base and base != mut and root not in seen:
                seen.add(root)
                links.append({"lemma": base, "function": root, "proven": status.get(base) is True})
        for root in roots:
            for fn in _check_calls(funcs[root]):
                if fn in roots or fn in seen or fn not in funcs:
                    continue
                seen.add(fn)
                lemma = fn_to_lemma.get(fn) or fn[len("check_"):]
                links.append({"lemma": lemma, "function": fn, "proven": status.get(lemma) is True})
        stem = path.stem
        benches = sorted(
            _rel(b)
            for b in BENCH_DIR.glob("*microbench*.py")
            if stem in b.read_text(encoding="utf-8", errors="ignore")
        )
        return {
            "mutation": mut,
            "artifact": _rel(path),
            "function": roots[0],
            "links": links,
            "chain_proven": status.get(mut) is True,
            "bench": benches,
            "status_source": _rel(BENCH_LATEST) if status else "",
        }
    return None


def chain_cite_note(cites: dict[str, Any] | None) -> str:
    """Human-readable cite clause for a proposal hypothesis (empty when nothing to cite)."""
    if not cites:
        return ""
    proven = [l["lemma"] for l in cites.get("links") or [] if l.get("proven")]
    unproven = [l["lemma"] for l in cites.get("links") or [] if not l.get("proven")]
    parts = [f" Cites {cites['artifact']}::{cites['function']}"]
    if cites.get("links"):
        parts.append(f" composing proven lemmas [{', '.join(proven) or 'none'}]")
        if unproven:
            parts.append(f" + unverified links [{', '.join(unproven)}]")
    if cites.get("status_source"):
        state = "pass" if cites.get("chain_proven") else "not yet passing"
        parts.append(f" ({cites['mutation']} {state} in {cites['status_source']})")
    if cites.get("bench"):
        parts.append(f"; checked by {', '.join(cites['bench'])}")
    return "".join(parts) + "."


def chain_cite_evidence(action_or_mutation: str) -> list[str]:
    """Evidence entries (bench paths + proven lemma ids) for a seek/chain proposal action."""
    if not guide_requires_chain_cites():
        return []
    raw = str(action_or_mutation or "")
    if ":" in raw:
        raw = raw.split(":", 1)[1]
    cites = chain_citations(raw)
    if not cites:
        return []
    ev = [f"{cites['artifact']}::{cites['function']}"]
    ev += list(cites.get("bench") or [])
    if cites.get("status_source"):
        ev.append(cites["status_source"])
    ev += [f"lemma:{l['lemma']}" for l in cites.get("links") or [] if l.get("proven")]
    return ev


# --- Unenabled harder variants built from proven lemmas (human_guide) --------------

VARIANT_GUIDE_TAGS = {"unenabled_variant", "unenabled_variants", "seek_unproven", "harder_variant"}


def guide_seeks_unenabled_variants() -> bool:
    """True when an active human_guide says: re-enabling adds nothing — seek unenabled variants."""
    for e in load_human_guides():
        tags = {str(x).lower() for x in (e.get("tags") or [])}
        hint = e.get("catalog_hint") or {}
        prefer = {str(x).lower() for x in (hint.get("prefer") or [])}
        if tags & VARIANT_GUIDE_TAGS or prefer & VARIANT_GUIDE_TAGS:
            return True
    return False


def target_enabled(mutation: str) -> bool | None:
    """Enabled flag of a catalog entry in society/benchmarks/artifacts (None = not in a catalog)."""
    mut = theme_key(mutation) or str(mutation or "").strip()
    if not mut or not BENCH_ARTIFACTS_DIR.is_dir():
        return None
    for path in sorted(BENCH_ARTIFACTS_DIR.glob("*.py")):
        if path.name.startswith("__"):
            continue
        _f, _c, enabled = _scan_bench_artifact_full(path)
        if mut in enabled:
            return enabled[mut]
    return None


def _variant_kind(artifact: str) -> str:
    """Desk mutation kind for an artifact catalog (kinematics → STEM pack, else hard tier)."""
    return "stem_enable" if "kinematics" in artifact else "hard_enable"


def unenabled_chain_variants(*, respect_cooldown: bool = True) -> list[dict[str, Any]]:
    """Disabled catalog entries whose components are ALL proven lemmas (discovered, not listed).

    Read from society/benchmarks/artifacts catalogs + latest.json. Each row carries the cite
    (artifact, component lemmas, microbench) so proposals stay honest. Cooled themes skipped.
    """
    if not BENCH_ARTIFACTS_DIR.is_dir():
        return []
    # Shared cooldown filter (same one the conjecture desk uses). A human "drop this theme"
    # also drops its harder variants (e.g. vandermonde_asymmetric).
    cooldown = mutation_cooldown() if respect_cooldown else None
    out: list[dict[str, Any]] = []
    for path in sorted(BENCH_ARTIFACTS_DIR.glob("*.py")):
        if path.name.startswith("__"):
            continue
        _f, _c, enabled = _scan_bench_artifact_full(path)
        for name, flag in enabled.items():
            if flag is not False:
                continue
            if cooldown is not None and not cooldown.allows(name):
                continue
            cites = chain_citations(name)
            if not cites:
                continue
            links = cites.get("links") or []
            if not links or not all(l.get("proven") for l in links):
                continue  # only variants composed of machine-checked, passing lemmas
            out.append(
                {
                    "name": name,
                    "kind": _variant_kind(cites["artifact"]),
                    "artifact": cites["artifact"],
                    "components": [l["lemma"] for l in links],
                    "bench": list(cites.get("bench") or []),
                }
            )
    return out


def variant_mutation_snippets() -> list[tuple[str, str, str]]:
    """(name, kind, snippet) desk candidates for unenabled variants when the guide is active."""
    if not guide_seeks_unenabled_variants():
        return []
    return [(v["name"], v["kind"], f"enable:{v['name']}") for v in unenabled_chain_variants()]


def preferred_variant_mutations() -> list[str]:
    """Unenabled-variant names to try first (empty unless the guide is active)."""
    return [n for n, _k, _s in variant_mutation_snippets()]


def seek_proposal_from_guides(*, cycle_id: str = "") -> tuple[str, str, str] | None:
    """Build one seek-oriented improvement from guides + papers/ledger themes (not process spam).

    Respects kill cooldown / guide avoid: never re-propose a repeatedly Oracle-killed theme.
    """
    if not (guide_process_spam_avoided() or guide_prefers_invariant_chains()):
        return None
    theme_title = ""
    theme_url = ""
    feed_cite = ""
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
        if tags & {"invariant", "invariants", "chain", "compose", "derived_chain"}:
            score += 4  # James: prefer machine-checkable invariants / lemma chains
        if "seek" in tags or "become" in tags or "extend" in tags:
            score += 1
        return score
    guide_rows = sorted(guide_rows, key=_guide_rank, reverse=True)
    # Unenabled variant guide: harder not-yet-enabled variants of proven lemmas go first
    seek_variants = guide_seeks_unenabled_variants()
    variant_rows = {v["name"]: v for v in unenabled_chain_variants()} if seek_variants else {}
    candidates.extend(variant_rows)
    # Prefer invariant-chain mutations when guides ask (compose lemmas, not renames)
    if guide_prefers_invariant_chains():
        candidates.extend(preferred_invariant_mutations())
    for e in guide_rows:
        h = e.get("catalog_hint") or {}
        if h.get("add_mutation"):
            candidates.append(str(h["add_mutation"]))
        for m in (h.get("prefer_mutations") or h.get("chain") or []):
            if m:
                candidates.append(str(m))
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
    # Re-enabling an already-enabled target adds nothing (Oracle: stripped_not_useful) — skip
    if seek_variants:
        fresh = [c for c in ordered if target_enabled(theme_key(c) or c) is not True]
        if fresh:
            ordered = fresh
    # Cite guide: prefer mutations that a society/benchmarks artifact actually checks
    # (proven chain first) so the proposal can name real lemmas — never invent a cite.
    require_cites = guide_requires_chain_cites()
    if require_cites:
        def _cite_rank(name: str) -> int:
            if (theme_key(name) or name) in variant_rows:
                return 0  # unenabled variant built from proven lemmas
            c = chain_citations(name)
            if not c:
                return 2
            return 0 if c.get("chain_proven") else 1
        ordered = sorted(ordered, key=_cite_rank)  # stable: keeps guide order within rank
    # Sensors: targets on a current revert streak go last (still eligible; Oracle decides)
    try:
        from colony.sensors import revert_streak_names
        streak = revert_streak_names()
        if streak:
            ordered = sorted(ordered, key=lambda c: (theme_key(c) or c) in streak)
    except Exception:
        pass
    mut = next_unblocked_mutation(ordered)
    if not mut:
        # Every candidate is cooled / guide-avoided: never re-propose a blocked target.
        # Return nothing — the desk authors new checks (author guide) instead.
        return None
    try:
        # Outward senses: a recent external feed paper (arXiv / Crossref) related to the
        # chosen target when possible, rotated per cycle. Untrusted pointer — cited, never run.
        from colony.feeds import pick_seek_theme
        ft = pick_seek_theme(cycle_id, target=mut)
        if ft:
            theme_title = str(ft.get("title") or "")[:90]
            theme_url = str(ft.get("url") or "")[:120]
            feed_cite = (f" Feed cite: {ft.get('source')} `{ft.get('id')}` <{theme_url}> "
                         f"fetched {ft.get('fetched_at')} (external pointer, not evidence of truth).")
    except Exception:
        feed_cite = ""
    cooled = blocked_themes()
    title = f"Seek+enable `{mut}` from papers/lessons"
    if theme_title:
        title = f"Seek `{mut}` citing {theme_title[:50]}"
    inv_note = ""
    if guide_prefers_invariant_chains():
        inv_note = (
            " Prefer machine-checkable invariants (combinatorics/FFT/kinematics) "
            "and compose proven lemmas into longer proof chains — not isolated renames."
        )
        title = f"Chain+seek `{mut}` from invariant priors"
        if theme_title:
            title = f"Chain `{mut}` citing {theme_title[:50]}"
    hyp = (
        f"SEEK INFORMATION prior: gather from ledger/papers before proposing. "
        f"Target mutation `{mut}`. Source={theme_url or 'papers.jsonl/lessons'}. "
        f"Raise novelty/citation_reuse/lesson_uptake — not process spam. "
        f"Cooled themes skipped={sorted(cooled)[:6]}. cycle={cycle_id}."
        f"{inv_note}"
    )
    hyp += feed_cite
    if mut in variant_rows:
        v = variant_rows[mut]
        hyp += (
            f" Harder not-yet-enabled variant `{mut}` built from proven lemmas "
            f"[{', '.join(v['components'])}]; re-enabling already-on targets adds nothing. "
            f"Enable only if the Oracle held-out check passes."
        )
    if require_cites:
        cite = chain_cite_note(chain_citations(mut))
        hyp += cite or (
            f" No society/benchmarks artifact checks `{mut}` yet — build the check before claiming it."
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
