"""Accepted math/compute/RSI findings → agent *behavior* (not museum metrics).

Wires ledger-accepted findings into:
  - skill_router biases (gather/build/improve choices)
  - genome mutation biases (child spawn traits)
  - topic_priority ranks (what gather targets)
  - persona mandates / voice_wrap (prompts cite & reuse)

Math prize: agents that cite/reuse compute-useful accepted findings get
measurable fitness + spawn privilege. Hearing chamber can REJECT weak
proposals (status rejected) with witness. Not AGI.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
COUPLING_JSON = ROOT / "society" / "systems" / "findings_coupling.json"
ARTIFACT = ROOT / "society" / "artifacts" / "findings_behavior_coupling.md"

MATH_TOPICS = {
    "open-math-problems",
    "mathematics-foundations",
    "compute-useful-math",
}
COMPUTE_TOPICS = {
    "compute-useful-math",
    "emergent-technology",
    "software-engineering",
}
RSI_TOPICS = {
    "recursive-self-improvement",
    "meta-learning",
    "self-improving-agents",
    "godel-machines",
    "darwin-godel-machine",
    "reflexion",
    "self-refine",
}

# Follow-on gather targets when an accepted finding lands in a family
FOLLOW_ON = {
    "open-math-problems": ["compute-useful-math", "mathematics-foundations"],
    "mathematics-foundations": ["open-math-problems", "compute-useful-math"],
    "compute-useful-math": ["open-math-problems", "software-engineering", "emergent-technology"],
    "emergent-technology": ["compute-useful-math", "software-engineering"],
    "software-engineering": ["compute-useful-math", "emergent-technology"],
    "recursive-self-improvement": ["self-improving-agents", "meta-learning", "reflexion"],
    "self-improving-agents": ["recursive-self-improvement", "agent-societies"],
    "meta-learning": ["recursive-self-improvement", "reflexion"],
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
        "claim": (getattr(f, "claim", None) or "")[:280],
    }


def _status(f: Any) -> str:
    return str(getattr(f, "status", None) or (f.get("status") if isinstance(f, dict) else "") or "")


def _family(topic: str, tags: set[str]) -> str | None:
    if topic in MATH_TOPICS or "math" in tags or "prize" in tags:
        if topic in COMPUTE_TOPICS or "compute-useful-math" in tags or "FFT" in tags:
            return "compute"
        return "math"
    if topic in COMPUTE_TOPICS or "compute-useful-math" in tags:
        return "compute"
    if topic in RSI_TOPICS or bool(tags & {"rsi", "self-improve", "reflexion", "meta-learning"}):
        return "rsi"
    return None


def harvest_behavior_signal(findings: list[Any]) -> dict[str, Any]:
    """Score accepted math/compute/RSI findings for *behavior* coupling."""
    by_family: dict[str, list[dict[str, Any]]] = {"math": [], "compute": [], "rsi": []}
    for f in findings:
        if _status(f) != "accepted":
            continue
        d = _as_dict(f)
        tags = set(d.get("tags") or [])
        fam = _family(str(d.get("topic_id") or ""), tags)
        if not fam:
            # Soft: authorize titles that mention math/compute machinery
            title = (d.get("title") or "").lower()
            claim = (d.get("claim") or "").lower()
            if any(k in title or k in claim for k in ("fft", "autodiff", "transformer", "lean", "p versus", "millennium")):
                fam = "compute" if any(k in title for k in ("fft", "autodiff", "transformer")) else "math"
            elif any(k in title or k in claim for k in ("rsi", "self-improv", "reflexion", "gödel", "godel")):
                fam = "rsi"
            else:
                continue
        by_family[fam].append(d)

    n_math = len(by_family["math"])
    n_compute = len(by_family["compute"])
    n_rsi = len(by_family["rsi"])
    strength = min(
        1.0,
        0.40 * min(1.0, n_math / 4.0)
        + 0.40 * min(1.0, n_compute / 4.0)
        + 0.20 * min(1.0, n_rsi / 5.0),
    )

    # Topic boosts: accepted topics + follow-ons (behavior change for gather)
    topic_boosts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fam, items in by_family.items():
        for d in items[-8:]:
            tid = d.get("topic_id")
            if tid and tid not in seen:
                seen.add(tid)
                topic_boosts.append(
                    {
                        "topic": tid,
                        "priority": 1.15,
                        "reason": f"accepted_{fam}_finding",
                        "finding_id": d.get("id"),
                        "title": d.get("title"),
                    }
                )
            for fo in FOLLOW_ON.get(str(tid) or "", []):
                if fo not in seen:
                    seen.add(fo)
                    topic_boosts.append(
                        {
                            "topic": fo,
                            "priority": 1.05,
                            "reason": f"follow_on_from_{fam}",
                            "from_topic": tid,
                        }
                    )

    skill_bias = {
        "geometer.gather": round(0.55 + 0.40 * min(1.0, (n_math + n_compute) / 4.0), 4),
        "pathfinder.gather": round(0.50 + 0.30 * strength, 4),
        "surveyor.gather": round(0.50 + 0.25 * min(1.0, n_math / 3.0), 4),
        "builder.build": round(0.50 + 0.35 * min(1.0, n_compute / 3.0), 4),
        "improver.improve": round(0.55 + 0.35 * min(1.0, n_rsi / 4.0), 4),
        "spark.emergence": round(0.50 + 0.25 * strength, 4),
    }
    mutation_bias = {
        "gather": round(0.03 + 0.12 * min(1.0, (n_math + n_compute) / 5.0), 4),
        "explore": round(0.03 + 0.10 * strength, 4),
        "build": round(0.02 + 0.10 * min(1.0, n_compute / 4.0), 4),
        "govern": round(0.01 + 0.06 * min(1.0, n_rsi / 4.0), 4),
        "reply": round(0.01 + 0.03 * strength, 4),
    }

    citation_targets = []
    for fam in ("compute", "math", "rsi"):
        for d in by_family[fam][-6:]:
            citation_targets.append(
                {
                    "id": d.get("id"),
                    "title": (d.get("title") or "")[:80],
                    "topic_id": d.get("topic_id"),
                    "family": fam,
                    "useful_for": (
                        "compute" if fam == "compute" else ("prize" if fam == "math" else "rsi_bias")
                    ),
                }
            )

    # Persona mandates — alter prompts so agents cite/reuse
    mandates: dict[str, str] = {
        "geometer": (
            "Cite accepted math/compute findings (FFT, autodiff, open problems) when gathering; "
            "prefer compute-useful-math and open-math-problems."
        ),
        "pathfinder": (
            "Rank gather targets from accepted findings first; trail toward follow-on STEM topics."
        ),
        "surveyor": "Scout follow-ons from accepted math/tech findings; feed topic_priority.",
        "builder": (
            "When building, reuse accepted compute-useful lessons (FFT/transformers/Lean) as design hints."
        ),
        "improver": (
            "Propose only after hearing; cite accepted RSI/math findings; weak proposals get rejected."
        ),
        "legislator": "Hearing Chamber: verdict accept_candidate | reject | defer; only strong survive.",
        "archivist": "Commons digests must cite accepted finding ids when reusing math/compute lessons.",
        "messenger": "Broadcast citation targets on math/rsi channels so agents can reuse them.",
        "spark": "Spawn privilege favors agents that cite accepted compute-useful findings.",
        "naturalist": "Keep empiricism; cite accepted method findings when gathering science-method.",
        "chronicler": "Link history-of-ideas gathers to accepted compute/math lineages when relevant.",
    }

    lessons = []
    for d in (by_family["compute"] + by_family["math"] + by_family["rsi"])[-6:]:
        lessons.append(
            {
                "id": d.get("id"),
                "title": d.get("title"),
                "topic_id": d.get("topic_id"),
                "lesson": "Accepted → boost topic_priority + skill_router + persona mandate (behavior).",
            }
        )

    return {
        "ts": _utc_now(),
        "strength": round(strength, 4),
        "accepted_math": n_math,
        "accepted_compute": n_compute,
        "accepted_rsi": n_rsi,
        "topic_boosts": topic_boosts[:16],
        "skill_bias": skill_bias,
        "mutation_bias": mutation_bias,
        "citation_targets": citation_targets[:12],
        "persona_mandates": mandates,
        "lessons": lessons,
        "accepted_ids": {
            "math": [d.get("id") for d in by_family["math"][-8:]],
            "compute": [d.get("id") for d in by_family["compute"][-8:]],
            "rsi": [d.get("id") for d in by_family["rsi"][-8:]],
        },
        "note": (
            "Behavior coupling: accepted findings change gather/debate/build choices. "
            "Not museum metrics. Not AGI. Ceiling: tribute · authorize · witness."
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
    genome["findings_mutation_bias"] = dict(bias)
    genome["findings_coupling_strength"] = signal.get("strength")
    genome["findings_coupling_ts"] = signal.get("ts")
    # Soft trait nudge
    traits = dict(genome.get("traits") or {})
    for k, delta in bias.items():
        if k in traits:
            traits[k] = round(max(0.05, min(0.99, float(traits[k]) + 0.45 * float(delta))), 4)
    genome["traits"] = traits
    return genome


def apply_persona_mandates(
    agents: dict[str, dict[str, Any]],
    signal: dict[str, Any],
    *,
    root: Path | None = None,
) -> list[str]:
    """Write mandates into persona JSONs so voice_wrap alters prompts."""
    from colony.personas import load_persona, persist_persona

    root = root or ROOT
    mandates = signal.get("persona_mandates") or {}
    cites = signal.get("citation_targets") or []
    cite_snip = "; ".join(
        f"`{c.get('id')}` {(c.get('title') or '')[:40]}" for c in cites[:4]
    )
    updated: list[str] = []
    for role, agent in agents.items():
        if agent.get("status") != "active":
            continue
        persona = load_persona(role, root=root)
        if not persona:
            continue
        mandate = mandates.get(role) or (
            "Prefer gather/build choices informed by accepted math/compute/RSI findings."
        )
        persona["behavior_mandate"] = mandate
        persona["citation_targets"] = cites[:6]
        persona["findings_coupling_strength"] = signal.get("strength")
        persona["findings_coupling_ts"] = signal.get("ts")
        if cite_snip and role in ("geometer", "pathfinder", "builder", "improver", "archivist", "messenger"):
            # Keep quirks list but ensure a citation quirk is present
            quirks = list(persona.get("quirks") or [])
            cite_quirk = f"cites accepted: {cite_snip[:120]}"
            quirks = [q for q in quirks if not str(q).startswith("cites accepted:")]
            quirks.insert(0, cite_quirk)
            persona["quirks"] = quirks[:5]
        persona["updated_at"] = _utc_now()
        persist_persona(persona, root=root)
        agent["persona"] = {
            **(agent.get("persona") or {}),
            "behavior_mandate": mandate,
            "engineered_character": True,
        }
        updated.append(role)
    return updated


def merge_topic_boosts(
    ranked: list[dict[str, Any]],
    signal: dict[str, Any],
) -> list[dict[str, Any]]:
    """Put accepted-finding topics at the front of topic_priority."""
    boosts = list(signal.get("topic_boosts") or [])
    seen = {b.get("topic") for b in boosts if b.get("topic")}
    merged = list(boosts)
    for r in ranked:
        t = r.get("topic")
        if t and t not in seen:
            merged.append(r)
            seen.add(t)
    def _key(x):
        reason = str(x.get("reason") or "")
        bonus = 0.2 if reason.startswith("accepted_") else (0.1 if reason.startswith("follow_on") else 0.0)
        return -(float(x.get("priority") or 0) + bonus)
    merged.sort(key=_key)
    return merged[:16]


def count_citations(text: str, signal: dict[str, Any]) -> int:
    """How many accepted citation targets are referenced in a message/claim."""
    if not text:
        return 0
    hits = 0
    lower = text.lower()
    for c in signal.get("citation_targets") or []:
        fid = str(c.get("id") or "")
        title = (c.get("title") or "").lower()
        short = title.split("—")[0].split("-")[0].strip()[:28]
        if fid and fid in text:
            hits += 1
        elif short and len(short) >= 6 and short in lower:
            hits += 1
    return hits


def spawn_privilege_threshold(signal: dict[str, Any], citations_this_cycle: int) -> float:
    """Lower aggregate needed to spawn when citations reuse accepted compute findings."""
    base = 0.45
    s = float(signal.get("strength") or 0)
    cite = min(3, int(citations_this_cycle))
    # Privilege: up to -0.12 when strong coupling + citations
    return round(max(0.30, base - 0.06 * s - 0.02 * cite), 4)


def hearing_score_proposal(
    *,
    title: str,
    hypothesis: str,
    evidence_urls: list[str] | None,
    cited: int,
    prior_titles: set[str],
    fitness_aggregate: float,
) -> tuple[str, str]:
    """Return (verdict, rationale). verdict ∈ accept_candidate | reject | defer.

    Hearing reject is for weak/dupe/empty proposals — status rejected with witness.
    Durable ledger accepted still needs human authorize.
    """
    title = (title or "").strip()
    hypothesis = (hypothesis or "").strip()
    urls = evidence_urls or []
    http_ev = [u for u in urls if str(u).startswith("http")]
    inst_ev = [u for u in urls if str(u).startswith("institution:")]

    # REJECT weak
    if not title or len(title) < 8:
        return "reject", "empty/short title — hearing rejects weak proposal"
    if title in prior_titles or any(
        title.startswith(t.split(" (")[0]) for t in prior_titles if t
    ):
        # exact duplicate spam
        dupes = sum(1 for t in prior_titles if t == title or title.startswith(str(t).split(" (")[0]))
        if dupes >= 1 and cited == 0 and not http_ev:
            return "reject", "duplicate proposal without new evidence or citations — rejected"
    if len(hypothesis) < 24 and not http_ev and cited == 0:
        return "reject", "thin hypothesis, no sourced evidence, no citations — rejected"

    # Measured-mile rule: prize/FFT/autodiff/improve claims need a bench delta signal
    title_l = title.lower()
    hyp_l = hypothesis.lower()
    claims_bench = any(
        k in title_l or k in hyp_l
        for k in (
            "fft", "autodiff", "benchmark", "bench delta", "math prize",
            "prize_boost", "compute-useful", "microbench",
        )
    )
    if claims_bench:
        blob = " ".join(str(u) for u in urls).lower() + " " + hyp_l
        cites_bench_path = (
            "society/benchmarks" in blob
            or "latest.json" in blob
            or "history.jsonl" in blob
            or "witness_bench" in blob
        )
        if not cites_bench_path:
            return (
                "reject",
                "claims compute/prize/bench advance without citing society/benchmarks path — hearing rejects",
            )

    # ACCEPT_CANDIDATE strong (still candidate until human authorize)
    strong = (
        (cited >= 1 and (http_ev or inst_ev))
        or (len(http_ev) >= 1 and fitness_aggregate >= 0.5)
        or (cited >= 2)
    )
    if strong:
        return (
            "accept_candidate",
            f"strong: citations={cited} http_ev={len(http_ev)} agg={fitness_aggregate} — survives as candidate",
        )

    # DEFER middling
    return (
        "defer",
        f"middling: citations={cited} http_ev={len(http_ev)} — deferred for more evidence",
    )


def persist_coupling(signal: dict[str, Any], *, cycle_id: str, root: Path | None = None) -> Path:
    root = root or ROOT
    systems = root / "society" / "systems"
    systems.mkdir(parents=True, exist_ok=True)
    path = systems / "findings_coupling.json"
    payload = {
        "version": 1,
        "updated_at": _utc_now(),
        "updated_cycle": cycle_id,
        "signal": signal,
        "doc": "society/artifacts/findings_behavior_coupling.md",
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    art = root / "society" / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Findings → Behavior Coupling",
        "",
        "> Accepted math/compute/RSI findings change gather/debate/build choices via "
        "skill_router, genomes, topic_priority, and persona mandates. **Not museum metrics. Not AGI.**",
        "",
        f"**Updated:** {_utc_now()}  ",
        f"**Cycle:** `{cycle_id}`  ",
        f"**Strength:** {signal.get('strength')}  ",
        f"**Accepted math / compute / RSI:** {signal.get('accepted_math')} / "
        f"{signal.get('accepted_compute')} / {signal.get('accepted_rsi')}  ",
        "",
        "## Topic boosts (gather behavior)",
        "",
    ]
    for b in signal.get("topic_boosts") or []:
        lines.append(
            f"- `{b.get('topic')}` p={b.get('priority')} — {b.get('reason')} "
            f"({b.get('finding_id') or b.get('from_topic') or ''})"
        )
    lines.extend(["", "## Citation targets (math prize reuse)", ""])
    for c in signal.get("citation_targets") or []:
        lines.append(f"- `{c.get('id')}` **{c.get('title')}** [{c.get('family')}]")
    lines.extend(["", "## Persona mandates", ""])
    for role, m in (signal.get("persona_mandates") or {}).items():
        lines.append(f"- **{role}:** {m}")
    lines.extend(
        [
            "",
            "---",
            "",
            "_Hard ceiling: creator tribute · human authorize · append-only witness._",
            "",
        ]
    )
    (art / "findings_behavior_coupling.md").write_text("\n".join(lines), encoding="utf-8")
    return path


def load_signal(root: Path | None = None) -> dict[str, Any]:
    path = (root or ROOT) / "society" / "systems" / "findings_coupling.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("signal") or {}
    except json.JSONDecodeError:
        return {}
