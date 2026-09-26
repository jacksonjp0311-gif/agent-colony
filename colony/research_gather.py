"""Research gather — fetch recent math/CS papers via OpenAlex and/or arXiv.

Honest frame: primary = paper metadata + abstracts (pointers). Never claim
Millennium problems solved. Durable discovered requires machine-check + human authorize.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "research_cache"
FINDINGS_CACHE = CACHE_DIR / "papers.jsonl"
SEED_PAPERS = CACHE_DIR / "offline_seeds.json"
USER_AGENT = "AgentColony/0.3 (+research-gather; math/CS education; not-AGI)"
FETCH_TIMEOUT = 12

_FALLBACK = [
    {"source": "offline_seed", "arxiv_id": "1706.03762", "doi": "10.48550/arXiv.1706.03762",
     "title": "Attention Is All You Need", "authors": ["Vaswani et al."], "year": 2017,
     "abstract_snippet": "Transformer architecture based solely on attention mechanisms.",
     "url": "https://arxiv.org/abs/1706.03762",
     "tags": ["compute-useful-math", "open-math"], "topic_id": "compute-useful-math"},
    {"source": "offline_seed", "arxiv_id": "cs/0309048", "doi": "",
     "title": "Godel Machines: Fully Self-Referential Optimal Universal Self-Improvers",
     "authors": ["Schmidhuber"], "year": 2003,
     "abstract_snippet": "Mathematically rigorous self-referential self-improving problem solvers.",
     "url": "https://arxiv.org/abs/cs/0309048",
     "tags": ["open-math", "recursive-self-improvement"], "topic_id": "godel-machines"},
    {"source": "offline_seed", "arxiv_id": "1412.6980", "doi": "10.48550/arXiv.1412.6980",
     "title": "Adam: A Method for Stochastic Optimization", "authors": ["Kingma", "Ba"], "year": 2014,
     "abstract_snippet": "First-order gradient-based optimization with adaptive moment estimates.",
     "url": "https://arxiv.org/abs/1412.6980",
     "tags": ["compute-useful-math", "open-math"], "topic_id": "compute-useful-math"},
]
OFFLINE_SEED_ENTRIES = list(_FALLBACK)

def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _http_get(url: str, *, accept: str = "application/json") -> tuple[bool, str]:
    try:
        try:
            import httpx
            with httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=True) as c:
                r = c.get(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
                return r.is_success, r.text
        except ImportError:
            req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
            with urlopen(req, timeout=FETCH_TIMEOUT) as resp:
                return True, resp.read(500_000).decode("utf-8", errors="replace")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

def _snip(text: str, n: int = 400) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()[:n]

@dataclass
class PaperHit:
    source: str
    title: str
    abstract_snippet: str
    url: str
    arxiv_id: str = ""
    doi: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    tags: list[str] = field(default_factory=list)
    topic_id: str = "compute-useful-math"
    raw: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "title": self.title, "abstract_snippet": self.abstract_snippet,
                "url": self.url, "arxiv_id": self.arxiv_id, "doi": self.doi, "authors": self.authors,
                "year": self.year, "tags": self.tags, "topic_id": self.topic_id, "fetched_at": _utc()}

def fetch_arxiv(*, query: str = "cat:math.CO OR cat:cs.DS OR cat:cs.LG OR cat:math.NT", max_results: int = 8) -> list[PaperHit]:
    params = urlencode({"search_query": query, "start": 0, "max_results": max_results,
                        "sortBy": "submittedDate", "sortOrder": "descending"})
    ok, body = _http_get(f"http://export.arxiv.org/api/query?{params}", accept="application/atom+xml")
    if not ok:
        return []
    hits: list[PaperHit] = []
    for ent in re.split(r"<entry>", body)[1:]:
        title_m = re.search(r"<title>(.*?)</title>", ent, re.S)
        summary_m = re.search(r"<summary>(.*?)</summary>", ent, re.S)
        id_m = re.search(r"<id>(.*?)</id>", ent, re.S)
        published_m = re.search(r"<published>(\d{4})", ent)
        authors = re.findall(r"<name>(.*?)</name>", ent)
        title = _snip(re.sub(r"\s+", " ", title_m.group(1) if title_m else ""), 200)
        abstract = _snip(summary_m.group(1) if summary_m else "", 400)
        entry_id = (id_m.group(1) if id_m else "").strip()
        arxiv_id = ""
        if "arxiv.org" in entry_id:
            arxiv_id = re.sub(r"v\d+$", "", entry_id.rstrip("/").split("/")[-1])
        if not title:
            continue
        hits.append(PaperHit(source="arxiv", title=title, abstract_snippet=abstract,
            url=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else entry_id, arxiv_id=arxiv_id,
            authors=[a.strip() for a in authors[:6]], year=int(published_m.group(1)) if published_m else None,
            tags=["compute-useful-math", "open-math", "arxiv", "research_gather"], topic_id="compute-useful-math"))
    return hits

def fetch_openalex(*, search: str = "mathematical lemma OR computational complexity", per_page: int = 8) -> list[PaperHit]:
    params = urlencode({"search": search, "filter": "type:article,from_publication_date:2020-01-01",
                        "per_page": per_page, "sort": "publication_date:desc", "mailto": "agent-colony@example.invalid"})
    ok, body = _http_get(f"https://api.openalex.org/works?{params}")
    if not ok:
        return []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []
    hits: list[PaperHit] = []
    for w in data.get("results") or []:
        title = _snip(w.get("display_name") or w.get("title") or "", 200)
        if not title:
            continue
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        land = next((loc.get("landing_page_url") for loc in (w.get("locations") or []) if loc.get("landing_page_url")), "") or ""
        authors = [a for a in ((a.get("author") or {}).get("display_name") for a in (w.get("authorships") or [])[:6]) if a]
        year = w.get("publication_year")
        hits.append(PaperHit(source="openalex", title=title, abstract_snippet=_snip(str(w.get("type") or ""), 80),
            url=land or (f"https://doi.org/{doi}" if doi else (w.get("id") or "")), doi=doi, authors=authors,
            year=int(year) if year else None, tags=["compute-useful-math", "open-math", "openalex", "research_gather"],
            topic_id="compute-useful-math"))
    return hits

def load_offline_seeds() -> list[PaperHit]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    entries = OFFLINE_SEED_ENTRIES
    if SEED_PAPERS.exists():
        try:
            entries = json.loads(SEED_PAPERS.read_text(encoding="utf-8"))
        except Exception:
            pass
    else:
        SEED_PAPERS.write_text(json.dumps(OFFLINE_SEED_ENTRIES, indent=2) + "\n", encoding="utf-8")
    return [PaperHit(source=e.get("source") or "offline_seed", title=e.get("title") or "",
        abstract_snippet=e.get("abstract_snippet") or "", url=e.get("url") or "",
        arxiv_id=e.get("arxiv_id") or "", doi=e.get("doi") or "", authors=list(e.get("authors") or []),
        year=e.get("year"), tags=list(e.get("tags") or ["compute-useful-math", "open-math"]),
        topic_id=e.get("topic_id") or "compute-useful-math") for e in entries]

def append_cache(hits: list[PaperHit]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with FINDINGS_CACHE.open("a", encoding="utf-8") as f:
        for h in hits:
            f.write(json.dumps(h.to_dict(), ensure_ascii=False) + "\n")

def cached_count() -> int:
    if not FINDINGS_CACHE.exists():
        return 0
    return sum(1 for ln in FINDINGS_CACHE.read_text(encoding="utf-8").splitlines() if ln.strip())

@dataclass
class GatherResult:
    hits: list[PaperHit] = field(default_factory=list)
    live_ok: int = 0
    live_fail: int = 0
    used_offline: bool = False
    findings_created: list[str] = field(default_factory=list)

def gather_papers(*, live: bool = True, max_per_source: int = 6, ledger: Any | None = None,
                  cycle_id: str = "", role: str = "tribute_keeper") -> GatherResult:
    result = GatherResult()
    hits: list[PaperHit] = []
    if live:
        arxiv = fetch_arxiv(max_results=max_per_source)
        if arxiv:
            result.live_ok += 1; hits.extend(arxiv)
        else:
            result.live_fail += 1
        oa = fetch_openalex(per_page=max_per_source)
        if oa:
            result.live_ok += 1; hits.extend(oa)
        else:
            result.live_fail += 1
    if not hits:
        hits = load_offline_seeds(); result.used_offline = True
    seen: set[str] = set(); uniq: list[PaperHit] = []
    for h in hits:
        key = h.title.strip().lower()
        if not key or key in seen: continue
        seen.add(key); uniq.append(h)
    result.hits = uniq; append_cache(uniq)
    if ledger is not None:
        existing: set[str] = set()
        for f in ledger.all():
            if "research_gather" in (f.tags or []) or (f.meta or {}).get("kind") == "research_paper":
                t = (f.title or "").strip().lower(); existing.add(t)
                if t.startswith("paper: "): existing.add(t[len("paper: "):])
                if (f.meta or {}).get("arxiv_id"): existing.add(f"arxiv:{(f.meta or {}).get('arxiv_id')}".lower())
                if (f.meta or {}).get("doi"): existing.add(f"doi:{(f.meta or {}).get('doi')}".lower())
        for h in uniq:
            keys = {h.title.strip().lower(), f"paper: {h.title.strip().lower()}"}
            if h.arxiv_id: keys.add(f"arxiv:{h.arxiv_id}".lower())
            if h.doi: keys.add(f"doi:{h.doi}".lower())
            if keys & existing: continue
            ids = "; ".join([x for x in ([f"arXiv:{h.arxiv_id}"] if h.arxiv_id else []) + ([f"DOI:{h.doi}"] if h.doi else [])]) or "no-id"
            claim = (f"PAPER POINTER (not a discovery claim): {h.title}. Ids={ids}. "
                     f"Abstract: {h.abstract_snippet[:240]} — sourced via {h.source}. "
                     f"Durable discovered requires machine-check + human authorize. Never claim Millennium solved.")
            tags = sorted(set(list(h.tags) + ["research_gather", "paper", "compute-useful-math", "open-math", "tribute"]))
            fnd = ledger.create(role=role or "tribute_keeper", claim=claim,
                evidence_urls=[u for u in [h.url, f"arxiv:{h.arxiv_id}" if h.arxiv_id else "", f"doi:{h.doi}" if h.doi else ""] if u],
                provenance=f"research_gather:{h.source}", status="candidate", tags=tags,
                notes=f"Research gather cycle={cycle_id}. Pointer only.", topic_id=h.topic_id,
                title=f"Paper: {h.title[:100]}",
                meta={"kind": "research_paper", "cycle_id": cycle_id, "arxiv_id": h.arxiv_id, "doi": h.doi,
                      "source": h.source, "year": h.year, "authors": h.authors, "not_discovery": True})
            result.findings_created.append(fnd.id); existing.add(h.title.strip().lower())
    return result

def run_from_tribute(*, ledger: Any, cycle_id: str, live: bool = True) -> GatherResult:
    return gather_papers(live=live, max_per_source=5, ledger=ledger, cycle_id=cycle_id, role="tribute_keeper")

if __name__ == "__main__":
    import sys
    live = "--offline" not in sys.argv
    r = gather_papers(live=live, max_per_source=4)
    print(json.dumps({"count": len(r.hits), "live_ok": r.live_ok, "live_fail": r.live_fail,
                      "used_offline": r.used_offline, "titles": [h.title for h in r.hits[:8]],
                      "cached_total": cached_count()}, indent=2))
