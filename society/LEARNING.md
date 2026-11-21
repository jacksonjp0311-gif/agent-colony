# Colony learning loop

The colony proposes trials from public method cards and from its
own failures. Hive's deterministic vote chooses at most one legal
op. A change is **kept** only when the self-heal trial window is
strictly better than its baseline *and* the twin control does not
lead on Oracle passes or verified depth. Fitness alone never
decides a keep. Reverts and voids are recorded too. This is not
AGI, not a novel theorem, and not a breakthrough claim.

- Method cards tried: **1**
- Kept: **20**
- Reverted (including twin-not-better): **25**
- Voided (environment changed mid-trial): **25**
- Inconclusive (no signal in either window; not counted against the action): **6**
- Proposed this snapshot: **10**
- Waiting on a twin judgment: **0**
- Hive decision deferred **8** times (`set_knob:direction=up:name=park_cycles:value=13`), waiting on a clean 6-cycle window (same Wilson 700‰ gate).
- Hive shadow picks: resolved 100, correct 0, pending 97, accuracy 0‰

## Per method card

| Card | Method | Tried | Kept | Reverted | Keep rate |
| --- | --- | ---: | ---: | ---: | ---: |
| `mc_bacbbd75d04b` | Perturb candidate claims a little more widely (annealing-style search). | 1 | 0 | 1 | 0‰ |

## Per op family

| Family | Tried | Kept | Reverted | Keep rate |
| --- | ---: | ---: | ---: | ---: |
| `set_knob:deep_digits` | 6 | 5 | 0 | 833‰ |
| `set_knob:deep_seconds` | 2 | 0 | 1 | 0‰ |
| `set_knob:evaluation_window` | 8 | 1 | 6 | 125‰ |
| `set_knob:fast_term_cap` | 7 | 4 | 0 | 571‰ |
| `set_knob:gf_term_cap` | 10 | 5 | 1 | 500‰ |
| `set_knob:park_cycles` | 21 | 4 | 9 | 190‰ |
| `set_knob:perturb_cooldown_cycles` | 2 | 0 | 1 | 0‰ |
| `set_knob:perturb_epsilon` | 2 | 0 | 1 | 0‰ |
| `set_knob:step_size` | 12 | 1 | 6 | 83‰ |

## Recent outcomes

- `reverted` · card `—` · family `set_knob:step_size` · cycle `20261119T140151Z_3ffac7` (baseline 4.0, trial 4.0)
- `reverted` · card `—` · family `set_knob:evaluation_window` · cycle `20261119T153843Z_bb7b69` (baseline 4.0, trial 4.0)
- `reverted` · card `—` · family `set_knob:park_cycles` · cycle `20261119T165615Z_1d9732` (baseline 4.0, trial 4.0)
- `reverted` · card `—` · family `set_knob:step_size` · cycle `20261119T183936Z_6fc954` (baseline 8.0, trial 4.0)
- `reverted` · card `—` · family `set_knob:evaluation_window` · cycle `20261119T200241Z_af2e28` (baseline 4.0, trial 4.0)
- `voided` · card `—` · family `set_knob:park_cycles` · cycle `20261119T202351Z_2926a6` (baseline 4.0, trial None)
- `reverted` · card `—` · family `set_knob:step_size` · cycle `20261119T233754Z_aa8d37` (baseline 4.0, trial 4.0)
- `reverted` · card `—` · family `set_knob:evaluation_window` · cycle `20261120T012810Z_d01708` (baseline 8.0, trial 4.0)
- `voided` · card `—` · family `set_knob:step_size` · cycle `20261120T020051Z_6fd496` (baseline 4.0, trial None)
- `kept` · card `—` · family `set_knob:gf_term_cap` · cycle `20261120T183030Z_577e72` (baseline 6.0, trial 7.0)
- `voided` · card `—` · family `set_knob:gf_term_cap` · cycle `20261120T233327Z_2f9c90` (baseline 2.0, trial None)
- `kept` · card `—` · family `set_knob:gf_term_cap` · cycle `20261121T033840Z_c01546` (baseline 12.0, trial 15.0)

## Reading breadth (knowledge library)

knowledge: 393 papers across 14/14 fields, 199 concepts, 97 cards formed, 1 tested, 0 kept.

| Field | Papers | Concepts | Cards formed | Cards tested | Cards kept |
| --- | ---: | ---: | ---: | ---: | ---: |
| automated_reasoning | 41 | 4 | 1 | 0 | 0 |
| cognitive_science | 13 | 7 | 6 | 0 | 0 |
| consciousness_self_models | 13 | 9 | 2 | 0 | 0 |
| learning_theory | 20 | 23 | 1 | 0 | 0 |
| mathematics | 71 | 0 | 0 | 0 | 0 |
| meta_learning | 17 | 13 | 2 | 0 | 0 |
| multi_agent_systems | 11 | 6 | 1 | 0 | 0 |
| neural_architecture | 49 | 35 | 9 | 0 | 0 |
| open_endedness | 34 | 33 | 34 | 0 | 0 |
| optimization_search | 32 | 34 | 20 | 0 | 0 |
| physics_complex_systems | 23 | 9 | 3 | 0 | 0 |
| recursive_self_improvement | 33 | 2 | 4 | 0 | 0 |
| self_learning_loops | 25 | 14 | 5 | 1 | 0 |
| swarm_collective_intelligence | 11 | 10 | 9 | 0 | 0 |

## Architecture ideas (proposals for a human-built PR; never auto-executed)

- `novelty_archive` — 39 papers (consciousness_self_models, neural_architecture, open_endedness, optimization_search, recursive_self_improvement): Keep an archive of behaviourally different claim forms and prefer under-explored ones (novelty/quality-diversity archive).
- `specialist_routing` — 25 papers (neural_architecture, physics_complex_systems): A gating step that sends each target to a specialist desk (mixture-of-experts style routing).
- `swarm_topology` — 12 papers (multi_agent_systems, neural_architecture, physics_complex_systems, swarm_collective_intelligence): Several improver agents propose over one shared candidate pool and a vote picks one (swarm/consensus topology).
- `self_play_challenger` — 11 papers (self_learning_loops): A challenger role that generates harder variants of solved targets for the solver desks (self-play curriculum).
- `meta_controller` — 10 papers (meta_learning, self_learning_loops): A meta-level desk that learns which kinds of self-heal trials tend to win and orders trials accordingly.

Not AGI. Not discovery. Human authorize still required for durable accepts.

