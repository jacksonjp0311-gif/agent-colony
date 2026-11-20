"""Self-refilling target supply (item 82).

The colony ran out of work: 0 of 64 OEIS conjecture targets open, 0 of 17
new-data entries open and the authored-check list full. This stage keeps
the OEIS target list stocked without a human rerunning
``tools/build_oeis_conjectures.py``.

* **Trigger.** Each treatment cycle counts open OEIS targets (what the
  colony's own chooser would still attempt). Below ``OPEN_MIN`` it runs one
  refill, at most once per ``COOLDOWN_CYCLES``.
* **Refill.** It walks a fixed, widened bank of public OEIS JSON searches
  (new query and topic combinations; OEIS serves only the first 100
  anonymous results, so later pages of old queries add nothing) with a cursor
  so every refill reads pages it has not read before. Pages whose topic
  words show up in the knowledge library (item 79) go first. Hits go
  through the builder's unchanged vetting: resolved / bad-keyword entries
  are skipped, the statement must parse, the b-file must agree with DATA,
  the claim must hold on DATA, and a NAME definition is kept only if it
  reproduces the whole b-file. Polite: cache first, >= 2 s between
  requests, at most ``REQUEST_BUDGET`` requests per refill, fail-soft.
  Fetched text is parsed as JSON / b-file numbers only; nothing fetched is
  ever executed.
* **Dedupe.** A-numbers already on the menu, already rejected by the
  vetting, or retired as compute_bound by self-heal are never added again.
* **Log.** Every added target is one row in the append-only
  ``data/commons/target_supply.jsonl``. The menu itself only grows.
* **Fair twin.** Target supply is the environment, not a self-change, so
  both arms get the *same* targets at the *same* time. Only the treatment
  job fetches; both arms copy entries from the shared supply log into their
  own menu, and only entries logged by an *earlier* run (the control job
  runs in parallel and cannot see the current run's rows). A lead over the
  control therefore cannot come from extra supply.

* **Pace (item 121, ``COLONY_SUPPLY_PACE``, shared environment).** Live refills read bank v2
  at 8 pages per run while the dry run read all 504 at once; the first 168 v2 pages are the
  low-yield relation family (8 targets), so the high-yield pages were ~20 runs away. Now: a page
  after a short page (< 10 hits; OEIS repeats it) is marked read with no request; each page is
  vetted right after it is read, so no hit past ``MAX_NEW`` is dropped; a starved menu (0 open)
  reads up to ``STARVED_PAGES``; all supply requests in one run share ``RUN_REQUEST_CAP``.

* **Bank v2 (item 118).** The first bank (640 pages) was exhausted on
  2026-11-18. ``COLONY_SUPPLY_BANK_V2`` (live by default, on *both* arms,
  because supply is environment) appends relation-form and name-definition
  query families; old page keys are unchanged, so nothing is re-read.

Nothing here touches the Oracle, the P >= 0.70 gate, the 150 authored-check
cap, Athanor math, Hive's Wilson gate, the 6-cycle windows, strictly-better
or the triviality filter, and it authorizes nothing.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
# Shared between arms on purpose (see "Fair twin"): os.path.join bypasses the
# control-arm Path hook, which would otherwise redirect it under control/.
SUPPLY_LOG = Path(os.path.join(os.fspath(ROOT), "data", "commons", "target_supply.jsonl"))
STATE_PATH = Path(os.path.join(os.fspath(ROOT), "society", "systems", "target_supply.json"))
LIBRARY_PATH = Path(os.path.join(os.fspath(ROOT), "data", "commons", "knowledge_library.jsonl"))
TOOL_PATH = ROOT / "tools" / "build_oeis_conjectures.py"

OPEN_MIN = 8               # refill when fewer open OEIS targets than this
COOLDOWN_CYCLES = 3        # at most one refill per run of 3 cycles
REQUEST_BUDGET = 40        # network requests per refill (>= 2 s apart)
PAGES_PER_REFILL = 8       # search pages read per refill
MAX_NEW = 10               # targets added per refill
PAGE_SIZE = 10             # OEIS JSON search hits per page
STARVED_PAGES = 24         # item 121: pages per refill when no OEIS target is open
STARVED_REQUEST_BUDGET = 64  # item 121: requests per starved refill (still >= 2 s apart)
RUN_REQUEST_CAP = 120      # item 121: all supply requests in one workflow run (politeness ceiling)
SUPPLY_MAX_TERMS = 500     # stored published terms per added target (published_hi keeps the real range)

# New topics beyond the builder's TOPICS (combinatorics / number theory, the
# item-79 mathematics fields).
WIDE_TOPICS = ("catalan", "fibonacci", "lattice", "permutations", "triangular", "polynomial", "pell",
               "motzkin", "binomial", "convolution", "walks", "paths", "trees", "compositions", "sigma",
               "totient", "palindromes", "squares", "factorial", "bell", "stirling", "lucas", "narayana",
               "dyck", "necklaces", "graphs", "tilings", "continued")


def _tool() -> Any:
    spec = importlib.util.spec_from_file_location("colony_build_oeis_conjectures", TOOL_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # our own repo file, not fetched code
    return mod


def _arm() -> str:
    try:
        from colony.arm import arm
        return arm()
    except Exception:
        return "treatment"


def _run_id() -> str:
    return os.environ.get("GITHUB_RUN_ID") or ""


# --------------------------------------------------------------------------- state / log

def _load_json(path: Path, default: Any) -> Any:
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def load_state(path: Path | None = None) -> dict[str, Any]:
    st = _load_json(Path(path or STATE_PATH), None)
    base = {"version": 1, "cycle_index": 0, "last_refill_index": None, "done_pages": {},
            "rejected": {}, "refills": 0, "added": 0, "last": None}
    if isinstance(st, dict):
        base.update(st)
    return base


def save_state(st: dict[str, Any], path: Path | None = None) -> None:
    p = Path(path or STATE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def load_log(path: Path | None = None) -> list[dict[str, Any]]:
    p = Path(path or SUPPLY_LOG)
    out: list[dict[str, Any]] = []
    try:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
    except Exception:
        pass
    return out


def append_log(row: dict[str, Any], path: Path | None = None) -> None:
    p = Path(path or SUPPLY_LOG)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


# --------------------------------------------------------------------------- query bank

# Item 118: the first bank (640 pages) was fully read on 2026-11-18. Bank v2 adds
# new query families, appended after the old pages so every old key is unchanged:
#  * "rel": relation-form conjectures that tie a(n) to another OEIS entry
#    ("Conjecture: a(n) = A...") -- both sides are published, independent data;
#  * "name": conjectures on entries whose NAME is a definition the item-105 parser
#    can evaluate (Sum / Product / "Number of" / "a(n) =") -- the route to an
#    independent definition, which item 113 now requires for beyond-published depth.
# Same vetting, same shared log, same fair-twin sync (both arms adopt the same rows).
V2_TOPICS = ("semiprimes", "powers", "triangular", "fibonacci", "catalan", "binomial", "primes", "divisors",
             "partitions", "digits", "sigma", "totient", "squares", "cubes", "factorial", "lattice", "paths",
             "permutations", "compositions", "words", "trees", "graphs", "polyominoes", "necklaces",
             "continued", "pell", "lucas", "motzkin", "narayana", "stirling", "bell", "dyck", "walks",
             "convolution", "recurrence", "congruence", "mod", "sum", "binary", "odd", "squarefree", "palindromes")
V2_FORMS = (
    ("rel", 'formula:"Conjecture: a(n) = A" {t}'),
    ("rel", 'comment:"Conjecture: a(n) = A" {t}'),
    ("name", 'formula:Conjecture name:"a(n) = Sum" {t}'),
    ("name", 'formula:Conjecture name:"Number of" {t}'),
    ("name", 'comment:Conjecture name:"Number of" {t}'),
    ("name", 'formula:Conjecture name:Product {t}'),
)
KIND_RANK = {"def": 0, "rel": 1, "name": 2, "plain": 3}


def query_bank_v2() -> list[dict[str, Any]]:
    bank: list[dict[str, Any]] = []
    for kind, form in V2_FORMS:
        for t in V2_TOPICS:
            for page in range(2):
                bank.append({"q": form.format(t=t) + " -keyword:tabl -keyword:dead", "page": page,
                             "kind": kind, "topic": t, "bank": 2})
    return bank


def query_bank(tool: Any) -> list[dict[str, Any]]:
    """Fixed, ordered list of (query, page) the refill walks. Computable first.

    OEIS shows anonymous searches only up to result 100 (pages 0-9), so the
    bank widens with new query/topic combinations, never with later pages.
    """
    bank: list[dict[str, Any]] = []
    topics = tuple(WIDE_TOPICS) + tuple(t for t in tool.TOPICS if t not in WIDE_TOPICS)
    def_forms = ('formula:Conjecture name:"Expansion of" {t}', 'formula:"Conjecture: D-finite" {t}',
                 'comment:Conjecture name:"a(n) =" {t}', 'formula:Conjecture name:"a(n) =" {t}',
                 'formula:Conjecture name:"G.f." {t}')
    for t in topics:
        for form in def_forms:
            for page in range(2):
                bank.append({"q": form.format(t=t) + " -keyword:tabl -keyword:dead", "page": page,
                             "kind": "def", "topic": t})
    for t in topics:
        old = t in tool.TOPICS
        for f in ("formula", "comment"):
            for page in (range(tool.PAGES, min(10, tool.PAGES + 3)) if old else range(3)):
                bank.append({"q": f"{f}:Conjecture keyword:nonn -keyword:core -keyword:nice -keyword:tabl "
                                  f"-keyword:cons {t}", "page": page, "kind": "plain", "topic": t})
    if (os.environ.get("COLONY_SUPPLY_BANK_V2") or "live").strip().lower() != "off":
        bank.extend(query_bank_v2())   # item 118: appended; old keys and order unchanged
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for b in bank:
        b["key"] = hashlib.sha256(f"{b['q']}|{b['page']}".encode()).hexdigest()[:16]
        if b["key"] not in seen:
            seen.add(b["key"])
            out.append(b)
    return out


def relevance(library_rows: Iterable[dict[str, Any]] | None = None) -> dict[str, int]:
    """Topic word -> number of knowledge-library papers that mention it (item 79). Cheap."""
    rows = list(library_rows) if library_rows is not None else load_log(LIBRARY_PATH)
    text = " ".join(str(r.get("title") or "") + " " + str(r.get("summary") or "")
                    for r in rows if r.get("event") == "paper").lower()
    return {t: text.count(t) for t in WIDE_TOPICS if text.count(t)}


def pending_pages(bank: list[dict[str, Any]], st: dict[str, Any], rel: dict[str, int]) -> list[dict[str, Any]]:
    done = st.get("done_pages") or {}
    todo = [(i, b) for i, b in enumerate(bank) if b["key"] not in done]
    todo.sort(key=lambda ib: (KIND_RANK.get(ib[1]["kind"], 3), -rel.get(ib[1]["topic"], 0), ib[0]))
    return [b for _, b in todo]


# --------------------------------------------------------------------------- open count / dedupe

def open_count(cycle_id: str = "supply", oc: Any = None) -> int:
    """Targets the colony's own OEIS chooser would still attempt now."""
    try:
        oc = oc or __import__("colony.oeis_conjectures", fromlist=["x"])
        menu = oc.load_menu() or []
        state = oc._load(oc.STATE, {"targets": {}, "families": {}})
        return len(oc.choose(menu, state, cycle_id, k=max(1, len(menu))) or [])
    except Exception:
        return 0


