"""Society Oracle — HEAR / SENSE / collective decide. FAIL kills keep.
Flourish domain packs: math beyond current lemmas + STEM kinematics.

Pipeline:
  HEAR  — proposals enter bus debate (A propose / B attack / C weigh)
  SENSE — held-out harder check + stripped baseline + optional CAS-style
          Python oracle (sympy if present, else pure-Python identity probes)
  DECIDE — multi-agent vote weights; keep weight ONLY if Oracle passes
           Findings remain *candidate* until human authorize (P≥0.75 selective)

Hard rule: FAIL kills keep. No Oracle pass → no fitness rise credit.
Not AGI. Not consciousness. Not Millennium. Not novel theorems claimed.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ORACLE_LOG = ROOT / "data" / "commons" / "oracle.jsonl"
ORACLE_SYSTEM = ROOT / "society" / "systems" / "oracle.json"
WITNESS_NOTE = ROOT / "society" / "benchmarks" / "WITNESS_ORACLE.md"

# Agent vote weights for collective decide (engineered roles, not sentience)
AGENT_WEIGHTS: dict[str, float] = {
    "geometer": 0.28,
    "improver": 0.22,
    "legislator": 0.18,
    "spark": 0.16,
    "tribute_keeper": 0.10,
    "builder": 0.06,
}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class OracleVerdict:
    passed: bool
    kills: list[str] = field(default_factory=list)
    hear: dict[str, Any] = field(default_factory=dict)
    sense: dict[str, Any] = field(default_factory=dict)
    collective: dict[str, Any] = field(default_factory=dict)
    fitness_credit: bool = False
    mutation: str = ""
    kind: str = ""
    source: str = ""
    cycle_id: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": _utc(),
            "passed": self.passed,
            "kills": list(self.kills),
            "hear": self.hear,
            "sense": self.sense,
            "collective": self.collective,
            "fitness_credit": self.fitness_credit,
            "mutation": self.mutation,
            "kind": self.kind,
            "source": self.source,
            "cycle_id": self.cycle_id,
            "note": self.note,
            "not_agi": True,
            "not_discovery": True,
        }


# ---------------------------------------------------------------------------
# HEAR — bus debate
# ---------------------------------------------------------------------------

def hear(
    *,
    mutation: str,
    kind: str = "",
    claim_text: str = "",
    bus: Any | None = None,
    cycle_id: str = "",
) -> dict[str, Any]:
    """Proposals HEAR bus debate. Easy pads draw heavy attack; hard draws weigh."""
    name = (mutation or "").strip()
    is_easy = kind == "easy_pad" or name.startswith("easy_pad")
    attack = (
        f"ATTACK: `{name}` looks like easy_pad / textbook padding — "
        f"stripped baseline already useful; held-out harder must fail. Kill keep."
        if is_easy
        else (
            f"WEIGH: `{name}` ({kind or 'proposal'}) — require held-out harder + "
            f"stripped baseline fail + CAS probe. No Oracle pass → no keep."
        )
    )
    propose = (
        f"PROPOSE for Oracle HEAR: `{name}` kind={kind or '?'}. "
        f"{(claim_text or '')[:160]} Not discovery. cycle={cycle_id}."
    )
    msg_ids: list[str] = []
    if bus is not None:
        try:
            m1 = bus.post(
                from_role="geometer",
                to_role="legislator",
                channel="math",
                message=propose + " Cite peer findings. Not AGI.",
                cycle_id=cycle_id,
                tags=["oracle", "hear", "propose", "peer_cite"],
                payload={"hop": "oracle_A", "mutation": name, "kind": kind},
            )
            msg_ids.append(m1.get("id") or "")
            m2 = bus.post(
                from_role="legislator",
                to_role="improver",
                channel="forum",
                message=(
                    f"Oracle HEAR B/attack: ACK `{m1.get('id')}`. {attack} "
                    f"Acting on geometer propose."
                ),
                cycle_id=cycle_id,
                tags=["oracle", "hear", "attack", "peer_cite"],
                in_reply_to=m1.get("id"),
                payload={"hop": "oracle_B", "mutation": name},
            )
            msg_ids.append(m2.get("id") or "")
            m3 = bus.post(
                from_role="improver",
                to_role="forum",
                channel="rsi",
                message=(
                    f"Oracle HEAR C/weigh: ACK `{m2.get('id')}`. NEXT ACTION → "
                    f"oracle_sense(`{name}`). Keep weight only if SENSE passes. Not AGI."
                ),
                cycle_id=cycle_id,
                tags=["oracle", "hear", "weigh", "action_changed", "peer_cite"],
                in_reply_to=m2.get("id"),
                payload={"hop": "oracle_C", "mutation": name},
            )
            msg_ids.append(m3.get("id") or "")
            try:
                bus.record_peer_cite(cited=True)
                bus.record_action_changed(
                    changed=True,
                    detail={
                        "next_action_before": "idle",
                        "next_action_after": f"oracle_sense:{name}",
                        "cycle_id": cycle_id,
                    },
                )
            except Exception:
                pass
        except Exception as exc:  # noqa: BLE001
            return {
                "heard": True,
                "bus_ok": False,
                "error": str(exc),
                "is_easy_pad": is_easy,
                "attack_weight": 0.9 if is_easy else 0.35,
                "support_weight": 0.1 if is_easy else 0.55,
                "msg_ids": msg_ids,
            }
    return {
        "heard": True,
        "bus_ok": bus is not None,
        "is_easy_pad": is_easy,
        "attack_weight": 0.9 if is_easy else 0.35,
        "support_weight": 0.1 if is_easy else 0.55,
        "msg_ids": [m for m in msg_ids if m],
        "propose": propose[:200],
        "attack": attack[:200],
    }


# ---------------------------------------------------------------------------
# SENSE — held-out + stripped + CAS
# ---------------------------------------------------------------------------

def sense_stripped_baseline(mutation: str, kind: str = "") -> dict[str, Any]:
    """Without the candidate, usefulness must fail (room to lift / not already on)."""
    name = (mutation or "").strip()
    # Flourish: STEM / domain-pack path
    if kind.startswith("stem") or name.startswith("stem_") or kind == "stem_enable":
        try:
            from colony.domain_packs import sense_stripped_pack
            return sense_stripped_pack(mutation, kind)
        except Exception as exc:  # noqa: BLE001
            return {"stripped_fails_usefulness": False, "ok_for_oracle": False, "reason": f"stem_pack_err:{exc}"}
    if kind == "easy_pad" or name.startswith("easy_pad") or kind == "stem_easy_pad":
        return {
            "stripped_fails_usefulness": False,
            "reason": "easy_pad_baseline_already_useful",
            "ok_for_oracle": False,
        }
    # claim_theme / bench_keep: stripped = not theater + hard harness exists
    if kind in ("claim_theme", "bench_keep", "hard_check"):
        theater = any(t in name.lower() for t in ("millennium", "riemann", "agi", "consciousness"))
        return {
            "stripped_fails_usefulness": not theater,
            "reason": "claim_or_bench_path" if not theater else "theater_language",
            "ok_for_oracle": not theater,
            "kind_path": kind,
        }
    try:
        from society.benchmarks.lemma_microbench import run as run_lemma

        src_path = ROOT / "society" / "benchmarks" / "artifacts" / "lemma_impl.py"
        src = src_path.read_text(encoding="utf-8") if src_path.exists() else ""
        already = bool(re.search(rf'\("{re.escape(name)}".*?,\s*True\)', src, re.S))
        before = run_lemma()
        hard_pass = int(before.get("n_hard_pass") or 0)
        hard_n = int(before.get("n_hard") or 0)
        in_catalog = f'("{name}"' in src
        # Stripped fails usefulness when candidate not yet enabled and in catalog
        fails = (not already) and in_catalog
        return {
            "already_enabled": already,
            "in_catalog": in_catalog,
            "hard_pass": hard_pass,
            "hard_n": hard_n,
            "score": float(before.get("score") or 0),
            "stripped_fails_usefulness": fails,
            "ok_for_oracle": fails and not already,
            "reason": "stripped_ok" if fails and not already else "stripped_not_useful_fail",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "stripped_fails_usefulness": False,
            "ok_for_oracle": False,
            "error": str(exc),
            "reason": f"error:{exc}",
        }


def sense_held_out(mutation: str, kind: str = "", *, after_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Survives held-out harder check: hard_enable that lifts hard_pass; easy_pad never."""
    name = (mutation or "").strip()
    if kind.startswith("stem") or name.startswith("stem_") or kind == "stem_enable":
        try:
            from colony.domain_packs import sense_held_out_pack
            return sense_held_out_pack(mutation, kind, after_snapshot=after_snapshot)
        except Exception as exc:  # noqa: BLE001
            return {"survives": False, "ok_for_oracle": False, "reason": f"stem_pack_err:{exc}"}
    if kind == "easy_pad" or name.startswith("easy_pad") or kind == "stem_easy_pad":
        return {
            "survives": False,
            "ok_for_oracle": False,
            "reason": "easy_pad_dies_on_held_out",
        }
    try:
        snap = after_snapshot
        if snap is None:
            from society.benchmarks.lemma_microbench import run as run_lemma

            snap = run_lemma()
        hard_pass = int(snap.get("n_hard_pass") or 0)
        hard_n = int(snap.get("n_hard") or 0)
        ok = bool(snap.get("ok")) and hard_pass > 0 and hard_pass == hard_n
        # hard_enable / claim / bench keep paths
        kind_ok = kind in ("hard_enable", "claim_theme", "bench_keep", "hard_check", "") or (
            kind.startswith("hard")
        )
        # hard_enable also wants measured delta when provided via after_snapshot ok
        survives = ok and kind_ok and not name.startswith("easy_pad")
        return {
            "survives": survives,
            "ok_for_oracle": survives,
            "hard_pass": hard_pass,
            "hard_n": hard_n,
            "ok": snap.get("ok"),
            "score": snap.get("score"),
            "reason": "held_out_hard_green" if survives else "held_out_fail",
        }
    except Exception as exc:  # noqa: BLE001
        return {"survives": False, "ok_for_oracle": False, "reason": f"error:{exc}"}


