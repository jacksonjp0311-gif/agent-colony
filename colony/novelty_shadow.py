"""Novelty SHADOW score against a local OEIS sequence-names corpus — REPORT-ONLY.

Never changes live novelty: ``novelty_gate.textbook_reuse_score`` and its kills are untouched.
``shadow(name, claim_text)`` searches a cached SQLite FTS5 index of OEIS names and logs a shadow
textbook-reuse score with hashed match receipts to ``society/systems/novelty_shadow.json``.

Corpus: OEIS sequence names (https://oeis.org/names.gz), The OEIS Foundation Inc.,
licensed CC BY-SA 4.0 (https://oeis.org/LICENSE). Downloaded at most once per cache key by
``python -m colony.novelty_shadow build`` (a CI step, cache-gated) — never per cycle. If the
index is absent the shadow logs ``corpus_absent`` and does nothing else. Free; no API key.

Flag: ``COLONY_NOVELTY_SHADOW=0`` turns it off. Search approach: simple SQLite FTS5 (BM25), in
the spirit of jacksonjp0311-gif/AgentSearch (local index, receipts), not its code.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "society" / "systems" / "novelty_shadow.json"
CORPUS_URL = "https://oeis.org/names.gz"
CREDIT = "OEIS sequence names, The OEIS Foundation Inc., CC BY-SA 4.0 (https://oeis.org/LICENSE)"
KEEP_ROWS = 60

# check-name tokens -> what the check actually is, in words an OEIS name would use
EXPAND = {
    "sieve": ["primes"], "hl": ["hardy", "littlewood"], "hl_within": ["hardy", "littlewood"],
    "residue_bal": ["primes", "congruent", "mod"], "two_counter": ["primes"],
    "totient": ["totient"], "catalan": ["catalan"],
    "cassini": ["fibonacci"], "vandermonde": ["binomial"], "conv": ["convolution"],
    "binom": ["binomial"], "stirling": ["stirling"], "bell": ["bell"], "derangement": ["derangements"],
    "subfactorial": ["subfactorial"], "pascal": ["binomial"], "geometric": ["powers"],
    "cubes": ["cubes"], "odds": ["odd"], "squares": ["squares"], "fibonacci": ["fibonacci"],
    "lucas": ["lucas"], "partition": ["partitions"], "partitions": ["partitions"],
}
STOP = {"authored", "check", "w1", "w2", "w3", "w4", "the", "of", "and", "a", "in", "is", "for", "to",
        "n", "sum", "first", "row", "small", "bound", "bounded", "identity", "within", "bal", "counter",
        "two", "inversion", "recurrence", "triangle", "symmetry", "oeis", "with", "that", "by", "on"}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cache_dir() -> Path:
    return Path(os.environ.get("COLONY_OEIS_CACHE") or (Path.home() / ".cache" / "colony" / "oeis"))


def db_path() -> Path:
    return cache_dir() / "oeis_names.sqlite"


def build(src_gz: Path | None = None, *, force: bool = False) -> dict[str, Any]:
    """Download names.gz once (unless cached or given) and build the FTS5 index."""
    d = cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    db = db_path()
    if db.exists() and not force:
        return {"built": False, "reason": "cached", "db": str(db)}
    gz = src_gz or d / "names.gz"
    if src_gz is None and not gz.exists():
        req = urllib.request.Request(CORPUS_URL, headers={"User-Agent": "agent-colony novelty-shadow (free, cached)"})
        with urllib.request.urlopen(req, timeout=120) as r, open(gz, "wb") as f:  # noqa: S310
            f.write(r.read())
    raw = gzip.open(gz, "rb").read()
    tmp = db.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.execute("CREATE VIRTUAL TABLE names USING fts5(anum UNINDEXED, name, tokenize='porter unicode61')")
    con.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
    rows = []
    for ln in raw.decode("utf-8", "replace").splitlines():
        if ln.startswith("#") or " " not in ln:
            continue
        a, nm = ln.split(" ", 1)
        rows.append((a, nm))
    con.executemany("INSERT INTO names VALUES (?, ?)", rows)
    meta = {"source": CORPUS_URL, "credit": CREDIT, "sha256": hashlib.sha256(raw).hexdigest(),
            "n_names": str(len(rows)), "built_at": _utc()}
    con.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
    con.commit()
    con.close()
    tmp.replace(db)
    return {"built": True, "db": str(db), **meta}


def query_terms(name: str, claim_text: str = "") -> list[str]:
    toks = re.split(r"[^a-z0-9]+", f"{name}".lower().replace("__", "_"))
    joined = name.lower()
    terms: list[str] = []
    gm = re.search(r"_g(\d+(?:_\d+)*)_w\d+$", joined)
    if gm:  # sieve gap pattern: single gap -> its prime-pair name, longer -> constellation size
        gaps = gm.group(1).split("_")
        if len(gaps) == 1:
            terms += [{"2": "twin", "4": "cousin", "6": "sexy"}.get(gaps[0], "gap")]
        else:
            terms += [{2: "triplets", 3: "quadruplets"}.get(len(gaps), "constellations")]
    for key in sorted(EXPAND, key=len, reverse=True):
        if re.search(rf"(^|_){re.escape(key)}(_|$)", joined):
            terms += EXPAND[key]
    for t in toks + re.split(r"[^a-z]+", (claim_text or "").lower())[:40]:
        if t and t not in STOP and len(t) > 2 and not re.fullmatch(r"[gw]?\d+|a\d{6}", t) and t not in EXPAND:
            terms.append(t)
    out: list[str] = []
    for t in terms:
        if t not in out:
            out.append(t)
    return out[:12]


def _stem(w: str) -> str:
    return re.sub(r"(ies|es|s)$", "", w)


def shadow_score(name: str, claim_text: str = "", *, db: Path | None = None, k: int = 5) -> dict[str, Any]:
    dbp = db or db_path()
    if not dbp.exists():
        return {"status": "corpus_absent"}
    terms = query_terms(name, claim_text)
    if not terms:
        return {"status": "no_terms", "shadow_textbook_reuse": 0.0, "terms": []}
    con = sqlite3.connect(f"file:{dbp}?mode=ro", uri=True)
    try:
        q = " OR ".join('"' + t.replace('"', "") + '"' for t in terms)
        hits = con.execute("SELECT anum, name, bm25(names) FROM names WHERE names MATCH ? "
                           "ORDER BY bm25(names) LIMIT ?", (q, 50)).fetchall()
    finally:
        con.close()
    want = {_stem(t) for t in terms}
    scored = []
    for anum, nm, rank in hits:
        have = {_stem(w) for w in re.split(r"[^a-z0-9]+", nm.lower()) if w}
        cov = len(want & have) / len(want)
        scored.append((cov, -rank, anum, nm))
    scored.sort(reverse=True)
    receipts = [{"anum": a, "name_sha256": hashlib.sha256(nm.encode()).hexdigest()[:16],
                 "coverage": round(c, 4), "bm25": round(-r, 3)} for c, r, a, nm in scored[:k]]
    best = scored[0][0] if scored else 0.0
    return {"status": "ok", "terms": terms, "shadow_textbook_reuse": round(best, 4), "matches": receipts}


def report(*, mutation: str, claim_text: str = "", live_textbook_reuse: float | None = None,
           live_novel: bool | None = None, cycle_id: str = "") -> dict[str, Any] | None:
    """Log one shadow row. Report-only: returns the row, never raises, never alters live novelty."""
    try:
        from colony.trust.flags import novelty_shadow_enabled
        if not novelty_shadow_enabled():
            return None
        r = shadow_score(mutation, claim_text)
        row = {"ts": _utc(), "cycle_id": cycle_id, "mutation": mutation, "mode": "report_only",
               "live_textbook_reuse": live_textbook_reuse, "live_novel": live_novel, **r}
        row["would_flag"] = bool(r.get("status") == "ok" and (r.get("shadow_textbook_reuse") or 0) >= 0.75)
        st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
        tot = st.get("totals") or {}
        tot["n"] = int(tot.get("n", 0)) + 1
        tot[r.get("status", "?")] = int(tot.get(r.get("status", "?"), 0)) + 1
        if row["would_flag"]:
            tot["would_flag"] = int(tot.get("would_flag", 0)) + 1
            if live_novel:
                tot["would_flag_live_novel"] = int(tot.get("would_flag_live_novel", 0)) + 1
        st = {"mode": "report_only", "credit": CREDIT, "flag_threshold": 0.75,
              "note": "Shadow only. Live novelty (novelty_gate.textbook_reuse_score) is unchanged.",
              "totals": tot, "rows": ((st.get("rows") or []) + [row])[-KEEP_ROWS:]}
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
        return row
    except Exception:  # noqa: BLE001
        return None


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        print(json.dumps(build(force="--force" in sys.argv), indent=2))
    elif len(sys.argv) > 2 and sys.argv[1] == "score":
        print(json.dumps(shadow_score(sys.argv[2], " ".join(sys.argv[3:])), indent=2))
    else:
        print("usage: python -m colony.novelty_shadow build [--force] | score <name> [claim text]")
