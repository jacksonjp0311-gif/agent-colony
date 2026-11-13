# Hive

Hive is a deterministic, retrieval-based fix chooser. It is built on
James Jackson's Bitwork router: a sparse binary scorer, not a neural
network and not an outside model. Given a description of a failure,
Hive looks up similar past cases in an append-only library and
proposes a fix from a closed set of safe operations. It cannot write
free-form code.

Hive lives inside Agent Colony as its own package so it can be taken
out, installed, tested, and examined on its own. It does not import
any colony code. The colony talks to it only through a small adapter
(`colony/hive_adapter.py`) that passes plain dictionaries and file
paths in and gets decisions out.

This is a tool for choosing among known, bounded repairs. It is not
a claim of general problem-solving ability.

## How Bitwork scores

The encoder and scores follow the Bitwork design published with
Perci (`github.com/jacksonjp0311-gif/Perci`). This package is a
pure-Python port of those formulas, not a Rust build and not a
loader of Perci weight packs.

1. **Features.** Input text is normalized (lowercase ASCII
   alphanumerics; other characters become single spaces) and broken
   into a bag of features: a bias term, a length bucket, words,
   prefixes, and suffixes.
2. **Hashing.** Each feature is hashed with 64-bit FNV-1a. Four
   12-bit slices of that hash set bits in a 4096-bit vector (64
   words of 64 bits). The same feature always sets the same bits.
3. **Category score.** For a query vector *q* and a category's
   positive and negative masks *m+*, *m−*, with an optional keyword
   prior *ρ*:

   *s_d = 2|q ∧ m+| − |q ∧ m−| + ρ*

4. **Prototype score.** For a stored example prototype *p*:

   *S(q, p) = 2|q ∧ p| − |p| = |q| − Hamming(q, p)*

5. **Abstain gate.** A match is accepted only if the Wilson 95%
   lower bound on the calibration bucket for its score margin is at
   least 700 permille (70%). The Wilson *z* used here is 1.96,
   written as the integer ratio 196/100. Below that bound, Hive
   abstains. It does not guess.

Calibration buckets follow Perci's `MARGIN_BUCKETS`: lower edges
0, 1, 2, 4, 8, 16, 32, 64. Adopt and revert outcomes update those
buckets so later decisions use what actually happened.

## Closed operation set

Every proposal is an operation from this fixed list. Unknown
operations are rejected. Each operation has hard bounds, and any
payload that names a frozen rule is rejected.

| Operation | What it does |
|-----------|----------------|
| `set_knob` | Propose a bounded change to a host policy knob (direction or an in-range value). |
| `add_skip_rule` | Skip a target, chain, or kind for a bounded number of cycles (1–24). |
| `add_park_rule` | Park a target, chain, or kind for a bounded number of cycles (3–18). |
| `reorder_desk` | Reorder a permutation of already-known desks. Does not create or retire desks. |
| `add_family_rotation` | Add one already-known search family to rotation. |
| `mark_ceiling` | Record that a target has a computational cap. This does not change any Oracle or Athanor number. |
| `add_triviality_candidate` | Offer a tighten-only triviality pattern to the host's checker lane. Never applied to the live Oracle. |

Knob names and bounds are shipped in `hive/data/knob_specs.json` so
standalone validation works. When a host is bound, its live specs
are used instead.

## How agents teach it

On each host cycle:

1. Swarm roles (improver, pathfinder, stem_checker, surveyor,
   archivist, legislator) independently label observed failures and
   each propose one legal operation, preferring a Bitwork retrieval
   when one is accepted.
2. A majority vote, with a deterministic tie-break, picks a winner.
   The legislator vetoes any proposal that touches a frozen rule.
   The Wilson 95% gate still abstains when the calibrated lower
   bound is below 700 permille.
3. At most one accepted action begins a trial on a cycle. Knob
   changes are handed back to the host to run as a self-heal trial;
   other operations use an equivalent windowed trial with the same
   fixed metric (new Oracle-reaching targets + new verified depth +
   3 × the change in Oracle passes).
4. An adopt becomes a positive library example; a revert becomes a
   negative one. Both are appended, never rewritten. The router
   learns from them, so later retrieval compounds what just
   happened.

