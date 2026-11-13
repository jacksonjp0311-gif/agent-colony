"""Deterministic mutations of already-verified/held claims into new Oracle-reaching checks.

Phase 1 supply path. Takes the colony's own held / machine-checked frontier
claims and applies a closed set of mutations:

* perturb_constant         — nudge a modulus or recurrence coefficient
* flip_inequality          — swap the sides of a ``le`` or ``divides`` claim
* tighten_inequality       — a strictly stronger bound (``lhs+one`` or ``dbl(lhs)``)
* swap_related_sequence    — replace one primitive with a co-occurring one
* widen_range              — a farther held-out window of an unproved claim

New claims are authored as disabled hard checks (prefix ``authored_mut_``),
count toward ``MAX_AUTHORED_TOTAL`` (150), and go through the existing
triviality, known-result, dedupe, and ``verify_candidate`` filters. The
Oracle is unchanged. Nothing here executes OEIS-fetched code: evaluation
uses only ``colony.frontier_conjectures`` on local tables.

Disabled on the control arm (``self_mod_enabled`` is false). Writes are
refused during pytest unless the lemma and log paths have been redirected.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import random
from pathlib import Path
from typing import Any

PREFIX = "authored_mut_"
MUTATION_KINDS = (
    "swap_related_sequence",
    "perturb_constant",
    "tighten_inequality",
    "flip_inequality",
    "widen_range",
)
LOG_NAME = "generated_targets.jsonl"
# Small verify windows so verify_candidate stays inside RUNTIME_BUDGET_S;
# the high end of the tables is held back for the Oracle's shifted window.
VERIFY_WINDOWS = ((40, 80), (80, 120), (120, 160))
PREFILTER_WINDOW = (20, 120)
MAX_PREFILTER = 24
MAX_VERIFY = 8
_IDENT = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)(?![A-Za-z0-9_])")

# Tests may redirect these.
def _repo() -> Path:
    return Path(__file__).resolve().parent.parent


def log_path() -> Path:
    return Path(os.environ.get("COLONY_GENERATED_TARGETS_LOG") or (
        _repo() / "society" / "systems" / LOG_NAME
    ))


def oracle_system_path() -> Path:
    return Path(os.environ.get("COLONY_TG_ORACLE") or (
        _repo() / "society" / "systems" / "oracle.json"
    ))


def _lemma_path() -> Path:
    override = os.environ.get("COLONY_TG_LEMMA")
    if override:
        return Path(override)
    from colony.authoring import _lemma_impl
    return _lemma_impl()


def self_mod_ok() -> bool:
    try:
        from colony.arm import self_mod_enabled
        return bool(self_mod_enabled())
    except Exception:
        return True


def _pytest_would_write_repo(path: Path) -> bool:
    """Refuse to mutate the real tree when a unit test forgot to isolate."""
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    try:
        real = (_repo() / "society").resolve()
        return real in path.resolve().parents or path.resolve().parent == real
    except Exception:
        return True


def canonical_key(claim: dict[str, Any], mut_kind: str = "") -> str:
    core = {
        "kind": claim.get("kind"),
        "lhs": claim.get("lhs"),
        "rhs": claim.get("rhs") or "",
        "params": claim.get("params") or {},
        "mut": mut_kind,
    }
    blob = json.dumps(core, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def check_name(claim: dict[str, Any], mut_kind: str) -> str:
    digest = canonical_key(claim, mut_kind)[:12]
    safe = re.sub(r"[^a-z0-9_]", "", mut_kind.lower())[:24] or "mut"
    return f"{PREFIX}{safe}_{digest}"


def _core(claim: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": claim["kind"],
        "lhs": claim["lhs"],
        "rhs": claim.get("rhs") or "",
        "params": dict(claim.get("params") or {}),
    }


def _with_statement(claim: dict[str, Any]) -> dict[str, Any]:
    out = _core(claim)
    try:
        from colony.frontier_conjectures import statement
        out["statement"] = statement(out)
    except Exception:
        out["statement"] = f"{out['kind']}: {out['lhs']} {out['rhs']}"
    out["sig"] = canonical_key(out)[:16]
    return out


def held_claims(registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Already-held or machine-checked frontier claims, stable order, no ids invented."""
    if registry is None:
        try:
            from colony.frontier_conjectures import load_state
            registry = (load_state().get("registry") or {})
        except Exception:
            registry = {}
    out: list[dict[str, Any]] = []
    for rec in registry.values() if isinstance(registry, dict) else list(registry):
        if not isinstance(rec, dict):
            continue
        if not rec.get("kind") or not rec.get("lhs"):
            continue
        row = _core(rec)
        row["statement"] = rec.get("statement") or ""
        row["sig"] = rec.get("sig") or canonical_key(row)[:16]
        row["certificate"] = rec.get("certificate")
        row["label"] = rec.get("label") or ""
        row["family"] = rec.get("family") or ""
        row["range"] = rec.get("range")
        out.append(row)
    out.sort(key=lambda r: (str(r.get("sig") or ""), r["kind"], r["lhs"], r["rhs"]))
    return out