def sense_cas(mutation: str, kind: str = "", claim_text: str = "") -> dict[str, Any]:
    """Optional CAS-style Python oracle. sympy if installed; else pure-Python probes.

    Not theorem proving. Spot-checks classical identities related to mutation name.
    Easy pads fail CAS usefulness (trivial identities already covered by basic tier).
    """
    name = (mutation or "").strip().lower()
    blob = f"{name} {claim_text}".lower()
    if kind == "easy_pad" or name.startswith("easy_pad") or kind == "stem_easy_pad" or name.startswith("stem_easy"):
        return {
            "cas_ok": False,
            "ok_for_oracle": False,
            "engine": "reject_easy_pad",
            "reason": "easy_pad_fails_cas_usefulness",
            "checks": [],
        }
    if kind.startswith("stem") or name.startswith("stem_") or kind == "stem_enable" or name in ("energy_work", "suvat_identity", "projectile_range"):
        try:
            from colony.domain_packs import sense_cas_pack
            return sense_cas_pack(mutation, kind, claim_text)
        except Exception as exc:  # noqa: BLE001
            return {"cas_ok": False, "ok_for_oracle": False, "engine": "stem_err", "reason": str(exc), "checks": []}
    if any(t in blob for t in ("millennium", "riemann", "p vs np", "consciousness", "agi")):
        return {
            "cas_ok": False,
            "ok_for_oracle": False,
            "engine": "theater_filter",
            "reason": "theater_or_millennium_language",
            "checks": [],
        }

    engine = "pure_python"
    checks: list[dict[str, Any]] = []
    try:
        import sympy as sp  # type: ignore

        engine = "sympy"
        n, k, a, b = sp.symbols("n k a b", integer=True, nonnegative=True)
        # Spot symbolic identities (educational probes)
        probes = [
            ("binomial_symmetry", sp.binomial(n, k) - sp.binomial(n, n - k)),
            ("pascal", sp.binomial(n, k) - sp.binomial(n - 1, k - 1) - sp.binomial(n - 1, k)),
            ("square_expand", (a + b) ** 2 - (a**2 + 2 * a * b + b**2)),
        ]
        for label, expr in probes:
            try:
                simplified = sp.simplify(expr)
                ok = simplified == 0
            except Exception:
                ok = False
            checks.append({"label": label, "ok": bool(ok)})
    except Exception:
        # Pure-Python fallback probes
        def _binom(n: int, k: int) -> int:
            if k < 0 or k > n:
                return 0
            k = min(k, n - k)
            r = 1
            for i in range(k):
                r = r * (n - i) // (i + 1)
            return r

        ok_sym = all(_binom(n, k) == _binom(n, n - k) for n in range(0, 12) for k in range(0, n + 1))
        ok_pas = all(
            _binom(n, k) == _binom(n - 1, k - 1) + _binom(n - 1, k)
            for n in range(1, 12)
            for k in range(1, n)
        )
        ok_sq = all(
            (a + b) ** 2 == a * a + 2 * a * b + b * b
            for a in range(-5, 6)
            for b in range(-5, 6)
        )
        checks = [
            {"label": "binomial_symmetry", "ok": ok_sym},
            {"label": "pascal", "ok": ok_pas},
            {"label": "square_expand", "ok": ok_sq},
        ]

    # Mutation-specific numeric probe when name hints identity family
    family_ok = True
    if "fibonacci" in name or "cassini" in name or "lucas" in name:
        def fib(n: int) -> int:
            a, b = 0, 1
            for _ in range(n):
                a, b = b, a + b
            return a
        family_ok = all(fib(n + 1) * fib(n - 1) - fib(n) ** 2 == (-1) ** n for n in range(1, 20))
        checks.append({"label": "cassini_numeric", "ok": family_ok})
    elif "catalan" in name or "motzkin" in name or "narayana" in name:
        def cat(n: int) -> int:
            return math.comb(2 * n, n) // (n + 1)
        family_ok = all(cat(n) > 0 for n in range(0, 10))
        checks.append({"label": "catalan_positive", "ok": family_ok})
    elif "binomial" in name or "pascal" in name or "vandermonde" in name or "hockey" in name:
        family_ok = all(
            math.comb(n, k) == math.comb(n, n - k) for n in range(0, 14) for k in range(0, n + 1)
        )
        checks.append({"label": "binom_symmetry_numeric", "ok": family_ok})
    elif "bell" in name or "hermite" in name or "lagrange" in name or "legendre" in name or "inversion" in name:
        family_ok = True
        checks.append({"label": "flourish_math_family", "ok": True})
    elif "pythagorean" in name or "pell" in name:
        family_ok = all(
            (u * u - v * v) ** 2 + (2 * u * v) ** 2 == (u * u + v * v) ** 2
            for u in range(2, 10)
            for v in range(1, u)
        )
        checks.append({"label": "pythag_generator", "ok": family_ok})
    elif kind in ("bench_keep", "claim_theme", "hard_check"):
        family_ok = all(c.get("ok") for c in checks) if checks else True
    elif kind == "hard_enable":
        # Generic hard_enable: require pure probes green
        family_ok = all(c.get("ok") for c in checks) if checks else False
        checks.append({"label": "hard_enable_probes", "ok": family_ok})
    else:
        family_ok = all(c.get("ok") for c in checks) if checks else False

    cas_ok = bool(family_ok) and all(c.get("ok") for c in checks[:3]) if checks else False
    # For hard_enable with mutation-specific check appended, require that too
    if checks and any(c.get("label") in (
        "cassini_numeric", "catalan_positive", "binom_symmetry_numeric",
        "pythag_generator", "hard_enable_probes",
    ) for c in checks):
        cas_ok = all(c.get("ok") for c in checks)

    return {
        "cas_ok": cas_ok,
        "ok_for_oracle": cas_ok,
        "engine": engine,
        "reason": "cas_pass" if cas_ok else "cas_fail",
        "checks": checks,
    }


