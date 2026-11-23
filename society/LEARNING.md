# Colony learning loop

The colony proposes trials from public method cards and from its
own failures. Hive's deterministic vote chooses at most one legal
op. A change is **kept** only when the self-heal trial window is
strictly better than its baseline *and* the twin control does not
lead on Oracle passes or verified depth. Fitness alone never
decides a keep. Reverts and voids are recorded too. This is not
AGI, not a novel theorem, and not a breakthrough claim.

- Method cards tried: **2**
- Kept: **22**
- Reverted (including twin-not-better): **25**
- Voided (environment changed mid-trial): **26**
- Inconclusive (no signal in either window; not counted against the action): **6**
- Proposed this snapshot: **10**
- Waiting on a twin judgment: **0**
- Hive decision deferred **1** times (`add_skip_rule:cycles=8:target_kind=already_held_range`), waiting on a clean 6-cycle window (same Wilson 700‰ gate).
- Hive shadow picks: resolved 82, correct 0, pending 118, accuracy 0‰

## Per method card

| Card | Method | Tried | Kept | Reverted | Keep rate |
| --- | --- | ---: | ---: | ---: | ---: |
| `mc_bacbbd75d04b` | Perturb candidate claims a little more widely (annealing-style search). | 1 | 0 | 1 | 0‰ |
| `mc_e170e02332fe` | Remember already-tried targets for longer before retrying them (longer working memory). | 1 | 1 | 0 | 1000‰ |

## Per op family

| Family | Tried | Kept | Reverted | Keep rate |
| --- | ---: | ---: | ---: | ---: |
| `set_knob:deep_digits` | 6 | 5 | 0 | 833‰ |
| `set_knob:deep_seconds` | 2 | 0 | 1 | 0‰ |
| `set_knob:evaluation_window` | 8 | 1 | 6 | 125‰ |
| `set_knob:fast_term_cap` | 7 | 4 | 0 | 571‰ |
| `set_knob:gf_term_cap` | 12 | 6 | 1 | 500‰ |
| `set_knob:park_cycles` | 21 | 4 | 9 | 190‰ |
| `set_knob:perturb_cooldown_cycles` | 2 | 0 | 1 | 0‰ |
| `set_knob:perturb_epsilon` | 2 | 0 | 1 | 0‰ |
| `set_knob:step_size` | 12 | 1 | 6 | 83‰ |
| `set_knob:unused_menu_cycles` | 1 | 1 | 0 | 1000‰ |

## Recent outcomes

- `reverted` · card `—` · family `set_knob:step_size` · cycle `20261119T183936Z_6fc954` (baseline 8.0, trial 4.0)
- `reverted` · card `—` · family `set_knob:evaluation_window` · cycle `20261119T200241Z_af2e28` (baseline 4.0, trial 4.0)
- `voided` · card `—` · family `set_knob:park_cycles` · cycle `20261119T202351Z_2926a6` (baseline 4.0, trial None)
- `reverted` · card `—` · family `set_knob:step_size` · cycle `20261119T233754Z_aa8d37` (baseline 4.0, trial 4.0)
- `reverted` · card `—` · family `set_knob:evaluation_window` · cycle `20261120T012810Z_d01708` (baseline 8.0, trial 4.0)
- `voided` · card `—` · family `set_knob:step_size` · cycle `20261120T020051Z_6fd496` (baseline 4.0, trial None)
- `kept` · card `—` · family `set_knob:gf_term_cap` · cycle `20261120T183030Z_577e72` (baseline 6.0, trial 7.0)
- `voided` · card `—` · family `set_knob:gf_term_cap` · cycle `20261120T233327Z_2f9c90` (baseline 2.0, trial None)
- `kept` · card `—` · family `set_knob:gf_term_cap` · cycle `20261121T033840Z_c01546` (baseline 12.0, trial 15.0)
- `voided` · card `—` · family `set_knob:gf_term_cap` · cycle `20261121T150321Z_64eb8c` (baseline 4.0, trial None)
- `kept` · card `mc_e170e02332fe` · family `set_knob:unused_menu_cycles` · cycle `20261121T185804Z_5d2655` (baseline 11.0, trial 20.0)
- `kept` · card `—` · family `set_knob:gf_term_cap` · cycle `20261122T092727Z_c1e88c` (baseline 13.0, trial 14.0)

## Reading breadth (knowledge library)

knowledge: 452 papers across 14/14 fields, 228 concepts, 114 cards formed, 2 tested, 1 kept.

| Field | Papers | Concepts | Cards formed | Cards tested | Cards kept |
| --- | ---: | ---: | ---: | ---: | ---: |
| automated_reasoning | 49 | 6 | 1 | 0 | 0 |
| cognitive_science | 13 | 7 | 6 | 1 | 1 |
| consciousness_self_models | 13 | 9 | 2 | 0 | 0 |
| learning_theory | 22 | 25 | 1 | 0 | 0 |
| mathematics | 79 | 0 | 0 | 0 | 0 |
| meta_learning | 18 | 13 | 2 | 0 | 0 |
| multi_agent_systems | 12 | 7 | 2 | 0 | 0 |
| neural_architecture | 57 | 40 | 9 | 0 | 0 |
| open_endedness | 42 | 41 | 43 | 0 | 0 |
| optimization_search | 37 | 40 | 23 | 0 | 0 |
| physics_complex_systems | 28 | 10 | 3 | 0 | 0 |
| recursive_self_improvement | 41 | 5 | 6 | 0 | 0 |
| self_learning_loops | 29 | 14 | 6 | 1 | 0 |
| swarm_collective_intelligence | 12 | 11 | 10 | 0 | 0 |

## Architecture ideas (proposals for a human-built PR; never auto-executed)

- `novelty_archive` — 47 papers (consciousness_self_models, neural_architecture, open_endedness, optimization_search, recursive_self_improvement): Keep an archive of behaviourally different claim forms and prefer under-explored ones (novelty/quality-diversity archive).
- `specialist_routing` — 30 papers (neural_architecture, physics_complex_systems): A gating step that sends each target to a specialist desk (mixture-of-experts style routing).
- `swarm_topology` — 13 papers (multi_agent_systems, neural_architecture, physics_complex_systems, swarm_collective_intelligence): Several improver agents propose over one shared candidate pool and a vote picks one (swarm/consensus topology).
- `meta_controller` — 11 papers (meta_learning, recursive_self_improvement, self_learning_loops): A meta-level desk that learns which kinds of self-heal trials tend to win and orders trials accordingly.
- `self_play_challenger` — 11 papers (self_learning_loops): A challenger role that generates harder variants of solved targets for the solver desks (self-play curriculum).

Not AGI. Not discovery. Human authorize still required for durable accepts.

