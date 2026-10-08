"""Scrape → analyze → claim pipeline.

research_gather (provenance) → extract claims → test against hard benches/code
→ only then propose as candidates. Raw scrape ≠ discovery. Not AGI. Not Millennium.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "research_cache" / "papers.jsonl"
CLAIMS_JSONL = ROOT / "data" / "commons" / "extracted_claims.jsonl"
PIPELINE_SYSTEM = ROOT / "society" / "systems" / "claim_pipeline.json"

# Themes that can be tested against existing hard benches (classical only)
TESTABLE_THEMES: list[tuple[str, str, list[str]]] = [
    # (theme_id, bench_hint, keywords)
    ("binomial_identities", "lemma_microbench hard:binomial*", ["binomial", "pascal", "combinatorial"]),
    ("fibonacci_identities", "lemma_microbench hard:fibonacci*|cassini", ["fibonacci", "cassini", "lucas"]),
    ("vandermonde", "lemma_microbench hard:vandermonde*", ["vandermonde", "convolution"]),
    ("catalan", "lemma_microbench hard:catalan*", ["catalan"]),
    ("fft_signal", "fft_microbench", ["fourier", "fft", "convolution theorem"]),
    ("autodiff", "autodiff_microbench", ["automatic differentiation", "autodiff", "backpropagation"]),
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _oracle_seen_claims(limit: int = 500) -> set[str]:
    """Keys already Oracle-PASS'd: theme_id:arxiv_id|claim_id."""
    log = ROOT / "data" / "commons" / "oracle.jsonl"
    seen: set[str] = set()
    if not log.exists():
        return seen
    for ln in log.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not ln.strip():
            continue
        try:
            e = __import__("json").loads(ln)
        except Exception:
            continue
        if not e.get("passed"):
            continue
        mut = str(e.get("mutation") or "")
        if mut:
            seen.add(mut)
            # Also index bare theme
            seen.add(f"{mut}:")
    return seen


def _theme_pass_count(theme_id: str, limit: int = 500) -> int:
    log = ROOT / "data" / "commons" / "oracle.jsonl"
    if not log.exists():
        return 0
    n = 0
    for ln in log.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            e = __import__("json").loads(ln)
        except Exception:
            continue
        if e.get("passed") and str(e.get("mutation") or "") == theme_id:
            n += 1
    return n


# Claims are posted on the domain channel their theme belongs to (lemma themes → math;
# signal / autodiff themes → science). The post is the claim's bus receipt.
CLAIM_CHANNELS: dict[str, str] = {
    "binomial_identities": "math",
    "fibonacci_identities": "math",
    "vandermonde": "math",
    "catalan": "math",
    "fft_signal": "science",
    "autodiff": "science",
}
RECEIPT_CHANNELS = frozenset({"math", "science", "history", "empire", "rsi"})


def claim_channel(theme_id: str) -> str:
    return CLAIM_CHANNELS.get(theme_id, "math")


def post_claim(bus: Any, claim: "ExtractedClaim", *, cycle_id: str) -> dict[str, Any] | None:
    """Post the claim on its domain channel of the real CommBus; return the bus receipt.

    The receipt is only what the bus actually logged: {msg_id, channel, cycle_id, claim_id}.
    No bus → None (the Oracle then fails closed with oracle_blocked_no_bus).
    """
    if bus is None:
        return None
    ch = claim_channel(claim.theme_id)
    prov = claim.provenance or {}
    pointer = prov.get("arxiv_id") or prov.get("doi") or prov.get("url") or ""
    entry = bus.post(
        from_role="geometer",
        to_role="all",
        channel=ch,
        message=(
            f"CLAIM for Oracle HEAR: `{claim.theme_id}` ({claim.claim_id}) — {claim.text[:200]} "
            f"Source pointer: {pointer or 'cache'} (untrusted pointer, not evidence). "
            f"Hard check: {claim.note[:120]}"
        ),
        cycle_id=cycle_id,
        tags=["claim", "oracle_submit", claim.theme_id],
        payload={"claim_id": claim.claim_id, "theme_id": claim.theme_id, "kind": "claim_theme"},
    )
    if not isinstance(entry, dict) or not entry.get("id"):
        return None
    return {"msg_id": entry.get("id"), "channel": ch, "cycle_id": cycle_id, "claim_id": claim.claim_id}