def known_anums(menu: list[dict[str, Any]], st: dict[str, Any], heal: dict[str, Any] | None = None) -> set[str]:
    out = {str(e.get("anum")) for e in menu if e.get("anum")}
    out |= set((st.get("rejected") or {}).keys())
    for tid in ((heal or {}).get("compute_bound_targets") or {}):
        parts = str(tid).split("_")
        if len(parts) >= 2:
            out.add(parts[1])
    return out


class BudgetNet:
    """The new-data polite fetcher with this refill's own request budget."""

    def __init__(self, budget: int = REQUEST_BUDGET, net: Any = None):
        from colony import new_data as N
        self._N = N
        self.net = net or N.Net()
        self.budget = int(budget)

    @property
    def n(self) -> int:
        return int(getattr(self.net, "n", 0))

    def exhausted(self) -> bool:
        return self.n >= self.budget

    def get(self, url: str, name: str) -> str | None:
        N = self._N
        old = N.NET_MAX_PER_CYCLE
        N.NET_MAX_PER_CYCLE = self.budget
        try:
            return self.net.get(url, name)
        finally:
            N.NET_MAX_PER_CYCLE = old


# --------------------------------------------------------------------------- refill / sync

def _trim(ent: dict[str, Any]) -> dict[str, Any]:
    """Keep the log and both menus small: store at most SUPPLY_MAX_TERMS published terms.

    ``bfile_hi_of`` reads ``published_hi``, so a shorter stored prefix never
    makes published terms count as new (41 of the 64 built entries already
    store fewer terms than were published)."""
    terms = list(ent.get("terms") or [])
    if len(terms) > SUPPLY_MAX_TERMS:
        ent["terms"] = terms[:SUPPLY_MAX_TERMS]
    refs = {}
    for r, v in (ent.get("refs") or {}).items():
        v = dict(v)
        v["terms"] = list(v.get("terms") or [])[:SUPPLY_MAX_TERMS + 12]
        refs[r] = v
    ent["refs"] = refs
    return ent


