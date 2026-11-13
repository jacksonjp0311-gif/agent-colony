"""OEIS conjectures as direct colony targets (James 2026-10-23 12:50 PM ET). COLONY_OEIS_CONJ=off|shadow|live.

A mechanism, not a pick:
  * MENU (society/frontier/oeis_conjectures.json, built by tools/build_oeis_conjectures.py from free
    OEIS JSON + b-files): real stated conjectures, each with its source A-number, the EXACT quoted
    OEIS line, the parsed testable form (relation / congruence / inequality / g.f. / property), the
    b-file terms and the b-files of any referenced A-numbers. Entries whose text says the conjecture
    was proved, is true, false or has a counterexample are skipped by the builder.
  * ACTIONS the colony takes on targets it picks from the menu each cycle:
      attempt_disprove  test the parsed form on every available term (b-file; beyond it when the
                        entry's own definition is computable and reproduces the whole b-file);
                        a failure is re-verified by an independent code path (colony.oeis_eval_b:
                        own tokenizer, shunting-yard parser, RPN evaluator, and a fresh b-file
                        fetch / own recomputation of extended terms) before it counts;
      attempt_prove     when the entry's definition is C-finite (rational g.f. or constant-
                        coefficient linear recurrence) and the claim is an identity of C-finite
                        terms or a rational g.f.: a certificate checked by the separate checker
                        colony.proof_check.check_oeis (order bound + finite check / polynomial
                        identity), which uses only path B.
  * CREDIT (selection layer only; never fitness, P, the Oracle, the 0.70 bar, charter, TributeKeeper,
    Ceiling or Athanor): CREDIT_RESOLVE for a counterexample confirmed by both paths beyond the DATA
    range, or a proof accepted by the checker; CREDIT_EXTEND (small, log-scaled) for testing beyond the
    range tested before; 0 otherwise. A failure inside the DATA range (terms the author saw) is
    recorded as 'fails_in_data' (almost always a misparse or an unstated initial condition) and earns
    nothing. Every resolved item is flagged for James's review (society/frontier/OEIS_CONJECTURE_REVIEW.md);
    nothing is authorized, submitted or posted.
  * shadow (code default): attempts run and are reported (society/systems/oeis_conjectures_report.json)
    but no state or credit is kept; live: state, credit and the review flags are written and the
    colony's target choice uses its own past credit.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import random
import re
import time
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from colony import oeis_eval_b as B

ROOT = Path(__file__).resolve().parent.parent
MENU = ROOT / "society" / "frontier" / "oeis_conjectures.json"
STATE = ROOT / "society" / "systems" / "oeis_conjecture_state.json"
REPORT = ROOT / "society" / "systems" / "oeis_conjectures_report.json"
REVIEW = ROOT / "society" / "frontier" / "OEIS_CONJECTURE_REVIEW.md"
# Selection bookkeeping, written in shadow and live. Not credit, not the Oracle.
ATTEMPT_LOG = ROOT / "society" / "systems" / "oeis_attempt_log.json"
MODES = ("off", "shadow", "live")
PICKS = 4                 # targets per cycle
CREDIT_RESOLVE = 1.0      # verified counterexample or checked proof
CREDIT_EXTEND = 0.05      # max for extending the tested range (log-scaled)
DEEP_N = 20000            # extension cap (terms) when the definition is computable
DEEP_SECONDS = 8.0
DEEP_DIGITS = 5000        # decimal digits; EGF holds near the series cap can move past ~957
GF_TERMS = 1200           # slow series-arithmetic cap (algebraic / egf / fallback g.f.)
FAST_TERM_CAP = 8000      # when a C-finite exact iterator applies, terms are cheap
MIN_TESTED = 8

# Physical-cap labels recorded on attempt results and log rows.
CAP_TERM = "term_cap"
CAP_DIGIT = "digit_cap"
CAP_TIME = "time_cap"
CAP_REF = "ref_limited"
CAP_DIGIT_OR_TIME = "digit_or_time_cap"  # inferred only, when the binding cap is unclear

# PR #6 shipped these defaults; used to tell whether a cap has been raised
# relative to an attempt that predates cap_reason recording.
_PR6_GF_TERMS = 1200
_PR6_DEEP_N = 20000
_PR6_DEEP_DIGITS = 3000
_PR6_DEEP_SECONDS = 8.0
_BITS_PER_DIGIT = 3.33

# Maps a self-heal knob name to the evaluator_caps() key.
_CAP_KNOB_KEYS = {
    "gf_term_cap": ("gf_terms", int),
    "deep_term_cap": ("deep_n", int),
    "fast_term_cap": ("fast_term_cap", int),
    "deep_digits": ("deep_digits", int),
    "deep_seconds": ("deep_seconds", float),
}


def evaluator_caps() -> dict[str, int | float]:
    """Live term / digit / time caps. Module constants, unless a self-heal knob is in force.

    A knob is applied only when its live value differs from its default, or
    when an in-flight trial is on that knob. Tests that monkeypatch the
    module constants therefore still work when no trial is running.
    """
    caps: dict[str, int | float] = {
        "gf_terms": int(GF_TERMS),
        "deep_n": int(DEEP_N),
        "fast_term_cap": int(FAST_TERM_CAP),
        "deep_digits": int(DEEP_DIGITS),
        "deep_seconds": float(DEEP_SECONDS),
    }
    try:
        from colony import self_heal as SH
        st = SH.load_state()
        knobs = st.get("knobs") or {}
        trial = st.get("trial") or {}
        trial_knob = trial.get("knob") if isinstance(trial, dict) else None
        for knob, (key, caster) in _CAP_KNOB_KEYS.items():
            if knob not in SH.KNOB_SPECS or knob not in knobs:
                continue
            val = knobs[knob]
            default = SH.KNOB_SPECS[knob].default
            if val != default or trial_knob == knob:
                caps[key] = caster(val)
    except Exception:
        pass
    return caps


def digit_bit_budget(digits: int | float | None = None) -> int:
    """Bit-length budget corresponding to a decimal-digit cap."""
    d = evaluator_caps()["deep_digits"] if digits is None else digits
    return max(1, int(float(d) * _BITS_PER_DIGIT))


def _defn_of(e: dict[str, Any] | None, defn: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if defn:
        return defn
    if not e:
        return None
    d = e.get("definition")
    if d:
        return d
    try:
        return computable_definition(e)
    except Exception:
        return None


def fast_cfinite_available(e: dict[str, Any] | None = None, defn: dict[str, Any] | None = None) -> bool:
    """True when a rational g.f. or constant-coeff recurrence can be iterated exactly."""
    d = _defn_of(e, defn)
    if not d or d.get("kind") not in ("gf", "rec"):
        return False
    try:
        from colony import oeis_deep as D
        off = int((e or {}).get("offset") or 0)
        terms = list((e or {}).get("terms") or [])
        D.cfinite(d, off, terms)
        return True
    except Exception:
        return False


def term_cap_for(e: dict[str, Any] | None = None, defn: dict[str, Any] | None = None) -> int:
    """Term cap that actually applies to this entry under current caps."""
    caps = evaluator_caps()
    d = _defn_of(e, defn)
    form = str(((e or {}).get("claim") or {}).get("form") or "")
    kind = str((d or {}).get("kind") or "")
    if fast_cfinite_available(e, d):
        return int(caps["fast_term_cap"])
    if form == "gf" or kind in ("gf", "alg", "egf"):
        return int(caps["gf_terms"])
    return int(caps["deep_n"])


def current_cap_value(reason: str, e: dict[str, Any] | None = None) -> int | float | None:
    """The live value of the cap named by ``reason``."""
    caps = evaluator_caps()
    if reason == CAP_TERM:
        return term_cap_for(e)
    if reason == CAP_DIGIT:
        return caps["deep_digits"]
    if reason == CAP_TIME:
        return caps["deep_seconds"]
    if reason == CAP_REF:
        return claim_testable_hi(e) if e is not None else None
    if reason == CAP_DIGIT_OR_TIME:
        return None
    return None


def cap_has_been_raised(row: dict[str, Any] | None, e: dict[str, Any] | None = None) -> bool:
    """True when a live cap is strictly higher than the one that bounded this attempt."""
    if not isinstance(row, dict):
        return False
    reason, old = cap_of_row(row, e)
    if not reason:
        return False
    if reason == CAP_DIGIT_OR_TIME:
        caps = evaluator_caps()
        return (
            float(caps["deep_digits"]) > _PR6_DEEP_DIGITS
            or float(caps["deep_seconds"]) > _PR6_DEEP_SECONDS
        )
    if old is None:
        return False
    now = current_cap_value(reason, e)
    if now is None:
        return False
    try:
        return float(now) > float(old)
    except (TypeError, ValueError):
        return False


def cap_of_row(row: dict[str, Any] | None, e: dict[str, Any] | None = None) -> tuple[str | None, int | float | None]:
    """(reason, value) recorded on a row, or inferred for a pre-cap_reason row."""
    if not isinstance(row, dict):
        return None, None
    reason = row.get("cap_reason")
    if reason:
        val = row.get("cap_value")
        try:
            if val is not None and reason != CAP_TIME:
                val = int(val)
            elif val is not None:
                val = float(val)
        except (TypeError, ValueError):
            val = None
        return str(reason), val
    return infer_cap_reason(row, e)


def infer_cap_reason(row: dict[str, Any] | None, e: dict[str, Any] | None = None) -> tuple[str | None, int | float | None]:
    """Best-effort (reason, value) for a row written before cap_reason existed.

    Used so already-committed same-depth holds (A165064 at the 1200-term
    cap, A126089 at a digit/time ceiling) are treated honestly, without
    rewriting the log.
    """
    if not isinstance(row, dict):
        return None, None
    try:
        planned = attempt_row_planned_depth(row)
    except Exception:
        planned = 0
        if "planned" in row:
            try:
                planned = int(row.get("planned") or 0)
            except (TypeError, ValueError):
                planned = 0
    try:
        verified = attempt_row_verified_depth(row, 0)
    except Exception:
        try:
            verified = int(row.get("verified_depth") or row.get("depth") or 0)
        except (TypeError, ValueError):
            verified = 0
    if planned <= 0 or verified <= 0 or verified >= planned:
        return None, None
    # Near a known term cap (verified is typically cap-1 because n runs
    # from offset to L-1).
    term_candidates = [_PR6_GF_TERMS, GF_TERMS, _PR6_DEEP_N, DEEP_N]
    try:
        term_candidates.append(int(FAST_TERM_CAP))
    except Exception:
        pass
    term_candidates.append(planned)
    for tc in term_candidates:
        try:
            tc_i = int(tc)
        except (TypeError, ValueError):
            continue
        if tc_i <= 0:
            continue
        if abs(verified - tc_i) <= 2 or abs(verified + 1 - tc_i) <= 1:
            return CAP_TERM, tc_i
    if e is not None:
        try:
            refs_hi = _ref_limited_hi(e)
        except Exception:
            refs_hi = None
        if refs_hi is not None and verified >= refs_hi:
            return CAP_REF, refs_hi
    return CAP_DIGIT_OR_TIME, verified


def _ref_limited_hi(e: dict[str, Any]) -> int | None:
    """Highest n the referenced b-files support, or None if refs do not bind."""
    text = _parts_text(e)
    anums = set(_ANUM.findall(text))
    anums.discard(str(e.get("anum") or ""))
    if not anums:
        return None
    limit = None
    off = int(e.get("offset") or 0)
    terms = list(e.get("terms") or [])
    a_hi = (off + len(terms) - 1) if terms else 0
    for anum in anums:
        rh = _ref_hi(e, anum)
        if rh is None:
            return a_hi
        shift = _ref_shift(text, anum)
        cand = rh - shift
        limit = cand if limit is None else min(limit, cand)
    return int(limit) if limit is not None else None


def mode() -> str:
    m = os.environ.get("COLONY_OEIS_CONJ", "shadow").strip().lower()
    return m if m in MODES else "shadow"


# ----------------------------------------------------------------------------- normalisation

ALIAS_SEQ = {"A000045": "fib", "A000032": "lucas", "A000203": "sigma", "A000005": "tau", "A000010": "phi",
             "A000040": "prime", "A000142": "fact"}
ALLOWED_NAMES = {"n", "x", "a", "floor", "ilog2", "binomial", "fib", "lucas", "fact", "sigma", "tau", "phi", "prime"}
FUNCS = {"a", "floor", "ilog2", "binomial", "fib", "lucas", "fact", "sigma", "tau", "phi", "prime", "sqrt"}
PROPS = ("prime", "odd", "even", "squarefree", "nonzero", "positive", "composite")
RESOLVED = re.compile(
    r"(conjectur\w*[^.]{0,120}\b(is|are|was|were)\s+(now\s+)?(true|correct|false|incorrect|wrong|proved|proven|confirmed|refuted|disproved))"
    r"|((proved|proven|proof|disproved|refuted|counterexample|counter-example)[^.]{0,80}conjectur)"
    r"|(conjectur\w*[^.]{0,80}(follows?|holds) (easily |immediately )?from)"
    r"|(above conjectur\w* (is|are) (true|correct|incorrect|false))"
    r"|(conjectured,? (in)?correctly|(in)?correctly conjectured|conjecture (verified|confirmed|proved)"
    r"|(was|were|is|are|been) (proved|proven|confirmed|disproved|refuted)|walnut)", re.I)
CONJ = re.compile(r"conjectur", re.I)


class Unparsed(Exception):
    pass


def _strip_attr(s: str) -> str:
    s = re.split(r"\s+-\s+_[A-Z]", s)[0]
    s = re.sub(r"\[\s*Conjectur[^\]]*\]", "", s)
    s = re.sub(r"\(\s*(conjecture[sd]?|conjectured[^)]*)\s*\)", "", s, flags=re.I)
    s = re.sub(r"^\s*(Conjectur\w*)(\s+\d+)?(\s*\([^)]*\))?(\s+from\s+_[^_]+_[^:]*)?\s*:?\s*", "", s)
    s = re.sub(r"^\s*(It is|We) conjecture[d]? that\s+", "", s, flags=re.I)
    s = re.sub(r"^\s*(the sequence is\s+)?(D-finite|P-recursive|holonomic)\s+with\s+(the\s+)?recurrence\s*:?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*\(End\)\s*$", "", s)
    return s.strip().rstrip(".;, ").strip()


def _ins_mul(s: str) -> str:
    tok = re.findall(r"\d+|A\d{6}|[A-Za-z_][A-Za-z0-9_]*|<=|>=|!=|==|\S", s)
    out: list[str] = []
    for t in tok:
        if out:
            p = out[-1]
            p_val = bool(re.fullmatch(r"\d+", p)) or p == ")" or (re.fullmatch(r"[A-Za-z_]\w*", p) and p not in FUNCS
                                                                   and not re.fullmatch(r"A\d{6}", p))
            t_start = bool(re.fullmatch(r"\d+|A\d{6}|[A-Za-z_]\w*", t)) or t == "("
            if p_val and t_start and not (t == "(" and p in FUNCS):
                out.append("*")
        out.append(t)
    return "".join(x if x not in ("<=", ">=", "!=", "==") else x for x in out)


def normalize(text: str) -> dict[str, Any]:
    """Quoted OEIS statement -> testable claim dict, or raise Unparsed(reason)."""
    s = _strip_attr(text)
    s = (s.replace("\u2212", "-").replace("\u2264", "<=").replace("\u2265", ">=").replace("\u2261", "==")
         .replace("\u00d7", "*").replace("\u00b7", "*").replace("\u2260", "!=").replace("\u00a0", " "))
    if not s:
        raise Unparsed("empty")
    m = re.fullmatch(r"(\d+) is the only prime (term )?in (this|the) sequence", s, re.I)
    if m:
        return {"form": "only_prime", "p": int(m.group(1))}
    m = re.fullmatch(r"(?:a\(n\) is (?:always )?|(?:all|every) terms? (?:are|is) (?:)?)(prime|odd|even|squarefree|nonzero|positive|composite)s?"
                     r"(?: numbers?)?(?: for (?:all )?n\s*(>=|>)\s*(\d+))?", s, re.I)
    if m:
        n0 = None if not m.group(2) else int(m.group(3)) + (1 if m.group(2) == ">" else 0)
        return {"form": "property", "prop": m.group(1).lower(), "n0": n0}
    aliases: dict[str, str] = {}
    w = re.search(r",?\s*where\s+(.*)$", s)
    if w:
        rest = w.group(1)
        for mm in re.finditer(r"\b([A-Za-z]\w*)(?:\(n\))?\s*=\s*(A\d{6})(?:\s*\([^)]*\))?", rest):
            aliases[mm.group(1)] = mm.group(2)
        left = re.sub(r"\b([A-Za-z]\w*)(?:\(n\))?\s*=\s*(A\d{6})(?:\s*\([^)]*\))?", "", rest)
        left = re.sub(r"\b(and|that is|i\.e\.)\b|[,.;]", " ", left).strip()
        if left:
            raise Unparsed("where-clause: " + left[:40])
        s = s[:w.start()]
    s = re.sub(r",?\s*with\s+a\(\d+\)\s*=\s*-?\d+((\s*(,|and)\s*)a\(\d+\)\s*=\s*-?\d+)*", "", s)
    n0 = None
    m = re.search(r",?\s*for (?:all )?n\s*(>=|>|=>)\s*(-?\d+)\s*$", s)
    if m:
        n0 = int(m.group(2)) + (1 if m.group(1) == ">" else 0)
        s = s[:m.start()]
    s = re.sub(r",?\s*for (?:all|every) (?:n|integers? n|positive n)\s*$", "", s)
    if re.search(r"\bfor\b|\bif\b|\bwhen\b|\biff\b", s):
        raise Unparsed("conditional")
    mod = None
    m = re.search(r"\(?\s*mod(?:ulo)?\s+(\d+)\s*\)?\s*$", s)
    if m:
        mod = int(m.group(1))
        s = s[:m.start()]
    gf = re.match(r"^(?:Conjectured\s+)?G\.f\.\s*(?:A\(x\)\s*)?(?:=|:)?\s*(.*)$", s)
    for k, v in aliases.items():
        target = ALIAS_SEQ.get(v, v)
        s = re.sub(r"\b%s\(" % re.escape(k), target + "(", s)
    s = re.sub(r"\bfloor\(\s*log_2\(", "ilog2((", s)
    s = re.sub(r"\bFibonacci\(", "fib(", s)
    s = re.sub(r"\bLucas\(", "lucas(", s)
    s = re.sub(r"\bsigma_1\(", "sigma(", s)
    s = re.sub(r"\b(\w)!", r"fact(\1)", s)
    s = re.sub(r"\b(A\d{6})\(", lambda mm: ALIAS_SEQ.get(mm.group(1), mm.group(1)) + "(", s)
    if gf:
        body = _ins_mul(gf.group(1) if gf else s)
        for nm in re.findall(r"[A-Za-z_]\w*", body):
            if nm != "x":
                raise Unparsed("g.f. name " + nm)
        B.rational(B.compile_expr(body))
        return {"form": "gf", "expr": body}
    if re.search(r"[\[\]{}~|!]|\.\.|Sum|Product|lim|Integral|sqrt|log|exp|Pi|round|ceiling|mod|\?", s.replace("!=", "")):
        raise Unparsed("outside grammar")
    s = _ins_mul(s)
    for nm in re.findall(r"[A-Za-z_]\w*", s):
        if nm not in ALLOWED_NAMES and not re.fullmatch(r"A\d{6}", nm):
            raise Unparsed("name " + nm)
    parts, rels = B.split_rel(s)
    if not rels:
        raise Unparsed("no relation")
    if mod is not None and rels != ["=="] and rels != ["="]:
        raise Unparsed("congruence shape")
    for p in parts:
        if not p:
            raise Unparsed("empty side")
        B.compile_expr(p)
    if "a(" not in s:
        raise Unparsed("no a(.)")
    return {"form": "relation", "parts": parts, "rels": ["=" if r == "==" else r for r in rels], "mod": mod, "n0": n0}


def refs(claim: dict[str, Any]) -> list[str]:
    txt = json.dumps(claim)
    return sorted(set(re.findall(r"A\d{6}", txt)))


# ----------------------------------------------------------------------------- path A evaluator (python ast)


class _A:
    def __init__(self, src: str):
        self.tree = ast.parse(src.replace("^", "**"), mode="eval").body
        self._check(self.tree)

    def _check(self, nd):
        ok = (ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div,
              ast.Pow, ast.USub, ast.UAdd, ast.Load)
        for x in ast.walk(nd):
            if not isinstance(x, ok):
                raise Unparsed("ast node " + type(x).__name__)
            if isinstance(x, ast.Constant) and not isinstance(x.value, int):
                raise Unparsed("constant")
            if isinstance(x, ast.Call) and not isinstance(x.func, ast.Name):
                raise Unparsed("call")

    def ev(self, nd, n, seq):
        if isinstance(nd, ast.Constant):
            return Fraction(nd.value)
        if isinstance(nd, ast.Name):
            if nd.id == "n":
                return Fraction(n)
            raise B.Bad("name " + nd.id)
        if isinstance(nd, ast.UnaryOp):
            v = self.ev(nd.operand, n, seq)
            return -v if isinstance(nd.op, ast.USub) else v
        if isinstance(nd, ast.BinOp):
            x, y = self.ev(nd.left, n, seq), self.ev(nd.right, n, seq)
            if isinstance(nd.op, ast.Add):
                return x + y
            if isinstance(nd.op, ast.Sub):
                return x - y
            if isinstance(nd.op, ast.Mult):
                return x * y
            if isinstance(nd.op, ast.Div):
                if y == 0:
                    raise B.Bad("div0")
                return x / y
            if y.denominator != 1 or abs(y) > 100000 or (x == 0 and y < 0):
                raise B.Bad("pow")
            if abs(x.numerator) > 1 and abs(int(y)) * math.log2(abs(x.numerator) + 1) > 200000:
                raise B.Bad("pow size")
            return x ** int(y)
        f = nd.func.id
        args = [self.ev(a, n, seq) for a in nd.args]
        for a in args:
            if a.denominator != 1 and f not in ("floor", "ilog2"):
                raise B.Bad("non-integer argument")
        if f == "floor":
            return Fraction(math.floor(args[0]))
        if f == "ilog2":
            v = math.floor(args[0])
            if v < 1:
                raise B.Bad("log")
            return Fraction(int(v).bit_length() - 1)
        if f == "binomial":
            p, q = int(args[0]), int(args[1])
            if q < 0:
                return Fraction(0)
            if p >= 0:
                return Fraction(math.comb(p, q) if q <= p else 0)
            return Fraction((-1) ** q * math.comb(q - p - 1, q))
        i = int(args[0])
        if f == "a" or re.fullmatch(r"A\d{6}", f):
            return Fraction(seq(f, i))
        return Fraction(_builtin_a(f, i))


def _fibA(k: int) -> int:
    if k < 0:
        return (-1) ** (k + 1) * _fibA(-k)
    a, b = 0, 1
    for _ in range(k):
        a, b = b, a + b
    return a


_PRA: list[int] = []


def _builtin_a(f: str, i: int) -> int:
    import sympy
    if f == "fib":
        if abs(i) > 100000:
            raise B.Bad("fib size")
        return _fibA(i)
    if f == "lucas":
        if abs(i) > 100000:
            raise B.Bad("lucas size")
        return _fibA(i - 1) + _fibA(i + 1)
    if f == "fact":
        if not 0 <= i <= 5000:
            raise B.Bad("fact")
        return math.factorial(i)
    if i <= 0:
        raise B.Bad(f + " domain")
    if f == "sigma":
        return int(sympy.divisor_sigma(i))
    if f == "tau":
        return int(sympy.divisor_count(i))
    if f == "phi":
        return int(sympy.totient(i))
    if f == "prime":
        if i > 200000:
            raise B.Bad("prime index")
        return int(sympy.prime(i))
    raise B.Bad("function " + f)


def _prop_ok(prop: str, v: int, path: str) -> bool:
    if prop in ("prime", "composite", "squarefree"):
        if path == "A":
            import sympy
            if prop == "prime":
                return bool(sympy.isprime(v))
            if prop == "composite":
                return v > 1 and not sympy.isprime(v)
            return v != 0 and all(e == 1 for e in sympy.factorint(abs(v)).values()) if abs(v) < 10 ** 30 else True
        if prop == "prime":
            return B.is_prime(v)
        if prop == "composite":
            return v > 1 and not B.is_prime(v)
        return v != 0 and (abs(v) >= 10 ** 12 or all(e == 1 for e in B._factor(abs(v)).values()))
    return {"odd": v % 2 == 1, "even": v % 2 == 0, "nonzero": v != 0, "positive": v > 0}[prop]


# ----------------------------------------------------------------------------- testing


class Tables:
    """Terms by name: 'a' (target) and referenced A-numbers; dict name -> (offset, list[int])."""

    def __init__(self, tabs: dict[str, tuple[int, list[int]]]):
        self.t = tabs

    def get(self, name: str, i: int) -> int:
        if name not in self.t:
            raise B.Missing(name)
        off, xs = self.t[name]
        j = i - off
        if j < 0 or j >= len(xs):
            raise B.Missing(name)
        return xs[j]

    def hi(self, name: str = "a") -> int:
        off, xs = self.t[name]
        return off + len(xs) - 1


def _rel(x: Fraction, y: Fraction, r: str, mod: int | None) -> bool:
    if mod:
        d = x - y
        return d.denominator == 1 and d.numerator % mod == 0
    return {"=": x == y, "<": x < y, "<=": x <= y, ">": x > y, ">=": x >= y, "!=": x != y}[r]


def test_claim(claim: dict[str, Any], T: Tables, path: str = "A", n_max: int | None = None) -> dict[str, Any]:
    """Test the claim at every n where all referenced terms are available.
    Returns tested count, lo/hi n tested, fails (first 5 n with values) and holds_from."""
    off, xs = T.t["a"]
    hi_a = off + len(xs) - 1
    seq = T.get
    tested, lo, hi, fails, undefined = 0, None, None, [], 0
    last_fail = None
    form = claim["form"]
    if form == "gf":
        # Same term cap the evaluator would use (fast cap when C-finite).
        cap_entry = {
            "claim": claim,
            "definition": {"kind": "gf", "expr": claim.get("expr")},
            "offset": off,
            "terms": list(xs),
        }
        L = min(len(xs) + off, term_cap_for(cap_entry))
        if path == "A":
            co = _series_A(claim["expr"], L)
        else:
            num, den = B.rational(B.compile_expr(claim["expr"]))
            co = B.series(num, den, L)
        for n in range(off, L):
            v = T.get("a", n)
            tested += 1
            lo = n if lo is None else lo
            hi = n
            if co[n] != v:
                last_fail = n
                if len(fails) < 5:
                    fails.append({"n": n, "lhs": str(co[n]), "a(n)": str(v)})
        return _summ(tested, lo, hi, fails, last_fail, undefined)
    n0 = claim.get("n0")
    start = off if n0 is None else max(off, n0)
    if form == "relation":
        ev = [(_A(p) if path == "A" else B.compile_expr(p)) for p in claim["parts"]]
        top = 2 * hi_a + 64
    else:
        top = hi_a
    if n_max is not None:
        top = min(top, n_max)
    miss_run = 0
    for n in range(start, top + 1):
        try:
            if form == "relation":
                vals = [(e.ev(e.tree, n, seq) if path == "A" else B.evaluate(e, {"n": n}, seq)) for e in ev]
                ok = all(_rel(vals[i], vals[i + 1], r, claim.get("mod")) for i, r in enumerate(claim["rels"]))
                shown = [str(v) for v in vals]
            elif form == "property":
                v = seq("a", n)
                ok = _prop_ok(claim["prop"], v, path)
                shown = [str(v)]
            elif form == "only_prime":
                v = seq("a", n)
                isp = (B.is_prime(v) if path == "B" else __import__("sympy").isprime(v))
                ok = (not isp) or v == claim["p"]
                shown = [str(v)]
            else:
                raise Unparsed(form)
        except B.Missing:
            miss_run += 1
            if n > hi_a and miss_run > 64:
                break
            continue
        except (B.Bad, ZeroDivisionError, OverflowError, ValueError):
            undefined += 1
            continue
        miss_run = 0
        tested += 1
        lo = n if lo is None else lo
        hi = n
        if not ok:
            last_fail = n
            if len(fails) < 5:
                fails.append({"n": n, "values": [s if len(s) < 80 else s[:38] + "..." + s[-38:] for s in shown]})
    return _summ(tested, lo, hi, fails, last_fail, undefined)


def _summ(tested, lo, hi, fails, last_fail, undefined):
    return {"tested": tested, "lo": lo, "hi": hi, "fails": fails, "first_fail": fails[0]["n"] if fails else None,
            "holds_from": None if last_fail is None else last_fail + 1, "undefined": undefined}


class _Ser:
    def __init__(self, c, L):
        self.c, self.L = (list(c) + [Fraction(0)] * L)[:L], L

    def __add__(self, o):
        o = _ser(o, self.L)
        return _Ser([a + b for a, b in zip(self.c, o.c)], self.L)

    __radd__ = __add__

    def __neg__(self):
        return _Ser([-a for a in self.c], self.L)

    def __sub__(self, o):
        return self + (-_ser(o, self.L))

    def __rsub__(self, o):
        return _ser(o, self.L) - self

    def __mul__(self, o):
        o = _ser(o, self.L)
        r = [Fraction(0)] * self.L
        nz = [(j, b) for j, b in enumerate(o.c) if b]
        for i, a in enumerate(self.c):
            if a:
                for j, b in nz:
                    if i + j >= self.L:
                        break
                    r[i + j] += a * b
        return _Ser(r, self.L)

    __rmul__ = __mul__

    def inv(self):
        if self.c[0] == 0:
            raise B.Bad("series inverse")
        r = [Fraction(0)] * self.L
        r[0] = 1 / self.c[0]
        nz = [(j, b) for j, b in enumerate(self.c) if b and j]
        for i in range(1, self.L):
            s = Fraction(0)
            for j, b in nz:
                if j > i:
                    break
                s += b * r[i - j]
            r[i] = -s / self.c[0]
        return _Ser(r, self.L)


    def sqrt(self):
        """s with s*s = self, s(0) = 1 (squaring recurrence; path B uses the ODE recurrence)."""
        if self.c[0] != 1:
            raise B.Bad("sqrt needs constant term 1")
        r = [Fraction(1)] + [Fraction(0)] * (self.L - 1)
        for n in range(1, self.L):
            t = self.c[n]
            for k in range(1, (n + 1) // 2):
                t -= 2 * r[k] * r[n - k]
            if n % 2 == 0:
                t -= r[n // 2] * r[n // 2]
            r[n] = t / 2
        return _Ser(r, self.L)


def _ser(v, L):
    return v if isinstance(v, _Ser) else _Ser([Fraction(v)], L)


def _series_A(expr: str, L: int) -> list[Fraction]:
    """Path A g.f. expansion: ast walk in truncated series (with an x^k shift for poles at 0)."""
    tree = ast.parse(expr.replace("^", "**"), mode="eval").body
    X = _Ser([0, 1], L + 40)

    def ev(nd):
        if isinstance(nd, ast.Constant):
            return _Ser([Fraction(nd.value)], L + 40)
        if isinstance(nd, ast.Name) and nd.id == "x":
            return X
        if isinstance(nd, ast.UnaryOp):
            v = ev(nd.operand)
            return -v if isinstance(nd.op, ast.USub) else v
        if isinstance(nd, ast.BinOp):
            a, b = ev(nd.left), ev(nd.right)
            if isinstance(nd.op, ast.Add):
                return a + b
            if isinstance(nd.op, ast.Sub):
                return a - b
            if isinstance(nd.op, ast.Mult):
                return a * b
            if isinstance(nd.op, ast.Div):
                k = next((i for i, c in enumerate(b.c) if c), None)
                if k is None:
                    raise B.Bad("div0")
                if any(a.c[:k]):
                    raise B.Bad("pole")
                return _Ser(a.c[k:], a.L) * _Ser(b.c[k:], b.L).inv()
            hx = _half_exp(nd.right) if isinstance(nd.op, ast.Pow) else None
            if hx is not None:
                r = _Ser([1], L + 40)
                rt = a.sqrt()
                for _ in range(abs(hx)):
                    r = r * rt
                return r if hx > 0 else _Ser([1], L + 40) * r.inv()
            if isinstance(nd.op, ast.Pow) and isinstance(nd.right, ast.Constant) and 0 <= nd.right.value <= 64:
                r = _Ser([1], L + 40)
                for _ in range(nd.right.value):
                    r = r * a
                return r
            if (isinstance(nd.op, ast.Pow) and isinstance(nd.right, ast.UnaryOp)
                    and isinstance(nd.right.operand, ast.Constant) and nd.right.operand.value <= 64):
                r = _Ser([1], L + 40)
                for _ in range(nd.right.operand.value):
                    r = r * a
                return _Ser([1], L + 40) * r.inv()
        if (isinstance(nd, ast.Call) and isinstance(nd.func, ast.Name) and nd.func.id == "sqrt"
                and len(nd.args) == 1 and not nd.keywords):
            return ev(nd.args[0]).sqrt()
        raise B.Bad("g.f. node")
    return ev(tree).c[:L]


def _half_exp(nd) -> int | None:
    """k for an exponent written k/2 (k odd, |k| <= 63), e.g. (1/2), (-1/2), (3/2)."""
    sg = 1
    if isinstance(nd, ast.UnaryOp) and isinstance(nd.op, ast.USub):
        sg, nd = -1, nd.operand
    if (isinstance(nd, ast.BinOp) and isinstance(nd.op, ast.Div) and isinstance(nd.left, ast.Constant)
            and isinstance(nd.right, ast.Constant) and nd.right.value == 2 and isinstance(nd.left.value, int)
            and nd.left.value % 2 == 1 and abs(nd.left.value) <= 63):
        return sg * nd.left.value
    return None


# ----------------------------------------------------------------------------- definitions (computable / C-finite)


def _peel_where(s: str) -> tuple[str, dict[str, str]]:
    """Pull `where X = <expr>` bindings out of a name. X is one letter.

    The expression stops before words such as `is` / `the` (the prose after the
    formula). Bindings are not a place to hide fetched code: they are text
    from the same name, substituted as formulas.
    """
    bindings: dict[str, str] = {}
    while True:
        m = re.search(r",?\s+where\s+([A-Za-z])(?:\(x\))?\s*=\s*", s)
        if not m:
            return s.strip().rstrip(","), bindings
        rest = s[m.end():]
        cut = re.search(r"\s+(?:is|the|for|with)\s+", rest)
        expr = (rest[:cut.start()] if cut else rest).strip().rstrip(".,")
        if not expr or m.group(1) in bindings:
            return s.strip().rstrip(","), bindings
        bindings[m.group(1)] = expr
        s = s[:m.start()]


def _substitute_bindings(body: str, bindings: dict[str, str]) -> str:
    for name, expr in bindings.items():
        body = re.sub(rf"\b{name}\(x\)", f"({expr})", body)
        body = re.sub(rf"\b{name}\b", f"({expr})", body)
    return body


def parse_definition(name: str) -> dict[str, Any] | None:
    """The entry's own definition, when it is a formula in the grammar:
    'a(n) = <expr>' (possibly recursive in a(n - i)), 'Expansion of <g.f. in x>',
    or the same with a one-letter `where X = <expr>` binding. An e.g.f. is the
    exponential generating function: a(n) = n! [x^n]. No fetched program is read.
    """
    s = re.split(r"[;]|\s+-\s+_", name)[0].strip().rstrip(".")
    s, bindings = _peel_where(s)
    s = re.sub(r",?\s*with\s+a\(\d+\)\s*=\s*-?\d+((\s*(,|and)\s*)a\(\d+\)\s*=\s*-?\d+)*\s*$", "", s)
    s = re.sub(r",?\s*(for )?n\s*>=?\s*\d+\s*$", "", s)
    egf = bool(re.match(r"^(?:Expansion of\s+)?e\.g\.f\b", s, re.I))
    m = re.match(
        r"^(?:Expansion of\s+)?(?:(?:e\.)?g\.f\.|ordinary generating function|exponential generating function)\s*:?\s*(.*)$",
        s, re.I,
    )
    if not m:
        m = re.match(r"^(?:Expansion of\s+)(.*)$", s)
    try:
        if m:
            body = _substitute_bindings(m.group(1), bindings)
            body = _ins_mul(body.replace("\u2212", "-").replace("Sqrt[", "sqrt(").replace("]", ")"))
            if re.search(r"[A-Za-wyz_]", body.replace("sqrt", "")):
                return None
            if "sqrt" in body or re.search(r"\^\(\s*-?\d+\s*/\s*2\s*\)", body):
                # algebraic (one square root): both series paths must agree on a prefix
                try:
                    a = _series_A(body, 24)
                    b = B.series_expr(B.compile_expr(body), 24)
                    if a != b or any(not isinstance(c, Fraction) or c.denominator != 1 for c in a):
                        return None
                except (B.Bad, ZeroDivisionError, TypeError, AttributeError, ValueError, RecursionError):
                    return None
                return {"kind": "egf" if egf else "alg", "expr": body}
            if egf:
                return {"kind": "egf", "expr": body}
            num, den = B.rational(B.compile_expr(body))
            return {"kind": "gf", "expr": body}
        m = re.match(r"^a\(n\)\s*=\s*(.*)$", s)
        if not m:
            return None
        body = m.group(1)
        if re.search(r"\bwhere\b|\bfor\b|Sum|Product|\.\.|[\[\]{}]|mod|sqrt|log|=", body):
            return None
        body = re.sub(r"\b(\w)!", r"fact(\1)", body)
        body = re.sub(r"\b(A\d{6})\(", lambda mm: ALIAS_SEQ.get(mm.group(1), mm.group(1)) + "(", body)
        body = _ins_mul(body)
        for nm in re.findall(r"[A-Za-z_]\w*", body):
            if nm not in ALLOWED_NAMES - {"x"}:
                return None
        B.compile_expr(body)
        rec = bool(re.search(r"\ba\(", body))
        lin = None
        if rec:
            try:
                L = B.linear(B.compile_expr(body))
                if all(k is None or isinstance(k, int) for k in L) and L.get(None, 0) == 0:
                    lin = {str(k): str(v) for k, v in L.items() if k is not None}
            except B.Bad:
                lin = None
        return {"kind": "rec" if rec else "closed", "expr": body, "linear": lin}
    except (B.Bad, Unparsed, SyntaxError):
        return None


def _extend_cfinite(
    defn: dict[str, Any],
    off: int,
    terms: list[int],
    N: int,
    seconds: float,
    bits: int,
) -> tuple[list[int] | None, str | None, int | float | None]:
    """Exact C-finite iteration. Returns (terms, cap_reason, cap_value).

    ``None`` for the terms means this method does not apply (caller falls back).
    """
    try:
        from colony import oeis_deep as D
        cf = D.cfinite(defn, off, terms)
    except Exception:
        return None, None, None
    hi = off + max(int(N), len(terms)) - 1
    t0 = time.time()
    try:
        xs = D.iter_exact(cf, hi, seconds=seconds, bits=bits)
    except Exception:
        return None, None, None
    s0 = int(cf.get("s0") or 0)
    out: list[int] = []
    for j in range(int(N)):
        n = off + j
        idx = n - s0
        if idx < 0 or idx >= len(xs):
            break
        try:
            out.append(int(xs[idx]))
        except (TypeError, ValueError):
            return None, None, None
    if len(out) < len(terms) or out[:len(terms)] != list(terms):
        return None, None, None
    reason: str | None = None
    value: int | float | None = None
    last_bits = abs(out[-1]).bit_length() if out else 0
    elapsed = time.time() - t0
    if len(out) < int(N):
        if last_bits > bits:
            reason, value = CAP_DIGIT, evaluator_caps()["deep_digits"]
        elif elapsed >= seconds:
            reason, value = CAP_TIME, seconds
        else:
            # iter_exact stops every 256 terms; treat a short stop at the
            # bit or time budget as those caps, otherwise as a term cap.
            if last_bits >= bits * 0.95:
                reason, value = CAP_DIGIT, evaluator_caps()["deep_digits"]
            elif elapsed >= seconds * 0.8:
                reason, value = CAP_TIME, seconds
            else:
                reason, value = CAP_TERM, int(N)
    return out, reason, value


def extend(defn: dict[str, Any], off: int, terms: list[int], N: int, path: str = "A",
           seconds: float | None = None, info: dict[str, Any] | None = None,
           entry: dict[str, Any] | None = None) -> list[int] | None:
    """Compute terms from the definition (initial values from the b-file for a recursion), require
    that they reproduce EVERY b-file term, then continue to N terms (time/size capped).

    When a C-finite exact iterator applies, the (higher) ``fast_term_cap`` is
    used: rational g.f. and constant-coefficient recurrences are cheap and
    integer-exact. Algebraic / EGF series stay on the slower path and the
    stricter ``gf_terms`` / digit / time caps.

    If ``info`` is provided it is filled with ``cap_reason``, ``cap_value``,
    ``computed_hi`` and the live caps. The return value is still the term
    list (or None), so existing callers are unchanged.
    """
    caps = evaluator_caps()
    if seconds is None:
        seconds = float(caps["deep_seconds"])
    bits = digit_bit_budget(caps["deep_digits"])
    term_cap = term_cap_for(entry, defn)
    want = min(max(int(N), len(terms)), int(term_cap))
    t0 = time.time()
    out: list[int] = []
    cap_reason: str | None = None
    cap_value: int | float | None = None

    used_fast = False
    if defn.get("kind") in ("gf", "rec"):
        got, cap_reason, cap_value = _extend_cfinite(defn, off, terms, want, seconds, bits)
        if got is not None:
            out = got
            used_fast = True

    if not used_fast and defn["kind"] in ("gf", "alg", "egf"):
        # Series path. Use the live (possibly lower) series cap so we do not
        # pre-expand thousands of EGF terms we will never scale past the
        # digit budget.
        series_cap = int(caps["fast_term_cap"] if defn["kind"] == "gf" else caps["gf_terms"])
        L = min(want, series_cap) + off + 2
        if defn["kind"] == "gf" and path != "A":
            num, den = B.rational(B.compile_expr(defn["expr"]))
            co = B.series(num, den, L)
        elif path == "A":
            co = _series_A(defn["expr"], L)
        else:
            co = B.series_expr(B.compile_expr(defn["expr"]), L)
        if defn["kind"] == "egf":
            # a(n) = n! [x^n] of the exponential generating function.
            fact = 1
            scaled: list[Fraction] = []
            for n, c in enumerate(co):
                if n:
                    fact *= n
                v = c * fact
                if v.denominator != 1:
                    return None
                if n > off + len(terms) and abs(int(v)).bit_length() > bits:
                    cap_reason, cap_value = CAP_DIGIT, caps["deep_digits"]
                    break
                if n > off + len(terms) and time.time() - t0 > seconds:
                    cap_reason, cap_value = CAP_TIME, seconds
                    break
                scaled.append(v)
            co = scaled
        if any(c.denominator != 1 for c in co):
            return None
        out = [int(c) for c in co[off:off + want]]
        if cap_reason is None and len(out) < want:
            if time.time() - t0 > seconds:
                cap_reason, cap_value = CAP_TIME, seconds
    elif not used_fast:
        e = _A(defn["expr"]) if path == "A" else B.compile_expr(defn["expr"])
        K = 0
        if defn["kind"] == "rec":
            K = max([int(k) for k in (defn.get("linear") or {})] + [0]) or 0
            if not defn.get("linear"):
                K = 8
        for j in range(want):
            n = off + j
            if j < K and j < len(terms):
                out.append(terms[j])
                continue

            def seq(nm, i, _o=out):
                if nm != "a" or i < off or i >= n:
                    raise B.Missing(nm)
                return _o[i - off]
            try:
                v = e.ev(e.tree, n, seq) if path == "A" else B.evaluate(e, {"n": n}, seq)
            except B.Missing:
                if j < len(terms):
                    out.append(terms[j])
                    continue
                return None
            except (B.Bad, ZeroDivisionError, OverflowError, ValueError):
                return None
            if v.denominator != 1:
                return None
            out.append(int(v))
            if j >= len(terms) and abs(out[-1]).bit_length() > bits:
                cap_reason, cap_value = CAP_DIGIT, caps["deep_digits"]
                break
            if j >= len(terms) and time.time() - t0 > seconds:
                cap_reason, cap_value = CAP_TIME, seconds
                break
    if len(out) < len(terms) or out[:len(terms)] != terms:
        if info is not None:
            info["cap_reason"] = cap_reason
            info["cap_value"] = cap_value
        return None
    out = out[:want]
    if cap_reason is None and (len(out) >= int(term_cap) or (want >= int(term_cap) and len(out) >= want)):
        cap_reason, cap_value = CAP_TERM, int(term_cap)
    if info is not None:
        info["cap_reason"] = cap_reason
        info["cap_value"] = cap_value
        info["computed_hi"] = (off + len(out) - 1) if out else 0
        info["n_terms"] = len(out)
        info["term_cap"] = int(term_cap)
        info["digit_cap"] = caps["deep_digits"]
        info["time_cap"] = seconds
        info["fast_cfinite"] = used_fast
    return out


def definition_reproduces(defn: dict[str, Any], off: int, terms: list[int], seconds: float = 6.0) -> bool:
    """Both vetted evaluators reproduce every stored term. No fetched code is run."""
    if not defn or not terms:
        return False
    got = extend(defn, off, list(terms), len(terms), "A", seconds=seconds)
    if got is None or got[:len(terms)] != list(terms):
        return False
    other = extend(defn, off, list(terms), len(terms), "B", seconds=seconds)
    return other is not None and other[:len(terms)] == list(terms)


def attach_verified_definitions(entries: list[dict[str, Any]]) -> list[str]:
    """Fill `definition` from the entry's own name when it reproduces the stored terms.

    Entries that already have a definition are left alone. A name that does not
    parse, or whose series disagrees with the stored terms, stays without one.
    """
    gained: list[str] = []
    for e in entries:
        if e.get("definition"):
            continue
        d = parse_definition(str(e.get("name") or ""))
        if not d:
            continue
        try:
            ok = definition_reproduces(d, int(e.get("offset") or 0), list(e.get("terms") or []))
        except (B.Bad, ZeroDivisionError, TypeError, ValueError, RecursionError, KeyError):
            ok = False
        if not ok:
            continue
        e["definition"] = d
        gained.append(str(e.get("id") or e.get("anum") or ""))
    return gained


# ----------------------------------------------------------------------------- the two actions


def _tables(e: dict[str, Any], terms: list[int] | None = None) -> Tables:
    tabs = {"a": (e["offset"], terms if terms is not None else e["terms"])}
    for k, v in (e.get("refs") or {}).items():
        tabs[k] = (v["offset"], v["terms"])
    return Tables(tabs)


def _fetch_b(anum: str) -> tuple[int, list[int]] | None:
    """Fresh b-file read for path B (cache or polite network via colony.new_data.Net)."""
    try:
        from colony import new_data as N
        txt = N.Net().get(f"https://oeis.org/{anum}/b{anum[1:]}.txt", f"b{anum[1:]}.txt")
    except Exception:  # noqa: BLE001
        return None
    if not txt:
        return None
    pairs = []
    for ln in txt.splitlines():
        p = ln.split("#")[0].split()
        if len(p) >= 2 and re.fullmatch(r"-?\d+", p[0]) and re.fullmatch(r"-?\d+", p[1]):
            pairs.append((int(p[0]), int(p[1])))
    if not pairs:
        return None
    o = pairs[0][0]
    xs = []
    for i, (k, v) in enumerate(pairs):
        if k != o + i:
            break
        xs.append(v)
    return o, xs


def _annotate_attempt_cap(
    e: dict[str, Any],
    res: dict[str, Any],
    deep: list[int] | None,
    cap_info: dict[str, Any] | None,
) -> None:
    """Record the physical cap that stopped this attempt, if any.

    A referenced-b-file ceiling binds first: we may have computed many a(n)
    terms, but the claim itself could only be tested up to the refs. Otherwise
    take the cap reported by ``extend``. Does not overwrite an already-set
    reason (e.g. from ``_deep``).
    """
    if res.get("cap_reason"):
        return
    verified = 0
    rng = res.get("range") or [0, 0]
    if isinstance(rng, (list, tuple)) and len(rng) > 1:
        try:
            verified = int(rng[1] or 0)
        except (TypeError, ValueError):
            verified = 0
    try:
        verified = max(verified, int(res.get("deep_hi") or 0))
    except (TypeError, ValueError):
        pass
    refs_hi = _ref_limited_hi(e)
    if refs_hi is not None and verified >= refs_hi:
        res["cap_reason"] = CAP_REF
        res["cap_value"] = int(refs_hi)
        return
    if cap_info and cap_info.get("cap_reason"):
        res["cap_reason"] = cap_info["cap_reason"]
        res["cap_value"] = cap_info.get("cap_value")
        if cap_info.get("fast_cfinite") is not None:
            res["fast_cfinite"] = cap_info["fast_cfinite"]
        return
    # Evaluator produced no more than the last verified n, and we planned
    # further: treat as a physical cap of unknown kind only when a planned
    # depth is on the result (filled later by remember_attempt).
    return


def attempt_disprove(e: dict[str, Any], prior_hi: int | None = None, fetch: bool = True) -> dict[str, Any]:
    if not e.get("definition"):
        try:
            defn = computable_definition(e)
        except Exception:
            defn = None
        if defn:
            e = dict(e)
            e["definition"] = defn
    claim = e["claim"]
    off, terms = e["offset"], e["terms"]
    data_hi = off + int(e.get("data_n") or 0) - 1
    deep = None
    cap_info: dict[str, Any] = {}
    if e.get("definition"):
        # Past the published terms, from the vetted definition. A g.f. claim is
        # included: the longer table is what test_claim compares the claim to.
        want = term_cap_for(e)
        deep = extend(e["definition"], off, terms, want, "A", info=cap_info, entry=e)
    tA = test_claim(claim, _tables(e, deep or terms), "A")
    res: dict[str, Any] = {"action": "attempt_disprove", "id": e["id"], "anum": e["anum"], "tested": tA["tested"],
                           "range": [tA["lo"], tA["hi"]], "deep_terms": len(deep) if deep else 0,
                           "bfile_terms": len(terms), "bfile_hi": max(off + len(terms) - 1, e.get("published_hi") or 0), "data_hi": data_hi, "status": "holds_on_range"}
    if tA["tested"] < MIN_TESTED:
        res["status"] = "untestable_here"
        _annotate_attempt_cap(e, res, deep, cap_info)
        return res
    if tA["first_fail"] is None:
        _deep(e, tA, res, deep)
        top = max(tA["hi"] or 0, res.get("deep_hi") or 0)
        res["extended"] = max(0, top - max(prior_hi or 0, data_hi, off + len(terms) - 1))
        _annotate_attempt_cap(e, res, deep, cap_info)
        return res
    res["fails_A"] = tA["fails"]
    res["holds_from"] = tA["holds_from"]
    if tA["first_fail"] <= data_hi:
        res["status"] = "fails_in_data"   # terms the author saw: a misparse or an unstated initial condition
        return res
    # path B: own parser/evaluator, fresh b-files, own recomputation of any extended terms
    tabs = {}
    fb = _fetch_b(e["anum"]) if fetch else None
    o, xs = fb if fb else (off, terms)
    res["b_source"] = "fresh b-file" if fb else "menu terms (fresh fetch unavailable)"
    if deep and len(deep) > len(xs):
        dB = extend(e["definition"], o, xs, len(deep), "B",
                    seconds=float(evaluator_caps()["deep_seconds"]) * 3, entry=e)
        if dB is None or dB[:len(deep)] != deep[:len(dB)]:
            res["status"] = "path_disagreement"
            return res
        xs = dB
    tabs["a"] = (o, xs[:len(deep or terms)])  # same index range as path A
    for k, v in (e.get("refs") or {}).items():
        fr = _fetch_b(k) if fetch else None
        tabs[k] = fr if fr else (v["offset"], v["terms"])
    tB = test_claim(claim, Tables(tabs), "B")
    res["fails_B"] = tB["fails"]
    if tB["first_fail"] == tA["first_fail"] and tB["fails"][:1] == tA["fails"][:1]:
        res["status"] = "counterexample_verified"
        res["counterexample_n"] = tA["first_fail"]
    else:
        res["status"] = "path_disagreement"
    return res


_GEN_CACHE: dict[str, Any] = {}


def _deep(e: dict[str, Any], tA: dict[str, Any], res: dict[str, Any], deep) -> None:
    """Beyond-b-file search with the fast evaluators (colony.oeis_deep), after the definition has been
    re-checked against the WHOLE b-file. Sets deep_* fields; a failure needs path B to agree."""
    from colony import oeis_deep as D
    from colony import oeis_guess as G
    d = e.get("definition") or {}
    claim = e["claim"]
    if not d or claim["form"] == "gf":
        return
    off, terms = e["offset"], e["terms"]
    key = e["id"]
    if key not in _GEN_CACHE:
        g = None
        if d.get("kind") == "alg":
            cr = G.certified_recurrence(d["expr"], off, terms)
            if cr:
                g = D.Holo(cr, off)
                res["definition_recurrence"] = {"text": cr["text"], "certificate": cr["certificate"]}
        else:
            g = D.generator(e)
        if g is not None and not D.matches_bfile(g, off, terms):
            res["deep_note"] = "definition does not reproduce the b-file; no deep search"
            g = None
        _GEN_CACHE[key] = g
    g = _GEN_CACHE[key]
    if g is None:
        return
    bh = max(off + len(terms) - 1, e.get("published_hi") or 0)   # the published range, even if stored terms stop earlier
    lo = max(tA["hi"] or 0, bh) + 1
    parts = claim.get("parts") or []
    evA = [_A(p) for p in parts]
    evB = [B.compile_expr(p) for p in parts]
    out = D.deep_search(g, claim, lo, float(evaluator_caps()["deep_seconds"]),
                        lambda k, n, sq: evA[k].ev(evA[k].tree, n, sq),
                        lambda k, n, sq: B.evaluate(evB[k], {"n": n}, sq))
    res["deep_mode"] = out.get("mode")
    res["deep_hi"] = out.get("hi")
    if out.get("fail_n") is not None:
        if out.get("path_b"):
            res["status"] = "counterexample_verified"
            res["counterexample_n"] = out["fail_n"]
            res["fails_A"] = [{"n": out["fail_n"], "modulus": out.get("modulus")}]
            res["fails_B"] = [{"n": out["fail_n"], "path": "independent recomputation (Kitamasa / Fraction recurrence)"}]
            res["b_source"] = "recomputed from the definition"
        else:
            res["status"] = "path_disagreement"
        res["deep_fail_n"] = out["fail_n"]


def attempt_prove(e: dict[str, Any]) -> dict[str, Any]:
    from colony import proof_check as PC
    res: dict[str, Any] = {"action": "attempt_prove", "id": e["id"], "anum": e["anum"], "status": "no_method"}
    d = e.get("definition")
    claim = e["claim"]
    if d and d["kind"] in ("gf", "alg") and claim["form"] == "relation" and not claim.get("mod") \
            and claim["rels"] == ["="] and len(claim["parts"]) == 2:
        try:
            PC.holonomic_form(claim["parts"], claim["rels"])
            holo = d["kind"] == "alg" or "n" in re.sub(r"a\([^()]*\)", "", " ".join(claim["parts"]))
        except (ValueError, TypeError, SyntaxError, Exception):  # noqa: BLE001
            holo = False
        if holo:
            cert = {"type": "holonomic_identity", "definition": d, "offset": e["offset"], "claim": claim,
                    "anum": e["anum"], "def_text": e["name"]}
            ok, why = PC.check_oeis(cert, e["terms"])
            res.update({"status": "proved_checked" if ok else "proof_rejected", "checker": why, "cert": cert})
            return res
    if not d or not (d["kind"] == "gf" or (d["kind"] == "rec" and d.get("linear"))):
        res["why"] = "definition is not C-finite or algebraic in the grammar"
        return res
    if claim["form"] == "gf":
        ctype = "gf_identity"
    elif claim["form"] == "relation" and not claim.get("mod") and all(r == "=" for r in claim["rels"]):
        ctype = "cfinite_identity"
    else:
        res["why"] = "claim form has no proof method (%s)" % claim["form"]
        return res
    cert = {"type": ctype, "definition": d, "offset": e["offset"], "claim": claim, "anum": e["anum"],
            "def_text": e["name"]}
    ok, why = PC.check_oeis(cert, e["terms"])
    res.update({"status": "proved_checked" if ok else "proof_rejected", "checker": why, "cert": cert})
    return res


# ----------------------------------------------------------------------------- menu, choice, credit, cycle


def load_menu() -> list[dict[str, Any]]:
    try:
        return json.loads(MENU.read_text()).get("entries") or []
    except (OSError, ValueError):
        return []


def _load(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def provable(e: dict[str, Any]) -> bool:
    d = e.get("definition") or {}
    return bool(d) and (d.get("kind") in ("gf", "alg") or bool(d.get("linear"))) and e["claim"]["form"] in ("gf", "relation")


def routine_holonomic(e: dict[str, Any]) -> bool:
    """A relation-form D-finite recurrence the holonomic checker already handles.

    Named by the form and the definition, not by any one author or sequence.
    """
    form = ((e.get("claim") or {}).get("form") or "")
    return bool(provable(e) and form == "relation")



def _empty_attempt_log() -> dict[str, Any]:
    return {"attempts": [], "by_cycle": {}, "last_forms": []}


def _load_raw_attempt_log() -> dict[str, Any]:
    raw = _load(ATTEMPT_LOG, _empty_attempt_log())
    if not isinstance(raw, dict):
        return _empty_attempt_log()
    raw.setdefault("attempts", [])
    raw.setdefault("by_cycle", {})
    raw.setdefault("last_forms", [])
    return raw


def _tested_and_scoreboard() -> tuple[dict[str, int], dict[str, int]]:
    """Current tested_hi and scoreboard extension ``to``, keyed by target id.

    Used only to derive a verified_depth view of legacy rows. Never written
    back into the committed log.
    """
    tested: dict[str, int] = {}
    score: dict[str, int] = {}
    try:
        st = _load(STATE, {})
        for eid, rec in (st.get("targets") or {}).items():
            if not isinstance(rec, dict):
                continue
            try:
                tested[str(eid)] = int(rec.get("tested_hi") or 0)
            except (TypeError, ValueError):
                pass
        for eid, rec in ((st.get("scoreboard") or {}).get("extensions") or {}).items():
            if not isinstance(rec, dict):
                continue
            try:
                score[str(eid)] = int(rec.get("to") or 0)
            except (TypeError, ValueError):
                pass
    except Exception:
        pass
    return tested, score


def attempt_log_view(log: dict[str, Any] | None) -> dict[str, Any]:
    """Derived view: legacy rows gain ``verified_depth`` (and an inferred cap
    when one can be read off the row). The committed file is not written.
    """
    src = log if isinstance(log, dict) else _empty_attempt_log()
    tested, score = _tested_and_scoreboard()
    out = dict(src)
    attempts: list[dict[str, Any]] = []
    for row in src.get("attempts") or []:
        if not isinstance(row, dict):
            attempts.append(row)  # type: ignore[arg-type]
            continue
        r = dict(row)
        if "verified_depth" not in r:
            eid = str(r.get("id") or "")
            th = max(tested.get(eid, 0), score.get(eid, 0))
            r["verified_depth"] = attempt_row_verified_depth(r, th)
            r["verified_depth_derived"] = True
        if not r.get("cap_reason"):
            reason, val = infer_cap_reason(r, None)
            if reason:
                r["cap_reason"] = reason
                r["cap_value"] = val
                r["cap_reason_derived"] = True
        attempts.append(r)
    out["attempts"] = attempts
    return out


def _strip_derived_attempt_log(log: dict[str, Any]) -> dict[str, Any]:
    """Drop derived-only fields so a save cannot rewrite legacy rows."""
    out = dict(log)
    attempts = []
    for row in log.get("attempts") or []:
        if not isinstance(row, dict):
            attempts.append(row)
            continue
        r = dict(row)
        if r.pop("verified_depth_derived", None):
            r.pop("verified_depth", None)
        if r.pop("cap_reason_derived", None):
            r.pop("cap_reason", None)
            r.pop("cap_value", None)
        attempts.append(r)
    out["attempts"] = attempts
    return out


def load_attempt_log(*, derived: bool = True) -> dict[str, Any]:
    """Load the attempt log. By default return a derived view that fills
    ``verified_depth`` on legacy rows from recorded holds / the scoreboard.

    Writers must pass ``derived=False`` (or rely on ``save_attempt_log``
    stripping derived fields) so the committed file is never rewritten.
    """
    raw = _load_raw_attempt_log()
    if derived:
        return attempt_log_view(raw)
    return raw


def save_attempt_log(log: dict[str, Any]) -> None:
    cleaned = _strip_derived_attempt_log(log)
    ATTEMPT_LOG.parent.mkdir(parents=True, exist_ok=True)
    tmp = ATTEMPT_LOG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cleaned, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(ATTEMPT_LOG)


def computable_definition(e: dict[str, Any]) -> dict[str, Any] | None:
    """A vetted, already-verified definition that can be evaluated, or None.

    Uses the entry's own ``definition`` when present. For a g.f. claim whose
    definition was never attached, the claim's own expression is tried: both
    evaluators must reproduce the stored b-file. No fetched code is run.
    """
    d = e.get("definition")
    if isinstance(d, dict) and (d.get("kind") or d.get("expr")):
        return d
    claim = e.get("claim") or {}
    expr = (claim.get("expr") or "").strip()
    if claim.get("form") == "gf" and expr:
        cand = {"kind": "gf", "expr": expr}
        try:
            if definition_reproduces(cand, int(e.get("offset") or 0), list(e.get("terms") or [])):
                return cand
        except (B.Bad, ZeroDivisionError, TypeError, ValueError, RecursionError, KeyError, OverflowError):
            return None
    return None


def bfile_hi_of(e: dict[str, Any]) -> int:
    off = int(e.get("offset") or 0)
    n = len(e.get("terms") or [])
    return max(off + n - 1 if n else 0, int(e.get("published_hi") or 0), off + int(e.get("data_n") or 0) - 1 if e.get("data_n") else 0)


def can_search_past_bfile(e: dict[str, Any]) -> bool:
    """True when a verified computable definition can be run past the published terms."""
    if not computable_definition(e):
        return False
    form = str((e.get("claim") or {}).get("form") or "")
    # g.f. identities are extended by series arithmetic; relations, properties
    # and only_prime claims use the fast recurrence / deep search.
    return form in ("gf", "relation", "property", "only_prime", "congruence", "inequality") or bool(form)


def planned_depth(e: dict[str, Any], prior_hi: int | None = None) -> int:
    """The depth the next attempt would reach.

    With a computable definition this is past the b-file (capped by the
    series/deep evaluators). Without one it is only the published range.
    """
    bh = bfile_hi_of(e)
    prior = int(prior_hi or 0)
    if can_search_past_bfile(e):
        # Live term cap: fast C-finite cap when available, otherwise the
        # series / deep caps. planned_depth is what we will ask for, not a
        # promise the evaluator will reach it (digit/time may stop earlier).
        cap = term_cap_for(e)
        advertised = claim_testable_hi(e)
        target = min(cap, advertised) if advertised else cap
        return max(bh, prior, target, bh + 1)
    return max(bh, prior)


def verified_depth(e: dict[str, Any], acts: list[dict[str, Any]] | None = None) -> int:
    """Highest n at which the claim was actually tested, from attempt results.

    This is the verified range, not the depth the attempt was asked to reach.
    Computed ``deep_terms`` that were not used in a claim test do not count.
    """
    off = int(e.get("offset") or 0)
    top = 0
    for r in acts or []:
        if not isinstance(r, dict):
            continue
        rng = r.get("range") or [0, 0]
        hi = 0
        if isinstance(rng, (list, tuple)) and len(rng) > 1:
            try:
                hi = int(rng[1] or 0)
            except (TypeError, ValueError):
                hi = 0
        try:
            deep_hi = int(r.get("deep_hi") or 0)
        except (TypeError, ValueError):
            deep_hi = 0
        try:
            tested = int(r.get("tested") or 0)
        except (TypeError, ValueError):
            tested = 0
        tested_n = (off + tested - 1) if tested else 0
        top = max(top, hi, deep_hi, tested_n)
    return int(top)


_ANUM = re.compile(r"A\d{6,}")
_ANUM_REF = re.compile(r"(A\d{6,})\(\s*n\s*([+-]\s*\d+)?\s*\)")


def _ref_hi(e: dict[str, Any], anum: str) -> int | None:
    refs = e.get("refs") or {}
    info = refs.get(anum) or refs.get(anum.upper() if anum else "") or refs.get(anum.lower() if anum else "")
    if not isinstance(info, dict):
        return None
    terms = info.get("terms") or []
    if not terms:
        return None
    off = int(info.get("offset") or 0)
    return off + len(terms) - 1


def _parts_text(e: dict[str, Any]) -> str:
    claim = e.get("claim") or {}
    parts = claim.get("parts") or []
    return " ".join(str(p) for p in parts) + " " + str(claim.get("expr") or "")


def _ref_shift(parts_text: str, anum: str) -> int:
    """Largest index offset the claim needs for ``anum``: A012345(n+1) is 1."""
    shift = 0
    for m in _ANUM_REF.finditer(parts_text or ""):
        if m.group(1) == anum:
            if m.group(2):
                s = int(re.sub(r"\s+", "", m.group(2)))
                if s > shift:
                    shift = s
    return shift


def claim_testable_hi(e: dict[str, Any]) -> int:
    """Highest n at which the claim can actually be evaluated with current data.

    A computable definition extends a(n), but a relation that names other
    A-numbers is limited by those referenced b-files (refs currently carry
    terms only). This is a bound on what can be tested, not a promise that
    the evaluator will reach it (time and digit caps may stop earlier).
    """
    off = int(e.get("offset") or 0)
    terms = list(e.get("terms") or [])
    a_hi = (off + len(terms) - 1) if terms else 0
    try:
        defn = computable_definition(e)
    except Exception:
        defn = None
    claim = e.get("claim") or {}
    form = str(claim.get("form") or "")
    if defn:
        cap = term_cap_for(e, defn)
        a_extend = max(a_hi, cap)
    else:
        a_extend = a_hi
    text = _parts_text(e)
    anums = set(_ANUM.findall(text))
    anums.discard(str(e.get("anum") or ""))
    limit = a_extend
    for anum in anums:
        rh = _ref_hi(e, anum)
        if rh is None:
            limit = min(limit, a_hi)
            continue
        shift = _ref_shift(text, anum)
        limit = min(limit, rh - shift)
    return int(max(limit, 0))


def _last_attempt_row(eid: str, log: dict[str, Any] | None = None) -> dict[str, Any] | None:
    eid = str(eid or "")
    if not eid:
        return None
    log = log if log is not None else load_attempt_log()
    for row in reversed(log.get("attempts") or []):
        if str(row.get("id") or "") == eid and isinstance(row, dict):
            return row
    return None


def _is_legacy_attempt_row(row: dict[str, Any] | None) -> bool:
    """True when a row predates the planned/verified split (PR #4).

    Those rows stored the *requested* depth in ``depth`` and have no
    ``planned`` or ``verified_depth`` marker. Treating that ``depth`` as
    already verified is what emptied the eligible pool (item 28).
    """
    if not isinstance(row, dict):
        return False
    return "planned" not in row and "verified_depth" not in row


def _tested_hi_from_state(
    eid: str,
    e: dict[str, Any] | None = None,
    prior_hi: int | None = None,
) -> int:
    """Verified high-water mark from a caller, the entry, or conjecture state."""
    if prior_hi is not None:
        try:
            return int(prior_hi or 0)
        except (TypeError, ValueError):
            return 0
    if isinstance(e, dict) and e.get("tested_hi") is not None:
        try:
            return int(e.get("tested_hi") or 0)
        except (TypeError, ValueError):
            pass
    eid = str(eid or "")
    if not eid:
        return 0
    try:
        st = (_load(STATE, {}).get("targets") or {}).get(eid) or {}
        return int(st.get("tested_hi") or 0)
    except Exception:
        return 0


def attempt_row_verified_depth(row: dict[str, Any] | None, tested_hi: int | None = 0) -> int:
    """Verified depth of an attempt-log row, without rewriting the log.

    Post-PR #4 rows have a ``planned`` field (``depth`` is the verified
    range) or an explicit ``verified_depth``. Legacy rows stored the
    requested window in ``depth``; for those, verified depth is
    ``min(depth, tested_hi)`` when ``tested_hi`` is known, and the
    requested depth is ignored otherwise.
    """
    try:
        th = int(tested_hi or 0)
    except (TypeError, ValueError):
        th = 0
    if not isinstance(row, dict):
        return th
    if "verified_depth" in row:
        try:
            return int(row.get("verified_depth") or 0)
        except (TypeError, ValueError):
            return th
    if "planned" in row:
        try:
            return int(row.get("depth") or 0)
        except (TypeError, ValueError):
            return 0
    try:
        requested = int(row.get("depth") or 0)
    except (TypeError, ValueError):
        requested = 0
    if th > 0:
        return min(requested, th) if requested else th
    return 0


def attempt_row_planned_depth(row: dict[str, Any] | None) -> int:
    """Requested depth on a post-PR #4 row. 0 for a legacy row.

    A legacy ``depth`` is the request, but it must not be used as an
    "already aimed this far" ceiling: the attempt may never have reached
    it, and a retry past ``tested_hi`` is exactly what item 28 asks for.
    """
    if not isinstance(row, dict) or "planned" not in row:
        return 0
    try:
        return int(row.get("planned") or 0)
    except (TypeError, ValueError):
        return 0


def can_progress_past(
    e: dict[str, Any],
    prior_hi: int | None = None,
    log: dict[str, Any] | None = None,
    *,
    require_past_published: bool = False,
) -> bool:
    """True if a new attempt could verify the claim past the range already held.

    For a never-attempted entry this is True when there are terms to test,
    or, with ``require_past_published``, when the claim can be tested past
    the published b-file. After a hold it is True only if the claim is
    actually evaluable past ``max(bfile_hi, tested_hi)`` and a prior attempt
    has not already hit a physical evaluator cap (term, digit, time, or
    ref-limited) with the same caps. A planned depth that was never
    reached does not close the target. When a recorded cap is later
    raised, the target is eligible again. Legacy attempt-log rows (no
    ``planned`` / ``verified_depth``) do not treat their requested
    ``depth`` as already verified.
    """
    eid = str(e.get("id") or "")
    try:
        log = log if log is not None else load_attempt_log()
    except Exception:
        log = _empty_attempt_log()
    bh = bfile_hi_of(e)
    last = _last_attempt_row(eid, log) if eid else None
    # A missing prior_hi means "not supplied", except when a legacy row
    # needs conjecture-state tested_hi to interpret its requested depth.
    entry_hi = None
    if isinstance(e, dict) and e.get("tested_hi") is not None:
        entry_hi = e.get("tested_hi")
    if prior_hi is not None:
        tested = _tested_hi_from_state(eid, e, prior_hi)
    elif entry_hi is not None:
        tested = _tested_hi_from_state(eid, e, entry_hi)
    elif _is_legacy_attempt_row(last):
        tested = _tested_hi_from_state(eid, e, None)
    else:
        tested = 0
    last_v = attempt_row_verified_depth(last, tested)
    last_planned = attempt_row_planned_depth(last)
    current = max(tested, last_v)
    advertised = claim_testable_hi(e)
    # What this cycle can actually compute. A prior physical cap at the
    # same (or tighter) caps is a real ceiling: do not advertise the
    # planned DEEP_N / GF_TERMS headroom the evaluator does not have.
    # When that cap is raised, the target becomes eligible again.
    reachable = advertised
    if last is not None and last_v > 0:
        reason, _cap_val = cap_of_row(last, e)
        if reason and not cap_has_been_raised(last, e):
            # Same physical ceiling as last time: we will re-hold at last_v.
            reachable = min(reachable, last_v)
    never = last is None and tested == 0
    bar = max(bh, current)
    if never:
        if require_past_published:
            return advertised > bh
        return advertised > 0 or bool(e.get("terms"))
    # A same-depth hold is not progress, and a planned depth that was
    # never actually reached is not a reason to mark the target done.
    return reachable > bar


def already_attempted_pair(eid: str, depth: int, cycle_id: str = "", log: dict[str, Any] | None = None) -> bool:
    """True when this (conjecture, depth) was already tried, or this id already this cycle.

    ``depth`` is what the next attempt would aim at. A prior row matches if
    its verified depth equals that, if it already reached at least that far,
    or if it already aimed at least that far (the ``planned`` field). Legacy
    rows without ``planned`` do not treat requested ``depth`` as either.
    """
    eid = str(eid or "")
    if not eid:
        return False
    log = log if log is not None else load_attempt_log()
    if cycle_id and eid in set(log.get("by_cycle", {}).get(cycle_id) or []):
        return True
    want = int(depth or 0)
    tested_cache: int | None = None
    for row in log.get("attempts") or []:
        if str(row.get("id") or "") != eid:
            continue
        if _is_legacy_attempt_row(row):
            if tested_cache is None:
                tested_cache = _tested_hi_from_state(eid)
            verified = attempt_row_verified_depth(row, tested_cache)
        else:
            verified = attempt_row_verified_depth(row, 0)
        planned = attempt_row_planned_depth(row)
        if want and verified >= want:
            return True
        if verified == want:
            return True
        if want and (planned == want or planned >= want):
            # A planned depth that was not actually reached because a
            # physical cap was hit must not block a later retry, especially
            # once that cap has been raised.
            reason, _ = cap_of_row(row, None)
            if reason and verified < planned:
                continue
            return True
    return False


def held_on_published_only(eid: str, e: dict[str, Any] | None = None, log: dict[str, Any] | None = None) -> bool:
    """True when a prior attempt already held on the published range and cannot go past it."""
    log = log if log is not None else load_attempt_log()
    bh = bfile_hi_of(e) if e is not None else None
    past_possible = can_search_past_bfile(e) if e is not None else False
    for row in reversed(log.get("attempts") or []):
        if str(row.get("id") or "") != str(eid):
            continue
        if row.get("status") != "holds_on_range":
            continue
        if past_possible:
            # A published-range hold is not a reason to skip if the next
            # attempt would actually go past that range.
            if int(row.get("depth") or 0) <= int(row.get("bfile_hi") or bh or 0) and planned_depth(e) > int(row.get("bfile_hi") or bh or 0):
                return False
            # Already searched past, at the planned depth: treat as done at that depth
            # (already_attempted_pair handles the exact pair).
            return False
        return True
    return False


def remember_attempt(
    e: dict[str, Any],
    acts: list[dict[str, Any]],
    cycle_id: str,
    planned: int | None = None,
) -> dict[str, Any]:
    """Record (conjecture, verified-depth) pairs actually attempted. Shadow and live.

    ``depth`` and ``beyond`` reflect the range that was verified, not the
    depth the attempt was asked to reach. The requested depth is stored
    separately as ``planned`` when the caller provides it.
    """
    log = load_attempt_log(derived=False)
    eid = str(e.get("id") or "")
    form = str((e.get("claim") or {}).get("form") or "")
    bh = bfile_hi_of(e)
    prior_th = _tested_hi_from_state(eid, e, None)
    by = log.setdefault("by_cycle", {})
    cycle_ids = list(by.get(cycle_id) or [])
    if eid and eid not in cycle_ids:
        cycle_ids.append(eid)
        by[cycle_id] = cycle_ids[-40:]
    # Keep a bounded map of recent cycles.
    if len(by) > 80:
        for old in list(by.keys())[:-80]:
            by.pop(old, None)
    for r in acts or [{}]:
        # Always record the verified range, not the requested (planned) depth.
        verified = verified_depth(e, [r] if isinstance(r, dict) else [])
        if verified <= 0:
            verified = bh
        beyond = int(verified or 0) > bh
        rec: dict[str, Any] = {
            "id": eid,
            "anum": e.get("anum"),
            "form": form,
            "depth": int(verified or 0),
            "bfile_hi": bh,
            "beyond": beyond,
            "status": str((r or {}).get("status") or ""),
            "cycle_id": cycle_id,
        }
        if planned is not None:
            rec["planned"] = int(planned)
        # Marker so a future reader can tell this ``depth`` is verified,
        # even when the caller omitted ``planned``. Existing rows are
        # never rewritten (no data churn).
        rec["verified_depth"] = int(verified or 0)
        rec["prior_tested_hi"] = int(prior_th or 0)
        if isinstance(r, dict):
            ext = r.get("extended")
            if ext is not None:
                try:
                    rec["extended"] = max(0, int(ext))
                except (TypeError, ValueError):
                    rec["extended"] = max(0, int(verified or 0) - int(prior_th or 0))
            else:
                rec["extended"] = max(0, int(verified or 0) - int(prior_th or 0))
            if r.get("cap_reason"):
                rec["cap_reason"] = r["cap_reason"]
                rec["cap_value"] = r.get("cap_value")
            if r.get("fast_cfinite") is not None:
                rec["fast_cfinite"] = r["fast_cfinite"]
            if r.get("deep_terms") is not None:
                rec["deep_terms"] = r.get("deep_terms")
        log["attempts"].append(rec)
    log["attempts"] = log["attempts"][-400:]
    if form:
        last = list(log.get("last_forms") or [])
        last.append(form)
        log["last_forms"] = last[-20:]
    save_attempt_log(log)
    return log


def choose_open(
    cycle_id: str,
    k: int = PICKS,
    menu: list[dict[str, Any]] | None = None,
    *,
    forms: set[str] | None = None,
    beyond_bfile: bool = False,
    state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Open menu entries, already filtered for repeat (id, depth) pairs."""
    menu = list(menu) if menu is not None else load_menu()
    state = state if state is not None else _load(STATE, {"targets": {}, "families": {}, "credit_total": 0.0})
    return choose(menu, state, cycle_id, k, forms=forms, beyond_bfile=beyond_bfile)