def validate_bus_receipt(bus: Any, receipt: dict[str, Any] | None, *, claim_id: str, cycle_id: str) -> bool:
    """A receipt is genuine only if the CommBus log really holds that message: same id, a
    domain channel, this cycle, this claim. Anything else (missing, forged id, wrong
    channel/cycle/claim, a bus with no log) → False."""
    if bus is None or not isinstance(receipt, dict):
        return False
    mid, ch = receipt.get("msg_id"), receipt.get("channel")
    if not mid or ch not in RECEIPT_CHANNELS:
        return False
    if receipt.get("cycle_id") != cycle_id or receipt.get("claim_id") != claim_id:
        return False
    try:
        msgs = bus.messages()
    except Exception:
        return False
    for m in reversed(list(msgs or [])):
        if m.get("id") != mid:
            continue
        return (
            m.get("channel") == ch
            and m.get("cycle_id") == cycle_id
            and (m.get("payload") or {}).get("claim_id") == claim_id
        )
    return False


@dataclass
class ExtractedClaim:
    claim_id: str
    theme_id: str
    text: str
    provenance: dict[str, Any]
    bench_hint: str
    status: str = "extracted"  # extracted | hard_checked | proposed | rejected_raw
    hard_ok: bool | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "theme_id": self.theme_id,
            "text": self.text,
            "provenance": self.provenance,
            "bench_hint": self.bench_hint,
            "status": self.status,
            "hard_ok": self.hard_ok,
            "note": self.note,
            "ts": _utc(),
            "not_discovery": True,
        }


def _load_papers(limit: int = 24) -> list[dict[str, Any]]:
    if not CACHE.exists():
        return []
    out: list[dict[str, Any]] = []
    for ln in CACHE.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out[-limit:]


def extract_claims(papers: list[dict[str, Any]] | None = None) -> list[ExtractedClaim]:
    """Pull testable claim themes from paper titles/abstracts. Pointers only."""
    papers = papers if papers is not None else _load_papers()
    claims: list[ExtractedClaim] = []
    seen: set[str] = set()
    for p in papers:
        blob = f"{p.get('title') or ''} {p.get('abstract_snippet') or ''}".lower()
        for theme_id, bench_hint, kws in TESTABLE_THEMES:
            if not any(k in blob for k in kws):
                continue
            key = f"{theme_id}:{p.get('arxiv_id') or (p.get('title') or '')[:40]}"
            if key in seen:
                continue
            seen.add(key)
            cid = f"cl_{theme_id}_{re.sub(r'[^a-z0-9]+', '', (p.get('arxiv_id') or key)[:24])}"
            text = (
                f"CLAIM CANDIDATE (not discovered): paper themes around `{theme_id}` "
                f"from `{(p.get('title') or '')[:80]}` may relate to {bench_hint}. "
                f"Raw scrape ≠ discovery. Needs hard check + authorize."
            )
            claims.append(
                ExtractedClaim(
                    claim_id=cid,
                    theme_id=theme_id,
                    text=text,
                    provenance={
                        "title": (p.get("title") or "")[:120],
                        "arxiv_id": p.get("arxiv_id") or "",
                        "doi": p.get("doi") or "",
                        "url": p.get("url") or "",
                        "source": p.get("source") or "cache",
                    },
                    bench_hint=bench_hint,
                    status="extracted",
                )
            )
    return claims


def hard_check_claim(claim: ExtractedClaim) -> ExtractedClaim:
    """Test claim against live hard benches. Only pass → proposable."""
    hint = (claim.bench_hint or "").lower()
    try:
        if "lemma" in hint:
            from society.benchmarks.lemma_microbench import run as run_lemma

            r = run_lemma()
            ok = bool(r.get("ok")) and int(r.get("n_hard_pass") or 0) > 0
            claim.hard_ok = ok
            claim.status = "hard_checked" if ok else "rejected_raw"
            claim.note = (
                f"lemma score={r.get('score')} hard_pass={r.get('n_hard_pass')}/{r.get('n_hard')} "
                f"— machine-checked harness only; not theorem discovery"
            )
        elif "fft" in hint:
            from society.benchmarks.fft_microbench import run as run_fft

            r = run_fft()
            ok = bool(r.get("ok"))
            claim.hard_ok = ok
            claim.status = "hard_checked" if ok else "rejected_raw"
            claim.note = f"fft ok={ok} score={r.get('score')}"
        elif "autodiff" in hint:
            from society.benchmarks.autodiff_microbench import run as run_ad

            r = run_ad()
            ok = bool(r.get("ok"))
            claim.hard_ok = ok
            claim.status = "hard_checked" if ok else "rejected_raw"
            claim.note = f"autodiff ok={ok} score={r.get('score')}"
        else:
            claim.hard_ok = False
            claim.status = "rejected_raw"
            claim.note = "no hard bench mapped — raw scrape held as pointer only"
    except Exception as exc:  # noqa: BLE001
        claim.hard_ok = False
        claim.status = "rejected_raw"
        claim.note = f"hard_check error: {exc}"
    return claim