def _cached(name: str) -> bool:
    try:
        from colony import new_data as N
        return (N._cache_dir() / name).exists()
    except Exception:
        return False


def pace_live() -> bool:
    """Item 121: ``COLONY_SUPPLY_PACE`` = live (default) | off. Supply is environment, so this is
    shared by both arms (only the treatment job fetches; both adopt the same logged rows)."""
    return (os.environ.get("COLONY_SUPPLY_PACE") or "live").strip().lower() != "off"


def _short_previous_page(b: dict[str, Any], done: dict[str, Any], by_qp: dict[tuple[str, int], str]) -> bool:
    """Page p > 0 whose page p-1 came back short (< PAGE_SIZE hits) is a duplicate.

    Measured on the cached bank-v2 pages (item 121): OEIS clamps ``start`` past the end of a
    short result, so all 142 page-1 reads whose page 0 was short returned exactly page 0's hits."""
    if int(b.get("page") or 0) <= 0:
        return False
    prev = by_qp.get((b["q"], int(b["page"]) - 1))
    row = done.get(prev) if prev else None
    return isinstance(row, dict) and int(row.get("n_hits") or 0) < PAGE_SIZE


def refill(cycle_id: str, *, net: Any = None, tool: Any = None, menu: list[dict[str, Any]] | None = None,
           st: dict[str, Any] | None = None, heal: dict[str, Any] | None = None,
           library_rows: list[dict[str, Any]] | None = None, write: bool = True,
           max_new: int = MAX_NEW, pages: int = PAGES_PER_REFILL) -> dict[str, Any]:
    """Read new OEIS search pages and vet new targets. ``write=False`` is a dry run.

    Item 121 (``COLONY_SUPPLY_PACE``): each page is vetted right after it is read and the
    refill stops after the page that reaches ``max_new``, so no hit is left unvetted on a
    page already marked read (before, hits past ``max_new`` were dropped for good). A page
    whose vetting the request budget cut short stays unread (its search result is cached, so
    the retry costs no search request). Duplicate pages after a short page are marked read
    without a request and do not use the page allowance.
    """
    tool = tool or _tool()
    st = st if st is not None else load_state()
    if menu is None:
        from colony import oeis_conjectures as OC
        menu = OC.load_menu() or []
    net = net if net is not None else BudgetNet()
    bank = query_bank(tool)
    todo = pending_pages(bank, st, relevance(library_rows))
    known = known_anums(menu, st, heal)
    paced = pace_live()
    if paced:
        known |= {str(r.get("anum")) for r in load_log() if r.get("event") == "target_added" and r.get("anum")}
    by_qp = {(b["q"], int(b["page"])): b["key"] for b in bank}
    done = st.setdefault("done_pages", {})
    stats = {"entries": 0, "resolved_skipped": 0, "keyword_skipped": 0, "statements": 0, "parsed": 0,
             "no_bfile": 0, "fails_on_data": 0, "kept": 0, "reasons": {}}
    new: list[dict[str, Any]] = []
    per_anum: dict[str, int] = {}
    read: list[dict[str, Any]] = []
    skipped_dup = 0

    def vet(raw: dict[str, dict[str, Any]]) -> bool:
        """Vet one batch of hits; False when the request budget cut it short."""
        stats["entries"] += len(raw)
        for cand in tool.collect_candidates(raw, stats):
            if net.exhausted():
                return False
            if not paced and len(new) >= max_new:
                break
            a = cand[2]
            if a in known or a in {x["anum"] for x in new}:
                continue
            before = net.n
            try:
                ent = tool.make_entry(cand, net, per_anum, stats, verbose=False)
            except Exception:  # noqa: BLE001
                ent = None
            if ent is None:
                # only remember a rejection the vetting made, not one the budget caused
                if not net.exhausted() or net.n == before:
                    st.setdefault("rejected", {})[a] = cycle_id
                    known.add(a)
                continue
            ent = _trim(dict(ent, supply={"cycle_id": cycle_id, "run_id": _run_id()}))
            new.append(ent)
        return True

    if paced:
        for b in todo:
            if len(read) >= pages or len(new) >= max_new or net.exhausted():
                break
            if _short_previous_page(b, done, by_qp):
                done[b["key"]] = {"cycle_id": cycle_id, "n_hits": 0, "skipped": "duplicate_after_short_page"}
                skipped_dup += 1
                continue
            fn = f"ts_{b['key']}.json"
            hits = tool.search_page(net, b["q"], b["page"], fn)
            if not hits and not _cached(fn):
                break  # fetch failed or budget hit: retry this page on a later refill
            raw = {}
            for e in hits:
                a = "A%06d" % int(e["number"])
                if a not in known:
                    raw[a] = e
            if not vet(raw):
                break  # budget ran out mid-page: the page stays unread (search result is cached)
            read.append(b)
            done[b["key"]] = {"cycle_id": cycle_id, "n_hits": len(hits)}
    else:
        raw_all: dict[str, dict[str, Any]] = {}
        for b in todo[:pages]:
            if net.exhausted():
                break
            fn = f"ts_{b['key']}.json"
            hits = tool.search_page(net, b["q"], b["page"], fn)
            if not hits and not _cached(fn):
                break
            read.append(b)
            done[b["key"]] = {"cycle_id": cycle_id, "n_hits": len(hits)}
            for e in hits:
                a = "A%06d" % int(e["number"])
                if a not in known:
                    raw_all[a] = e
        vet(raw_all)
    stats["kept"] = len(new)
    if write:
        for ent in new:
            append_log({"event": "target_added", "cycle_id": cycle_id, "run_id": _run_id(),
                        "anum": ent["anum"], "id": ent["id"], "form": (ent.get("claim") or {}).get("form"),
                        "definition": bool(ent.get("definition")), "entry": ent, "authorized": False})
    return {"pages_read": len(read), "pages_skipped_duplicate": skipped_dup, "requests": net.n, "new": [
        {"id": e["id"], "form": (e.get("claim") or {}).get("form"), "definition": bool(e.get("definition"))}
        for e in new], "stats": {k: v for k, v in stats.items() if k != "reasons"},
        "entries": new}