Seed examples in `hive/data/seeds.jsonl` and
`hive/data/paraphrases.jsonl` are drawn from Agent Colony pull
requests #1–#7 and from the diagnosis vocabulary the colony already
uses. They are starting teaching material, not a rewrite of any
live log.

## What Hive cannot do

- It cannot write free-form code, patches, or new programs. It can
  only choose among the closed operations above.
- It cannot call a paid model, an outside API, or a neural network.
- It cannot authorize durable changes. A human authorize step, if
  the host has one, stays with the host.
- It cannot loosen, set, or rewrite the frozen rules listed next.

## Frozen rules Hive can never touch

These are rejected on every operation, by name and by fragment,
regardless of what a host asks:

- The Oracle, including its thresholds and the live Oracle
- The standing-trust gate *P* ≥ 0.70
- The 150 authored-check cap
- Athanor mathematics (ΔΦ, *C* = 1/(1+|ΔΦ|), H7, coherence, verdicts)
- The append-only witness (Hive will not rewrite witness records)
- Human authorize, and human_guide lessons (only a human writes those)

Metric weights used to score a trial (*w_targets*, *w_depth*,
*w_passes*) are also fixed.

## Public API

```python
import hive
from pathlib import Path

# Encode and score (pure functions, no I/O).
vec = hive.encode("stall loop same targets selected repeatedly")
router = hive.Router()

# Validate a proposed operation against the closed set.
decision = hive.validate({"op": "set_knob", "name": "park_cycles", "direction": "up"})
assert decision.ok
print(decision.fingerprint, hive.describe(decision.as_dict()))

# Train from the shipped seeds into a library you choose.
path = Path("fix_library.jsonl")
hive.ensure_seeded(path=path)
router = hive.train_router(path=path)
report = router.replay_accuracy(hive.held_out_cases(hive.load_records(path=path)), hold_out=True)
print(report)  # n, correct, abstained, accuracy_permille, lower_permille

# Teach from an adopt or revert the host already decided.
hive.teach_from_event(router, {
    "event": "adopt",
    "cycle_id": "c12",
    "action": decision.as_dict(),
    "symptom": "repeated targets in the stall loop",
    "label": "repeated_targets",
    "baseline_score": 0,
    "trial_score": 3,
    "helped": True,
}, path=path)

# Cycle entry used by a host adapter (observations come from the host).
# result = hive.run_cycle("c12")
```

The host adapter binds live helpers (diagnosis, knob bounds, trial
start, metric rows) through `hive.host.bind(heal=..., checker=...)`.
Hive looks those up at call time and never imports the host.

Default paths for the library and swarm state are next to the
package's parent directory (`data/commons/`, `society/systems/`).
Pass an explicit `path=` or have the adapter set the module
constants when you install Hive somewhere else.

## Running Hive on its own

Hive is pure Python 3.10+ with no third-party dependencies. Pytest
is needed only for the test suite.

```bash
# From this directory's parent (the Agent Colony repo, or a copy):
python3 -m hive                 # seed, train, held-out replay, print a report
python3 -m pytest hive/tests -q # Hive's own tests

# Install into a virtual environment (no extra packages are pulled in):
pip install ./hive
python -m hive
```

`python -m hive` writes only inside a temporary directory and
leaves no files behind.

## Extracting Hive from the colony

Hive is meant to be lifted out and inspected.

```bash
# Copy the package alone. No colony code comes along.
cp -a hive /tmp/hive-extract/hive
# Confirm the host is not there:
test ! -e /tmp/hive-extract/colony
PYTHONPATH=/tmp/hive-extract python3 -m hive
PYTHONPATH=/tmp/hive-extract python3 -m pytest /tmp/hive-extract/hive/tests -q
```

A colony test (`tests/test_hive_standalone.py`) and a CI step do
this copy-and-run check on every pull request, so a change that
makes Hive depend on the colony will fail.

The files you need are all under `hive/`:

