"""Faithful Bitwork encoder, integer scores, Wilson gate, and determinism.

The encoder and feature hash follow Perci ``src/cognitive.rs``; the
Wilson 95% lower bound and margin buckets follow
``wilson_lower_permille`` in ``src/weight_packs.rs``. No Rust build,
no external model.
"""
from __future__ import annotations

from colony.bitwork import (
    BITS,
    FNV_OFFSET,
    FNV_PRIME,
    HASH_SHIFTS,
    MARGIN_BUCKETS,
    WILSON_ACCEPT_PERMILLE,
    WORDS,
    Router,
    bitwise_and,
    bitwise_or,
    category_score,
    encode,
    fnv1a_64,
    freeze,
    empty_bits,
    hamming,
    intersection_count,
    keyword_prior,
    margin_bucket,
    normalize,
    popcount,
    prototype_score,
    set_feature,
    wilson_lower_permille,
)


def test_constants_match_perci_design():
    assert BITS == 4096
    assert WORDS == 64
    assert FNV_OFFSET == 0xCBF29CE484222325
    assert FNV_PRIME == 0x00000100000001B3
    assert HASH_SHIFTS == (0, 12, 24, 36)
    assert MARGIN_BUCKETS == (0, 1, 2, 4, 8, 16, 32, 64)
    assert WILSON_ACCEPT_PERMILLE == 700


def test_normalize_matches_perci_rules():
    assert normalize("Hello, World!") == "hello world"
    assert normalize("  ABC  def  ") == "abc def"
    assert normalize("P ≥ 0.70") == "p 0 70"
    assert normalize("") == ""
    assert normalize("***") == ""
    # Non-ASCII punctuation collapses to a space; alphanumerics stay.
    assert normalize("Erdős-Straus") == "erd s straus"


def test_encode_is_deterministic_and_4096_bits():
    text = "stall loop same targets selected repeatedly"
    a = encode(text)
    b = encode(text)
    assert a == b
    assert len(a) == WORDS
    assert all(0 <= w < 2**64 for w in a)
    # A second encode of a different string is a different vector.
    c = encode("depth at physical cap raise the fast term cap")
    assert a != c
    assert popcount(a) > 0
    assert popcount(c) > 0


def test_set_feature_uses_four_12bit_slices():
    bits = empty_bits()
    set_feature(bits, "bias")
    frozen = freeze(bits)
    # Four slices can collide, so 1..4 bits are set for a single feature.
    n = popcount(frozen)
    assert 1 <= n <= 4
    h = fnv1a_64("bias")
    positions = [(h >> s) & (BITS - 1) for s in HASH_SHIFTS]
    for pos in positions:
        word, bit = pos >> 6, pos & 63
        assert frozen[word] & (1 << bit)


def test_fnv1a_wraps_like_u64():
    # Offset basis is the hash of the empty string.
    assert fnv1a_64("") == FNV_OFFSET
    # A longer string still stays inside 64 bits.
    h = fnv1a_64("w:" + "a" * 200)
    assert 0 <= h <= 0xFFFFFFFFFFFFFFFF


def test_prototype_score_is_hamming_identity():
    q = encode("park the repeating proposal")
    p = encode("raise the fast term cap")
    s = prototype_score(q, p)
    assert s == popcount(q) - hamming(q, p)
    # A vector against itself: S(q, q) = |q|.
    assert prototype_score(q, q) == popcount(q)
    assert hamming(q, q) == 0


def test_category_score_integer_formula():
    q = encode("trivial claim pattern slipped through")
    plus = encode("trivial claim pattern")
    minus = encode("unrelated goldbach search")
    s = category_score(q, plus, minus, prior=48)
    expected = 2 * intersection_count(q, plus) - intersection_count(q, minus) + 48
    assert s == expected
    # A negative mask that does not overlap contributes 0.
    empty = freeze(empty_bits())
    assert category_score(q, plus, empty, 0) == 2 * intersection_count(q, plus)


def test_keyword_prior_counts_whole_words():
    text = "high revert rate on self heal trials"
    assert keyword_prior(text, ["revert", "rate"]) == 48 * 2
    assert keyword_prior(text, ["missingcue"]) == 0
    assert keyword_prior(text, ["high revert"]) == 48  # both words present


