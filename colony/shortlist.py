"""Ranked proposal shortlist for James — a VIEW only.

Written at the end of every cycle to society/shortlist/SHORTLIST.json and SHORTLIST.md
(overwritten, never appended). It never authorizes, never changes a score, P value, status or
any colony decision; it reads state and logs and writes these two files only.

Authorize bar (all must hold; the same bar James uses):
  1. status == candidate_measured                (measured, still pending)
  2. Hearing verdict == accept_candidate
  3. target resolves to a real catalog entry and the Oracle PASSED that target in the
     proposal's own cycle
  4. not novelty-killed: no kills on the novelty-gate row for the target in that cycle, and the
     current live textbook_reuse score is below the 0.34 kill line
  5. P under the current rule (standing_trust.compute_proposal_P, recomputed now) >= 0.70

Rank = 0.6·P + 0.2·novelty + 0.2·builds_on, where
  novelty   = 1 − textbook_reuse (current live rule, the same term P uses),
  builds_on = mean over the building blocks the proposal names ("built from proven lemmas
              [...]" and the components of a composed check ``authored_A__B``) of
              1 = Oracle-passed lemma, 0.5 = machine instrument (e.g. instrument:sieve.*), 0 = other;
              0 when it names none.
Building blocks (textbook / classical lemmas) never rank as novel: a target that is a desk
catalog lemma (no ``authored_`` prefix — e.g. the 30 classical lemmas refilled in 68954ec) or
whose name is one of the novelty gate's TEXTBOOK_IDENTITIES (pascal_identity, cassini, ...) gets
novelty 0 for ranking and is listed in a separate "building blocks enabled" section, so the
top list is the colony's own authored work. View only: the live novelty killer and every score
are untouched (``novelty_raw`` keeps the live value for reference).
Near-duplicates (same target family = target name without its ``_wN`` window suffix) are
grouped: one representative (highest rank) plus a count.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "society" / "shortlist"
ORACLE_LOG = ROOT / "data" / "commons" / "oracle.jsonl"
NOVELTY_LOG = ROOT / "data" / "commons" / "novelty_gate.jsonl"
STATE_PATH = ROOT / "data" / "society_state.json"
ATHANOR_STATE = ROOT / "society" / "systems" / "athanor_gate.json"
P_MIN = 0.70
# The 30 classical building-block lemmas added to the desk catalog in 68954ec (listed for the
# record; the rule below already covers them because none carries the ``authored_`` prefix).
REFILL_68954EC = frozenset("""fermat_little euler_theorem wilson_theorem quadratic_reciprocity
mobius_divisor_sum gauss_phi_divisor_sum sigma_multiplicative mobius_inversion_sigma bezout_identity
crt_coprime_pair lucas_theorem_binomial stirling_first_row_sum bell_stirling_sum
alternating_binomial_row multinomial_three euler_pentagonal odd_distinct_partitions
partition_conjugate_parts cayley_tree_count cycle_spanning_trees complete_bipartite_trees
cayley_hamilton_2x2 cayley_hamilton_3x3 newton_identities polynomial_remainder telescoping_sum
abel_summation faulhaber_power_sums lagrange_cyclic_orders burnside_necklaces""".split())


def building_block_kind(target: str, identities: Any = None) -> str | None:
    """'catalog_refill' | 'catalog' | 'classical_identity' when the target is textbook material, else None."""
    t = str(target or "")
    if not t:
        return None
    if t in REFILL_68954EC:
        return "catalog_refill"
    if not t.startswith("authored_"):
        return "catalog"
    if identities is None:
        try:
            from colony.novelty_gate import TEXTBOOK_IDENTITIES as identities  # noqa: N811
        except Exception:  # noqa: BLE001
            identities = ()
    low = t.lower()
    if any(i in low for i in identities if i != "easy_pad"):
        return "classical_identity"
    return None
NOVELTY_KILL = 0.34
TOP_N = 10
W_P, W_NOV, W_BUILD = 0.6, 0.2, 0.2
_BUILT_RE = re.compile(r"built from proven lemmas \[([^\]]*)\]", re.I)
_COMPOSE_RE = re.compile(r"^authored_([a-z0-9_]+?)__([a-z0-9_]+?)(?:_w\d+)?$")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if path.exists():
        for ln in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return out


def family(target: str) -> str:
    return re.sub(r"_w\d+$", "", target or "")


def building_blocks(prop: dict[str, Any], target: str) -> list[str]:
    blocks: list[str] = []
    m = _BUILT_RE.search(prop.get("hypothesis") or "")
    if m:
        blocks += [b.strip() for b in m.group(1).split(",") if b.strip()]
    c = _COMPOSE_RE.match(target or "")
    if c:
        blocks += [c.group(1), c.group(2)]
    return list(dict.fromkeys(blocks))


def builds_on(blocks: list[str], passed: set[str]) -> float:
    if not blocks:
        return 0.0
    vals = [1.0 if b in passed else (0.5 if b.startswith("instrument:") else 0.0) for b in blocks]
    return round(sum(vals) / len(vals), 4)


def _default_resolve(prop: dict[str, Any]) -> str:
    from colony.standing_trust import resolve_proposal_target
    return resolve_proposal_target(action=prop.get("action") or "", mutation=prop.get("title") or "")


def _default_reuse(prop: dict[str, Any]) -> float:
    from colony.novelty_gate import textbook_reuse_score
    return float(textbook_reuse_score((prop.get("title") or prop.get("action") or "").strip(), prop.get("action") or ""))


def _default_P(prop: dict[str, Any]) -> float | None:
    # defer_title_check: with a resolved target this never submits anything to the Oracle
    from colony.standing_trust import compute_proposal_P
    P, _t = compute_proposal_P(mutation=prop.get("title") or "", action=prop.get("action") or "",
                               fingerprint=prop.get("fingerprint") or "",
                               bench_delta=prop.get("delta_aggregate"), cycle_id=prop.get("cycle_id") or "",
                               defer_title_check=True)
    return P


def evaluate(prop: dict[str, Any], *, oracle_rows: list[dict[str, Any]], novelty_rows: list[dict[str, Any]],
             athanor_rows: list[dict[str, Any]], resolve=_default_resolve, reuse=_default_reuse,
             p_rule=_default_P, block_kind=None) -> dict[str, Any]:
    """Bar check + rank terms for one proposal. Pure given its inputs."""
    why: list[str] = []
    cid = prop.get("cycle_id") or ""
    if prop.get("status") != "candidate_measured":
        why.append(f"status={prop.get('status')}")
    if prop.get("hearing_verdict") != "accept_candidate":
        why.append(f"hearing={prop.get('hearing_verdict')}")
    target = ""
    try:
        target = resolve(prop) or ""
    except Exception:  # noqa: BLE001
        target = ""
    if not target:
        why.append("target_unresolved")
    own = [o for o in oracle_rows if o.get("mutation") == target and o.get("cycle_id") == cid] if target else []
    if target and not (own and own[-1].get("passed")):
        why.append("no_oracle_pass_in_own_cycle" if not own else "oracle_killed_in_own_cycle")
    nov_rows = [n for n in novelty_rows if n.get("mutation") == target and n.get("cycle_id") == cid] if target else []
    tr = None
    if target:
        tr = reuse(prop)
        if nov_rows and nov_rows[-1].get("kills"):
            why.append(f"novelty_killed:{nov_rows[-1]['kills'][:2]}")
        if tr >= NOVELTY_KILL:
            why.append(f"novelty_killed:textbook_reuse={tr}")
    P = None
    if not why:  # P recompute only for proposals that already clear the other conditions
        P = p_rule(prop)
        if P is None or float(P) < P_MIN:
            why.append(f"P={P}<{P_MIN}")
    passed = {o.get("mutation") for o in oracle_rows if o.get("passed")}
    blocks = building_blocks(prop, target)
    b = builds_on(blocks, passed)
    nov_raw = round(1.0 - float(tr), 4) if tr is not None else None
    bb = (block_kind or building_block_kind)(target)
    nov = 0.0 if (bb and nov_raw is not None) else nov_raw
    ath = next((r for r in reversed(athanor_rows) if r.get("mutation") == target), None)
    rank = round(W_P * float(P) + W_NOV * float(nov or 0.0) + W_BUILD * b, 4) if P is not None else None
    return {"id": prop.get("id"), "title": prop.get("title"), "cycle_id": cid, "target": target,
            "family": family(target), "meets_bar": not why, "why_not": why, "P": P,
            "P_stored": prop.get("P"), "novelty": nov, "novelty_raw": nov_raw,
            "building_block": bb, "builds_on": b, "building_blocks": blocks,
            "athanor_verdict": (ath or {}).get("verdict"), "rank": rank}


def plain_line(e: dict[str, Any]) -> str:
    t = e["target"]
    if e.get("building_block"):
        return (f"Building block `{t}` ({e['building_block'].replace('_', ' ')}; textbook, not novel) — "
                f"Oracle passed it in its own cycle; P {e['P']}.")
    blocks = ", ".join(e["building_blocks"][:3]) or "no named building blocks"
    return (f"Enable `{t}` (Oracle passed it in its own cycle); builds on {blocks}; "
            f"P {e['P']}, novelty {e['novelty']}.")


def build(*, proposals: list[dict[str, Any]], oracle_rows: list[dict[str, Any]],
          novelty_rows: list[dict[str, Any]], athanor_rows: list[dict[str, Any]] | None = None,
          top_n: int = TOP_N, **kw: Any) -> dict[str, Any]:
    seen: set[str] = set()
    evals = []
    for p in proposals:
        if not p.get("id") or p["id"] in seen:
            continue
        seen.add(p["id"])
        evals.append(evaluate(p, oracle_rows=oracle_rows, novelty_rows=novelty_rows,
                              athanor_rows=athanor_rows or [], **{k: v for k, v in kw.items() if k != "oeis"}))
    hunt = None
    try:  # REPORT-ONLY hunt shadow: adds e["hunt"]; never changes P, rank or the bar
        from colony.hunt_shadow import annotate, enabled as _hunt_on, summarize
        if _hunt_on():
            annotate(evals, oracle_rows=oracle_rows, oeis=kw.get("oeis"))
            hunt = summarize(evals, oracle_rows=oracle_rows)
            allsh = sorted([e for e in evals if e["hunt"]["rank_shadow"] is not None],
                           key=lambda e: (-(e["hunt"]["rank_shadow"] or 0), e["id"]))
            spos = {e["id"]: i for i, e in enumerate(allsh, 1)}
            for e in evals:
                e["hunt"]["shadow_pos"] = spos.get(e["id"])
    except Exception:  # noqa: BLE001
        hunt = None
    ok = sorted([e for e in evals if e["meets_bar"]], key=lambda e: (-e["rank"], -(e["P"] or 0), e["id"]))
    groups: dict[str, dict[str, Any]] = {}
    for e in ok:
        g = groups.get(e["family"])
        if g is None:
            groups[e["family"]] = {**e, "group_count": 1, "group_ids": [e["id"]]}
        else:
            g["group_count"] += 1
            g["group_ids"].append(e["id"])
    allg = list(groups.values())
    ranked = [g for g in allg if not g.get("building_block")]
    blocks = [g for g in allg if g.get("building_block")]
    for lst in (ranked, blocks):
        for i, g in enumerate(lst, 1):
            g["position"] = i
            g["line"] = plain_line(g)
    reasons: dict[str, int] = {}
    for e in evals:
        for w in e["why_not"]:
            k = w.split(":")[0].split("=")[0]
            reasons[k] = reasons.get(k, 0) + 1
    return {"ts": _utc(), "view_only": True, "n_considered": len(evals), "n_meet_bar": len(ok),
            "n_groups": len(allg), "n_authored_groups": len(ranked),
            "n_building_block_groups": len(blocks), "top": ranked[:top_n],
            "building_blocks_enabled": blocks[:top_n], "hunt_shadow": hunt, "excluded_reasons": reasons,
            "rule": {"P_min": P_MIN, "novelty_kill": NOVELTY_KILL, "rank": f"{W_P}*P + {W_NOV}*novelty + {W_BUILD}*builds_on",
                     "building_blocks": "novelty=0 for ranking; listed separately"},
            "note": "View only. Does not authorize or change anything. Only James authorizes."}


def _et(ts: str) -> str:
    try:
        from zoneinfo import ZoneInfo
        d = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return d.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M %p ET")
    except Exception:  # noqa: BLE001
        return ts


def _shadow_cell(g: dict[str, Any]) -> str:
    h = g.get("hunt") or {}
    if not h:
        return "–"
    return f"{h.get('shadow_pos') or '–'} ({h.get('P_shadow')}{'' if h.get('meets_bar_shadow') else ', below bar'})"


def to_markdown(sl: dict[str, Any]) -> str:
    lines = [f"# Proposal shortlist — {_et(sl['ts'])}", "",
             "View only: nothing here is authorized. Only James authorizes.", "",
             f"{sl['n_meet_bar']} of {sl['n_considered']} proposals meet the authorize bar "
             f"({sl['n_groups']} after grouping near-duplicates; {sl.get('n_authored_groups', sl['n_groups'])} "
             f"colony-authored, {sl.get('n_building_block_groups', 0)} building blocks). Rank = {sl['rule']['rank']}.", "",
             "| # | Proposal | P | Novelty | Builds on | Athanor | Similar | Shadow # (P) | What it is |",
             "|---|---|---:|---:|---:|---|---:|---|---|"]
    for g in sl["top"]:
        lines.append(f"| {g['position']} | {g['id']} | {g['P']} | {g['novelty']} | {g['builds_on']} | "
                     f"{g['athanor_verdict'] or 'n/a yet'} | {g['group_count']} | {_shadow_cell(g)} | {g['line']} |")
    if not sl["top"]:
        lines.append("| – | no colony-authored proposal meets the bar this cycle | | | | | | |")
    bbs = sl.get("building_blocks_enabled") or []
    lines += ["", f"## Building blocks enabled ({sl.get('n_building_block_groups', len(bbs))} groups meet the bar)", "",
              "Textbook / classical lemmas (desk catalog incl. the 68954ec refill, or a classical identity). "
              "They meet the bar but are not novel: novelty counts as 0 for ranking and they are kept out "
              "of the top list above.", ""]
    if bbs:
        lines += ["| # | Proposal | P | Kind | Athanor | Similar | Shadow # (P) | What it is |",
                  "|---|---|---:|---|---|---:|---|---|"]
        for g in bbs:
            lines.append(f"| {g['position']} | {g['id']} | {g['P']} | {g['building_block']} | "
                         f"{g['athanor_verdict'] or 'n/a yet'} | {g['group_count']} | {_shadow_cell(g)} | {g['line']} |")
    else:
        lines.append("None this cycle.")
    h = sl.get("hunt_shadow")
    if h:
        lines += ["", "## Hunt shadow (view only — would-be ranking if the unknown were rewarded)", "",
                  f"Rules in colony/hunt_shadow.py. Would meet the bar: {h['n_meet_bar_shadow']} "
                  f"(actual {h['n_meet_bar_actual']}). Unknown claims (Oracle-surviving, not textbook, not in "
                  f"OEIS): {h['n_unknown_claims']} ({h['n_unknown_oeis_unchecked']} with OEIS unchecked). "
                  f"Would drop out of the bar: {len(h['drop_out_of_bar'])}; would enter: {len(h['enter_bar'])}.", "",
                  "| Shadow # | Proposal | Target | P → P_shadow | Shadow bar | Unknown | Expected | Actual # |",
                  "|---:|---|---|---|---|---|---:|---:|"]
        for m in h["top_shadow"]:
            lines.append(f"| {m['shadow_pos']} | {m['id']} | `{m['target']}` | {m['P']} → {m['P_shadow']} | "
                         f"{'meets' if m['meets_bar_shadow'] else 'below'} | {'yes' if m['unknown'] else 'no'} | "
                         f"{m['expected']} | {m['actual_pos'] or '–'} |")
        if not h["top_shadow"]:
            lines.append("| – | no proposal clears the non-P bar conditions | | | | | | |")
    lines += ["", "Excluded (reason: count): " + (", ".join(f"{k}: {v}" for k, v in
                                                       sorted(sl["excluded_reasons"].items())) or "none"), ""]
    return "\n".join(lines)


def write(cycle_id: str = "", **kw: Any) -> dict[str, Any] | None:
    """Rebuild and overwrite the shortlist from current state. Never raises."""
    try:
        st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        props = list(st.get("improvement_proposals") or []) + list(st.get("improvement_proposals_archived") or [])
        try:
            ath = json.loads(ATHANOR_STATE.read_text(encoding="utf-8")).get("rows") or []
        except Exception:  # noqa: BLE001
            ath = []
        sl = build(proposals=props, oracle_rows=_jsonl(ORACLE_LOG), novelty_rows=_jsonl(NOVELTY_LOG),
                   athanor_rows=ath, **kw)
        sl["cycle_id"] = cycle_id
        if sl.get("hunt_shadow"):
            try:
                from colony.hunt_shadow import near_misses, record
                sl["hunt_shadow"]["cycle_id"] = cycle_id
                sl["hunt_shadow"]["near_misses"] = near_misses(_jsonl(ORACLE_LOG), cycle_id)
                record(sl["hunt_shadow"])
            except Exception:  # noqa: BLE001
                pass
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "SHORTLIST.json").write_text(json.dumps(sl, indent=2) + "\n", encoding="utf-8")
        (OUT_DIR / "SHORTLIST.md").write_text(to_markdown(sl), encoding="utf-8")
        return sl
    except Exception:  # noqa: BLE001
        return None


if __name__ == "__main__":
    out = write()
    print(to_markdown(out) if out else "shortlist: unavailable")