def _prims(claim: dict[str, Any]) -> set[str]:
    try:
        from colony.frontier_conjectures import parse, prims_of
        ps = prims_of(parse(claim["lhs"]))
        if claim.get("rhs"):
            ps |= prims_of(parse(claim["rhs"]))
        return set(ps)
    except Exception:
        return set(_IDENT.findall(f"{claim.get('lhs') or ''} {claim.get('rhs') or ''}"))


def related_primitives(claims: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Undirected co-occurrence graph: primitives that appear together in a held claim.

    A mechanism, not a hardcoded sibling list. Two names are related when
    they share at least one already-held claim.
    """
    graph: dict[str, set[str]] = {}
    for c in claims:
        ps = sorted(_prims(c))
        for a in ps:
            graph.setdefault(a, set())
            for b in ps:
                if a != b:
                    graph[a].add(b)
    return graph


def _replace_prim(expr: str, old: str, new: str) -> str:
    return re.sub(
        rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])",
        new,
        expr,
    )


def is_degenerate(claim: dict[str, Any]) -> str:
    """Structural collapse: gcd(x,x), x*x from a swap, self-index, identical sides."""
    lhs = str(claim.get("lhs") or "")
    rhs = str(claim.get("rhs") or "")
    text = f"{lhs} {rhs}"
    if re.search(r"gcd\(([A-Za-z0-9_]+),\1\)", text):
        return "gcd_same"
    if re.search(r"\(([A-Za-z0-9_]+)\*\1\)", text):
        return "product_same"
    if re.search(r"([A-Za-z0-9_]+)\[\1\]", text):
        return "index_same"
    kind = claim.get("kind")
    if kind in ("le", "identity", "divides") and lhs == rhs:
        return "identical_sides"
    # Unknown primitives (ValueError from the frontier parser) are not
    # degenerate; only a true parse crash on broken syntax is. Unit tests
    # use placeholder names; live swaps stay in the colony's language.
    try:
        from colony.frontier_conjectures import parse
        parse(lhs)
        if rhs:
            parse(rhs)
    except ValueError:
        pass
    except Exception:
        return "unparsable"
    return ""


def is_trivial(claim: dict[str, Any]) -> str:
    """Current triviality and known-result filters; empty string means it may proceed."""
    try:
        from colony import frontier_conjectures as FC
        if FC._BRIDGE_T is None:
            FC._BRIDGE_T = FC.Tables(lim=FC.BRIDGE_LIM, exp_n=FC.BRIDGE_EXP)
        c = {
            "kind": claim["kind"],
            "lhs": claim["lhs"],
            "rhs": claim.get("rhs") or "",
            "params": dict(claim.get("params") or {}),
            "_le": FC.parse(claim["lhs"]),
            "_re": FC.parse(claim["rhs"]) if claim.get("rhs") else None,
        }
        if FC.known_result(c):
            return "known_result"
        why = FC.trivial_reason(c, FC._BRIDGE_T, random.Random(canonical_key(c)), FC.fit_n())
        return str(why or "")
    except Exception as exc:  # noqa: BLE001
        return f"filter_error:{type(exc).__name__}"


def prefilter_holds(claim: dict[str, Any], lo: int | None = None, hi: int | None = None) -> bool:
    """True when the claim holds on a small local window (colony evaluator only)."""
    lo = PREFILTER_WINDOW[0] if lo is None else int(lo)
    hi = PREFILTER_WINDOW[1] if hi is None else int(hi)
    try:
        from colony.frontier_conjectures import holds_on
        n = holds_on(_core(claim), lo, hi)
        return bool(n and int(n) > 0)
    except Exception:
        return False


def apply_mutation(
    claim: dict[str, Any],
    kind: str,
    *,
    related: dict[str, set[str]] | None = None,
    spec: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return zero or more mutated cores for ``kind``, deterministic order."""
    src = _core(claim)
    out: list[dict[str, Any]] = []
    spec = dict(spec or {})

    if kind == "flip_inequality":
        if src["kind"] in ("le", "divides") and src["rhs"]:
            dst = dict(src)
            dst["lhs"], dst["rhs"] = src["rhs"], src["lhs"]
            out.append(dst)

    elif kind == "tighten_inequality":
        if src["kind"] == "le" and src["rhs"]:
            lhs = src["lhs"]
            for wrapped in (f"({lhs}+one)", f"dbl({lhs})"):
                if wrapped == lhs:
                    continue
                dst = dict(src)
                dst["lhs"] = wrapped
                out.append(dst)

    elif kind == "perturb_constant":
        if src["kind"] == "cong":
            params = dict(src["params"])
            try:
                m0 = int(params.get("m") or 0)
                r0 = int(params.get("r") or 0)
            except (TypeError, ValueError):
                m0, r0 = 0, 0
            seen_m = {m0}
            for dm in (1, 2, -1, 3):
                m = m0 + dm
                if m < 2 or m in seen_m or r0 >= m:
                    continue
                seen_m.add(m)
                dst = dict(src)
                dst["params"] = {**params, "m": m}
                out.append(dst)
        elif src["kind"] == "rec":
            coeffs = list((src["params"] or {}).get("c") or [])
            for i, ci in enumerate(coeffs):
                try:
                    base = int(ci)
                except (TypeError, ValueError):
                    continue
                for d in (1, -1):
                    cc = list(coeffs)
                    cc[i] = base + d
                    dst = dict(src)
                    dst["params"] = {**(src["params"] or {}), "c": cc}
                    out.append(dst)

    elif kind == "swap_related_sequence":
        graph = related or {}
        present = _prims(src)
        pairs: list[tuple[str, str]] = []
        for a in sorted(present):
            for b in sorted(graph.get(a) or []):
                if b == a or b in present:
                    continue
                pairs.append((a, b))
        # Stable, limited: every pair is a distinct claim; caller caps tries.
        for a, b in pairs:
            dst = dict(src)
            dst["lhs"] = _replace_prim(src["lhs"], a, b)
            dst["rhs"] = _replace_prim(src["rhs"], a, b) if src["rhs"] else ""
            if dst["lhs"] == src["lhs"] and dst["rhs"] == src["rhs"]:
                continue
            dst["_swap"] = {"from": a, "to": b}
            out.append(dst)

    elif kind == "widen_range":
        # Same assertion; a farther window is a new check, not a new math claim.
        # Only offered for unproved (no certificate) survivors.
        if claim.get("certificate"):
            return []
        dst = dict(src)
        dst["_widen"] = True
        out.append(dst)

    return out


def enumerate_mutations(
    claims: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """All mutation candidates in deterministic order (kind, then source sig, then key)."""
    held = claims if claims is not None else held_claims()
    graph = related_primitives(held)
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for kind in MUTATION_KINDS:
        for src in held:
            for dst in apply_mutation(src, kind, related=graph):
                key = canonical_key(dst, kind)
                if key in seen:
                    continue
                seen.add(key)
                row = _with_statement(dst)
                row["mut_kind"] = kind
                row["source_sig"] = src.get("sig") or ""
                row["source_statement"] = src.get("statement") or ""
                if dst.get("_swap"):
                    row["swap"] = dst["_swap"]
                if dst.get("_widen"):
                    row["widen"] = True
                found.append(row)
    found.sort(key=lambda r: (MUTATION_KINDS.index(r["mut_kind"]), r.get("source_sig") or "", canonical_key(r, r["mut_kind"])))
    return found


def _seen_keys_and_names(
    extra: set[str] | None = None,
    src: str | None = None,
) -> tuple[set[str], set[str]]:
    """Prior targets, kills, and already-authored names (append-only log + lemma)."""
    keys: set[str] = set(extra or [])
    names: set[str] = set()
    # Lemma file: any authored_mut_ already present (enabled or not).
    try:
        from colony.authoring import _entries, AUTHORED_PREFIX
        text = src if src is not None else _lemma_path().read_text(encoding="utf-8")
        import ast
        tree = ast.parse(text)
        for n, _c, _f in _entries(tree):
            if n.startswith(PREFIX) or n.startswith(AUTHORED_PREFIX):
                names.add(n)
    except Exception:
        pass
    # Append-only generator log.
    path = log_path()
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("key"):
                    keys.add(str(row["key"]))
                if row.get("name"):
                    names.add(str(row["name"]))
                if row.get("claim"):
                    keys.add(canonical_key(row["claim"], str(row.get("mut_kind") or "")))
    except Exception:
        pass
    # Retired names.
    try:
        from colony.retire import retired_names
        names |= set(retired_names())
    except Exception:
        pass
    return keys, names


def _append_log(row: dict[str, Any]) -> None:
    path = log_path()
    if _pytest_would_write_repo(path):
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    except Exception:
        pass


def _widen_windows() -> list[tuple[int, int]]:
    # Farther than VERIFY_WINDOWS, still short of typical table ends, with headroom.
    return [(400, 700), (700, 1000), (1000, 1300)]


def build_check(claim: dict[str, Any], mut_kind: str) -> dict[str, Any] | None:
    """Disabled hard-check candidate, same shape as frontier_checks.build."""
    import ast
    from colony.frontier_checks import BRIDGE_FNS

    name = check_name(claim, mut_kind)
    core = _core(claim)
    stmt = str(claim.get("statement") or "")
    if not stmt:
        try:
            from colony.frontier_conjectures import statement
            stmt = statement(core)
        except Exception:
            stmt = name
    stmt = stmt.replace('"""', "'")
    wins = _widen_windows() if claim.get("widen") or mut_kind == "widen_range" else list(VERIFY_WINDOWS)
    lit = repr(dict(sorted({
        "kind": core["kind"], "lhs": core["lhs"], "rhs": core["rhs"],
        "params": core["params"],
    }.items())))
    expr = f"all(type(c := frontier_holds({lit}, a, b)) is int and c > 0 for a, b in {wins!r})"
    try:
        body = ast.parse(expr, mode="eval").body
    except SyntaxError:
        return None
    fn_src = (
        f"def check_{name}() -> bool:\n"
        f'    """Authored mutated claim (target generator, {mut_kind}):\n'
        f"    {stmt}\n"
        f"    verified on windows {wins}. Bounded evidence, not proof.\n"
        f"    Disabled until the Oracle passes it. Never executes fetched code.\n"
        f'    """\n'
        f"    return {expr}\n"
    )
    return {
        "name": name,
        "fn_src": fn_src,
        "body": body,
        "expr": expr,
        "components": [],
        "verify_fns": list(BRIDGE_FNS),
        "evidence": ["colony/target_generator.py", "colony/frontier_conjectures.py", f"claim:{stmt}"],
        "source": "target_generator",
        "mut_kind": mut_kind,
        "claim": core,
        "statement": stmt,
        "what": f"authored disabled mutated check `{name}` ({mut_kind}): {stmt}; awaits Oracle via proposal",
    }


def _eligible_candidate(
    row: dict[str, Any],
    seen_keys: set[str],
    seen_names: set[str],
    *,
    skip_filters: bool = False,
) -> dict[str, Any] | None:
    kind = str(row.get("mut_kind") or "")
    key = canonical_key(row, kind)
    name = check_name(row, kind)
    if key in seen_keys or name in seen_names:
        return None
    if is_degenerate(row):
        return None
    if not skip_filters:
        why = is_trivial(row)
        if why:
            return None
        if kind != "widen_range" and not prefilter_holds(row):
            return None
        if kind == "widen_range" and not prefilter_holds(row):
            return None
    built = build_check(row, kind)
    if built is None:
        return None
    built["key"] = key
    built["row"] = row
    return built


def author_targets(
    *,
    max_new: int = 1,
    cycle_id: str = "",
    write: bool = True,
    claims: list[dict[str, Any]] | None = None,
    lemma_src: str | None = None,
    verify: Any = None,
    skip_filters: bool = False,
) -> list[dict[str, Any]]:
    """Author up to ``max_new`` new Oracle-reaching checks. Empty on control or at the cap.

    Independent of lemma-score saturation (``hard_pass_cannot_raise_score``):
    a new claim can still earn a new Oracle verdict even when the microbench
    hard component is already pinned. The 150 cap and per-cycle cap still bind.
    """
    if not self_mod_ok():
        return []
    try:
        from colony.authoring import (
            MAX_AUTHORED_TOTAL, MAX_AUTHORED_PER_CYCLE, authored_count,
            insert_disabled, verify_candidate, _invalidate,
        )
        from colony.frontier_checks import ensure_bridges, BRIDGE_FNS
        from colony.authoring import INSERT_MARKER, FALLBACK_MARKER
    except Exception:
        return []
    cap = int(MAX_AUTHORED_TOTAL)
    try:
        n = int(authored_count())
    except Exception:
        n = 0
    if n >= cap or max_new <= 0:
        return []
    budget = min(int(max_new), int(MAX_AUTHORED_PER_CYCLE), cap - n)

    path = _lemma_path()
    if lemma_src is None:
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            return []
    else:
        src = lemma_src
    if write and _pytest_would_write_repo(path):
        return []

    marker = INSERT_MARKER if INSERT_MARKER in src else FALLBACK_MARKER
    bridged = ensure_bridges(src, marker)
    if bridged != src:
        src = bridged

    seen_keys, seen_names = _seen_keys_and_names(src=src)
    verify_fn = verify if verify is not None else verify_candidate
    accepted: list[dict[str, Any]] = []
    tried = 0
    for row in enumerate_mutations(claims if claims is not None else held_claims()):
        if len(accepted) >= budget or tried >= MAX_VERIFY:
            break
        cand = _eligible_candidate(row, seen_keys, seen_names, skip_filters=skip_filters)
        if cand is None:
            continue
        new_src = insert_disabled(src, cand["name"], cand["fn_src"])
        if new_src is None:
            continue
        tried += 1
        try:
            res = verify_fn(new_src, cand["name"], list(cand["verify_fns"] or BRIDGE_FNS))
        except Exception as exc:  # noqa: BLE001
            res = {"accepted": False, "reason": f"verify_error:{type(exc).__name__}"}
        if not res.get("accepted"):
            if write:
                _append_log({
                    "event": "reject",
                    "name": cand["name"],
                    "key": cand["key"],
                    "mut_kind": cand["mut_kind"],
                    "reason": res.get("reason"),
                    "cycle_id": cycle_id,
                    "claim": cand.get("claim"),
                    "statement": cand.get("statement"),
                })
            seen_keys.add(cand["key"])
            seen_names.add(cand["name"])
            continue
        if write:
            try:
                path.write_text(new_src, encoding="utf-8")
                _invalidate(path)
            except OSError:
                return accepted
            _append_log({
                "event": "authored",
                "name": cand["name"],
                "key": cand["key"],
                "mut_kind": cand["mut_kind"],
                "cycle_id": cycle_id,
                "claim": cand.get("claim"),
                "statement": cand.get("statement"),
                "source_statement": (cand.get("row") or {}).get("source_statement"),
            })
            src = new_src
        seen_keys.add(cand["key"])
        seen_names.add(cand["name"])
        accepted.append({
            "name": cand["name"],
            "accepted": True,
            "source": "target_generator",
            "mut_kind": cand["mut_kind"],
            "statement": cand.get("statement"),
            "claim": cand.get("claim"),
            "key": cand["key"],
            "seconds": res.get("seconds"),
        })
    return accepted


def _enabled_flags(src: str | None = None) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    try:
        from colony.authoring import _entries
        import ast
        text = src if src is not None else _lemma_path().read_text(encoding="utf-8")
        for n, _c, flag in _entries(ast.parse(text)):
            if n.startswith(PREFIX):
                flags[n] = bool(flag)
    except Exception:
        pass
    return flags


def oracle_final_verdicts() -> dict[str, str]:
    """Map mutation name → ``killed`` or ``passed`` from the Oracle snapshot.

    ``unique_mutations_kill`` and ``unique_mutations_pass`` are final
    verdicts. A name in both is treated as killed (FAIL kills keep).
    ``latest`` is consulted when it names a generated check. This never
    invents ids and never executes fetched code.
    """
    out: dict[str, str] = {}
    path = oracle_system_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(data, dict):
        return out
    for n in data.get("unique_mutations_pass") or []:
        name = str(n or "")
        if name:
            out[name] = "passed"
    for n in data.get("unique_mutations_kill") or []:
        name = str(n or "")
        if name:
            out[name] = "killed"  # kill wins over a stale pass if both appear
    latest = data.get("latest") if isinstance(data.get("latest"), dict) else {}
    mut = str(latest.get("mutation") or "")
    if mut:
        if latest.get("passed") is True:
            out.setdefault(mut, "passed")
        elif latest.get("passed") is False or latest.get("kills"):
            out.setdefault(mut, "killed")
    return out


def note_oracle_verdicts() -> list[dict[str, Any]]:
    """Append-only: record Oracle killed/passed lines not yet in the generator log.

    Disabled on the control arm and during unisolated pytest. Does not
    rewrite earlier log lines. Only generated (``authored_mut_``) names
    are written; other Oracle mutations are left to the Oracle snapshot.
    """
    if not self_mod_ok():
        return []
    verdicts = {
        n: ev for n, ev in oracle_final_verdicts().items()
        if n.startswith(PREFIX) and ev in ("killed", "passed")
    }
    if not verdicts:
        return []
    already: set[str] = set()
    path = log_path()
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("event") in ("killed", "passed") and row.get("name"):
                    already.add(str(row["name"]))
    except Exception:
        pass
    written: list[dict[str, Any]] = []
    for name, event in sorted(verdicts.items()):
        if name in already:
            continue
        row = {
            "event": event,
            "name": name,
            "source": "oracle",
        }
        _append_log(row)
        written.append(row)
    return written


def oracle_reachable_generated(
    state: dict[str, Any] | None = None,
    *,
    src: str | None = None,
) -> list[dict[str, Any]]:
    """Authored mutated checks that can still receive a new Oracle verdict.

    A target is reachable only when it exists as a real ``authored_mut_``
    check, is still disabled, has not been retired or logged as rejected,
    has a non-empty id, and does not already have a final Oracle verdict
    (``unique_mutations_kill`` or ``unique_mutations_pass``, plus
    ``latest``). Already-passed (enabled or unique-pass) or killed checks
    are not eligible. Noticing a new verdict appends a ``killed`` or
    ``passed`` line to the generator log (append-only). This never
    invents ids.
    """
    try:
        note_oracle_verdicts()
    except Exception:
        pass
    flags = _enabled_flags(src)
    _keys, logged = _seen_keys_and_names(src=src)
    # Names logged as reject / killed / passed are not reachable.
    rejected: set[str] = set()
    path = log_path()
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("event") in ("reject", "killed", "passed", "retired") and row.get("name"):
                    rejected.add(str(row["name"]))
    except Exception:
        pass
    try:
        from colony.retire import retired_names
        rejected |= set(retired_names())
    except Exception:
        pass
    for name, ev in oracle_final_verdicts().items():
        if ev in ("killed", "passed") and name:
            rejected.add(name)
    out: list[dict[str, Any]] = []
    for name, enabled in sorted(flags.items()):
        if enabled:
            continue  # already has an Oracle / desk pass
        if name in rejected:
            continue
        out.append({
            "id": name,
            "source": "authored_check",
            "kind": "authored_check",
            "form": "mutated_claim",
            "text": name,
            "can_progress": True,
            "untried": True,
            "unseen": True,
            "unused": True,
            "band": 0,
            "mutated": True,
        })
    return out


def perturb_candidates(
    tried: set[str] | None = None,
    ledger: set[str] | None = None,
    *,
    src: str | None = None,
) -> list[dict[str, Any]]:
    """PERTURB-menu slice of still-reachable generated checks."""
    tried = tried or set()
    ledger = ledger or set()
    out = []
    for t in oracle_reachable_generated(src=src):
        tid = str(t.get("id") or "")
        if not tid or not t.get("can_progress"):
            continue
        if tid in tried:
            t = dict(t)
            t["untried"] = False
            t["unused"] = False
        if tid in ledger:
            t = dict(t)
            t["unseen"] = False
        out.append(t)
    return out