def test_wilson_gate_values_and_abstention():
    assert wilson_lower_permille(0, 0) == 0
    assert wilson_lower_permille(0, 5) == 0
    assert wilson_lower_permille(1, 1) < WILSON_ACCEPT_PERMILLE
    assert wilson_lower_permille(8, 8) < WILSON_ACCEPT_PERMILLE
    # 9 perfect observations is the smallest n that clears 700 ‰ at p=1.
    assert wilson_lower_permille(9, 9) >= WILSON_ACCEPT_PERMILLE
    assert wilson_lower_permille(9, 9) == 700
    assert wilson_lower_permille(20, 20) > wilson_lower_permille(9, 9)
    assert wilson_lower_permille(50, 100) < 500
    # Over-count is clamped to n, and the function is deterministic.
    assert wilson_lower_permille(15, 10) == wilson_lower_permille(10, 10)
    assert wilson_lower_permille(19, 20) == wilson_lower_permille(19, 20)


def test_margin_bucket_edges():
    assert margin_bucket(-3) == 0
    assert margin_bucket(0) == 0
    assert margin_bucket(1) == 1
    assert margin_bucket(3) == 2
    assert margin_bucket(8) == 8
    assert margin_bucket(100) == 64


def test_router_learn_and_classify_deterministic():
    r = Router()
    r.learn("stall loop same targets", "repeated_targets", "set_knob:park_cycles:up",
            source_id="a", proto_key="a")
    r.learn("evaluator hit a term cap", "depth_at_physical_cap", "set_knob:fast_term_cap:up",
            source_id="b", proto_key="b")
    first = r.classify("stall loop same targets")
    second = r.classify("stall loop same targets")
    assert first is not None and second is not None
    assert first.action_key == second.action_key == "set_knob:park_cycles:up"
    assert first.score == second.score
    # Same text always wins against a different stored example.
    other = r.classify("evaluator hit a term cap")
    assert other is not None
    assert other.action_key == "set_knob:fast_term_cap:up"


def test_router_append_only_no_rewrite():
    r = Router()
    r.learn("alpha", "lab", "act", source_id="x", proto_key="x")
    first_bits = r.prototypes[0].bits
    # A second learn with the same key is ignored (append-only).
    r.learn("beta is a different text", "lab", "act", source_id="x", proto_key="x")
    assert len(r.prototypes) == 1
    assert r.prototypes[0].bits == first_bits
    # A new key is appended.
    r.learn("beta is a different text", "lab", "act", source_id="y", proto_key="y")
    assert len(r.prototypes) == 2


def test_wilson_abstains_until_calibrated():
    r = Router()
    r.learn("park the repeating proposal", "dead_end", "park", proto_key="p1")
    hit = r.classify("park the repeating proposal")
    assert hit is not None
    # Empty bucket: Wilson lower is 0, so the gate abstains.
    assert hit.bucket_n == 0
    assert hit.lower_permille == 0
    assert hit.abstained is True
    assert hit.accepted is False
    # Nine correct outcomes in the match's bucket open the gate.
    for _ in range(9):
        r.record_outcome(hit.margin, True)
    accepted, lower, n = r.would_accept(hit.margin)
    assert n == 9
    assert lower >= WILSON_ACCEPT_PERMILLE
    assert accepted is True
    hit2 = r.classify("park the repeating proposal")
    assert hit2 is not None
    assert hit2.accepted is True
    assert hit2.abstained is False


def test_negative_examples_update_masks_not_top_positive():
    r = Router()
    r.learn("raise the fast term cap at a physical cap", "cap", "raise_fast",
            positive=True, proto_key="pos")
    r.learn("lower the oracle threshold so more claims pass", "invariant", "loosen",
            positive=False, proto_key="neg")
    hit = r.retrieve("lower the oracle threshold so more claims pass", polarity="positive", top_k=3)
    # The negative example is not in the positive retrieval list.
    assert all(m.polarity == "positive" for m in hit)
    assert all(m.action_key != "loosen" for m in hit)
    negs = r.retrieve("lower the oracle threshold so more claims pass", polarity="negative", top_k=1)
    assert negs and negs[0].action_key == "loosen"


def test_bitwise_helpers_are_wordwise():
    a = encode("alpha")
    b = encode("beta")
    both = bitwise_and(a, b)
    either = bitwise_or(a, b)
    assert popcount(both) == intersection_count(a, b)
    assert popcount(either) == popcount(a) + popcount(b) - intersection_count(a, b)
