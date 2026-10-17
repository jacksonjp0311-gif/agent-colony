"""Live textbook_reuse_score: prime-gap / k-tuple textbook topics with partial weights (going forward)."""
from colony import novelty_gate as NG

t = NG.textbook_reuse_score


def test_classic_shapes_with_hl_estimate_are_textbook_kill():
    for n in ("authored_sieve_hl_within_g2_w1", "authored_sieve_hl_within_g4_w1",
              "authored_sieve_hl_within_g2_4_w1", "authored_sieve_hl_within_g2_4_2_w1"):
        assert t(n) >= 0.34, n  # classic shape (1.0) + HL estimate (0.5) -> 0.5


def test_classic_residue_balance_is_textbook_kill():
    assert t("authored_sieve_residue_bal_g2_w2") == 0.5


def test_rarer_multigap_shapes_are_partial_not_kill():
    assert t("authored_sieve_hl_within_g6_4_2_w1") == round(1 / 3, 4)
    assert t("authored_sieve_residue_bal_g6_2_4_w1") == round(1 / 3, 4)
    assert t("authored_sieve_two_counter_g6_2_6_w1") == round(0.5 / 3, 4)
    assert t("authored_sieve_two_counter_g2_w1") == round(1 / 3, 4)


def test_topic_counted_once_name_and_text():
    # "twin primes" in the text and a twin shape in the name are the same topic (max, not sum)
    assert t("authored_sieve_two_counter_g2_w1", "counts twin primes") == round(1 / 3, 4)
    assert t("x", "twin primes and Brun's constant") == round(2 / 3, 4)
    assert t("x", "Hardy-Littlewood k-tuple conjecture") == round(0.5 / 3, 4)


def test_proposal_titles_scored_via_embedded_check_name():
    assert t("Chain `authored_sieve_hl_within_g2_w2` citing The large sieve") == 0.5


def test_never_loosens_existing_scores():
    # Non-prime names unchanged; the added term is >= 0 everywhere.
    assert t("authored_cassini__catalan_bounded_w1") == round(2 / 3, 4)
    assert t("lucas_addition") == 0.0
    assert t("easy_pad_assoc_add") >= 0.6667
    assert NG.prime_topic_hits("anything at all") == 0.0