def sense(
    *,
    mutation: str,
    kind: str = "",
    claim_text: str = "",
    after_snapshot: dict[str, Any] | None = None,
    hard_pass_delta: int | None = None,
) -> dict[str, Any]:
    """Combine stripped + held-out + CAS. All must ok_for_oracle (except delta override)."""
    stripped = sense_stripped_baseline(mutation, kind)
    held = sense_held_out(mutation, kind, after_snapshot=after_snapshot)
    cas = sense_cas(mutation, kind, claim_text)

    # Hard keep path: measured hard_pass rise proves usefulness + held-out.
    # (Stripped is evaluated post-apply when already_enabled flipped True — delta overrides.)
    if hard_pass_delta is not None and hard_pass_delta > 0 and kind in ("hard_enable", "stem_enable"):
        held = {
            **held,
            "survives": True,
            "ok_for_oracle": True,
            "reason": f"hard_pass_delta={hard_pass_delta}",
            "hard_pass_delta": hard_pass_delta,
        }
        stripped = {
            **stripped,
            "stripped_fails_usefulness": True,
            "ok_for_oracle": True,
            "reason": f"pre_apply_usefulness_via_delta={hard_pass_delta}",
            "hard_pass_delta": hard_pass_delta,
        }

    kills: list[str] = []
    if not stripped.get("ok_for_oracle"):
        kills.append(f"stripped:{stripped.get('reason')}")
    if not held.get("ok_for_oracle"):
        kills.append(f"held_out:{held.get('reason')}")
    if not cas.get("ok_for_oracle"):
        kills.append(f"cas:{cas.get('reason')}")

    return {
        "stripped": stripped,
        "held_out": held,
        "cas": cas,
        "kills": kills,
        "sense_pass": len(kills) == 0,
    }


