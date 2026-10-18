"""Retire low-value authored checks to make room under MAX_AUTHORED_TOTAL (James 2026-10-17 10:26 PM ET).

COLONY_RETIRE=live|shadow|off (code default shadow = report only). Rule-based, never hand-picked.
Only checks named ``authored_*`` in the lemma catalog are ever considered.

Rules (first match wins):
  sweep             a near-duplicate parameter sweep of an already-proven family: hunt family
                    (colony.hunt_shadow.claim_family strips the parameters) where the OTHER
                    Oracle-passed members s give expected = s/(s+K) >= EXPECTED_MIN (K = the
                    calibrated hunt K_PRIOR), and at least KEEP_MIN Oracle-passed members stay.
  textbook_pair     a plain pairing of two textbook catalog lemmas: the body is just
                    all(check_A ...) and all(check_B ...) on separate windows, so the claim is
                    implied by its two parts (the triviality filter's implied_parts idea).
  trivial_frontier  an authored frontier conjecture that the CURRENT triviality filter flags.

Never retired (protected): anything on a receipt under society/receipts (authorized or decided);
the target or a building block of a proposal currently meeting the shortlist bar; anything named
in a human_guide lesson; catalog / hard-bench lemmas (not authored_*); anything named in colony/ or
tests/ code; anything another remaining check calls; anything with an Oracle verdict in the last
GRACE_HOURS (its proposal may not be evaluated yet).

Retire = remove the check's function and catalog entry from lemma_impl.py and append a record
(name, category, reason, ts, cycle, catalog flag, full source) to society/systems/retired_checks.json.
No history is rewritten; Oracle / desk logs are untouched. Reversible:
``python -m colony.retire restore NAME`` puts it back DISABLED (it must pass the Oracle again), or
git revert the commit. Authoring never re-authors a retired name (nor, for textbook_pair, the same
pair). Never touches P, the Oracle, the 0.70 bar, the charter, TributeKeeper, Ceiling or Athanor.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RECORD = ROOT / "society" / "systems" / "retired_checks.json"
REPORT = ROOT / "society" / "systems" / "retire_report.json"
RECEIPTS = ROOT / "society" / "receipts"
ORACLE = ROOT / "data" / "commons" / "oracle.jsonl"
STATE = ROOT / "data" / "society_state.json"
WITHDRAWN = "withdrawn_retired"
MODES = ("live", "shadow", "off")
EXPECTED_MIN = 0.95
KEEP_MIN = 3
GRACE_HOURS = 2.0
MAX_PER_RUN = 60
PREFIX = "authored_"
_NAME = re.compile(r"authored_[a-z0-9_]+")


def mode() -> str:
    m = os.environ.get("COLONY_RETIRE", "shadow").strip().lower()
    return m if m in MODES else "shadow"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _jsonl(path: Path) -> list[dict[str, Any]]:
    out = []
    try:
        with path.open(encoding="utf-8") as fh:
            for ln in fh:
                try:
                    out.append(json.loads(ln))
                except Exception:  # noqa: BLE001
                    pass
    except OSError:
        pass
    return out


def load_record(path: Path = RECORD) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"version": 1, "records": []}


def retired_names(path: Path = RECORD) -> set[str]:
    return {r["name"] for r in load_record(path).get("records") or [] if not r.get("restored_at")}


def retired_pair_families(path: Path = RECORD) -> set[str]:
    return {re.sub(r"_w\d+$", "", r["name"]) for r in load_record(path).get("records") or []
            if r.get("category") == "textbook_pair" and not r.get("restored_at")}


def count_retired(path: Path = RECORD) -> int:
    return len(retired_names(path))


# ----------------------------------------------------------------------------- facts

def _lemma_path() -> Path:
    from colony.authoring import _lemma_impl
    return _lemma_impl()


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def plain_pair(fn: ast.FunctionDef, catalog: dict[str, str]) -> tuple[str, str] | None:
    """(A, B) when the body is exactly ``return all(check_A(..) for ..) and all(check_B(..) for ..)``
    with A, B textbook catalog lemmas (not authored). ``catalog`` maps function name -> lemma name."""
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return None
    v = body[0].value
    if not (isinstance(v, ast.BoolOp) and isinstance(v.op, ast.And) and len(v.values) == 2):
        return None
    out = []
    for part in v.values:
        if not (isinstance(part, ast.Call) and isinstance(part.func, ast.Name) and part.func.id == "all"
                and len(part.args) == 1 and isinstance(part.args[0], ast.GeneratorExp)):
            return None
        elt = part.args[0].elt
        if not (isinstance(elt, ast.Call) and isinstance(elt.func, ast.Name) and elt.func.id.startswith("check_")):
            return None
        lem = catalog.get(elt.func.id)
        if lem is None or lem.startswith(PREFIX):
            return None
        out.append(lem)
    return (out[0], out[1]) if out[0] != out[1] else None


def receipt_names(root: Path = RECEIPTS) -> set[str]:
    out: set[str] = set()
    for p in root.rglob("*") if root.exists() else []:
        if p.is_file():
            try:
                out |= set(_NAME.findall(p.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                pass
    return out


def code_names() -> set[str]:
    out: set[str] = set()
    for d in ("colony", "tests"):
        for p in (ROOT / d).rglob("*.py"):
            if p.name == "retire.py" or "test_retire" in p.name:
                continue
            try:
                out |= set(_NAME.findall(p.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                pass
    return out


def guide_names() -> set[str]:
    try:
        from colony.lessons import load_human_guides
        return set(_NAME.findall(json.dumps(load_human_guides(include_expired=True))))
    except Exception:  # noqa: BLE001
        return set()


def bar_dependencies() -> set[str] | None:
    """Building blocks of every proposal that currently meets the shortlist bar (the check a
    proposal is about is not protected by this; its proposal is withdrawn when it is retired).
    None when it cannot be computed (then nothing is retired)."""
    try:
        from colony import shortlist as SL
        st = json.loads(SL.STATE_PATH.read_text(encoding="utf-8"))
        props = list(st.get("improvement_proposals") or []) + list(st.get("improvement_proposals_archived") or [])
        orc, nov = SL._jsonl(SL.ORACLE_LOG), SL._jsonl(SL.NOVELTY_LOG)
        out: set[str] = set()
        seen: set[str] = set()
        for p in props:
            if not p.get("id") or p["id"] in seen:
                continue
            seen.add(p["id"])
            e = SL.evaluate(p, oracle_rows=orc, novelty_rows=nov, athanor_rows=[])
            if e.get("meets_bar"):   # James 2026-10-18 1:48 AM ET: building blocks only, not the subject check
                out |= set(e.get("building_blocks") or [])
        return out
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------------- the rule

def plan(*, src: str | None = None, oracle_rows: list[dict[str, Any]] | None = None,
         protected_extra: dict[str, str] | None = None, deps: set[str] | None | str = "compute",
         receipts: set[str] | None = None, guides: set[str] | None = None, code: set[str] | None = None,
         k_prior: float | None = None, now: datetime | None = None, frontier_new=None) -> dict[str, Any]:
    from colony.authoring import _entries
    from colony.hunt_shadow import claim_family
    if k_prior is None:
        from colony.hunt_shadow import K_PRIOR as k_prior
    src = src if src is not None else _lemma_path().read_text(encoding="utf-8")
    tree = ast.parse(src)
    ents = _entries(tree)
    flags = {n: f for n, _c, f in ents}
    catalog: dict[str, str] = {}   # check function -> textbook lemma whose catalog entry uses it
    for n, c, _f in ents:
        if not n.startswith(PREFIX):
            for x in ast.walk(c):
                if isinstance(x, ast.Name) and x.id.startswith("check_") and not x.id.startswith("check_" + PREFIX):
                    catalog.setdefault(x.id, n)
    authored = [n for n in flags if n.startswith(PREFIX)]
    fns = _functions(tree)
    oracle_rows = oracle_rows if oracle_rows is not None else _jsonl(ORACLE)
    now = now or datetime.now(timezone.utc)
    first_pass: dict[str, str] = {}
    last_verdict: dict[str, str] = {}
    for r in oracle_rows:
        m = r.get("mutation")
        if m in flags and r.get("ts"):
            last_verdict[m] = r["ts"]
            if r.get("passed") and m not in first_pass:
                first_pass[m] = r["ts"]
    deps = bar_dependencies() if deps == "compute" else deps
    receipts = receipt_names() if receipts is None else receipts
    guides = guide_names() if guides is None else guides
    code = code_names() if code is None else code
    called: set[str] = set()
    for n in flags:
        fn = fns.get(f"check_{n}")
        if fn:
            called |= {x.id[len("check_"):] for x in ast.walk(fn)
                       if isinstance(x, ast.Name) and x.id.startswith("check_") and x.id != f"check_{n}"}
    protected: dict[str, str] = {}
    for n in authored:
        why = None
        if n in receipts:
            why = "on a receipt (authorized / decided)"
        elif deps is None:
            why = "shortlist bar unavailable (fail closed)"
        elif n in deps:
            why = "a building block of a proposal meeting the bar"
        elif n in guides:
            why = "named in a human_guide"
        elif n in code:
            why = "named in colony/ or tests/ code"
        elif n in called:
            why = "another check calls it"
        else:
            lv = _ts(last_verdict.get(n, ""))
            if lv and now - lv < timedelta(hours=GRACE_HOURS):
                why = f"Oracle verdict within {GRACE_HOURS:g}h (grace)"
        if why is None and protected_extra and n in protected_extra:
            why = protected_extra[n]
        if why:
            protected[n] = why
    cands: list[dict[str, Any]] = []
    # sweeps: families by the hunt's parameter-stripping family; newest first
    fams: dict[str, list[str]] = {}
    for n in authored:
        if n.startswith(PREFIX + "sieve_") or claim_family(n) != re.sub(r"_w\d+$", "", n):
            fams.setdefault(claim_family(n), []).append(n)
    for fam, mem in sorted(fams.items()):
        passed = sorted([n for n in mem if n in first_pass], key=lambda n: (first_pass[n], n))
        alive = list(passed)
        for n in reversed(passed):
            if n in protected:
                continue
            s = len(alive) - 1
            exp = s / (s + k_prior) if s + k_prior > 0 else 0.0
            if exp >= EXPECTED_MIN and len(alive) - 1 >= KEEP_MIN:
                alive.remove(n)
                cands.append({"name": n, "category": "sweep", "family": fam, "expected": round(exp, 4),
                              "reason": (f"near-duplicate parameter sweep of proven family `{fam}`: "
                                         f"{s} other Oracle-passed members, expected = s/(s+K) = {exp:.3f} "
                                         f">= {EXPECTED_MIN} (K={k_prior}); {len(alive)} members stay")})
    done = {c["name"] for c in cands}
    for n in authored:
        if n in done or n in protected:
            continue
        fn = fns.get(f"check_{n}")
        if fn is None:
            continue
        pp = plain_pair(fn, catalog)
        if pp:
            cands.append({"name": n, "category": "textbook_pair", "components": list(pp),
                          "reason": (f"plain pairing of textbook lemmas {pp[0]} + {pp[1]} on separate windows: "
                                     "the claim is implied by its two parts")})
            continue
        if n.startswith(PREFIX + "frontier_"):
            ok = frontier_new(n) if frontier_new else _frontier_still_new(n, fn)
            if ok is False:
                cands.append({"name": n, "category": "trivial_frontier",
                              "reason": "the current triviality filter flags this frontier claim as a rewrite"})
    cands = cands[:MAX_PER_RUN]
    by_cat: dict[str, int] = {}
    for c in cands:
        by_cat[c["category"]] = by_cat.get(c["category"], 0) + 1
    return {"ts": _utc(), "mode": mode(), "n_authored": len(authored), "n_candidates": len(cands),
            "by_category": by_cat, "candidates": cands,
            "protected": {k: v for k, v in sorted(protected.items())},
            "rule": {"expected_min": EXPECTED_MIN, "keep_min": KEEP_MIN, "K": k_prior, "grace_hours": GRACE_HOURS,
                     "max_per_run": MAX_PER_RUN}}


def _frontier_still_new(name: str, fn: ast.FunctionDef) -> bool | None:
    """Re-screen the claim behind an authored frontier check with the current filter."""
    try:
        from colony.frontier_checks import trivial_now
        t = trivial_now(name, src=ast.unparse(fn))
        return None if t is None else not t
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------------- apply / restore

def remove(src: str, names: list[str]) -> tuple[str, dict[str, dict[str, Any]]]:
    """Drop the functions and catalog entries of ``names``; returns (new_src, archive)."""
    from colony.authoring import _catalog_lists
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    fns = _functions(tree)
    cuts: list[tuple[int, int]] = []
    archive: dict[str, dict[str, Any]] = {}
    for lst_name, lst in _catalog_lists(tree).items():
        for elt in lst.elts:
            if (isinstance(elt, ast.Tuple) and len(elt.elts) >= 3 and isinstance(elt.elts[0], ast.Constant)
                    and elt.elts[0].value in names):
                n = elt.elts[0].value
                flag = elt.elts[2].value if isinstance(elt.elts[2], ast.Constant) else None
                archive.setdefault(n, {})["catalog"] = lst_name
                archive[n]["enabled"] = flag
                archive[n]["entry"] = "".join(lines[elt.lineno - 1:elt.end_lineno])
                cuts.append((elt.lineno - 1, elt.end_lineno))
    for n in names:
        fn = fns.get(f"check_{n}")
        if fn is None:
            continue
        end = fn.end_lineno
        while end < len(lines) and not lines[end].strip() and end - fn.end_lineno < 2:
            end += 1
        archive.setdefault(n, {})["fn_src"] = "".join(lines[fn.lineno - 1:fn.end_lineno])
        cuts.append((fn.lineno - 1, end))
    for a, b in sorted(cuts, reverse=True):
        del lines[a:b]
    out = "".join(lines)
    ast.parse(out)
    return out, archive


def bench_ok(src: str) -> dict[str, Any]:
    """Every remaining enabled check still passes (run in a subprocess on a temp copy)."""
    import subprocess
    import tempfile
    path = _lemma_path()
    with tempfile.NamedTemporaryFile("w", suffix=".py", dir=path.parent, prefix="_retire_probe_",
                                     delete=False, encoding="utf-8") as fh:
        fh.write(src)
        tmp = Path(fh.name)
    code = ("import importlib.util,json,sys;sys.path.insert(0,sys.argv[2]);"
            "s=importlib.util.spec_from_file_location('retire_probe',sys.argv[1]);"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
            "b=m.run_basic_checks();h=m.run_hard_checks();"
            "print(json.dumps({'basic':len(b),'basic_pass':sum(map(bool,b.values())),"
            "'hard':len(h),'hard_pass':sum(map(bool,h.values()))}))")
    try:
        p = subprocess.run([sys.executable, "-c", code, str(tmp), str(ROOT)], capture_output=True, text=True,
                           timeout=600)
        r = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else {"error": p.stderr[-400:]}
    except Exception as e:  # noqa: BLE001
        r = {"error": str(e)[:400]}
    finally:
        tmp.unlink(missing_ok=True)
    r["ok"] = bool(r.get("hard")) and r.get("hard") == r.get("hard_pass") and r.get("basic") == r.get("basic_pass")
    return r


def apply(p: dict[str, Any], *, cycle_id: str = "", path: Path | None = None, record: Path = RECORD,
          check_bench: bool = True, state_path: Path | None = STATE) -> dict[str, Any]:
    path = path or _lemma_path()
    names = [c["name"] for c in p.get("candidates") or []]
    if not names:
        return {"applied": 0}
    src = path.read_text(encoding="utf-8")
    new_src, archive = remove(src, names)
    if check_bench:
        b = bench_ok(new_src)
        if not b.get("ok"):
            return {"applied": 0, "aborted": "bench check failed after removal", "bench": b}
    rec = load_record(record)
    ts = _utc()
    for c in p["candidates"]:
        a = archive.get(c["name"]) or {}
        rec.setdefault("records", []).append({
            "name": c["name"], "category": c["category"], "reason": c["reason"], "ts": ts, "cycle_id": cycle_id,
            "catalog": a.get("catalog"), "enabled": a.get("enabled"), "fn_src": a.get("fn_src"),
            "entry": a.get("entry"), **{k: c[k] for k in ("family", "expected", "components") if k in c}})
    rec["n_retired"] = len([r for r in rec["records"] if not r.get("restored_at")])
    rec["note"] = ("Retired authored checks (COLONY_RETIRE). Restore with `python -m colony.retire restore NAME` "
                   "(comes back disabled; must pass the Oracle again). Logs and history untouched.")
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    path.write_text(new_src, encoding="utf-8")
    try:
        from colony.authoring import _invalidate
        _invalidate(path)
    except Exception:  # noqa: BLE001
        pass
    withdrawn = []
    if state_path is not None:
        for c in p["candidates"]:
            ids = withdraw_proposals({c["name"]}, reason=f"subject check retired ({c['category']}): {c['reason']}",
                                     state_path=state_path)
            withdrawn += ids
            for r in rec["records"]:
                if r["name"] == c["name"] and r["ts"] == ts:
                    r["proposals_withdrawn"] = ids
        record.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
        try:  # earlier retirements too (idempotent)
            st = json.loads(state_path.read_text(encoding="utf-8"))
            more = withdraw_all_retired(st, record)
            if more:
                state_path.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
                withdrawn += more
        except Exception:  # noqa: BLE001
            pass
    return {"applied": len(names), "names": names, "withdrawn": withdrawn}




def _subject(p: dict[str, Any]) -> str:
    """The authored check a proposal is about (action first, e.g. seek_enable:NAME; else title).
    Parsed directly: the shortlist resolver needs the check to still be in the catalog."""
    for field in (p.get("action") or "", p.get("title") or ""):
        m = _NAME.search(field)
        if m:
            return m.group(0)
    return ""


def withdraw_in(data: dict[str, Any], names: set[str], reasons: dict[str, str]) -> list[str]:
    """In-place on a society state dict: proposals whose subject check is in ``names`` get
    status withdrawn_retired + the reason + their prior status (so restore can undo it)."""
    out = []
    for key in ("improvement_proposals", "improvement_proposals_archived"):
        for p in data.get(key) or []:
            if p.get("status") == WITHDRAWN:
                continue
            t = _subject(p)
            if t in names:
                p["withdrawn"] = {"reason": reasons.get(t, "subject check retired"), "retired_check": t,
                                  "prior_status": p.get("status"), "ts": _utc()}
                p["status"] = WITHDRAWN
                out.append(p.get("id"))
    return out


def _active_reasons(record: Path = RECORD) -> dict[str, str]:
    return {r["name"]: f"subject check retired ({r['category']}): {r['reason']}"
            for r in load_record(record).get("records") or [] if not r.get("restored_at")}


def withdraw_all_retired(data: dict[str, Any], record: Path = RECORD) -> list[str]:
    """Catch-up, idempotent: withdraw the proposals of every currently retired check."""
    reasons = _active_reasons(record)
    return withdraw_in(data, set(reasons), reasons)


def withdraw_proposals(names: set[str], *, reason: str, state_path: Path = STATE) -> list[str]:
    try:
        st = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out = withdraw_in(st, names, {n: reason for n in names})
    if out:
        state_path.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
    return out


def unwithdraw_proposals(name: str, *, state_path: Path = STATE) -> list[str]:
    try:
        st = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for key in ("improvement_proposals", "improvement_proposals_archived"):
        for p in st.get(key) or []:
            w = p.get("withdrawn") or {}
            if p.get("status") == WITHDRAWN and w.get("retired_check") == name:
                p["status"] = w.get("prior_status") or "candidate_measured"
                p["withdrawn"] = {**w, "restored_at": _utc()}
                out.append(p.get("id"))
    if out:
        state_path.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
    return out


def restore(name: str, *, path: Path | None = None, record: Path = RECORD, state_path: Path | None = STATE) -> bool:
    """Put a retired check back, DISABLED (it must pass the Oracle again)."""
    from colony.authoring import insert_disabled
    path = path or _lemma_path()
    rec = load_record(record)
    row = next((r for r in reversed(rec.get("records") or []) if r["name"] == name and not r.get("restored_at")), None)
    if row is None or not row.get("fn_src"):
        return False
    new_src = insert_disabled(path.read_text(encoding="utf-8"), name, row["fn_src"].rstrip() + "\n")
    if new_src is None:
        return False
    path.write_text(new_src, encoding="utf-8")
    row["restored_at"] = _utc()
    if state_path is not None:
        row["proposals_restored"] = unwithdraw_proposals(name, state_path=state_path)
    rec["n_retired"] = len([r for r in rec["records"] if not r.get("restored_at")])
    record.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    return True


def run_cycle(cycle_id: str = "") -> dict[str, Any]:
    """Shadow: write the report. Live: also apply. Never raises."""
    m = mode()
    if m == "off":
        return {"skipped": "COLONY_RETIRE=off"}
    try:
        p = plan()
        p["cycle_id"] = cycle_id
        if m == "live":
            p["applied"] = apply(p, cycle_id=cycle_id)
        REPORT.write_text(json.dumps({k: v for k, v in p.items() if k != "protected"} |
                                     {"n_protected": len(p["protected"])}, indent=1) + "\n", encoding="utf-8")
        return p
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:300]}


def to_markdown(p: dict[str, Any]) -> str:
    lines = [f"# Retire plan ({p.get('mode')})", "",
             f"{p['n_candidates']} of {p['n_authored']} authored checks would be retired: {p['by_category']}. "
             f"{len(p.get('protected') or {})} protected.", ""]
    for c in p["candidates"]:
        lines.append(f"- `{c['name']}` [{c['category']}] — {c['reason']}")
    lines += ["", "Protected (reason counts):"]
    cnt: dict[str, int] = {}
    for v in (p.get("protected") or {}).values():
        cnt[v] = cnt.get(v, 0) + 1
    lines += [f"- {k}: {v}" for k, v in sorted(cnt.items(), key=lambda t: -t[1])]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "restore":
        print("restored" if restore(sys.argv[2]) else "not restored")
    else:
        pl = plan()
        print(to_markdown(pl))
