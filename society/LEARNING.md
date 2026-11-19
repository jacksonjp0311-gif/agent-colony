# Colony learning loop

The colony proposes trials from public method cards and from its
own failures. Hive's deterministic vote chooses at most one legal
op. A change is **kept** only when the self-heal trial window is
strictly better than its baseline *and* the twin control does not
lead on Oracle passes or verified depth. Fitness alone never
decides a keep. Reverts and voids are recorded too. This is not
AGI, not a novel theorem, and not a breakthrough claim.

- Method cards tried: **1**
- Kept: **18**
- Reverted (including twin-not-better): **16**
- Voided (environment changed mid-trial): **21**
- Inconclusive (no signal in either window; not counted against the action): **6**
- Proposed this snapshot: **10**
- Waiting on a twin judgment: **0**
- Hive decision deferred **9** times (`set_knob:direction=up:name=park_cycles:value=13`), waiting on a clean 6-cycle window (same Wilson 700‰ gate).
- Hive shadow picks: resolved 1, correct 0, pending 199, accuracy 0‰

## Per method card

| Card | Method | Tried | Kept | Reverted | Keep rate |
| --- | --- | ---: | ---: | ---: | ---: |
| `mc_bacbbd75d04b` | Perturb candidate claims a little more widely (annealing-style search). | 1 | 0 | 1 | 0‰ |

## Per op family

| Family | Tried | Kept | Reverted | Keep rate |
| --- | ---: | ---: | ---: | ---: |
| `set_knob:deep_digits` | 6 | 5 | 0 | 833‰ |
| `set_knob:deep_seconds` | 2 | 0 | 1 | 0‰ |
| `set_knob:evaluation_window` | 4 | 1 | 2 | 250‰ |
| `set_knob:fast_term_cap` | 7 | 4 | 0 | 571‰ |
| `set_knob:gf_term_cap` | 7 | 3 | 1 | 428‰ |
| `set_knob:park_cycles` | 19 | 4 | 8 | 210‰ |
| `set_knob:perturb_cooldown_cycles` | 2 | 0 | 1 | 0‰ |
| `set_knob:perturb_epsilon` | 2 | 0 | 1 | 0‰ |
| `set_knob:step_size` | 6 | 1 | 2 | 166‰ |

## Recent outcomes

- `reverted` · card `—` · family `set_knob:step_size` · cycle `20261118T052640Z_d72734` (baseline 4.0, trial 4.0)
- `kept` · card `—` · family `set_knob:park_cycles` · cycle `20261118T063231Z_f7d8ec` (baseline 4.0, trial 9.0)
- `kept` · card `—` · family `set_knob:evaluation_window` · cycle `20261118T084732Z_ecfd3b` (baseline 4.0, trial 6.0)
- `reverted` · card `—` · family `set_knob:evaluation_window` · cycle `20261118T102815Z_f488c2` (baseline 9.0, trial 2.0)
- `kept` · card `—` · family `set_knob:park_cycles` · cycle `20261118T115552Z_3b7d06` (baseline 3.0, trial 13.0)
- `reverted` · card `—` · family `set_knob:park_cycles` · cycle `20261118T135951Z_b01427` (baseline 10.0, trial 4.0)
- `voided` · card `—` · family `set_knob:park_cycles` · cycle `20261118T152905Z_deeb8d` (baseline 4.0, trial None)
- `reverted` · card `—` · family `set_knob:step_size` · cycle `20261118T202459Z_211471` (baseline 4.0, trial 4.0)
- `voided` · card `—` · family `set_knob:evaluation_window` · cycle `20261118T221919Z_a13b46` (baseline 4.0, trial None)
- `reverted` · card `mc_bacbbd75d04b` · family `set_knob:perturb_epsilon` · cycle `20261119T005408Z_a427b4` (baseline 4.0, trial 4.0)
- `reverted` · card `—` · family `set_knob:evaluation_window` · cycle `20261119T024154Z_15fcbb` (baseline 4.0, trial 0.0)
- `voided` · card `—` · family `set_knob:step_size` · cycle `20261119T032234Z_7a7360` (baseline 4.0, trial None)

## Reading breadth (knowledge library)

knowledge: 295 papers across 14/14 fields, 156 concepts, 75 cards formed, 1 tested, 0 kept.

| Field | Papers | Concepts | Cards formed | Cards tested | Cards kept |
| --- | ---: | ---: | ---: | ---: | ---: |
| automated_reasoning | 26 | 4 | 0 | 0 | 0 |
| cognitive_science | 10 | 6 | 5 | 0 | 0 |
| consciousness_self_models | 11 | 7 | 2 | 0 | 0 |
| learning_theory | 17 | 19 | 1 | 0 | 0 |
| mathematics | 51 | 0 | 0 | 0 | 0 |
| meta_learning | 16 | 12 | 2 | 0 | 0 |
| multi_agent_systems | 9 | 4 | 1 | 0 | 0 |
| neural_architecture | 37 | 27 | 8 | 0 | 0 |
| open_endedness | 20 | 20 | 20 | 0 | 0 |
| optimization_search | 24 | 25 | 15 | 0 | 0 |
| physics_complex_systems | 19 | 8 | 3 | 0 | 0 |
| recursive_self_improvement | 21 | 2 | 4 | 0 | 0 |
| self_learning_loops | 23 | 12 | 5 | 1 | 0 |
| swarm_collective_intelligence | 11 | 10 | 9 | 0 | 0 |

## Architecture ideas (proposals for a human-built PR; never auto-executed)

- `novelty_archive` — 25 papers (consciousness_self_models, neural_architecture, open_endedness, recursive_self_improvement): Keep an archive of behaviourally different claim forms and prefer under-explored ones (novelty/quality-diversity archive).
- `specialist_routing` — 18 papers (neural_architecture, physics_complex_systems): A gating step that sends each target to a specialist desk (mixture-of-experts style routing).
- `swarm_topology` — 12 papers (multi_agent_systems, neural_architecture, physics_complex_systems, swarm_collective_intelligence): Several improver agents propose over one shared candidate pool and a vote picks one (swarm/consensus topology).
- `meta_controller` — 9 papers (meta_learning, self_learning_loops): A meta-level desk that learns which kinds of self-heal trials tend to win and orders trials accordingly.
- `self_play_challenger` — 9 papers (self_learning_loops): A challenger role that generates harder variants of solved targets for the solver desks (self-play curriculum).

Not AGI. Not discovery. Human authorize still required for durable accepts.