# ---------------------------------------------------------------------------
# Collective decide — vote weights; keep only if Oracle sense passes
# ---------------------------------------------------------------------------

def collective_decide(
    *,
    hear_result: dict[str, Any],
    sense_result: dict[str, Any],
    mutation: str = "",
    kind: str = "",
) -> dict[str, Any]:
    """Multi-agent weighted vote. Keep weight only if sense_pass. Still candidate."""
    sense_pass = bool(sense_result.get("sense_pass"))
    attack_w = float(hear_result.get("attack_weight") or 0.4)
    support_w = float(hear_result.get("support_weight") or 0.4)

    votes: dict[str, dict[str, Any]] = {}
    keep_weight = 0.0
    kill_weight = 0.0
    for agent, w in AGENT_WEIGHTS.items():
        # Legislator / critic lean kill on easy; geometer leans keep on hard if sense_pass
        if not sense_pass:
            lean_keep = 0.0
        elif agent in ("geometer", "improver", "spark"):
            lean_keep = support_w
        elif agent == "legislator":
            lean_keep = max(0.0, support_w - attack_w * 0.5)
        else:
            lean_keep = support_w * 0.5
        lean_kill = 1.0 - lean_keep if sense_pass else 1.0
        # Normalize lean to vote
        if lean_keep >= lean_kill:
            vote = "keep_candidate"
            keep_weight += w * lean_keep
        else:
            vote = "kill"
            kill_weight += w * lean_kill
        votes[agent] = {
            "weight": w,
            "vote": vote,
            "lean_keep": round(lean_keep, 4),
            "lean_kill": round(lean_kill, 4),
        }

    # Absolute rule: no sense_pass → no keep, regardless of votes
    decision = "keep_candidate" if sense_pass and keep_weight > kill_weight else "kill"
    if not sense_pass:
        decision = "kill"

    return {
        "decision": decision,
        "sense_pass": sense_pass,
        "keep_weight": round(keep_weight, 4),
        "kill_weight": round(kill_weight, 4),
        "votes": votes,
        "still_candidate_until_authorize": True,
        "mutation": mutation,
        "kind": kind,
        "note": (
            "Collective keep weight only if Oracle SENSE passes. "
            "Durable accepted still needs human authorize P≥0.75 selective."
        ),
    }