def refill_size(n_open: int, st: dict[str, Any] | None = None) -> tuple[int, int]:
    """(pages, request budget) for one refill. Item 121: a starved menu (0 open) reads more, and
    every refill in one workflow run shares ``RUN_REQUEST_CAP`` requests."""
    pages, budget = PAGES_PER_REFILL, REQUEST_BUDGET
    if pace_live():
        if n_open <= 0:
            pages, budget = STARVED_PAGES, STARVED_REQUEST_BUDGET
        if st is not None:
            budget = max(0, min(budget, RUN_REQUEST_CAP - run_requests_used(st)))
    return pages, budget


def run_requests_used(st: dict[str, Any]) -> int:
    row = st.get("run_requests") or {}
    rid = _run_id()
    return int(row.get("n") or 0) if rid and row.get("run_id") == rid else 0


def note_run_requests(st: dict[str, Any], n: int) -> None:
    rid = _run_id()
    if not rid:
        return
    st["run_requests"] = {"run_id": rid, "n": run_requests_used(st) + int(n or 0)}


def sync(*, oc: Any = None, rows: list[dict[str, Any]] | None = None, write: bool = True,
         run_id: str | None = None) -> dict[str, Any]:
    """Copy logged targets from earlier runs into this arm's menu (menu only grows)."""
    oc = oc or __import__("colony.oeis_conjectures", fromlist=["x"])
    rows = rows if rows is not None else load_log()
    cur = _run_id() if run_id is None else run_id
    try:
        doc = json.loads(Path(oc.MENU).read_text(encoding="utf-8")) if Path(oc.MENU).exists() else None
    except Exception:
        doc = None
    if not isinstance(doc, dict):
        doc = {"note": "OEIS conjectures as colony targets", "stats": {}, "entries": []}
    have_ids = {str(e.get("id")) for e in doc.get("entries") or []}
    have_anums = {str(e.get("anum")) for e in doc.get("entries") or []}
    added = []
    for r in rows:
        if r.get("event") != "target_added" or not isinstance(r.get("entry"), dict):
            continue
        if cur and str(r.get("run_id") or "") == cur:
            continue  # same run: both arms adopt it next run (control runs in parallel)
        ent = r["entry"]
        if str(ent.get("id")) in have_ids or str(ent.get("anum")) in have_anums:
            continue
        doc.setdefault("entries", []).append(ent)
        have_ids.add(str(ent.get("id")))
        have_anums.add(str(ent.get("anum")))
        added.append(str(ent.get("id")))
    if added and write:
        st = doc.setdefault("stats", {})
        st["supply_added"] = int(st.get("supply_added") or 0) + len(added)
        Path(oc.MENU).parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(oc.MENU) + ".tmp")
        tmp.write_text(json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8")
        os.replace(tmp, Path(oc.MENU))
    return {"added": added, "menu_size": len(doc.get("entries") or [])}


def _heal() -> dict[str, Any]:
    try:
        from colony import self_heal as SH
        return SH.load_state() or {}
    except Exception:
        return {}


def run_cycle(cycle_id: str = "", *, write: bool = True) -> dict[str, Any]:
    """Both arms: adopt earlier-run targets. Treatment only: refill when low."""
    out: dict[str, Any] = {"cycle_id": cycle_id, "arm": _arm()}
    try:
        from colony import oeis_conjectures as OC
        if OC.mode() == "off":
            return {**out, "skipped": "COLONY_OEIS_CONJ=off"}
    except Exception as exc:  # noqa: BLE001
        return {**out, "skipped": f"import:{type(exc).__name__}"}
    try:
        out["sync"] = sync(write=write)
    except Exception as exc:  # noqa: BLE001
        out["sync"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    if out["arm"] != "treatment" or os.environ.get("COLONY_TARGET_SUPPLY", "live").lower() == "off":
        return out
    st = load_state()
    st["cycle_index"] = int(st.get("cycle_index") or 0) + 1
    n_open = open_count(cycle_id or "supply")
    out["open"] = n_open
    last = st.get("last_refill_index")
    cooling = last is not None and st["cycle_index"] - int(last) < COOLDOWN_CYCLES
    if n_open < OPEN_MIN and not cooling:
        try:
            pg, bud = refill_size(n_open, st)
            rep = refill(cycle_id, net=BudgetNet(budget=bud), st=st, heal=_heal(), write=write, pages=pg)
            note_run_requests(st, rep.get("requests") or 0)
            rep.pop("entries", None)
            st["last_refill_index"] = st["cycle_index"]
            st["refills"] = int(st.get("refills") or 0) + 1
            st["added"] = int(st.get("added") or 0) + len(rep.get("new") or [])
            st["last"] = {"cycle_id": cycle_id, "open_before": n_open, **rep}
            out["refill"] = rep
        except Exception as exc:  # noqa: BLE001
            out["refill"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    if write:
        save_state(st)
    return out


def slot_refill(cycle_id: str = "", *, write: bool = True, net: Any = None, tool: Any = None,
                menu: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Item 119: one extra refill for a conjecture-desk turn freed by the learned-family skip.

    Treatment only (the control job never fetches). Ignores ``COOLDOWN_CYCLES``
    but keeps ``OPEN_MIN``, the per-refill request budget, the page order (the
    first bank is read, so this walks bank v2) and the unchanged vetting. At most
    one per cycle. Rows go to the shared supply log, so both arms adopt the new
    targets on their next run (fair twin); nothing is attempted here.
    """
    out: dict[str, Any] = {"cycle_id": cycle_id, "arm": _arm(), "slot": True}
    if out["arm"] != "treatment" or os.environ.get("COLONY_TARGET_SUPPLY", "live").lower() == "off":
        return {**out, "skipped": "not_treatment_or_supply_off"}
    st = load_state()
    if cycle_id and st.get("last_slot_refill_cycle") == cycle_id:
        return {**out, "skipped": "already_this_cycle"}
    n_open = open_count(cycle_id or "supply")
    out["open"] = n_open
    if n_open >= OPEN_MIN:
        return {**out, "skipped": "enough_open"}
    try:
        pg, bud = refill_size(n_open, st)
        if net is None and bud <= 0:
            return {**out, "skipped": "run_request_cap"}
        rep = refill(cycle_id, net=net if net is not None else BudgetNet(budget=bud), tool=tool, menu=menu,
                     st=st, heal=_heal(), write=write, pages=pg)
        note_run_requests(st, rep.get("requests") or 0)
    except Exception as exc:  # noqa: BLE001
        return {**out, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    rep.pop("entries", None)
    st["last_slot_refill_cycle"] = cycle_id
    st["slot_refills"] = int(st.get("slot_refills") or 0) + 1
    st["added"] = int(st.get("added") or 0) + len(rep.get("new") or [])
    if write:
        save_state(st)
    return {**out, **rep}