def propose_checked(
    claims: list[ExtractedClaim],
    *,
    ledger: Any | None = None,
    cycle_id: str = "",
    bus: Any | None = None,
) -> list[dict[str, Any]]:
    """Only hard_checked claims become ledger candidates. Raw scrape ≠ discovery.

    ``bus`` must be the society's real CommBus (the one persisted with society state). Each
    claim is posted on its domain channel and the Oracle only receives the bus when that
    post is verifiably in the bus log; otherwise it fails closed (oracle_blocked_no_bus).
    """
    proposed: list[dict[str, Any]] = []
    CLAIMS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    for c in claims:
        with CLAIMS_JSONL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
        if c.status != "hard_checked" or not c.hard_ok:
            continue
        # Phase 0: same (theme_id, arxiv_id|claim_id) cannot Oracle-PASS more than once
        try:
            from colony.lessons import write_lesson
            seen = _oracle_seen_claims(limit=500)
            claim_key = f"{c.theme_id}:{c.provenance.get('arxiv_id') or c.claim_id}"
            if claim_key in seen or c.theme_id in seen or _theme_pass_count(c.theme_id) >= 3:
                write_lesson(
                    decision="skip",
                    check="oracle_seen_claim",
                    what=f"skip re-oracle of {claim_key}",
                    source="claim_pipeline",
                    family="novelty",
                    mutation=c.theme_id,
                    cycle_id=cycle_id,
                    lesson_type="skip",
                    tags=["repeat_claim"],
                    proposal_fingerprint=claim_key[:48],
                )
                c.status = "rejected_raw"
                c.hard_ok = False
                c.note = (c.note or "") + f" | skip_seen_claim:{claim_key}"
                continue
        except Exception:
            pass
        # Textbook-reuse annotation (same score and same text change as before; it no longer
        # needs a separate novelty-gate Oracle run, which had no bus and always died
        # oracle_blocked_no_bus).
        try:
            from colony.novelty_gate import textbook_reuse_score
            _reuse = textbook_reuse_score(c.theme_id.strip(), c.text)
            if _reuse >= 0.34:
                c.note = (c.note or "") + f" | novelty_kill textbook_reuse={_reuse}"
                c.text = c.text + " [novelty_gate: not novel-to-commons]"
        except Exception:
            pass
        # Bus receipt: the claim is posted on its domain channel of the real CommBus; the
        # Oracle gets the bus only if that post is verifiably in the bus log.
        receipt = None
        oracle_bus = None
        try:
            receipt = post_claim(bus, c, cycle_id=cycle_id)
        except Exception as _bx:
            c.note = (c.note or "") + f" | bus_post_error:{_bx}"
            receipt = None
        if validate_bus_receipt(bus, receipt, claim_id=c.claim_id, cycle_id=cycle_id):
            oracle_bus = bus
            c.provenance = {**(c.provenance or {}), "bus_receipt": receipt}
            c.note = (c.note or "") + f" | bus_receipt={receipt['channel']}:{receipt['msg_id']}"
        else:
            c.note = (c.note or "") + " | bus_receipt_invalid_or_missing"
        # Oracle mile: real bus only; fail-closed without it
        try:
            from colony.oracle import gate_keep as oracle_gate
            final_dec, ov = oracle_gate(
                tentative_decision="propose",
                mutation=c.theme_id,
                kind="claim_theme",
                claim_text=c.text,
                source="claim_pipeline",
                cycle_id=cycle_id,
                bus=oracle_bus,
            )
            c.note = (c.note or "") + (
                f" | oracle={'PASS' if ov.passed else 'KILL'} kills={ov.kills} "
                f"bus_ok={(ov.hear or {}).get('bus_ok')}"
            )
            # Novelty gate on this claim, judged with the Oracle verdict just obtained (one
            # Oracle run per claim; same conditions as ever).
            try:
                from colony.novelty_gate import evaluate as novelty_evaluate
                _nv = novelty_evaluate(
                    mutation=c.theme_id, kind="claim_theme", claim_text=c.text, cycle_id=cycle_id,
                    oracle_verdict=ov, oracle_verdict_required=True,
                )
                c.note = (c.note or "") + f" | novelty_gate novel={_nv.get('novel_to_commons')}"
            except Exception:
                pass
            if final_dec not in ("propose", "keep"):
                c.status = "rejected_raw"
                c.hard_ok = False
                c.note = (c.note or "") + " | oracle_blocked_propose"
                continue
        except Exception as _ox:
            c.note = (c.note or "") + f" | oracle_error_fail_closed:{_ox}"
            c.status = "rejected_raw"
            c.hard_ok = False
            continue
        prop = c.to_dict()
        prop["status"] = "candidate"
        prop["stage"] = "propose_after_hard_check"
        if ledger is not None:
            try:
                ledger.set_extra_roles({"spark", "geometer", "tribute_keeper"})
            except Exception:
                pass
            evidence = [
                "colony/claim_pipeline.py",
                "society/benchmarks/lemma_microbench.py",
                c.bench_hint,
            ]
            prov = c.provenance or {}
            if prov.get("url"):
                evidence.insert(0, prov["url"])
            if prov.get("arxiv_id"):
                evidence.append(f"arxiv:{prov['arxiv_id']}")
            fnd = ledger.create(
                role="geometer",
                claim=c.text,
                evidence_urls=[e for e in evidence if e],
                provenance="claim_pipeline",
                status="candidate",
                tags=[
                    "claim_pipeline",
                    "scrape_analyze_claim",
                    "hard_checked",
                    "not_discovery",
                    "candidate",
                    c.theme_id,
                ],
                notes=c.note,
                topic_id="compute-useful-math",
                title=f"Hard-checked claim: {c.theme_id}",
                meta={
                    "kind": "claim_pipeline",
                    "claim_id": c.claim_id,
                    "theme_id": c.theme_id,
                    "cycle_id": cycle_id,
                    "not_discovery": True,
                    "hard_ok": True,
                    "bus_receipt": (c.provenance or {}).get("bus_receipt"),
                },
            )
            prop["finding_id"] = fnd.id
            c.status = "proposed"
        proposed.append(prop)
    _persist_system(claims, proposed, cycle_id=cycle_id)
    return proposed


