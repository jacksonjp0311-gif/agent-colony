"""Citation relevance: a source is kept only if it states the claim's key objects."""
from colony.citations import assess, assess_oeis, assess_paper, components


def P(title, text=""):
    return {"source": "arxiv", "kind": "paper", "title": title, "text": text}


def test_components_split_chain_names():
    assert components("authored_cassini__catalan_convolution_w1") == ["cassini", "catalan_convolution"]
    assert components("pell_companion") == ["pell_companion"]


def test_shared_word_is_not_support():
    t = "authored_cassini__catalan_convolution_w1"
    assert not assess_paper(t, P("Seasonal variation of the main gases in Titan's ionosphere from Cassini INMS data"))["relevant"]
    assert not assess_paper("authored_hockey_stick__motzkin_bounded_w1".replace("motzkin", "pell"),
                            P("Minimal skin incision versus conventional hockey stick incision"))["relevant"]
    assert not assess_paper("authored_binomial_symmetry__vandermonde_conv_w1",
                            P("Les vostres Catalonian girls preferides: national identity"))["relevant"]
    assert not assess_paper("authored_pythagorean_generation__x_w1", P("Pythagorean fuzzy topological polygroups"))["relevant"]
    assert not assess_paper("authored_vandermonde_conv__y_w1", P("Confluent Vandermonde matrix and related topics"))["relevant"]
    assert not assess_paper("authored_binomial_sum_row__z_w1", P("Classification of unmixed parity binomial edge ideals"))["relevant"]


def test_object_phrase_is_support_with_reason():
    r = assess_paper("authored_cassini__catalan_convolution_w1", P("A note", "We prove a q-analogue of Cassini's identity."))
    assert r["relevant"] and "cassini" in r["reason"].lower()
    r = assess_paper("authored_geometric_sum__pell_companion_w1", P("Cofactor dynamics and Pell equations in GCD-augmented recurrences"))
    assert r["relevant"] and r["matched"][0].startswith("pell_companion:")
    assert assess_paper("authored_catalan_bounded__x_w1", P("Lattice points and rational q-Catalan numbers"))["relevant"]
    assert assess_paper("authored_motzkin_bounded__x_w1", P("Enumeration via Motzkin paths"))["relevant"]


def test_negative_has_reason_naming_objects():
    r = assess_paper("authored_hockey_stick__stirling_second_row_w1", P("TANGO: RNA topology and geometry co-design"))
    assert not r["relevant"] and "hockey" in r["reason"] and "stirling" in r["reason"]


def test_oeis_requires_id_or_term_match():
    fib = [1, 1, 2, 3, 5, 8, 13, 21, 34]
    assert assess_oeis("x", {"oeis_id": "A000045", "terms": fib}, claim_terms=fib)["relevant"]
    assert not assess_oeis("x", {"oeis_id": "A000045", "terms": fib}, claim_terms=[1, 2, 4, 8, 16, 32, 64])["relevant"]
    assert assess_oeis("authored_oeis_a000108__catalan_bounded", {"oeis_id": "A000108", "terms": []})["relevant"]
    assert assess({"x": 1} and "x", {"oeis_id": "A000079", "source": "oeis", "terms": [1, 2, 4, 8, 16, 32]},
                  claim_terms=[1, 2, 4, 8, 16, 32])["relevant"]


def test_non_math_senses_rejected():
    assert not assess_paper("authored_geometric_sum__hockey_stick_w1", P("Bent hockey-stick stock-recruitment function"))["relevant"]
    assert not assess_paper("authored_derangement_subfactorial__x_w1",
                            P("Hypothyroidism, an underappreciated metabolic derangement"))["relevant"]
    assert assess_paper("authored_derangement_subfactorial__x_w1",
                        P("Fixed points", "We count derangements, i.e. permutations without fixed points."))["relevant"]
