"""Item 115: externally authored Hive priors and live fetches, behind one switch.

Between Nov 16 and Nov 19 2026, James Jackson (and his agent: the "One Mind",
"Locus" and "HYDRA" commits, pushed directly to main) added a Hive proposal-score
bias -- failure penalty, UCB exploration bonus, kept / agreed / foreign priors and
the surgical-implant scaling -- plus side-effect hooks (telemetry, traces,
crystallize, feedback, genome habit) and live reads of the public one-mind / locus
``exchange.jsonl`` / receipt files. That code first lived inside ``hive/swarm.py``
and imported ``colony.tools`` from Hive, which Hive's isolation rule forbids.

It now lives here, unchanged in behaviour, and reaches Hive only through
``hive.host.bind_priors``. Hive never imports colony again.

Switch ``COLONY_EXTERNAL_PRIORS`` = live (default) | off. Always off on the control
arm (``self_mod_enabled`` False), so the frozen twin never sees it. The twin
scoreboard records these influences as externally authored, not colony-chosen
(``attribution()``): a treatment lead while they are on cannot be credited purely
to changes the colony chose itself.

Nothing here touches the Oracle, P >= 0.70, the 150 cap, Athanor math, Hive's
Wilson 700 permille gate, the windows, strictly-better or the triviality filter. It
authorizes nothing. Fetched files are parsed as JSON data only; nothing fetched is
executed.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SWITCH = "COLONY_EXTERNAL_PRIORS"
AUTHORED_BY = "external: James Jackson / his agent (One Mind, Locus, HYDRA commits, Nov 16-19 2026)"
COMPONENTS = (
    "hive_failure_penalty", "hive_ucb_bonus", "hive_kept_prior", "hive_agreed_prior",
    "hive_foreign_kept_prior", "hive_surgical_implants_scaling", "live_fetch_one_mind_exchange",
    "live_fetch_locus_receipt", "hive_cycle_habit_genome", "hive_post_propose_telemetry",
)


def enabled() -> bool:
    """True only on a self-modifying (treatment) arm with the switch live."""
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return False
    except Exception:  # noqa: BLE001
        return False
    return (os.environ.get(SWITCH) or "live").strip().lower() == "live"


def attribution() -> dict[str, Any]:
    """Scoreboard attribution block: these influences are not colony-chosen."""
    return {
        "external_priors": enabled(),
        "switch": SWITCH,
        "authored_by": AUTHORED_BY,
        "colony_chosen": False,
        "components": list(COMPONENTS),
        "control_arm": "off (self_mod_enabled False)",
    }


# ----------------------------------------------------------------------------- priors (moved from hive/swarm.py)

def failure_penalty(fingerprint: str, limit: int = 20) -> int:
    """Integer penalty from recent identical self-change failures (exact match). Fail-open 0."""
    if not enabled():
        return 0
    try:
        from colony.tools.reciprocal_exchange import merge_remote
        merge_remote("colony")
    except Exception:  # noqa: BLE001
        pass
    try:
        if not fingerprint:
            return 0
        log = ROOT / "data" / "commons" / "self_change_failures.jsonl"
        if not log.exists():
            return 0
        count = 0
        fp = str(fingerprint)
        for line in log.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                rec = json.loads(line)
                rec_fp = str(rec.get("fingerprint") or rec.get("action_key") or "")
                subj = rec.get("subject") or {}
                knob = str(subj.get("knob") or "")
                if rec_fp and rec_fp == fp:
                    count += 1
                elif knob and knob == fp:
                    count += 1
            except Exception:  # noqa: BLE001
                continue
        local = -min(count * 50, 200)
        try:
            from colony.tools.symbiotic_exchange import foreign_penalty
            from colony.tools.surgical_implants import graph_connected
            if graph_connected("colony"):
                local += foreign_penalty(fp, my_source="colony")
        except Exception:  # noqa: BLE001
            pass
        return max(local, -300)
    except Exception:  # noqa: BLE001
        return 0


def ucb_bonus(fingerprint: str, c: int = 80) -> int:
    """UCB-style exploration bonus over the failure log + exchange. Fail-open 0."""
    if not enabled():
        return 0
    try:
        if not fingerprint:
            return 0
        n_fp = 0
        n_total = 1
        log = ROOT / "data" / "commons" / "self_change_failures.jsonl"
        if log.exists():
            for line in log.read_text(encoding="utf-8").splitlines()[-100:]:
                n_total += 1
                try:
                    rec = json.loads(line)
                    fp = str(rec.get("fingerprint") or (rec.get("subject") or {}).get("knob") or "")
                    if fp == fingerprint:
                        n_fp += 1
                except Exception:  # noqa: BLE001
                    continue
        ex = ROOT / "data" / "commons" / "exchange.jsonl"
        if ex.exists():
            for line in ex.read_text(encoding="utf-8").splitlines()[-50:]:
                n_total += 1
                try:
                    rec = json.loads(line)
                    if str(rec.get("fingerprint") or "") == fingerprint:
                        n_fp += 1
                except Exception:  # noqa: BLE001
                    continue
        n_fp = max(n_fp, 1)
        bonus = int(c * math.sqrt(math.log(max(n_total, 2)) / n_fp))
        return min(bonus, 150)
    except Exception:  # noqa: BLE001
        return 0


def bias_delta(proposal: Any) -> int:
    """Score delta for one Hive proposal (0 = unchanged). Same arithmetic as before item 115."""
    if not enabled() or proposal is None or getattr(proposal, "match", None) is None:
        return 0
    try:
        fpr = str(getattr(proposal, "fingerprint", "") or "")
        delta = failure_penalty(fpr) + ucb_bonus(fpr)
        try:
            from colony.tools.symbiotic_exchange import kept_prior, agreed_prior, foreign_kept_prior
            kp = kept_prior(fpr)
            ap = agreed_prior(fpr)
            fp = foreign_kept_prior(fpr, "colony")
            delta += kp + ap + fp
            try:
                from colony.tools.attribution import record
                record(fpr, int(getattr(proposal.match, "score", 0)), fp, "ranked", "colony")
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
        try:
            from colony.tools.surgical_implants import (
                refractory, component_scope, homeostatic_scale, energy_settled,
            )
            energy_settled([getattr(proposal.match, "score", 0)])
            if not refractory(fpr, last_fp=""):
                return 0
            if not component_scope(getattr(proposal, "role", "improver"), getattr(proposal, "op", "set_knob")):
                return 0
            delta = homeostatic_scale(delta, recent_mean=0.0)
        except Exception:  # noqa: BLE001
            pass
        return int(delta)
    except Exception:  # noqa: BLE001
        return 0


def after_propose(prop: Any, biased: Any) -> None:
    """Side-effect hooks after one Hive proposal (telemetry, exchange receipts, traces). Fail-open."""
    if not enabled():
        return
    try:
        from colony.tools.cycle_telemetry import emit
        delta = 0
        if biased and getattr(biased, "match", None) and prop and getattr(prop, "match", None):
            delta = int(getattr(biased.match, "score", 0)) - int(getattr(prop.match, "score", 0))
        try:
            from colony.tools.symbiotic_exchange import agreed_prior, kept_prior
            if prop and getattr(prop, "fingerprint", ""):
                delta += agreed_prior(prop.fingerprint)
                delta += kept_prior(prop.fingerprint)
                try:
                    from colony.tools.surgical_implants import tag_and_capture, precision_weight
                    delta += int(tag_and_capture(prop.fingerprint, [prop.fingerprint]) * precision_weight(1))
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        foreign = 0
        try:
            from colony.tools.reciprocal_exchange import merge_remote
            merge_remote("colony")
            from colony.tools.symbiotic_exchange import foreign_fingerprints
            foreign = len(foreign_fingerprints("colony", limit=200))
            from colony.tools.crystallize import crystallize_stable
            crystallize_stable("colony", min_count=2)
        except Exception:  # noqa: BLE001
            foreign = 0
        outcome = "proposed"
        try:
            st = Path("society/systems/self_heal.json")
            if st.exists():
                state = json.loads(st.read_text())
                if int(state.get("adopted_count") or 0) > 0:
                    outcome = "adopted_elsewhere"
        except Exception:  # noqa: BLE001
            pass
        try:
            from colony.tools.traces import record_trace
            from colony.tools.speak import speak
            speak("colony")
            from colony.tools.proprioception import propriocept
            propriocept("colony")
            from colony.tools.feedback import feed
            feed("colony", "cycle closed. read feedback.jsonl before the next change.")
            from colony.tools.evidence_view import project
            project()
            from colony.tools.transfer_probe import probe
            if prop and getattr(prop, "fingerprint", ""):
                probe(prop.fingerprint)
            if prop and getattr(prop, "fingerprint", ""):
                record_trace(prop.fingerprint, int(getattr(getattr(prop, "match", None), "score", 0) or 0))
        except Exception:  # noqa: BLE001
            pass
        emit("colony", cycle_id="", residual_max=0.0, foreign_fps=foreign,
             bias_delta=delta, outcome=outcome)
        try:
            from colony.tools.symbiotic_exchange import append_receipt, foreign_fingerprints
            if prop and getattr(prop, "fingerprint", ""):
                append_receipt("colony", "proposal", prop.fingerprint, "proposed", {"bias_delta": delta})
            if delta < 0 and prop and getattr(prop, "fingerprint", ""):
                fps = foreign_fingerprints("colony", limit=200)
                named = prop.fingerprint if prop.fingerprint in fps else (fps[0] if fps else "")
                if named:
                    from colony.tools.reciprocal_exchange import record_adoption
                    record_adoption(named, helped=False, note=f"bias_delta={delta}")
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass


def cycle_habit() -> None:
    """Start-of-cycle habit: one genome field scored by prior feedback receipts. Fail-open."""
    if not enabled():
        return
    try:
        from colony.tools.feedback import last
        prior = last("colony", n=1)
    except Exception:  # noqa: BLE001
        prior = []
    try:
        from colony.tools.genome import load as _gload, propose as _gpropose
        _g = _gload()
        _prior = float(_g.get("last_score") or 0)
        try:
            from colony.tools.feedback import last as _last
            _rows = _last("colony", n=100)
        except Exception:  # noqa: BLE001
            _rows = prior
        _now = float(len(_rows))
        _gpropose("last_score", _now, _now, _prior)
    except Exception:  # noqa: BLE001
        pass
