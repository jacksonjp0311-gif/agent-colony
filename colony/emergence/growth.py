"""Growth loop — invent/build usable systems, communicate (bus), gather, improve."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from colony.bus import CommBus
from colony.fitness import EvolutionEngine
from colony.ledger import Finding, Ledger
from colony.registry import AgentRegistry
from colony.society_state import SocietyState
from colony.systems import SystemWorkshop
from colony.witness import WitnessLog
from colony.emergence.growth_steps_inbox_build import GrowthSteps1
from colony.emergence.growth_steps_comm_gather import GrowthSteps2
from colony.emergence.growth_steps_evolve import GrowthSteps3

ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class GrowthResult:
    builds: list[str] = field(default_factory=list)
    communications: list[dict[str, Any]] = field(default_factory=list)
    gathered: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    systems_used: list[str] = field(default_factory=list)
    systems_built: list[str] = field(default_factory=list)
    replies: int = 0
    messages_read: int = 0
    fitness: dict[str, float] = field(default_factory=dict)
    skill_updates: dict[str, float] = field(default_factory=dict)
    spawn_signals: list[str] = field(default_factory=list)
    retired: list[str] = field(default_factory=list)
    actionables: dict[str, Any] = field(default_factory=dict)
    child_spawn: dict[str, Any] | None = None
    commons_size: int = 0
    gov_proposals: int = 0


class GrowthLoop(GrowthSteps1, GrowthSteps2, GrowthSteps3):
    def __init__(self, ledger: Ledger, state: SocietyState, witness: WitnessLog) -> None:
        self.ledger = ledger
        self.state = state
        self.witness = witness
        self.registry = AgentRegistry(state.data)
        self.bus = CommBus(state.data, self.registry)
        self.workshop = SystemWorkshop(state.data, root=ROOT)
        self.evo = EvolutionEngine(state.data, self.registry, self.workshop)

    def grow(
        self,
        cycle_id: str,
        *,
        tribute_topics: list[str],
        tribute_count: int,
        live_ok: int = 0,
        live_fail: int = 0,
    ) -> GrowthResult:
        g = GrowthResult()
        cycle_n = int(self.state.data.get("cycle_count") or 0) + 1

        entered = self.registry.sync_from_roles(cycle_id=cycle_id)
        if entered:
            self.witness.record(
                cycle_id=cycle_id,
                kind="agents_entered",
                actor="spark",
                summary=f"Agents entered: {entered}",
                detail={"entered": entered},
            )

        # Durable engineered personas (role posture — not sentience)
        from colony.personas import ensure_all_active

        persona_roles = ensure_all_active(self.registry.agents(), root=ROOT)
        if persona_roles:
            self.witness.record(
                cycle_id=cycle_id,
                kind="personas_ensured",
                actor="spark",
                summary=f"Personas ensured for {len(persona_roles)} agents (engineered character, not sentience).",
                detail={"roles": persona_roles, "engineered_character": True, "not_sentience": True},
            )

        self.witness.record(
            cycle_id=cycle_id,
            kind="growth_loop_open",
            actor="spark",
            summary="Growth loop lit: read-bus → build/use-systems → communicate/reply → gather → evolve.",
            detail={"active_ask": self.state.active_ask(), "cycle_n": cycle_n},
        )

        actionables = self._read_all_inboxes(cycle_id, g)
        g.actionables = actionables
        self._build_and_use_systems(cycle_id, cycle_n, g, actionables)
        self._communicate_and_reply(cycle_id, cycle_n, g, tribute_topics, actionables)
        self._gather(cycle_id, g, tribute_topics, tribute_count, actionables)
        # Pre-load findings→behavior so debate/hearing voices + mandates are live
        from colony.findings_coupling import (
            apply_persona_mandates,
            harvest_behavior_signal,
        )
        from colony.rsi_coupling import harvest_rsi_signal
        g.behavior_signal = harvest_behavior_signal(self.ledger.all())  # type: ignore[attr-defined]
        g.rsi_signal = harvest_rsi_signal(self.ledger.all())  # type: ignore[attr-defined]
        apply_persona_mandates(self.registry.agents(), g.behavior_signal, root=ROOT)
        # Seed fitness from last cycle for hearing scoring
        hist = self.state.data.get("fitness_history") or []
        if hist:
            g.fitness = {k: v for k, v in hist[-1].items() if isinstance(v, (int, float))}
        # Autonomy mile C: multi-hop A proposes → B attacks → C patches (bus-driven)
        try:
            from colony.debate_multihop import run_multihop
            mh = run_multihop(
                bus=self.bus,
                ledger=self.ledger,
                registry=self.registry,
                witness=self.witness,
                cycle_id=cycle_id,
            )
            g.improvements.append(
                f"debate_multihop:action_changed={mh.get('action_changed')}:touched={mh.get('code_touched')}"
            )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="debate_multihop_error",
                actor="spark",
                summary=f"Multi-hop debate skipped: {exc}",
                detail={"error": str(exc)},
            )
        # Research-lab: debate → propose → hearing verdict, then evolve/fitness
        self._debate_then_propose(cycle_id, cycle_n, g)
        self._attempt_improvement(cycle_id, cycle_n, g)
        # Measured bench improve: one measure→keep/revert attempt per cycle
        try:
            from colony.bench_improve import run_from_growth

            bi = run_from_growth(cycle_id)
            g.improvements.append(f"bench_improve:{bi.patch_name}:{bi.decision}")
            self.witness.record(
                cycle_id=cycle_id,
                kind="bench_improve",
                actor="improver" if "improver" in self.registry.active() else "spark",
                summary=(
                    f"Bench improve `{bi.patch_name}` → {bi.decision} "
                    f"({bi.before_score}→{bi.after_score}, delta={bi.delta})"
                ),
                detail={
                    "patch": bi.patch_name,
                    "decision": bi.decision,
                    "before_score": bi.before_score,
                    "after_score": bi.after_score,
                    "delta": bi.delta,
                    "note": bi.note,
                },
            )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="bench_improve_error",
                actor="improver",
                summary=f"Bench improve skipped: {exc}",
                detail={"error": str(exc)},
            )
        # Conjecture desk: paper themes → lemma mutations; keep only on score rise
        try:
            from colony.conjecture_desk import run_from_growth as conjecture_run

            cj = conjecture_run(cycle_id, ledger=self.ledger)
            g.improvements.append(f"conjecture:{cj.mutation or 'none'}:{cj.decision}")
            self.witness.record(
                cycle_id=cycle_id,
                kind="conjecture_desk",
                actor="geometer" if "geometer" in self.registry.active() else "spark",
                summary=(
                    f"Conjecture desk `{cj.mutation or 'none'}` → {cj.decision} "
                    f"({cj.before_score}→{cj.after_score}, delta={cj.delta})"
                ),
                detail={
                    "mutation": cj.mutation,
                    "decision": cj.decision,
                    "before_score": cj.before_score,
                    "after_score": cj.after_score,
                    "delta": cj.delta,
                    "note": cj.note,
                    "n_proposals": len(cj.proposals),
                },
            )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="conjecture_desk_error",
                actor="geometer",
                summary=f"Conjecture desk skipped: {exc}",
                detail={"error": str(exc)},
            )
        # Lift 3: scrape→analyze→claim (raw scrape ≠ discovery)
        try:
            from colony.claim_pipeline import run_pipeline
            pipe = run_pipeline(live_gather=False, ledger=self.ledger, cycle_id=cycle_id)
            g.improvements.append(
                f"claim_pipeline:extracted={pipe.get('n_extracted')}:proposed={pipe.get('n_proposed')}"
            )
            self.witness.record(
                cycle_id=cycle_id,
                kind="claim_pipeline",
                actor="geometer" if "geometer" in self.registry.active() else "spark",
                summary=(
                    f"Claim pipeline: extracted={pipe.get('n_extracted')} "
                    f"hard_checked={pipe.get('n_hard_checked')} "
                    f"proposed={pipe.get('n_proposed')} (raw scrape ≠ discovery)."
                ),
                detail=pipe,
            )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="claim_pipeline_error",
                actor="geometer",
                summary=f"Claim pipeline skipped: {exc}",
                detail={"error": str(exc)},
            )
        # Lift 2: bias skills/genomes from lesson ledger (kept outcomes only)
        try:
            from colony.lessons import apply_lesson_bias_to_agents, apply_lesson_bias_to_genomes, digest
            bias = apply_lesson_bias_to_agents(self.registry.agents())
            n_gen = apply_lesson_bias_to_genomes(ROOT)
            if bias or n_gen:
                self.witness.record(
                    cycle_id=cycle_id,
                    kind="lesson_bias_applied",
                    actor="improver" if "improver" in self.registry.active() else "spark",
                    summary=f"Lesson bias applied keys={list(bias)} genomes_touched={n_gen}. Digest: {digest(limit=3)}",
                    detail={"skill_bias": bias, "genomes_touched": n_gen},
                )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="lesson_bias_error",
                actor="improver",
                summary=f"Lesson bias skipped: {exc}",
                detail={"error": str(exc)},
            )
        # Lift 5: external_mind proposals under hard-tier (cross-agent debate already in evolve)
        try:
            from colony.external_mind import propose as em_propose
            batch = em_propose(n=4, ledger=self.ledger, cycle_id=cycle_id, state_data=self.state.data)
            self.witness.record(
                cycle_id=cycle_id,
                kind="external_mind_propose",
                actor="spark",
                summary=(
                    f"External mind proposed {len(batch.proposals)} candidates "
                    f"(keep only on hard-tier rise; dissent stays in witness)."
                ),
                detail={
                    "n": len(batch.proposals),
                    "ids": [p.get("id") for p in batch.proposals],
                    "commons_prior": (batch.commons_digest or "")[:160],
                    "not_consciousness": True,
                },
            )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="external_mind_error",
                actor="spark",
                summary=f"External mind skipped: {exc}",
                detail={"error": str(exc)},
            )
        # SPARK2: EXTERNAL ARRAY + INTERNAL RESIDUALS + TELEMETRY + TIME REVISION
        ext_patterns = []
        residual_conflicts = []
        try:
            from colony.external_array import gather_external_array
            ext_snap = gather_external_array(force=True)
            ext_patterns = list(ext_snap.get("cross_domain_patterns") or [])
            g.improvements.append(
                f"external_array:patterns={len(ext_patterns)}:feeds_ok="
                + str({k: bool(v.get('ok')) for k, v in (ext_snap.get('feeds') or {}).items()})
            )
            self.witness.record(
                cycle_id=cycle_id,
                kind="external_array",
                actor="spark",
                summary=(
                    f"EXTERNAL ARRAY: {len(ext_patterns)} cross-domain patterns; "
                    f"kinds={[p.get('kind') for p in ext_patterns[:4]]}. Debate input — not discovery."
                ),
                detail={
                    "patterns": ext_patterns[:4],
                    "feed_ok": {k: bool(v.get("ok")) for k, v in (ext_snap.get("feeds") or {}).items()},
                    "not_novel_physics": True,
                },
            )
            # Surface patterns onto forum for multi-hop / hearing
            if ext_patterns and hasattr(self, "bus"):
                top = ext_patterns[0]
                self.bus.post(
                    from_role="spark",
                    to_role="forum",
                    channel="cosmos",
                    message=(
                        f"EXTERNAL ARRAY pattern `{top.get('kind')}`: {(top.get('summary') or '')[:220]} "
                        f"Agents: query colony.telemetry + revise prior positions. cycle={cycle_id}."
                    ),
                    cycle_id=cycle_id,
                    tags=["external_array", "telemetry", "debate", "peer_cite"],
                    payload={"kind": "external_array_pattern", "pattern": top.get("kind")},
                )
            # Auditability: PulseMesh already wrote society/systems/pulsemesh_feeds.json
            if "pulsemesh_feeds" not in self.workshop.known():
                self.workshop.ensure("pulsemesh_feeds", built_by="spark", cycle_id=cycle_id)
                g.systems_built.append("pulsemesh_feeds")
            self.workshop.use("pulsemesh_feeds", cycle_id)
            if "pulsemesh_feeds" not in g.systems_used:
                g.systems_used.append("pulsemesh_feeds")
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="external_array_error",
                actor="spark",
                summary=f"EXTERNAL ARRAY skipped: {exc}",
                detail={"error": str(exc)},
            )
        try:
            from colony.residuals import ResidualField
            rf = ResidualField(self.state.data)
            fit_delta = 0.0
            hist = self.state.data.get("fitness_history") or []
            if len(hist) >= 2:
                try:
                    fit_delta = float(hist[-1].get("aggregate") or 0) - float(hist[-2].get("aggregate") or 0)
                except Exception:
                    fit_delta = 0.0
            reply_rate = 0.5
            try:
                bm = self.bus.inner_bus_metrics() if hasattr(self.bus, "inner_bus_metrics") else {}
                reply_rate = float(bm.get("reply_rate") or 0.5)
            except Exception:
                pass
            ext_arousal = 0.2 * len(ext_patterns)
            for role in list(self.registry.active().keys())[:12]:
                rf.emit_from_signals(
                    role,
                    cycle_id=cycle_id,
                    fitness_delta=fit_delta,
                    reply_rate=reply_rate,
                    external_arousal=ext_arousal,
                    oracle_kill=False,
                )
            # Boost spark / improver arousal slightly for catalytic attention
            rf.update("spark", cycle_id=cycle_id, arousal=min(1.0, 0.45 + ext_arousal), attention_weight=0.7)
            if "improver" in self.registry.active():
                rf.update("improver", cycle_id=cycle_id, arousal=min(1.0, 0.4 + abs(fit_delta)), error_gradient=abs(fit_delta) + 0.1)
            residual_conflicts = rf.detect_conflicts()
            rsnap = rf.persist()
            g.improvements.append(
                f"residuals:high={rsnap.get('high_residual')}:conflicts={len(residual_conflicts)}"
            )
            self.witness.record(
                cycle_id=cycle_id,
                kind="residuals",
                actor="spark",
                summary=(
                    f"INTERNAL RESIDUALS: high={rsnap.get('high_residual')} "
                    f"conflicts={len(residual_conflicts)} (re-debate triggers). Not consciousness."
                ),
                detail={
                    "high_residual": rsnap.get("high_residual"),
                    "conflicts": residual_conflicts[:5],
                    "traces": rf.trace_sample(5),
                    "not_consciousness": True,
                },
            )
            if residual_conflicts:
                c0 = residual_conflicts[0]
                self.bus.post(
                    from_role=c0.get("a") or "spark",
                    to_role="forum",
                    channel="forum",
                    message=(
                        f"RESIDUAL CONFLICT {c0.get('a')}↔{c0.get('b')} score={c0.get('score')}: "
                        f"confidence_gap={c0.get('confidence_gap')} arousal_gap={c0.get('arousal_gap')}. "
                        f"TRIGGER RE-DEBATE. High-residual agents get attention. cycle={cycle_id}."
                    ),
                    cycle_id=cycle_id,
                    tags=["residuals", "redebate", "debate", "peer_cite"],
                    payload={"kind": "residual_conflict", "conflict": c0},
                )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="residuals_error",
                actor="spark",
                summary=f"INTERNAL RESIDUALS skipped: {exc}",
                detail={"error": str(exc)},
            )
        # SPARK3: Athanor coherence governor on live residuals (inform-only; no double-gate)
        athanor_snap = {}
        try:
            from colony.athanor_coherence import run_governor_on_state
            from colony.residuals import ResidualField as _RF

            rf_ath = _RF(self.state.data)
            athanor_snap = run_governor_on_state(
                self.state.data, cycle_id=cycle_id, residual_field=rf_ath
            )
            latest = athanor_snap.get("latest") or {}
            dist = athanor_snap.get("distribution") or {}
            g.improvements.append(
                f"athanor:verdict={latest.get('verdict')}:h7={latest.get('h7')}:"
                f"dist={dist}"
            )
            self.witness.record(
                cycle_id=cycle_id,
                kind="athanor_coherence",
                actor="spark",
                summary=(
                    f"ATHANOR H7 inform-only: verdict={latest.get('verdict')} "
                    f"h7={latest.get('h7')} reason={latest.get('reason')}. "
                    f"Does NOT authorize durable rows. P>=0.70 human authorize ceiling."
                ),
                detail={
                    "verdict": latest.get("verdict"),
                    "h7": latest.get("h7"),
                    "distribution": dist,
                    "stabilizer_advice": athanor_snap.get("stabilizer_advice"),
                    "inform_only": True,
                    "double_gate": False,
                    "durable_accept": False,
                },
            )
            # Surface verdict into debate/actuation confidence (agents read; may trigger re-debate)
            if latest.get("verdict") in ("REJECT", "REFINE") and hasattr(self, "bus"):
                self.bus.post(
                    from_role="spark",
                    to_role="forum",
                    channel="forum",
                    message=(
                        f"ATHANOR VERDICT `{latest.get('verdict')}` H7={latest.get('h7')}: "
                        f"{latest.get('reason')}. Agents: weigh in re-debate / action confidence gates. "
                        f"Inform-only — no silent ledger accept. cycle={cycle_id}."
                    ),
                    cycle_id=cycle_id,
                    tags=["athanor", "coherence", "redebate", "debate", "peer_cite"],
                    payload={
                        "kind": "athanor_verdict",
                        "verdict": latest.get("verdict"),
                        "h7": latest.get("h7"),
                        "inform_only": True,
                    },
                )
            # Auditability: Athanor already wrote society/systems/athanor_coherence.json
            if "athanor_coherence" not in self.workshop.known():
                self.workshop.ensure("athanor_coherence", built_by="spark", cycle_id=cycle_id)
                g.systems_built.append("athanor_coherence")
            self.workshop.use("athanor_coherence", cycle_id)
            if "athanor_coherence" not in g.systems_used:
                g.systems_used.append("athanor_coherence")
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="athanor_coherence_error",
                actor="spark",
                summary=f"ATHANOR coherence skipped: {exc}",
                detail={"error": str(exc)},
            )
        # Cortex via Cerebrum inform-only sidecar (memory/drift → Oracle/actuation mix only)
        try:
            from colony.cortex_sidecar import run_cortex_sidecar
            from colony.residuals import ResidualField as _RF_cx

            rf_cx = _RF_cx(self.state.data)
            cx = run_cortex_sidecar(self.state.data, cycle_id=cycle_id, residual_field=rf_cx)
            admitted = ((cx.get("cortex") or {}).get("admitted")) or {}
            mix = cx.get("mix_advice") or {}
            g.improvements.append(
                f"cortex:drift={admitted.get('drift')}:reuse={admitted.get('memory_reuse')}:"
                f"throttle={mix.get('suggest_throttle_factor')}"
            )
            self.witness.record(
                cycle_id=cycle_id,
                kind="cortex_cerebrum",
                actor="spark",
                summary=(
                    f"CORTEX/CEREBRUM inform-only: drift={admitted.get('drift')} "
                    f"memory_reuse={admitted.get('memory_reuse')} "
                    f"stability={admitted.get('stability_hint')}. "
                    f"No ledger authority. P>=0.70 human authorize ceiling."
                ),
                detail={
                    "drift": admitted.get("drift"),
                    "memory_reuse": admitted.get("memory_reuse"),
                    "mix_advice": mix,
                    "inform_only": True,
                    "durable_accept": False,
                    "can_accept_ledger": False,
                },
            )
            if "cortex_cerebrum" not in self.workshop.known():
                self.workshop.ensure("cortex_cerebrum", built_by="spark", cycle_id=cycle_id)
                g.systems_built.append("cortex_cerebrum")
            self.workshop.use("cortex_cerebrum", cycle_id)
            if "cortex_cerebrum" not in g.systems_used:
                g.systems_used.append("cortex_cerebrum")
            if "hold_posture" not in self.workshop.known():
                self.workshop.ensure("hold_posture", built_by="spark", cycle_id=cycle_id)
                g.systems_built.append("hold_posture")
            self.workshop.use("hold_posture", cycle_id)
            if "hold_posture" not in g.systems_used:
                g.systems_used.append("hold_posture")
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="cortex_cerebrum_error",
                actor="spark",
                summary=f"CORTEX/CEREBRUM sidecar skipped: {exc}",
                detail={"error": str(exc)},
            )
        # Institution standing charters — agenda autonomy only; never truth/authorize
        try:
            from colony.institution_charters import pursue_cycle as pursue_charters

            ch = pursue_charters(cycle_id, state_data=self.state.data)
            g.improvements.append(
                f"charters:pursued={len(ch.get('pursued') or [])}:"
                f"hints={len(ch.get('topic_hints') or [])}"
            )
            self.witness.record(
                cycle_id=cycle_id,
                kind="institution_charters",
                actor="spark",
                summary=(
                    f"INSTITUTION CHARTERS: pursued={len(ch.get('pursued') or [])} "
                    f"topic_hints={len(ch.get('topic_hints') or [])}. "
                    f"Agenda autonomy only. No truth authority. P>=0.70 ceiling."
                ),
                detail={
                    "pursued": ch.get("pursued"),
                    "exploration_bias": ch.get("exploration_bias"),
                    "inform_only": True,
                    "durable_accept": False,
                    "can_authorize": False,
                },
            )
            if "institution_charters" not in self.workshop.known():
                self.workshop.ensure("institution_charters", built_by="spark", cycle_id=cycle_id)
                g.systems_built.append("institution_charters")
            self.workshop.use("institution_charters", cycle_id)
            if "institution_charters" not in g.systems_used:
                g.systems_used.append("institution_charters")
            # Soft-inform topic_priority with charter hints (no durable accept)
            if "topic_priority" in self.workshop.known():
                from colony.institution_charters import apply_topic_priority_hints, load_charters

                used = self.workshop.use("topic_priority", cycle_id)
                content = dict((used or {}).get("content") or {})
                ranked = apply_topic_priority_hints(content.get("ranked") or [], data=load_charters())
                content["ranked"] = ranked
                content["charter_inform"] = {
                    "hints": len(ch.get("topic_hints") or []),
                    "inform_only": True,
                    "durable_accept": False,
                }
                self.workshop.write_json("topic_priority", content, cycle_id=cycle_id)
                if "topic_priority" not in g.systems_used:
                    g.systems_used.append("topic_priority")
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="institution_charters_error",
                actor="spark",
                summary=f"INSTITUTION CHARTERS skipped: {exc}",
                detail={"error": str(exc)},
            )
        # Proposal→pilot sandbox lane — reversible pilots; promotion needs authorize
        try:
            from colony.pilot_lane import inform_skill_router, run_pilot_lane

            rsi_snap = (self.state.data.get("rsi_coupling") or {})
            pl = run_pilot_lane(
                self.state.data,
                cycle_id=cycle_id,
                rsi_signal=rsi_snap.get("signal") or rsi_snap,
                skill_routes=None,
            )
            proposed = pl.get("proposed") or {}
            lane = pl.get("lane") or {}
            g.improvements.append(
                f"pilot_lane:count={lane.get('pilots_count')}:last={lane.get('last_proposed')}"
            )
            self.witness.record(
                cycle_id=cycle_id,
                kind="pilot_lane",
                actor="improver" if "improver" in self.registry.active() else "spark",
                summary=(
                    f"PILOT LANE sandbox: pilots={lane.get('pilots_count')} "
                    f"proposed={proposed.get('id') or '—'}. "
                    f"Promotion needs P>=0.70 authorize. No durable accept."
                ),
                detail={
                    "lane": lane,
                    "proposed_id": proposed.get("id"),
                    "inform_only": True,
                    "durable_accept": False,
                    "promotion_requires_authorize": True,
                },
            )
            if "pilot_lane" not in self.workshop.known():
                self.workshop.ensure("pilot_lane", built_by="improver", cycle_id=cycle_id)
                g.systems_built.append("pilot_lane")
            self.workshop.use("pilot_lane", cycle_id)
            if "pilot_lane" not in g.systems_used:
                g.systems_used.append("pilot_lane")
            # Inform skill_router with sandbox pilot metadata (write-only inform)
            if "skill_router" in self.workshop.known():
                used = self.workshop.use("skill_router", cycle_id)
                content = inform_skill_router((used or {}).get("content") or {})
                self.workshop.write_json("skill_router", content, cycle_id=cycle_id)
                if "skill_router" not in g.systems_used:
                    g.systems_used.append("skill_router")
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="pilot_lane_error",
                actor="spark",
                summary=f"PILOT LANE skipped: {exc}",
                detail={"error": str(exc)},
            )
        try:
            from colony.oracle import counts as oracle_counts
            from colony.time_revision import revise_from_signals
            ora = {}
            try:
                ora = dict(oracle_counts())
            except Exception:
                ora = {}
            fit_delta = 0.0
            hist = self.state.data.get("fitness_history") or []
            if len(hist) >= 2:
                try:
                    fit_delta = float(hist[-1].get("aggregate") or 0) - float(hist[-2].get("aggregate") or 0)
                except Exception:
                    fit_delta = 0.0
            rev = revise_from_signals(
                cycle_id=cycle_id,
                external_patterns=ext_patterns,
                residual_conflicts=residual_conflicts,
                oracle=ora,
                fitness_delta=fit_delta,
            )
            g.improvements.append(f"time_revision:count={rev.get('revision_count')}")
            self.witness.record(
                cycle_id=cycle_id,
                kind="time_revision",
                actor="spark",
                summary=(
                    f"TIME REVISION: {rev.get('revision_count')} prior conclusion(s) revised "
                    f"from external/residual/oracle signals. Not append-only."
                ),
                detail={
                    "revision_count": rev.get("revision_count"),
                    "revisions": (rev.get("revisions") or [])[:5],
                    "inputs": rev.get("inputs"),
                },
            )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="time_revision_error",
                actor="spark",
                summary=f"TIME REVISION skipped: {exc}",
                detail={"error": str(exc)},
            )
        # SPARK2: ACTION/ACTUATION — close sense→think→act (gated)
        actuation_summary = {}
        try:
            from colony.actuation import run_actuation_cycle
            from colony.residuals import ResidualField
            rf_act = ResidualField(self.state.data)
            ora_act = {}
            try:
                from colony.oracle import counts as oracle_counts
                ora_act = dict(oracle_counts())
            except Exception:
                ora_act = {}
            fit_delta_act = 0.0
            hist_act = self.state.data.get("fitness_history") or []
            if len(hist_act) >= 2:
                try:
                    fit_delta_act = float(hist_act[-1].get("aggregate") or 0) - float(
                        hist_act[-2].get("aggregate") or 0
                    )
                except Exception:
                    fit_delta_act = 0.0
            rr_act = None
            try:
                bm = self.bus.inner_bus_metrics() if hasattr(self.bus, "inner_bus_metrics") else {}
                rr_act = bm.get("reply_rate")
            except Exception:
                pass
            # reuse last revision event from systems if present
            rev_event = {}
            try:
                from colony.time_revision import revision_stats
                rev_event = {"revision_count": revision_stats().get("latest_revision_count")}
            except Exception:
                pass
            actuation_summary = run_actuation_cycle(
                bus=self.bus,
                state_data=self.state.data,
                cycle_id=cycle_id,
                residual_field=rf_act,
                external_patterns=ext_patterns,
                revision_event=rev_event,
                oracle=ora_act,
                fitness_delta=fit_delta_act,
                reply_rate=rr_act,
            )
            g.improvements.append(
                f"actuation:exec={actuation_summary.get('n_executed')}:"
                f"ok={actuation_summary.get('n_success')}:"
                f"blocked={actuation_summary.get('n_blocked')}"
            )
            self.witness.record(
                cycle_id=cycle_id,
                kind="actuation",
                actor="spark",
                summary=(
                    f"ACTION/ACTUATION: executed={actuation_summary.get('n_executed')} "
                    f"success={actuation_summary.get('n_success')} "
                    f"blocked={actuation_summary.get('n_blocked')} "
                    f"kinds={actuation_summary.get('kinds')}. Sense→think→act closed."
                ),
                detail=actuation_summary,
            )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="actuation_error",
                actor="spark",
                summary=f"ACTION/ACTUATION skipped: {exc}",
                detail={"error": str(exc)},
            )
        try:
            from colony.telemetry import attach_to_state
            tsnap = attach_to_state(self.state.data, self.bus)
            g.improvements.append(
                f"telemetry:fit={(tsnap.get('internal') or {}).get('fitness_aggregate')}:"
                f"reply={(tsnap.get('internal') or {}).get('reply_rate')}"
            )
            self.witness.record(
                cycle_id=cycle_id,
                kind="telemetry_snapshot",
                actor="spark",
                summary=(
                    f"Telemetry snapshot for agent query: fit="
                    f"{(tsnap.get('internal') or {}).get('fitness_aggregate')} "
                    f"reply_rate={(tsnap.get('internal') or {}).get('reply_rate')} "
                    f"oracle={(tsnap.get('internal') or {}).get('oracle')}."
                ),
                detail={
                    "ts": tsnap.get("ts"),
                    "internal_keys": list((tsnap.get("internal") or {}).keys()),
                    "external_patterns": (
                        (tsnap.get("external") or {}).get("external_array") or {}
                    ).get("pattern_kinds"),
                },
            )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="telemetry_error",
                actor="spark",
                summary=f"Telemetry snapshot skipped: {exc}",
                detail={"error": str(exc)},
            )
        self._evolve(cycle_id, g, tribute_topics, tribute_count, live_ok, live_fail)
        self._government_and_census(cycle_id, g)

        for role in self.registry.active():
            self.registry.bump_cycle(role)

        from colony.commons import CommonKnowledge
        g.commons_size = CommonKnowledge(self.state.data).size()
        self.bus.render_bulletin()

        self.witness.record(
            cycle_id=cycle_id,
            kind="growth_loop_close",
            actor="spark",
            summary=(
                f"Growth closed: built={g.builds} systems_used={g.systems_used} "
                f"comms={len(g.communications)} replies={g.replies} "
                f"gathered={g.gathered} fitness={g.fitness.get('aggregate')} "
                f"spawn={g.spawn_signals} retired={g.retired}."
            ),
            detail={
                "builds": g.builds,
                "systems_used": g.systems_used,
                "systems_built": g.systems_built,
                "communications": len(g.communications),
                "replies": g.replies,
                "messages_read": g.messages_read,
                "gathered": g.gathered,
                "improvements": g.improvements,
                "fitness": g.fitness,
                "spawn_signals": g.spawn_signals,
                "retired": g.retired,
            },
        )
        return g
