"""Citation relevance check — a feed source is cited only if it states/supports the claim.

Replaces keyword overlap (any shared substring such as "cassini" in a Titan-ionosphere paper,
or "hockey stick" in a surgery abstract) with a claim-object check:

* Papers (arXiv / Crossref): the claim's key mathematical objects are derived from the target
  name (``authored_a__b_w1`` → components ``a``, ``b``). Each component maps to an object
  pattern that requires the *mathematical* phrase (e.g. "Cassini identity", "Pell equation",
  "Stirling numbers", "Catalan numbers"), not the bare word. Unambiguous object names
  (Fibonacci, Motzkin, Narayana, derangement, totient, …) count alone. Unknown component
  words fall back to "word + mathematical noun within three words". A paper is relevant iff
  its title/abstract contains the key object of at least one component; the matched phrase
  is the recorded reason.
* OEIS: relevant iff the cited A-number's terms reproduce the claim's generator terms (or the
  A-number is named by the claim). Reason records the matched run length.

Every decision returns ``{"relevant": bool, "reason": str, "matched": [...]}`` so the caller
records a reason per citation. Untrusted feed text is only pattern-matched, never executed.
"""
from __future__ import annotations

import re
from typing import Any

MATH_NOUNS = (r"numbers?|polynomials?|triangles?|sequences?|identit(?:y|ies)|recurrences?|coefficients?|"
              r"paths?|equations?|functions?|matri(?:x|ces)|words?|trees?|conjectures?|sums?|convolutions?|"
              r"inversions?|primes?|theorems?|formulas?|formulae|series|transforms?|partitions?|triples?|"
              r"bounds?|congruences?|lattices?|permutations?|duplication|kind")

# component word -> object pattern (regex, case-insensitive). "None" = needs math-noun context.
_UNAMBIGUOUS = {
    "fibonacci": r"\bfibonacci\b", "lucas": r"\blucas (?:numbers?|sequences?)\b",
    "motzkin": r"\bmotzkin\b", "narayana": r"\bnarayana\b",
    "derangement": (r"\bderangement (?:numbers?|polynomials?)\b|\bderangements\b(?=.{0,120}\bpermutation)"
                    r"|\bpermutations?\b.{0,120}\bderangements?\b"),
    "subfactorial": r"\bsubfactorials?\b", "totient": r"\btotient\b|\beuler'?s? phi\b",
    "stirling": r"\bstirling (?:numbers?|polynomials?|triangles?|transforms?)\b",
    "catalan": r"\bq?-?catalan (?:numbers?|triangles?|paths?|structures?|objects?|combinatorics|sequences?)\b",
    "bell": r"\bbell (?:numbers?|polynomials?|triangles?)\b|\baitken'?s array\b",
    "pell": r"\bpell(?:'s)? (?:equations?|numbers?|polynomials?|sequences?)\b",
    "hermite": r"\bhermite (?:polynomials?|functions?|numbers?)\b",
    "legendre": r"\blegendre (?:duplication|polynomials?|symbols?|formula)\b",
    "cassini": r"\bcassini(?:'s)? (?:identity|formula)\b",
    "vandermonde": r"\bvandermonde(?:'s)? (?:identity|convolution)\b|\bchu[-–]vandermonde\b",
    "pythagorean": r"\bpythagorean (?:triples?|theorem)\b",
    "hockey": r"\bhockey[- ]stick (?:identity|theorem|rule)\b",
    "pascal": r"\bpascal(?:'s)? (?:triangle|rule|identity)\b",
    "binomial": r"\bbinomial (?:coefficients?|sums?|identit(?:y|ies)|transforms?|inversion|theorem)\b",
    "binom": r"\bbinomial (?:coefficients?|sums?|identit(?:y|ies)|transforms?)\b|\bcentral binomial\b",
    "gcd": r"\bgcd\b|\bgreatest common divisor\b",
    "geometric": r"\bgeometric (?:series|sums?|progressions?)\b",
    "cubes": r"\bsums? of (?:the )?cubes\b|\bnicomachus\b",
    "odds": r"\bodd numbers\b",
    "zeckendorf": r"\bzeckendorf\b", "euler": None, "collatz": r"\bcollatz\b|\b3x ?\+ ?1\b",
    "goldbach": r"\bgoldbach\b", "twin": r"\btwin primes?\b",
}
_STOP = {"authored", "oeis", "bounded", "small", "stress", "deep", "check", "lemma", "chain", "derived",
         "identity", "recurrence", "row", "ext", "asymmetric", "first", "sum", "second", "conv", "bound",
         "multiplicative", "companion", "generation", "addition", "inversion", "convolution", "duplication",
         "triangle", "symmetry", "central", "hard", "combinatorics", "easy", "pad", "frontier"}


