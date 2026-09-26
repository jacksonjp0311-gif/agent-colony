"""Hard-tier mutation snippets and apply helpers for conjecture desk.

Not novel discovery. Easy pads must fail keep under harder bench.
Exploration budget may reorder these; distribution must change after reverts.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HISTORY = Path(__file__).resolve().parent.parent / "society" / "benchmarks" / "conjecture_history.jsonl"

_EASY_PAD_DIFF = """
def check_easy_pad_diff_squares() -> bool:
    \"\"\"Easy pad - tiny difference-of-squares range (must fail keep under hard tier).\"\"\"
    return all(a * a - b * b == (a - b) * (a + b) for a in range(-2, 3) for b in range(-2, 3))
"""

_EASY_PAD_SNIP = """
def check_easy_pad_square_again() -> bool:
    \"\"\"Easy pad - small-range square identity only (should not ace hard tier).\"\"\"
    return all((a + b) ** 2 == a * a + 2 * a * b + b * b for a in range(-3, 4) for b in range(-3, 4))
"""

_EASY_PAD_COMM = """
def check_easy_pad_commutativity() -> bool:
    \"\"\"Easy pad - trivial commutativity (must fail keep under hard tier).\"\"\"
    return all(a + b == b + a and a * b == b * a for a in range(-3, 4) for b in range(-3, 4))
"""

_EASY_PAD_ABS = """
def check_easy_pad_abs_identity() -> bool:
    \"\"\"Easy pad - |a|^2 == a*a on tiny range (must fail keep under hard tier).\"\"\"
    return all(abs(a) * abs(a) == a * a for a in range(-4, 5))
"""

MUTATION_SNIPPETS: list[tuple[str, str, str]] = [
    ("vandermonde_conv", "hard_enable", "enable:vandermonde_conv"),
    ("hockey_stick", "hard_enable", "enable:hockey_stick"),
    ("cassini", "hard_enable", "enable:cassini"),
    ("workload_derived_chain", "hard_enable", "enable:workload_derived_chain"),
    ("binomial_sum_row", "hard_enable", "enable:binomial_sum_row"),
    ("fibonacci_addition", "hard_enable", "enable:fibonacci_addition"),
    ("catalan_bounded", "hard_enable", "enable:catalan_bounded"),
    ("lucas_addition", "hard_enable", "enable:lucas_addition"),
    ("central_binom_bound", "hard_enable", "enable:central_binom_bound"),
    ("pell_companion", "hard_enable", "enable:pell_companion"),
    # Autonomy mile — new hard enables (start disabled in lemma_impl)
    ("gcd_fibonacci", "hard_enable", "enable:gcd_fibonacci"),
    ("stirling_second_row", "hard_enable", "enable:stirling_second_row"),
    ("pythagorean_generation", "hard_enable", "enable:pythagorean_generation"),
    ("motzkin_bounded", "hard_enable", "enable:motzkin_bounded"),
    ("easy_pad_square_again", "easy_pad", _EASY_PAD_SNIP),
    ("easy_pad_diff_squares", "easy_pad", _EASY_PAD_DIFF),
    ("easy_pad_commutativity", "easy_pad", _EASY_PAD_COMM),
    ("easy_pad_abs_identity", "easy_pad", _EASY_PAD_ABS),
]


def already_has(src: str, name: str) -> bool:
    if f'("{name}"' in src and "True)," in src:
        m = re.search(rf'\("{re.escape(name)}".*?,\s*(True|False)\)', src, re.S)
        if m and m.group(1) == "True":
            return True
        if name.startswith("easy_pad") and f'("{name}"' in src:
            return True
    if name.startswith("easy_pad") and (f"check_{name}" in src or f'"{name}"' in src):
        return True
    return False


def enable_hard(src: str, name: str) -> str | None:
    pat = re.compile(rf'(\("{re.escape(name)}",\s*.*?,\s*)False(\))', re.S)
    m = pat.search(src)
    if not m:
        return None
    return src[: m.start()] + m.group(1) + "True" + m.group(2) + src[m.end() :]


def apply_easy_pad(src: str, name: str, snippet: str) -> str | None:
    if already_has(src, name):
        return None
    marker = "# Mutable catalog the conjecture desk may extend / mutate."
    if marker not in src:
        return None
    fn_block = snippet.strip() + "\n\n"
    src = src.replace(marker, fn_block + marker, 1)
    fn_name = f"check_{name}"
    entry = f'    ("{name}", {fn_name}, True),\n'
    hard_marker = "HARD_TIER_LEMMAS:"
    hi = src.find(hard_marker)
    if hi < 0:
        return None
    close = src.rfind("]", 0, hi)
    if close < 0:
        return None
    return src[:close] + entry + src[close:]


def apply_mutation(src: str, name: str, kind: str, snippet: str) -> str | None:
    if kind == "hard_enable":
        if already_has(src, name):
            return None
        return enable_hard(src, name)
    if kind == "easy_pad":
        return apply_easy_pad(src, name, snippet)
    return None


def recent_revert_counts(limit: int = 30) -> dict[str, int]:
    out: dict[str, int] = {}
    if not HISTORY.exists():
        return out
    for ln in HISTORY.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            h = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if h.get("decision") == "revert" and h.get("mutation"):
            out[h["mutation"]] = out.get(h["mutation"], 0) + 1
    return out
