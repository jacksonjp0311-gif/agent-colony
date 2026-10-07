"""Oracle/novelty 'enabled' reads must use the entry's OWN flag, not a later entry's True."""
from __future__ import annotations

import colony.oracle as O


def test_held_out_window_disabled_even_if_next_entry_enabled(tmp_path, monkeypatch):
    art = tmp_path / "society" / "benchmarks" / "artifacts"
    art.mkdir(parents=True)
    (art / "lemma_impl.py").write_text(
        "HARD_TIER_LEMMAS = [\n"
        "    (\"adversarial_vandermonde_asymmetric\", check_x, False),\n"
        "    (\"adversarial_hockey_deep\", check_y, True),\n"
        "]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(O, "ROOT", tmp_path)
    r = O._held_out_for_theme("vandermonde", after_snapshot={"ok": True, "n_hard_pass": 3, "n_hard": 3})
    assert r["survives"] is False
    assert r["reason"] == "held_out:already_saturated_no_harder_window"
