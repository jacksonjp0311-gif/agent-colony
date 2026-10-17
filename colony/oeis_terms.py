"""Local OEIS TERMS index (stripped.gz) — is a computed integer sequence already in the OEIS?

Free, cached, no API key. The CI workflow builds it once a month into ~/.cache/colony/oeis
(the same actions/cache as the OEIS names corpus) and every lookup is local. OEIS data is
CC BY-SA 4.0 (https://oeis.org). When the index is absent every lookup answers "unchecked" —
callers must then say "OEIS unchecked", never "not in OEIS".

Index: for each sequence, the WINDOW consecutive terms starting at term positions 0..SHIFTS-1
(offsets differ between entries) hashed to a 63-bit key. A lookup tries the query's windows at
positions 0..QSHIFTS-1. A window with fewer than MIN_DISTINCT distinct values is too simple to
identify a sequence and answers "too_simple".
"""
from __future__ import annotations

import gzip
import hashlib
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path
from typing import Sequence

URL = "https://oeis.org/stripped.gz"
CREDIT = "OEIS Foundation Inc., The On-Line Encyclopedia of Integer Sequences, https://oeis.org (CC BY-SA 4.0)"
WINDOW = 10
SHIFTS = 4
QSHIFTS = 3
MIN_DISTINCT = 4


def cache_dir() -> Path:
    return Path(os.environ.get("COLONY_OEIS_CACHE") or (Path.home() / ".cache" / "colony" / "oeis"))


def db_path() -> Path:
    return cache_dir() / "oeis_terms.sqlite"


def _key(terms: Sequence[int]) -> int:
    h = hashlib.blake2b(",".join(str(int(t)) for t in terms).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") >> 1


def build(src_gz: Path | None = None, *, force: bool = False) -> dict:
    d = cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    db = db_path()
    if db.exists() and not force:
        return {"built": False, "reason": "cached", "db": str(db)}
    gz = src_gz or d / "stripped.gz"
    if src_gz is None and not gz.exists():
        req = urllib.request.Request(URL, headers={"User-Agent": "agent-colony frontier (free, cached monthly)"})
        with urllib.request.urlopen(req, timeout=180) as r, open(gz, "wb") as f:  # noqa: S310
            f.write(r.read())
    tmp = db.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.execute("CREATE TABLE k (key INTEGER, anum INTEGER)")
    rows, n_seq = [], 0
    with gzip.open(gz, "rt", encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if not ln.startswith("A"):
                continue
            a, _, body = ln.partition(" ")
            try:
                terms = [int(x) for x in body.strip().strip(",").split(",") if x]
                anum = int(a[1:])
            except ValueError:
                continue
            n_seq += 1
            for s in range(SHIFTS):
                w = terms[s:s + WINDOW]
                if len(w) == WINDOW:
                    rows.append((_key(w), anum))
            if len(rows) > 200000:
                con.executemany("INSERT INTO k VALUES (?, ?)", rows)
                rows = []
    con.executemany("INSERT INTO k VALUES (?, ?)", rows)
    con.execute("CREATE INDEX ki ON k(key)")
    con.commit()
    con.close()
    tmp.replace(db)
    return {"built": True, "db": str(db), "sequences": n_seq}


def available(db: Path | None = None) -> bool:
    return (db or db_path()).exists()


def lookup(seq: Sequence[int], db: Path | None = None) -> dict:
    """{'status': 'found'|'not_found'|'too_simple'|'unchecked', 'anums': [...]}; seq = a(1), a(2), ..."""
    dbp = db or db_path()
    if not dbp.exists():
        return {"status": "unchecked", "anums": []}
    seq = [int(x) for x in seq]
    wins = [seq[s:s + WINDOW] for s in range(QSHIFTS) if len(seq[s:s + WINDOW]) == WINDOW]
    if not wins or all(len(set(w)) < MIN_DISTINCT for w in wins):
        return {"status": "too_simple", "anums": []}
    con = sqlite3.connect(f"file:{dbp}?mode=ro", uri=True)
    try:
        found: set[int] = set()
        for w in wins:
            if len(set(w)) >= MIN_DISTINCT:
                found |= {r[0] for r in con.execute("SELECT anum FROM k WHERE key = ?", (_key(w),))}
    finally:
        con.close()
    if found:
        return {"status": "found", "anums": [f"A{a:06d}" for a in sorted(found)[:5]]}
    return {"status": "not_found", "anums": []}


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        print(build(Path(sys.argv[2]) if len(sys.argv) > 2 else None))