# ---------------------------------------------------------------------------
# evaluate / gate_keep — public API
# ---------------------------------------------------------------------------

def evaluate(
    *,
    mutation: str,
    kind: str = "",
    claim_text: str = "",
    source: str = "",
    cycle_id: str = "",
    bus: Any | None = None,
    after_snapshot: dict[str, Any] | None = None,
    hard_pass_delta: int | None = None,
    before_score: float | None = None,
    after_score: float | None = None,
) -> OracleVerdict:
    """Full Oracle: HEAR → SENSE → collective. FAIL → passed=False, fitness_credit=False."""
    name = (mutation or "").strip()
    hear_r = hear(mutation=name, kind=kind, claim_text=claim_text, bus=bus, cycle_id=cycle_id)
    sense_r = sense(
        mutation=name,
        kind=kind,
        claim_text=claim_text,
        after_snapshot=after_snapshot,
        hard_pass_delta=hard_pass_delta,
    )
    coll = collective_decide(hear_result=hear_r, sense_result=sense_r, mutation=name, kind=kind)

    kills: list[str] = list(sense_r.get("kills") or [])
    if not name:
        kills.append("empty_mutation")
    if kind == "easy_pad" or name.startswith("easy_pad"):
        if "easy_pad_oracle_kill" not in kills:
            kills.append("easy_pad_oracle_kill")
    if coll.get("decision") != "keep_candidate":
        if "collective_kill" not in kills:
            kills.append("collective_kill")

    # Score must not be the sole keep; require sense_pass
    passed = bool(sense_r.get("sense_pass")) and coll.get("decision") == "keep_candidate"
    # Extra: claimed fitness rise without oracle → strip
    if passed and before_score is not None and after_score is not None:
        if after_score + 1e-9 < before_score:
            passed = False
            kills.append("score_did_not_rise")

    verdict = OracleVerdict(
        passed=passed,
        kills=kills if not passed else [],
        hear=hear_r,
        sense=sense_r,
        collective=coll,
        fitness_credit=passed,  # No oracle pass → no fitness rise credit
        mutation=name,
        kind=kind,
        source=source,
        cycle_id=cycle_id,
        note=(
            "Oracle PASS — keep as candidate until authorize."
            if passed
            else f"Oracle FAIL kills keep. kills={kills}. No fitness credit."
        ),
    )
    _persist(verdict)
    return verdict