```
hive/
  __init__.py          public API
  __main__.py          python -m hive
  bitwork.py           encoder, scores, Wilson gate, Router
  ops.py               closed operations and validation
  library.py           append-only library, training, mining
  swarm.py             roles, vote, trials, teach, cycle loop
  host.py              optional host hooks (unbound by default)
  data/
    seeds.jsonl        seed examples (PRs #1–#7)
    paraphrases.jsonl  held-out wording of the same actions
    historical.jsonl   real logged failures with known PR resolutions (#4, #6, #7)
    knob_specs.json    default knob bounds for standalone use
    diagnosis_suggestions.json
  tests/               self-contained tests (no colony imports)
  pyproject.toml
  README.md
```

## Structured features

Live findings and seed examples share a canonical feature string,
built by `hive.library.feature_text`. Structured tokens such as
`failure_class:no_progress_perturb`, `exit_reason:no_candidates`,
`cap_reason:term_cap`, `stall_reason`, `desk`, and `target_kind`
are prepended to a short prose symptom. Unique cycle ids and raw
evidence dumps are omitted. That is what lets a live failure
retrieve the seed it is supposed to, with a real (nonzero) margin.

`historical.jsonl` holds labeled seeds derived from the real
failures logged in `society/systems/swarm_learn.json` (12 stall
examples and 3 shadow picks of `add_skip_rule` /
`already_held_range` / `no_progress_perturb`) with the resolutions
from PRs #4, #6, and #7. Each is tagged with its source PR and
has a paraphrase so leave-one-out replay still has a sibling.
The Wilson 95% lower-bound gate and the 700 permille accept
threshold are unchanged.

## Persistence

Hive's live state has to survive a fresh CI checkout in order to
compound. The append-only JSONL logs (`data/commons/fix_library.jsonl`,
`data/commons/swarm_learn.jsonl`) are gitignored so they cannot bloat
the repository. Three committed snapshots are enough to restore
everything the next run needs:

- `society/systems/swarm_learn.json` — cycle counters, open trial,
  evidence (last 200), learning curve (last 200), calibration
  buckets with per-source counts, recent calibration outcomes
  (last 1,000), and pending or recently resolved shadow picks
  (at most 200).
- `society/systems/swarm_rules.json` — active non-knob rules.
- `society/systems/swarm_library.json` — the bounded library
  snapshot. Seed records are always kept. Other records are kept
  newest-first until the total reaches `LIBRARY_KEEP` (2,000).
  Record contents are never rewritten; compaction is only a size
  bound.

On a fresh checkout the JSONL log is missing, so `load_records`
restores the library from the snapshot and materializes a JSONL
file for in-run appends. The host's treatment job commits the
three snapshots after each evolve. The Wilson gate, the Oracle,
and authorize are not in this path.

## Calibration and the live gate

The Wilson 95% lower bound and the 700 permille accept threshold
are unchanged. What changed is *how the buckets get their counts*.

Calibration buckets used to start empty and only grow when a live
decision was applied. The gate abstains on an empty bucket, so
nothing was ever applied, and the buckets stayed empty.

Hive now fills buckets from labeled evidence only, never from
fabricated outcomes:

1. **Replay (`source=replay`).** After the library is seeded,
   each held-out leave-one-out case is routed on a temporary
   router trained on every other case. The top pick's margin and
   whether it matched the labeled action are counted in that
   margin's bucket, tagged `source=replay`. This slice is a
   deterministic function of the current library and is replaced
   (not double-counted) on every cycle.
2. **Shadow (`source=shadow`).** When the gate abstains, Hive
   records its top pick (failure class, action, margin) and does
   not apply it. When a later self-heal adopt or revert, or a
   human-merged positive fix, resolves the same failure class,
   the shadow is scored: an adopt or human-merged fix is correct
   iff the fingerprints match; a revert of the same action is
   incorrect; a revert of a different action leaves the shadow
   unresolved (there is no label for that pick).
3. **Apply (`source=apply`).** A live trial that is adopted or
   reverted still updates the bucket, as before, tagged
   `source=apply`. Append-only.

The Wilson lower bound for a bucket uses the sum of those
sources. An uncalibrated (empty) bucket still abstains.

## License

MIT, the same license as Agent Colony. See the repository's
`LICENSE` file.