def desk_attempt(e: dict[str, Any], cycle_id: str, *, fetch: bool = False) -> list[dict[str, Any]]:
    """One prove / past-b-file disprove attempt, with held-out tail when possible.

    Records the (conjecture, depth) pair so a later call this cycle, or a
    later cycle at the same depth, will skip it. Does not touch the Oracle.
    """
    entry = dict(e)
    defn = computable_definition(entry)
    if defn and not entry.get("definition"):
        entry["definition"] = defn
    depth = planned_depth(entry)
    prior = entry.get("tested_hi")
    if already_attempted_pair(str(entry.get("id") or ""), depth, cycle_id):
        return []
    if held_on_published_only(str(entry.get("id") or ""), entry) and not can_search_past_bfile(entry):
        return []
    # A prior hold that cannot actually be tested past its verified range
    # is not retried. First attempts (no log, no prior_hi) still run.
    if not can_progress_past(entry, prior):
        return []
    # Held-out tail: reserve the last slice of published terms and confirm
    # the definition still reproduces them. The attempt itself may then
    # search past the b-file. This is a check, not an Oracle verdict.
    terms = list(entry.get("terms") or [])
    if defn and len(terms) >= 16:
        hold = max(8, len(terms) // 5)
        tail = terms[-hold:]
        head = terms[:-hold]
        tail_off = int(entry.get("offset") or 0) + len(head)
        try:
            if not definition_reproduces(defn, tail_off, tail):
                # Definition failed the held-out tail: still run the attempt
                # (the two-path checker is the authority) but note it.
                entry = dict(entry)
                entry["held_out_tail_ok"] = False
            else:
                entry["held_out_tail_ok"] = True
        except Exception:
            pass
    acts: list[dict[str, Any]] = []
    # Prefer a search that can go past the b-file when a definition exists.
    past = can_search_past_bfile(entry)
    if (not past) and provable(entry) and (entry.get("claim") or {}).get("form") != "relation":
        acts.append(attempt_prove(entry))
    if past or not acts or acts[-1].get("status") != "proved_checked":
        if past and provable(entry) and (entry.get("claim") or {}).get("form") != "relation":
            # A g.f. identity can also be proved; try that first, then search past.
            try:
                acts.append(attempt_prove(entry))
            except Exception:
                pass
            if acts and acts[-1].get("status") == "proved_checked":
                remember_attempt(entry, acts, cycle_id, planned=depth)
                return acts
        acts.append(attempt_disprove(entry, prior, fetch=fetch))
    remember_attempt(entry, acts, cycle_id, planned=depth)
    return acts


def choose(
    menu: list[dict[str, Any]],
    state: dict[str, Any],
    cycle_id: str,
    k: int = PICKS,
    *,
    forms: set[str] | None = None,
    beyond_bfile: bool = False,
) -> list[dict[str, Any]]:
    """The colony's own choice: open targets scored by tractability and its credit history per form
    (a bandit (credit+1)/(attempts+2)), with an exploration bonus for untried targets; sampled
    without replacement with a cycle-seeded rng.

    ``forms`` keeps only those claim forms. ``beyond_bfile`` keeps computable claims whose
    search can run past the published terms (g.f., relation, property, only_prime, and any
    other form with a verified definition). A (conjecture, depth) pair already attempted is
    skipped; a target that held only on its published range is not picked again unless the
    new attempt would actually test past that range (a definition of a(n) is not enough
    if referenced sequences cannot be evaluated there). At most one attempt per target per cycle. Forms
    and targets rotate so the same zero-credit family is not retried first every call.
    """
    tg = state.get("targets", {})
    fam = state.get("families", {})
    rng = random.Random(int(hashlib.sha256(cycle_id.encode()).hexdigest()[:12], 16))
    try:
        log = load_attempt_log()
    except Exception:
        log = _empty_attempt_log()
    recent_forms = list(log.get("last_forms") or [])
    last_form = recent_forms[-1] if recent_forms else ""
    scored = []
    for e in menu:
        eid = e.get("id")
        if not eid:
            continue
        st = tg.get(eid, {})
        if st.get("status") in ("counterexample_verified", "proved_checked", "fails_in_data", "untestable_here"):
            continue
        form = (e.get("claim") or {}).get("form") or ""
        if forms is not None and form not in forms:
            continue
        past = can_search_past_bfile(e)
        if beyond_bfile and not past:
            continue
        depth = planned_depth(e, st.get("tested_hi"))
        if already_attempted_pair(eid, depth, cycle_id, log):
            continue
        # Held on the published range and the next attempt would not go past it.
        if held_on_published_only(eid, e, log) and not (past and depth > bfile_hi_of(e)):
            continue
        # Skip a target that already held and cannot be tested any further
        # (refs exhausted, no definition, or a prior attempt already hit the
        # evaluator ceiling). beyond_bfile requires a real search past the
        # published range, not just a computable a(n) definition.
        if not can_progress_past(
            e, st.get("tested_hi"), log, require_past_published=beyond_bfile,
        ):
            continue
        f = fam.get(form, {})
        bandit = (f.get("credit", 0.0) + 1.0) / (f.get("attempts", 0) + 2.0)
        # Do not boost already-provable relation recurrences; they run after
        # zero-credit families and other beyond-b-file targets.
        routine = routine_holonomic(e)
        defn = computable_definition(e)
        tract = 0.5 if routine else (0.85 if (defn and past) else (0.8 if (defn or e.get("definition")) else 0.4))
        fresh = 1.0 / (1 + st.get("attempts", 0))
        score = tract * bandit * (0.25 + fresh) * (0.5 + rng.random())
        try:
            from colony.stall import selection_bonus
            score *= 1.0 + float(selection_bonus(eid))
        except Exception:
            pass
        # Rotate off the form that was just attempted, when others are available.
        if last_form and form == last_form:
            score *= _rotation_penalty()
        # Band 0: zero-credit, not an already-handled holonomic relation.
        # Within band 0, a computable past-b-file target ranks ahead of a
        # published-range-only one via the tract/score, not a hardcoded id.
        # Band 1: everything else that is not that kind of relation.
        # Band 2: routine holonomic relations — after the others, or a small share.
        credit = float(f.get("credit") or 0)
        if credit == 0 and not routine:
            band = 0
        elif not routine:
            band = 1
        else:
            band = 2
        scored.append((band, -score, e, form))
    scored.sort(key=lambda t: (t[0], t[1]))
    preferred = [(e, form) for band, _neg, e, form in scored if band < 2]
    routine_tail = [(e, form) for band, _neg, e, form in scored if band >= 2]

    def _take(candidates: list, need: int, rotate: bool) -> tuple[list, list]:
        picked: list = []
        used_forms: list[str] = []
        deferred: list = []
        for e, form in candidates:
            if len(picked) >= need:
                deferred.append((e, form))
                continue
            if rotate and form in used_forms and any(f2 not in used_forms for _e2, f2 in candidates if _e2 is not e):
                deferred.append((e, form))
                continue
            picked.append((e, form))
            used_forms.append(form)
        return picked, deferred

    taken, leftover = _take(preferred, k, rotate=True)
    if len(taken) < k:
        more, leftover = _take(leftover, k - len(taken), rotate=False)
        taken.extend(more)
    picked = [e for e, _f in taken]
    if len(picked) < k:
        remaining = k - len(picked)
        if preferred and k >= 5:
            remaining = min(remaining, max(1, k // 5))
        picked.extend([e for e, _f in routine_tail[:remaining]])
    return picked[:k]


def _rotation_penalty() -> float:
    """Score multiplier for the form just attempted. Policy may override 0.85."""
    try:
        from colony.self_heal import active_knob
        v = active_knob("family_rotation_penalty")
        if v is not None:
            return float(v)
    except Exception:
        pass
    return 0.85


def zero_credit_forms(state: dict[str, Any], menu: list[dict[str, Any]]) -> list[str]:
    """Claim forms on the menu whose recorded family credit is still 0.

    A form with no family row yet has earned nothing, so it is included. Forms
    are not hardcoded: whatever the menu and the state say is what counts.
    """
    fam = (state or {}).get("families") or {}
    out: list[str] = []
    seen: set[str] = set()
    for e in menu:
        form = str((e.get("claim") or {}).get("form") or "")
        if not form or form in seen:
            continue
        seen.add(form)
        if float((fam.get(form) or {}).get("credit") or 0) == 0:
            out.append(form)
    return out


def credit_of(res: dict[str, Any], prior_hi: int | None) -> float:
    if res.get("status") in ("counterexample_verified", "proved_checked"):
        return CREDIT_RESOLVE
    if res.get("action") == "attempt_disprove" and res.get("status") == "holds_on_range":
        hi = max((res.get("range") or [0, 0])[1] or 0, res.get("deep_hi") or 0)
        # only range beyond the OEIS b-file (already checked by OEIS contributors) counts as extension
        base = max(prior_hi or 0, res.get("data_hi") or 0, res.get("bfile_hi") or 0, 1)
        if hi > base:
            return round(CREDIT_EXTEND * min(1.0, math.log10(hi / base)), 4)
    return 0.0


def _flag(e: dict[str, Any], res: dict[str, Any], cid: str) -> None:
    if not REVIEW.exists():
        REVIEW.write_text("# OEIS conjecture results for James's review\n\nMachine results only. Nothing here "
                          "has been authorized, submitted to OEIS or posted. Each needs a human check of the "
                          "parse, the b-file and the literature.\n")
    lines = [f"\n## {e['anum']} — {res['status']} (cycle {cid})\n", f"OEIS text ({e['section']}): \"{e['text']}\"\n",
             f"Parsed claim: `{json.dumps(e['claim'])}`\n"]
    if res["status"] == "counterexample_verified":
        lines.append(f"First failure n = {res['counterexample_n']} (both code paths): A {res['fails_A'][:1]} | "
                     f"B {res['fails_B'][:1]}; b-file source for B: {res.get('b_source')}; DATA ends at n = "
                     f"{res['data_hi']}; deep terms {res['deep_terms']}.\n")
    else:
        lines.append(f"Checker: {res.get('checker')}\n")
    with REVIEW.open("a") as fh:
        fh.write("".join(lines))


def _score(state: dict[str, Any], e: dict[str, Any], acts: list[dict[str, Any]]) -> None:
    """Honest scoreboard: (a) counterexamples verified on two code paths, (b) proof_check-accepted proofs,
    (c) entries whose computable definition was checked beyond the published (b-file) range."""
    sb = state.setdefault("scoreboard", {"counterexamples": {}, "proofs": {}, "extensions": {}})
    for r in acts:
        if r["status"] == "counterexample_verified":
            sb["counterexamples"][e["id"]] = {"anum": e["anum"], "n": r.get("counterexample_n")}
        elif r["status"] == "proved_checked":
            checker = r.get("checker") or ""
            kind = (e.get("definition") or {}).get("kind")
            # Algebraic g.f. certificates and C-finite order-bound closures are routine.
            # Anything else proof_check accepted is counted with them, but not as routine.
            routine = kind == "alg" or checker.startswith("routine")
            sb["proofs"][e["id"]] = {"anum": e["anum"], "checker": checker[:120],
                                     "routine": routine}
        elif r.get("action") == "attempt_disprove" and r["status"] == "holds_on_range":
            bh = r.get("bfile_hi") or 0
            top_exact = (r.get("range") or [0, 0])[1] or 0
            top = max(top_exact, r.get("deep_hi") or 0)
            if top > bh:
                old = sb["extensions"].get(e["id"], {})
                if top > old.get("to", 0):
                    modular = bool(r.get("deep_hi") and r["deep_hi"] > top_exact and "prime" in (r.get("deep_mode") or ""))
                    sb["extensions"][e["id"]] = {"anum": e["anum"], "bfile_hi": bh, "to": top,
                                                 "check": "modular (two primes)" if modular else "exact"}


def honest_scoreboard() -> dict[str, Any]:
    """The selection-layer scoreboard. It is not fitness, not P, and not the Oracle."""
    state = _load(STATE, {})
    board = scoreboard(state)
    board["note"] = "counterexamples, checked proofs, and range extensions only; not fitness"
    return board


def format_honest_scoreboard(board: dict[str, Any] | None = None) -> str:
    b = board if board is not None else honest_scoreboard()
    return (f"counterexamples {b.get('counterexamples_verified', 0)}; "
            f"proofs {b.get('proofs_checked', 0)} "
            f"({b.get('proofs_routine_known_in_principle', 0)} routine); "
            f"past published range {b.get('beyond_published_range', 0)}")


def scoreboard(state: dict[str, Any]) -> dict[str, Any]:
    sb = state.get("scoreboard") or {"counterexamples": {}, "proofs": {}, "extensions": {}}
    a, b, c = len(sb["counterexamples"]), len(sb["proofs"]), len(sb["extensions"])
    return {"score": a + b + c, "counterexamples_verified": a, "proofs_checked": b,
            "proofs_routine_known_in_principle": sum(1 for v in sb["proofs"].values() if v.get("routine")),
            "beyond_published_range": c,
            "beyond_exact": sum(1 for v in sb["extensions"].values() if v.get("check") == "exact"),
            "max_depth": max([v["to"] for v in sb["extensions"].values()] or [0])}


def run_cycle(
    cycle_id: str,
    fetch: bool = True,
    *,
    forms: set[str] | None = None,
    k: int | None = None,
    beyond_bfile: bool = False,
    use_state_for_choice: bool = False,
    purpose: str = "",
) -> dict[str, Any] | None:
    m = mode()
    if m == "off":
        return None
    menu = load_menu()
    if not menu:
        return None
    state = _load(STATE, {"targets": {}, "families": {}, "credit_total": 0.0})
    choice_state = state if (m == "live" or use_state_for_choice) else {"targets": {}, "families": {}}
    picks = choose(
        menu, choice_state, cycle_id, PICKS if k is None else k,
        forms=forms, beyond_bfile=beyond_bfile,
    )
    results = []
    for e in picks:
        st = state["targets"].get(e["id"], {})
        entry = dict(e)
        defn = computable_definition(entry)
        if defn and not entry.get("definition"):
            entry["definition"] = defn
        acts = []
        if beyond_bfile:
            # The idle fallback is a search past the published terms, not another proof of a
            # holonomic relation the checker already handles. g.f. claims with a verified
            # definition are included (series arithmetic past the b-file).
            acts.append(attempt_disprove(entry, st.get("tested_hi"), fetch=fetch))
        else:
            if provable(entry):
                acts.append(attempt_prove(entry))
            if not acts or acts[-1]["status"] != "proved_checked":
                acts.append(attempt_disprove(entry, st.get("tested_hi"), fetch=fetch))
        try:
            remember_attempt(entry, acts, cycle_id, planned=planned_depth(entry, st.get("tested_hi")))
        except Exception:
            pass
        for r in acts:
            r["credit"] = credit_of(r, st.get("tested_hi"))
            r.pop("cert", None) if r["status"] != "proved_checked" else None
            results.append(r)
        if m == "live":
            fin = next((r for r in acts if r["credit"] >= CREDIT_RESOLVE), acts[-1])
            st["attempts"] = st.get("attempts", 0) + 1
            st["status"] = fin["status"]
            hi = max([max((r.get("range") or [0, 0])[1] or 0, r.get("deep_hi") or 0) for r in acts]
                     + [st.get("tested_hi") or 0])
            st["tested_hi"] = hi
            st["credit"] = round(st.get("credit", 0.0) + sum(r["credit"] for r in acts), 4)
            state["targets"][e["id"]] = st
            f = state["families"].setdefault(e["claim"]["form"], {"attempts": 0, "credit": 0.0})
            f["attempts"] += 1
            f["credit"] = round(f["credit"] + sum(r["credit"] for r in acts), 4)
            state["credit_total"] = round(state.get("credit_total", 0.0) + sum(r["credit"] for r in acts), 4)
            for r in acts:
                if r["status"] in ("counterexample_verified", "proved_checked"):
                    _flag(e, r, cycle_id)
            _score(state, e, acts)
    rep = {"mode": m, "cycle": cycle_id, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "menu_size": len(menu), "purpose": purpose,
           "chosen": [{"id": e["id"], "anum": e["anum"], "form": (e.get("claim") or {}).get("form"),
                       "text": e["text"]} for e in picks],
           "results": results, "scoreboard": scoreboard(state),
           "note": "selection-layer credit only; nothing authorized or posted"}
    hist = _load(REPORT, {"runs": []}).get("runs", [])[-24:]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"runs": hist + [rep]}, indent=1) + "\n")
    if m == "live":
        STATE.write_text(json.dumps(state, indent=1) + "\n")
    return rep


def idle_turn(cycle_id: str) -> dict[str, Any] | None:
    """One OEIS attempt when the lemma catalog has nothing left to mutate.

    A family with credit 0 is tried first (one open target). If every family on
    the menu already has credit, one computable claim is searched past its
    published b-file. Shadow still writes the report and does not update state.
    """
    if mode() == "off":
        return None
    menu = load_menu()
    if not menu:
        return None
    state = _load(STATE, {"targets": {}, "families": {}, "credit_total": 0.0})
    forms = zero_credit_forms(state, menu)
    if forms:
        rep = run_cycle(
            cycle_id, fetch=False, forms=set(forms), k=1,
            use_state_for_choice=True, purpose="zero_credit_family",
        )
        if rep and rep.get("chosen"):
            return rep
    return run_cycle(
        cycle_id, fetch=False, k=1, beyond_bfile=True,
        use_state_for_choice=True, purpose="beyond_bfile",
    )