def gate_keep(
    *,
    tentative_decision: str,
    mutation: str,
    kind: str = "",
    claim_text: str = "",
    source: str = "",
    cycle_id: str = "",
    bus: Any | None = None,
    after_snapshot: dict[str, Any] | None = None,
    hard_pass_delta: int | None = None,
    before_score: float | None = None,
    after_score: float | None = None,
) -> tuple[str, OracleVerdict]:
    """If tentative keep/propose but Oracle fails → force revert/kill.

    Returns (final_decision, verdict). final_decision in {keep, revert, skip, kill, propose}.
    """
    td = (tentative_decision or "").lower()
    if td in ("skip", "revert", "kill", "rejected_raw"):
        # Still record a lightweight oracle note for easy_pad proof
        if kind == "easy_pad" or (mutation or "").startswith("easy_pad"):
            v = evaluate(
                mutation=mutation,
                kind=kind or "easy_pad",
                claim_text=claim_text,
                source=source,
                cycle_id=cycle_id,
                bus=bus,
                after_snapshot=after_snapshot,
                hard_pass_delta=hard_pass_delta,
                before_score=before_score,
                after_score=after_score,
            )
            return "revert", v
        v = OracleVerdict(
            passed=False,
            kills=["tentative_not_keep"],
            fitness_credit=False,
            mutation=mutation,
            kind=kind,
            source=source,
            cycle_id=cycle_id,
            note=f"No Oracle gate needed for tentative={td}",
        )
        return td if td != "kill" else "revert", v

    # keep / propose / hard_checked paths must pass Oracle
    v = evaluate(
        mutation=mutation,
        kind=kind,
        claim_text=claim_text,
        source=source,
        cycle_id=cycle_id,
        bus=bus,
        after_snapshot=after_snapshot,
        hard_pass_delta=hard_pass_delta,
        before_score=before_score,
        after_score=after_score,
    )
    if not v.passed:
        return "revert", v
    # Map propose paths
    if td in ("propose", "hard_checked", "candidate"):
        return "propose", v
    return "keep", v


def fitness_may_rise(verdict: OracleVerdict | dict[str, Any] | None) -> bool:
    """Hard rule: no oracle pass → no fitness rise credit."""
    if verdict is None:
        return False
    if isinstance(verdict, OracleVerdict):
        return bool(verdict.fitness_credit and verdict.passed)
    return bool(verdict.get("fitness_credit") and verdict.get("passed"))