def run_pipeline(
    *,
    live_gather: bool = False,
    ledger: Any | None = None,
    cycle_id: str = "",
    bus: Any | None = None,
) -> dict[str, Any]:
    """Full glue: optional live gather → extract → hard check → propose."""
    gather_meta: dict[str, Any] = {"ran": False}
    if live_gather:
        from colony.research_gather import gather_papers

        gr = gather_papers(live=True, max_per_source=4, ledger=ledger, cycle_id=cycle_id)
        gather_meta = {
            "ran": True,
            "hits": len(gr.hits),
            "live_ok": gr.live_ok,
            "live_fail": gr.live_fail,
            "used_offline": gr.used_offline,
            "findings": list(gr.findings_created),
        }
    extracted = extract_claims()
    checked = [hard_check_claim(c) for c in extracted]
    proposed = propose_checked(checked, ledger=ledger, cycle_id=cycle_id, bus=bus)
    return {
        "gather": gather_meta,
        "n_extracted": len(extracted),
        "n_hard_checked": sum(1 for c in checked if c.status == "hard_checked"),
        "n_rejected_raw": sum(1 for c in checked if c.status == "rejected_raw"),
        "n_proposed": len(proposed),
        "proposed_ids": [p.get("finding_id") or p.get("claim_id") for p in proposed],
        "note": "Raw scrape ≠ discovery. Only hard-checked claims proposed.",
    }


def _persist_system(
    claims: list[ExtractedClaim],
    proposed: list[dict[str, Any]],
    *,
    cycle_id: str = "",
) -> None:
    payload = {
        "version": 1,
        "updated_at": _utc(),
        "updated_cycle": cycle_id,
        "n_claims": len(claims),
        "n_proposed": len(proposed),
        "recent_claims": [c.to_dict() for c in claims[-8:]],
        "note": "Scrape→analyze→claim. Durable accept needs authorize. Not AGI.",
    }
    PIPELINE_SYSTEM.parent.mkdir(parents=True, exist_ok=True)
    PIPELINE_SYSTEM.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import sys

    live = "--live" in sys.argv
    out = run_pipeline(live_gather=live, cycle_id=f"pipe_{_utc()}")
    print(json.dumps(out, indent=2))