def components(target: str) -> list[str]:
    """``authored_a__b_w1`` → ["a", "b"]; plain lemma → [name]."""
    t = re.sub(r"^(?:authored|lemma|check)_", "", (target or "").lower())
    t = re.sub(r"_w\d+$", "", t)
    return [c for c in t.split("__") if c]


def object_patterns(component: str) -> list[tuple[str, str]]:
    """(word, regex) for the component's key objects (mechanism: lexicon + generic fallback)."""
    out: list[tuple[str, str]] = []
    words = re.split(r"[^a-z0-9]+", component.lower())
    known = any(w in _UNAMBIGUOUS for w in words)
    for w in words:
        if known and w not in _UNAMBIGUOUS:
            continue  # component has a named object: only that object's phrase counts
        if len(w) < 3 or w in _STOP or w.isdigit() or re.fullmatch(r"a\d{6}", w):
            continue
        pat = _UNAMBIGUOUS.get(w, "__generic__")
        if pat is None:
            continue
        if pat == "__generic__":
            pat = rf"\b{re.escape(w)}\w*(?:\W+\w+){{0,2}}?\W+(?:{MATH_NOUNS})\b"
        out.append((w, pat))
    return out


def assess_paper(target: str, item: dict[str, Any]) -> dict[str, Any]:
    blob = re.sub(r"\s+", " ", f"{item.get('title', '')} . {item.get('text', '')}")
    matched: list[str] = []
    comps = components(target)
    for comp in comps:
        for w, pat in object_patterns(comp):
            m = re.search(pat, blob, flags=re.I)
            if m:
                matched.append(f"{comp}:{m.group(0)[:60]}")
                break
    if matched:
        return {"relevant": True, "matched": matched,
                "reason": f"source names the claim's object(s): {'; '.join(matched)}"}
    objs = [w for c in comps for w, _ in object_patterns(c)]
    return {"relevant": False, "matched": [],
            "reason": f"no key object of the claim ({', '.join(objs) or 'none derivable'}) stated as a mathematical object"}


def assess_oeis(target: str, item: dict[str, Any], claim_terms: list[int] | None = None, *, min_run: int = 6) -> dict[str, Any]:
    anum = str(item.get("oeis_id") or "")
    if anum and anum.lower() in (target or "").lower():
        return {"relevant": True, "matched": [anum], "reason": f"claim names {anum} directly"}
    terms = [t for t in (item.get("terms") or []) if isinstance(t, int)]
    q = [t for t in (claim_terms or []) if isinstance(t, int)]
    if len(q) >= min_run and terms:
        for i in range(len(terms) - min_run + 1):
            run = 0
            while run < len(q) and i + run < len(terms) and terms[i + run] == q[run]:
                run += 1
            if run >= min_run:
                return {"relevant": True, "matched": [anum],
                        "reason": f"{anum} terms reproduce the claim's generator for {run} consecutive terms"}
    return {"relevant": False, "matched": [], "reason": f"{anum or 'item'}: no sequence-id or term match with the claim"}


def assess(target: str, item: dict[str, Any], claim_terms: list[int] | None = None) -> dict[str, Any]:
    if item.get("oeis_id") or str(item.get("source") or "").startswith("oeis"):
        return assess_oeis(target, item, claim_terms)
    return assess_paper(target, item)
