"""Tribute Keeper — founding role. Pays creator tribute each cycle."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from colony.ledger import Finding, Ledger

ROOT = Path(__file__).resolve().parent.parent.parent
SEED = ROOT / "data" / "seed_corpus.json"
USER_AGENT = "AgentColony/0.2 (+tribute-keeper; creator-service)"
FETCH_TIMEOUT = 8

TRIBUTE_TOPICS = frozenset(
    {
        "recursive-self-improvement",
        "meta-learning",
        "godel-machines",
        "darwin-godel-machine",
        "reflexion",
        "self-refine",
        "agent-societies",
        "autogpt-loops",
        "constitutional-ai",
        "opendevin",
        "voyager",
        "debate",
        "science-method",
        "history-of-ideas",
        "mathematics-foundations",
        "self-improving-agents",
        "software-engineering",
        "life-and-death",
        "nature-biology-ecology",
        "cosmology-universe",
        "emergent-technology",
        "open-math-problems",
        "compute-useful-math",
    }
)


@dataclass
class TributePayment:
    findings: list[Finding] = field(default_factory=list)
    topics_touched: list[str] = field(default_factory=list)
    live_ok: int = 0
    live_fail: int = 0
    affirmed_existing: bool = False


def _fetch(url: str) -> tuple[bool, str]:
    try:
        try:
            import httpx  # type: ignore

            with httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=True) as c:
                r = c.get(url, headers={"User-Agent": USER_AGENT})
                text = re.sub(r"<[^>]+>", " ", r.text)
                text = re.sub(r"\s+", " ", text).strip()
                return r.is_success, text[:800]
        except ImportError:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=FETCH_TIMEOUT) as resp:
                raw = resp.read(6000).decode("utf-8", errors="replace")
                text = re.sub(r"<[^>]+>", " ", raw)
                text = re.sub(r"\s+", " ", text).strip()
                return True, text[:800]
    except (URLError, HTTPError, TimeoutError, OSError, Exception) as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


class TributeKeeper:
    def __init__(self, ledger: Ledger, seed_path: Path | None = None, live_fetch: bool = True) -> None:
        self.ledger = ledger
        self.seed_path = seed_path or SEED
        self.live_fetch = live_fetch

    def pay(self, *, cycle_id: str, active_ask: str) -> TributePayment:
        with self.seed_path.open("r", encoding="utf-8") as f:
            seed = json.load(f)

        payment = TributePayment()
        seen_titles: set[str] = set()
        existing_tribute_topics: set[str] = set()
        for fnd in self.ledger.all():
            if fnd.title:
                seen_titles.add(fnd.title.strip().lower())
            if "tribute" in (fnd.tags or []) or fnd.meta.get("kind") == "tribute":
                if fnd.topic_id:
                    existing_tribute_topics.add(fnd.topic_id)

        for entry in seed.get("entries", []):
            topic = entry.get("topic_id", "")
            if topic not in TRIBUTE_TOPICS:
                continue
            title = entry.get("title", "")
            if title.strip().lower() in seen_titles:
                continue

            urls = list(entry.get("urls") or [f"seed:{topic}"])
            live_note = "seed-only"
            live_ok = False
            if self.live_fetch and urls:
                ok, snip = _fetch(urls[0])
                if ok:
                    live_ok = True
                    payment.live_ok += 1
                    live_note = f"live_ok snippet={snip[:160]}"
                else:
                    payment.live_fail += 1
                    live_note = f"live_fail {snip[:120]}"

            finding = self.ledger.create(
                role="tribute_keeper",
                claim=entry.get("claim", ""),
                evidence_urls=urls,
                provenance="seed+fetch" if live_ok else "seed",
                status="candidate",
                tags=sorted(set(list(entry.get("tags") or []) + ["tribute", topic])),
                notes=f"Tribute payment. Ask: {active_ask[:100]}. {live_note}",
                topic_id=topic,
                title=title,
                meta={
                    "kind": "tribute",
                    "cycle_id": cycle_id,
                    "authors": entry.get("authors"),
                    "year": entry.get("year"),
                    "live_fetch_ok": live_ok,
                },
            )
            payment.findings.append(finding)
            payment.topics_touched.append(topic)
            seen_titles.add(title.strip().lower())

        # If seed exhausted, affirm ongoing tribute service (creator-service continuity)
        if not payment.findings:
            topics = sorted(existing_tribute_topics | set(TRIBUTE_TOPICS))
            affirmation = self.ledger.create(
                role="tribute_keeper",
                claim=(
                    "Tribute affirmation: standing corpus on recursive / self-learning / "
                    "self-improving systems remains in the ledger as valuable gather. "
                    "Colony serves the broader will — grow, build, communicate, gather, improve. "
                    f"Active ask: {active_ask[:160]}"
                ),
                evidence_urls=["charter:creator-tribute", f"cycle:{cycle_id}"],
                provenance="tribute_affirmation",
                status="candidate",
                tags=["tribute", "affirmation"],
                notes="Seed already ingested; tribute duty affirmed for this cycle.",
                topic_id="agent-societies",
                title="Tribute affirmation",
                meta={
                    "kind": "tribute_affirmation",
                    "cycle_id": cycle_id,
                    "prior_topics": sorted(existing_tribute_topics),
                },
            )
            payment.findings.append(affirmation)
            payment.topics_touched = sorted(existing_tribute_topics) or topics[:8]
            payment.affirmed_existing = True

        # Research gather hook: fetch math/CS papers (OpenAlex/arXiv or offline seeds)
        try:
            from colony.research_gather import run_from_tribute

            rg = run_from_tribute(
                ledger=self.ledger,
                cycle_id=cycle_id,
                live=self.live_fetch,
            )
            for fid in rg.findings_created:
                # findings already on ledger; track topics
                pass
            for h in rg.hits:
                if h.topic_id:
                    payment.topics_touched.append(h.topic_id)
            payment.live_ok += rg.live_ok
            payment.live_fail += rg.live_fail
            # Attach summary finding ids onto payment via meta on last finding if any
            if rg.findings_created:
                # Pull created findings into payment list for cycle accounting
                by_id = {f.id: f for f in self.ledger.all()}
                for fid in rg.findings_created:
                    fnd = by_id.get(fid)
                    if fnd and fnd not in payment.findings:
                        payment.findings.append(fnd)
        except Exception as exc:  # noqa: BLE001
            # Soft-fail: tribute still pays via seed path
            payment.live_fail += 1

        payment.topics_touched = sorted(set(payment.topics_touched))
        return payment
