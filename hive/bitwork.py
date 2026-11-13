"""Hive's Bitwork-style deterministic sparse binary router, in pure Python.

Design source: Perci (github.com/jacksonjp0311-gif/Perci). The encoder
and feature hash match ``src/cognitive.rs`` (``normalize``,
``set_feature``, bag-of-features ``encode``). The Wilson 95% lower
bound and margin buckets match ``wilson_lower_permille`` and
``MARGIN_BUCKETS`` in ``src/weight_packs.rs``. Category and prototype
scores are the white-paper integer formulas:

* ``s_d = 2|q AND m+| - |q AND m-| + prior``
* ``S(q, p) = 2|q AND p| - |p|``  (= ``|q| - Hamming(q, p)``)
* accept iff the Wilson lower bound for the margin bucket is
  ``>= 700`` permille

This module is integer-scored and deterministic. It does not load
Perci weight packs, does not call an external model, and is not a
Rust build. Cite Perci as the source design; do not treat this file
as a byte-for-byte pack scanner (record layout and quality terms are
Perci-pack-specific and are not used here).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isqrt
from typing import Iterable, Mapping, Sequence

# 4096-bit space, 64 words of 64 bits. Same as Perci ``BITS`` / ``WORDS``.
BITS = 4096
WORDS = BITS // 64  # 64

# FNV-1a 64-bit, as in Perci ``set_feature``.
FNV_OFFSET = 0xCBF29CE484222325
FNV_PRIME = 0x00000100000001B3
U64 = 0xFFFFFFFFFFFFFFFF

# Four 12-bit slices of the FNV hash, same shifts as Perci.
HASH_SHIFTS = (0, 12, 24, 36)

# Wilson 95% z = 1.96 = 196/100; accept iff lower bound >= 700 ‰.
WILSON_Z_NUM = 196
WILSON_Z_DEN = 100
WILSON_ACCEPT_PERMILLE = 700

# Perci ``MARGIN_BUCKETS``: lower edges of calibration buckets.
MARGIN_BUCKETS: tuple[int, ...] = (0, 1, 2, 4, 8, 16, 32, 64)

# Keyword prior points per cue, from the Bitwork white paper (v1 packs).
PRIOR_POINTS = 48

# A frozen 4096-bit vector: 64 Python ints, each a u64 word.
BitVec = tuple[int, ...]


def fnv1a_64(feature: str) -> int:
    """64-bit FNV-1a of a UTF-8 feature string, wrapping like Rust ``u64``."""
    h = FNV_OFFSET
    for byte in feature.encode("utf-8"):
        h ^= byte
        h = (h * FNV_PRIME) & U64
    return h


def empty_bits() -> list[int]:
    return [0] * WORDS


def freeze(bits: Sequence[int]) -> BitVec:
    if len(bits) != WORDS:
        raise ValueError(f"bit vector must have {WORDS} words, got {len(bits)}")
    return tuple(int(w) & U64 for w in bits)


def set_feature(bits: list[int], feature: str) -> None:
    """OR four hashed bit positions into ``bits``. Matches Perci ``set_feature``."""
    h = fnv1a_64(feature)
    for shift in HASH_SHIFTS:
        position = (h >> shift) & (BITS - 1)
        bits[position >> 6] |= 1 << (position & 63)


def normalize(text: str) -> str:
    """Lowercase ASCII alphanumerics; other chars become single spaces.

    Matches Perci ``cognitive.rs`` ``normalize``.
    """
    out: list[str] = []
    previous_space = True
    for ch in text:
        if ch.isascii() and ch.isalnum():
            out.append(ch.lower())
            previous_space = False
        elif not previous_space:
            out.append(" ")
            previous_space = True
    return "".join(out).strip()


def encode(text: str) -> BitVec:
    """Bag-of-features encode: bias, length, words, prefixes, suffixes,
    adjacent word pairs, and character trigrams on the underscored
    compact form. Matches Perci ``encode_bag_only``.
    """
    normalized = normalize(text)
    words = normalized.split()
    bits = empty_bits()
    set_feature(bits, "bias")
    set_feature(bits, f"len:{min(len(words), 31)}")
    for word in words:
        set_feature(bits, f"w:{word}")
        if len(word) >= 3:
            set_feature(bits, f"p:{word[:3]}")
            set_feature(bits, f"s:{word[-3:]}")
    for i in range(len(words) - 1):
        set_feature(bits, f"b:{words[i]}|{words[i + 1]}")
    compact = "_".join(words)
    if len(compact) >= 3:
        for start in range(0, len(compact) - 2):
            set_feature(bits, f"c:{compact[start:start + 3]}")
    return freeze(bits)


def popcount(bits: Sequence[int]) -> int:
    return sum(int(w).bit_count() for w in bits)


def bitwise_and(a: Sequence[int], b: Sequence[int]) -> BitVec:
    return tuple((int(x) & int(y)) & U64 for x, y in zip(a, b, strict=True))


def bitwise_or(a: Sequence[int], b: Sequence[int]) -> BitVec:
    return tuple((int(x) | int(y)) & U64 for x, y in zip(a, b, strict=True))


def intersection_count(a: Sequence[int], b: Sequence[int]) -> int:
    """``|q AND p|``. Matches Perci ``intersection_count``."""
    return sum((int(x) & int(y)).bit_count() for x, y in zip(a, b, strict=True))


def hamming(a: Sequence[int], b: Sequence[int]) -> int:
    """Hamming distance: ``|a| + |b| - 2|a AND b|``."""
    return popcount(a) + popcount(b) - 2 * intersection_count(a, b)


def category_score(
    query: Sequence[int],
    mask_plus: Sequence[int],
    mask_minus: Sequence[int],
    prior: int = 0,
) -> int:
    """``s_d = 2|q AND m+| - |q AND m-| + prior``. Integer-only."""
    return (
        2 * intersection_count(query, mask_plus)
        - intersection_count(query, mask_minus)
        + int(prior)
    )


def prototype_score(query: Sequence[int], proto: Sequence[int]) -> int:
    """``S(q, p) = 2|q AND p| - |p|``. Equals ``|q| - Hamming(q, p)``."""
    return 2 * intersection_count(query, proto) - popcount(proto)


def keyword_prior(text: str, cues: Iterable[str], points: int = PRIOR_POINTS) -> int:
    """``points`` per cue whose normalized form is a whole word in ``text``."""
    words = set(normalize(text).split())
    total = 0
    for cue in cues:
        token = normalize(cue)
        if token and all(part in words for part in token.split()):
            total += int(points)
    return total


def wilson_lower_permille(correct: int, n: int) -> int:
    """Wilson 95% lower bound of ``correct / n``, in permille.

    Design source: Perci ``wilson_lower_permille`` (weight_packs.rs).
    The formula is

        L = (p + z²/(2n) - z √((p(1-p) + z²/(4n))/n)) / (1 + z²/n)

    with ``z = 196/100``. This implementation uses integer fixed-point
    arithmetic and ``math.isqrt`` so the result is platform-deterministic
    (no IEEE rounding). Accept iff the returned value is ``>= 700``.
    """
    if n <= 0 or correct <= 0:
        return 0
    if correct > n:
        correct = n
    # Work in units of 1/S. Intermediate floors are deterministic.
    # z² = 38416 / 10000.
    scale = 10**12
    z2_s = (38416 * scale) // 10000
    p_s = (correct * scale) // n
    centre_s = p_s + z2_s // (2 * n)
    denom_s = scale + z2_s // n
    # radicand = (p(1-p) + z²/(4n)) / n
    # radicand * scale² = [p_s * (scale - p_s) + z2_s * scale / (4n)] / n
    inner_s2 = p_s * (scale - p_s) + (z2_s * scale) // (4 * n)
    radicand_s2 = inner_s2 // n
    root_s = isqrt(radicand_s2)
    half_s = (WILSON_Z_NUM * root_s) // WILSON_Z_DEN
    numer_s = centre_s - half_s
    if numer_s <= 0:
        return 0
    return int((numer_s * 1000) // denom_s)


def margin_bucket(margin: int) -> int:
    """Largest lower edge in ``MARGIN_BUCKETS`` that is ``<= margin``."""
    m = int(margin)
    edge = MARGIN_BUCKETS[0]
    for b in MARGIN_BUCKETS:
        if b <= m:
            edge = b
        else:
            break
    return edge


@dataclass
class BucketStats:
    """Calibration counts for one margin bucket. Append-only counters."""

    min_margin: int
    n: int = 0
    correct: int = 0

    def lower_permille(self) -> int:
        return wilson_lower_permille(self.correct, self.n)

    def accuracy_permille(self) -> int:
        if self.n <= 0:
            return 0
        return int((self.correct * 1000) // self.n)

    def record(self, correct: bool) -> None:
        self.n += 1
        if correct:
            self.correct += 1

    def as_dict(self) -> dict[str, int]:
        return {
            "min_margin": self.min_margin,
            "n": self.n,
            "correct": self.correct,
            "accuracy_permille": self.accuracy_permille(),
            "lower_permille": self.lower_permille(),
        }


@dataclass
class Prototype:
    """One stored example used for Hamming-style retrieval."""

    key: str
    bits: BitVec
    category: str
    action_key: str
    polarity: str  # "positive" or "negative"
    source_id: str = ""


@dataclass
class Category:
    name: str
    mask_plus: BitVec = field(default_factory=lambda: freeze(empty_bits()))
    mask_minus: BitVec = field(default_factory=lambda: freeze(empty_bits()))
    cues: tuple[str, ...] = ()


@dataclass(frozen=True)
class Match:
    """A single retrieval result, with Wilson-gated acceptance."""

    category: str
    action_key: str
    score: int
    margin: int
    overlap: int
    hamming: int
    prototype_key: str
    polarity: str
    lower_permille: int
    accuracy_permille: int
    bucket_n: int
    accepted: bool
    abstained: bool
    reason: str


class Router:
    """Deterministic Bitwork router over a growing example library.

    Shared by every swarm agent. Learning is append-only: new examples
    OR into category masks and are stored as prototypes. Calibration
    counters only increase. Nothing here touches the Oracle.
    """

    def __init__(self) -> None:
        self.categories: dict[str, Category] = {}
        self.prototypes: list[Prototype] = []
        self.buckets: dict[int, BucketStats] = {
            b: BucketStats(min_margin=b) for b in MARGIN_BUCKETS
        }
        self._proto_keys: set[str] = set()

    def ensure_category(self, name: str, cues: Iterable[str] = ()) -> Category:
        key = str(name or "").strip()
        if not key:
            raise ValueError("category name is required")
        if key not in self.categories:
            self.categories[key] = Category(name=key, cues=tuple(cues))
        elif cues:
            existing = self.categories[key]
            merged = tuple(dict.fromkeys(existing.cues + tuple(cues)))
            self.categories[key] = Category(
                name=key,
                mask_plus=existing.mask_plus,
                mask_minus=existing.mask_minus,
                cues=merged,
            )
        return self.categories[key]

    def learn(
        self,
        text: str,
        category: str,
        action_key: str,
        *,
        positive: bool = True,
        source_id: str = "",
        cues: Iterable[str] = (),
        proto_key: str = "",
    ) -> Prototype:
        """Add one example. Masks and prototypes are append-only (OR / append)."""
        bits = encode(text)
        cat = self.ensure_category(category, cues=cues)
        if positive:
            cat.mask_plus = bitwise_or(cat.mask_plus, bits)
        else:
            cat.mask_minus = bitwise_or(cat.mask_minus, bits)
        key = proto_key or source_id or f"{category}:{action_key}:{len(self.prototypes)}"
        if key in self._proto_keys:
            # Same id seen again: keep the first vector (append-only, no rewrite).
            for p in self.prototypes:
                if p.key == key:
                    return p
        proto = Prototype(
            key=key,
            bits=bits,
            category=category,
            action_key=action_key,
            polarity="positive" if positive else "negative",
            source_id=source_id or key,
        )
        self.prototypes.append(proto)
        self._proto_keys.add(key)
        return proto

    def _category_scores(self, text: str, query: Sequence[int]) -> dict[str, int]:
        out: dict[str, int] = {}
        for name, cat in self.categories.items():
            prior = keyword_prior(text, cat.cues)
            out[name] = category_score(query, cat.mask_plus, cat.mask_minus, prior)
        return out

    def retrieve(
        self,
        text: str,
        *,
        polarity: str = "positive",
        top_k: int = 5,
    ) -> list[Match]:
        """Score every stored prototype; return the top-k (deterministic order)."""
        query = encode(text)
        qn = popcount(query)
        scored: list[tuple[int, int, Prototype]] = []
        for i, proto in enumerate(self.prototypes):
            if polarity and proto.polarity != polarity:
                continue
            # Pure prototype score S(q, p) = 2|q AND p| - |p|.
            # Category score is computed for inspection but is not
            # added here: a 2 s_d lift would let a popular category
            # mask drown a closer prototype (the paper's 2 s_d term
            # is for a packed per-domain scan, not this library).
            s = prototype_score(query, proto.bits)
            overlap = intersection_count(query, proto.bits)
            scored.append((s, overlap, proto))
        # Deterministic: higher score first, then stable key.
        scored.sort(key=lambda t: (-t[0], t[2].key))
        matches: list[Match] = []
        for rank, (s, overlap, proto) in enumerate(scored[: max(1, int(top_k))]):
            runner = scored[1][0] if len(scored) > 1 else 0
            margin = max(0, s - runner) if rank == 0 else 0
            ham = qn + popcount(proto.bits) - 2 * overlap
            bucket = self.buckets[margin_bucket(margin if rank == 0 else 0)]
            lower = bucket.lower_permille()
            accepted = lower >= WILSON_ACCEPT_PERMILLE
            matches.append(Match(
                category=proto.category,
                action_key=proto.action_key,
                score=s,
                margin=margin if rank == 0 else 0,
                overlap=overlap,
                hamming=ham,
                prototype_key=proto.key,
                polarity=proto.polarity,
                lower_permille=lower,
                accuracy_permille=bucket.accuracy_permille(),
                bucket_n=bucket.n,
                accepted=accepted and rank == 0,
                abstained=(not accepted) or rank > 0,
                reason=(
                    "wilson_accept" if accepted and rank == 0
                    else "wilson_abstain" if rank == 0
                    else "not_top"
                ),
            ))
        return matches

    def classify(self, text: str) -> Match | None:
        """Top positive match, or None when the library is empty."""
        hits = self.retrieve(text, polarity="positive", top_k=2)
        return hits[0] if hits else None

    def score_action(self, text: str, action_key: str) -> Match | None:
        """Best prototype for a proposed action, regardless of rank overall.

        Margin is this action's best score minus the best score of any
        *other* action. That is the same notion of margin that replay
        and ``classify`` use (top vs a real runner-up), not the gap
        between two examples of the same action, and not a default
        runner-up of 0 that clamps a negative score to margin 0.
        The Wilson 95% gate and the 700 permille threshold are
        unchanged.
        """
        query = encode(text)
        qn = popcount(query)
        best: tuple[int, int, int, Prototype] | None = None
        best_other: int | None = None
        for proto in self.prototypes:
            if proto.polarity != "positive":
                continue
            s = prototype_score(query, proto.bits)
            overlap = intersection_count(query, proto.bits)
            if proto.action_key == action_key:
                if best is None or s > best[0] or (s == best[0] and proto.key < best[3].key):
                    best = (s, overlap, qn, proto)
            else:
                if best_other is None or s > best_other:
                    best_other = s
        if best is None:
            return None
        s, overlap, qn, proto = best
        if best_other is None:
            margin = max(0, s)
        else:
            margin = max(0, s - best_other)
        ham = qn + popcount(proto.bits) - 2 * overlap
        bucket = self.buckets[margin_bucket(margin)]
        lower = bucket.lower_permille()
        accepted = lower >= WILSON_ACCEPT_PERMILLE
        return Match(
            category=proto.category,
            action_key=proto.action_key,
            score=s,
            margin=margin,
            overlap=overlap,
            hamming=ham,
            prototype_key=proto.key,
            polarity=proto.polarity,
            lower_permille=lower,
            accuracy_permille=bucket.accuracy_permille(),
            bucket_n=bucket.n,
            accepted=accepted,
            abstained=not accepted,
            reason="wilson_accept" if accepted else "wilson_abstain",
        )

    def record_outcome(self, margin: int, correct: bool) -> BucketStats:
        """Update the calibration bucket for ``margin``. Counters only grow."""
        bucket = self.buckets[margin_bucket(int(margin))]
        bucket.record(bool(correct))
        return bucket

    def would_accept(self, margin: int) -> tuple[bool, int, int]:
        """``(accepted, lower_permille, bucket_n)`` for a margin, no mutation."""
        bucket = self.buckets[margin_bucket(int(margin))]
        lower = bucket.lower_permille()
        return lower >= WILSON_ACCEPT_PERMILLE, lower, bucket.n

    def library_size(self) -> int:
        return len(self.prototypes)

    def snapshot(self) -> dict[str, object]:
        """JSON-friendly view of masks and calibration (not the raw bits)."""
        return {
            "n_categories": len(self.categories),
            "n_prototypes": len(self.prototypes),
            "categories": sorted(self.categories),
            "buckets": [self.buckets[b].as_dict() for b in MARGIN_BUCKETS],
        }

    def replay_accuracy(
        self,
        cases: Sequence[tuple[str, str]],
        *,
        hold_out: bool = True,
    ) -> dict[str, int]:
        """Route each ``(text, expected_action_key)`` and score accuracy.

        When ``hold_out`` is true, a temporary router is trained on all
        cases except the one under test (leave-one-out). Calibration is
        not required for the raw accuracy figure; the Wilson gate is
        reported separately as the abstention rate on the same split.
        """
        if not cases:
            return {
                "n": 0, "correct": 0, "abstained": 0,
                "accuracy_permille": 0, "lower_permille": 0,
            }
        correct = 0
        abstained = 0
        n = len(cases)
        for i, (text, expected) in enumerate(cases):
            if hold_out:
                tmp = Router()
                for j, (t, a) in enumerate(cases):
                    if j == i:
                        continue
                    tmp.learn(t, category=a, action_key=a, source_id=f"loo-{j}",
                              proto_key=f"loo-{j}")
                # Give the held-out router the parent's calibration, so
                # the Wilson gate is the one the live system would use.
                tmp.buckets = {
                    k: BucketStats(b.min_margin, b.n, b.correct)
                    for k, b in self.buckets.items()
                }
                hit = tmp.classify(text)
            else:
                hit = self.classify(text)
            if hit is None:
                abstained += 1
                continue
            if hit.abstained:
                abstained += 1
            if hit.action_key == expected:
                correct += 1
        return {
            "n": n,
            "correct": correct,
            "abstained": abstained,
            "accuracy_permille": int((correct * 1000) // n) if n else 0,
            "lower_permille": wilson_lower_permille(correct, n),
        }

    def leave_one_out_outcomes(
        self,
        cases: Sequence[tuple[str, str]],
    ) -> list[dict[str, object]]:
        """Labeled leave-one-out results, for honest calibration.

        For each ``(text, expected_action_key)`` a temporary router is
        trained on every other case and asked for its top pick. The
        outcome is the pick's margin and whether it matched the label.
        Cases with no retrieval are omitted: that is not a labeled
        correct or incorrect, and we do not fabricate one.

        This method does not mutate this router's calibration buckets.
        """
        out: list[dict[str, object]] = []
        for i, (text, expected) in enumerate(cases):
            tmp = Router()
            for j, (t, a) in enumerate(cases):
                if j == i:
                    continue
                tmp.learn(
                    t, category=str(a), action_key=str(a),
                    source_id=f"loo-{j}", proto_key=f"loo-{j}",
                )
            hit = tmp.classify(text)
            if hit is None:
                continue
            out.append({
                "source": "replay",
                "index": i,
                "text": text,
                "expected": expected,
                "predicted": hit.action_key,
                "margin": int(hit.margin),
                "correct": hit.action_key == expected,
                "score": int(hit.score),
            })
        return out

    def load_buckets(self, buckets: Iterable[Mapping[str, object]]) -> None:
        """Restore calibration counters from a snapshot. Does not drop edges."""
        for raw in buckets:
            try:
                edge = int(raw.get("min_margin"))  # type: ignore[arg-type]
            except (TypeError, ValueError, AttributeError):
                continue
            if edge not in self.buckets:
                continue
            try:
                n = int(raw.get("n") or 0)
                correct = int(raw.get("correct") or 0)
            except (TypeError, ValueError):
                continue
            if n < 0 or correct < 0:
                continue
            if correct > n:
                correct = n
            self.buckets[edge].n = n
            self.buckets[edge].correct = correct


def action_fingerprint(action: Mapping[str, object]) -> str:
    """Stable, readable key for an action dict. Sorted, compact."""
    op = str(action.get("op") or "")
    parts = [op]
    for k in sorted(action):
        if k == "op":
            continue
        v = action[k]
        if v is None or v == "":
            continue
        parts.append(f"{k}={v}")
    return ":".join(parts)
