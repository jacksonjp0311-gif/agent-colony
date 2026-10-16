# Real citations — 2026-10-16

**Change.** Feed papers used to be cited by keyword overlap: `pick_seek_theme` ranked papers by shared
words with the target and, with no overlap, fell back to a rotating random recent paper. Now every
citation passes `colony/citations.py`:
- **papers**: the title or abstract must state one of the claim's key mathematical objects as a
  mathematical phrase ("Cassini's identity", "Pell equation", "Stirling numbers", "q-Catalan numbers", …),
  not just the word (so the Cassini spacecraft, hockey-stick surgery, a "metabolic derangement" and
  "Vandermonde matrix" for Vandermonde's *identity* are all rejected). There is no relevant paper → no
  citation, and the hypothesis says so explicitly. The legacy `papers.jsonl` theme goes through the same check.
- **OEIS**: an authored OEIS cross-check is kept only if the A-number's queried terms reproduce the
  colony's generator, recomputed at authoring time rather than trusted from the cache.
- A reason is recorded with every citation (`Relevance: …` in the proposal hypothesis; `citation_check`
  on authored OEIS rows).
Tests: `tests/test_citations.py` (6) plus updated feed tests.

**Measurement** (`scripts/citation_relevance_sample.py` → `sample.json`). Sample: all 66 distinct
(target, paper) citations the colony actually wrote to the ledger with the old picker. "After" is what the
new picker cites for the same 66 targets from the same feed cache. Ground truth comes from manual labels
(`labels.json`; 119 pairs, title and abstract read).

| | cited | relevant | share relevant |
|---|---|---|---|
| before (keyword) | 66 / 66 | 14 | **21.2%** |
| after (relevance check) | 55 / 66 (11 cite nothing) | 55 | **100%** |

Checker vs manual labels over all 119 pairs: precision 1.00, recall 0.955 (3 misses, e.g. a
binomial-coefficient paper for the hockey-stick identity, which is a binomial identity the
lexicon doesn't link).

**Caveats, stated honestly.**
- The labeller (Grok Bot) knew the checker's design, so the labels are not blind.
- Relevant means "the paper is about the claim's objects", not "the paper proves this claim". Most
  of these claims are textbook identities, so no feed paper actually states them.
- "After" picks come from the whole cache rather than the 24-item window used at citation time.
  The production window is now 120 papers.