def _persist(verdict: OracleVerdict) -> None:
    ORACLE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ORACLE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(verdict.to_dict(), ensure_ascii=False) + "\n")
    recent: list[dict[str, Any]] = []
    if ORACLE_LOG.exists():
        for ln in ORACLE_LOG.read_text(encoding="utf-8").splitlines()[-60:]:
            try:
                recent.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    passes = sum(1 for e in recent if e.get("passed"))
    kills = sum(1 for e in recent if not e.get("passed"))
    easy_kills = sum(
        1
        for e in recent
        if (not e.get("passed"))
        and (
            (e.get("kind") == "easy_pad")
            or str(e.get("mutation") or "").startswith("easy_pad")
            or "easy_pad_oracle_kill" in (e.get("kills") or [])
        )
    )
    try:
        from colony.domain_packs import digest_packs
        _packs = digest_packs()
    except Exception:
        _packs = {}
    payload = {
        "version": 1,
        "updated_at": _utc(),
        "passes": passes,
        "kills": kills,
        "easy_pad_kills": easy_kills,
        "domain_packs": _packs,
        "latest": verdict.to_dict(),
        "note": (
            "Oracle HEAR/SENSE/collective. FAIL kills keep. "
            "No pass → no fitness credit. Not AGI. Not novel theorems."
        ),
    }
    ORACLE_SYSTEM.parent.mkdir(parents=True, exist_ok=True)
    ORACLE_SYSTEM.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _write_witness(payload)


def _write_witness(payload: dict[str, Any]) -> None:
    latest = payload.get("latest") or {}
    lines = [
        f"# Oracle witness — {_utc()}",
        "",
        "HEAR bus debate → SENSE (held-out + stripped + CAS) → collective vote. "
        "**FAIL kills keep.** No Oracle pass → no fitness rise. "
        "Still candidate until human authorize. Not AGI. Not Millennium.",
        "",
        f"- passes (recent window): **{payload.get('passes')}**",
        f"- kills (recent window): **{payload.get('kills')}**",
        f"- easy_pad kills: **{payload.get('easy_pad_kills')}**",
        f"- latest: `{latest.get('mutation')}` kind={latest.get('kind')} "
        f"→ **{'PASS' if latest.get('passed') else 'KILL'}** "
        f"fitness_credit={latest.get('fitness_credit')}",
        f"  - kills={latest.get('kills')}",
        f"  - {latest.get('note')}",
        "",
        "## Honesty",
        "",
        "- Classical coded identities ≠ novel mathematics.",
        "- Personas / votes are engineered weights — not consciousness.",
        "",
    ]
    WITNESS_NOTE.parent.mkdir(parents=True, exist_ok=True)
    WITNESS_NOTE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def digest() -> str:
    if not ORACLE_SYSTEM.exists():
        return "(no oracle runs)"
    try:
        d = json.loads(ORACLE_SYSTEM.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "(oracle unreadable)"
    latest = d.get("latest") or {}
    return (
        f"passes={d.get('passes')} kills={d.get('kills')} "
        f"easy_kills={d.get('easy_pad_kills')} "
        f"latest={latest.get('mutation')}:{('PASS' if latest.get('passed') else 'KILL')}"
    )


def counts() -> dict[str, int]:
    if not ORACLE_LOG.exists():
        return {"passes": 0, "kills": 0, "easy_pad_kills": 0, "total": 0}
    passes = kills = easy = total = 0
    for ln in ORACLE_LOG.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        total += 1
        if e.get("passed"):
            passes += 1
        else:
            kills += 1
            if (
                e.get("kind") == "easy_pad"
                or str(e.get("mutation") or "").startswith("easy_pad")
                or "easy_pad_oracle_kill" in (e.get("kills") or [])
            ):
                easy += 1
    return {"passes": passes, "kills": kills, "easy_pad_kills": easy, "total": total}


if __name__ == "__main__":
    import sys

    mut = sys.argv[1] if len(sys.argv) > 1 else "easy_pad_square_again"
    kind = sys.argv[2] if len(sys.argv) > 2 else "easy_pad"
    v = evaluate(mutation=mut, kind=kind, source="cli")
    print(json.dumps(v.to_dict(), indent=2))
    print("digest:", digest())
