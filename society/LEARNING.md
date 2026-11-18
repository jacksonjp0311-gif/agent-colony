# Colony learning loop

The colony proposes trials from public method cards and from its
own failures. Hive's deterministic vote chooses at most one legal
op. A change is **kept** only when the self-heal trial window is
strictly better than its baseline *and* the twin control does not
lead on Oracle passes or verified depth. Fitness alone never
decides a keep. Reverts and voids are recorded too. This is not
AGI, not a novel theorem, and not a breakthrough claim.

- Method cards tried: **0**
- Kept: **17**
- Reverted (including twin-not-better): **12**
- Voided (environment changed mid-trial): **18**
- Inconclusive (no signal in either window; not counted against the action): **6**
- Proposed this snapshot: **10**
- Waiting on a twin judgment: **0**
- Hive decision deferred **1** times (`set_knob:direction=up:name=park_cycles:value=13`), waiting on a clean 6-cycle window (same Wilson 700‰ gate).
- Hive shadow picks: resolved 30, correct 0, pending 170, accuracy 0‰

## Per method card

_None yet._

## Per op family

| Family | Tried | Kept | Reverted | Keep rate |
| --- | ---: | ---: | ---: | ---: |
| `set_knob:deep_digits` | 6 | 5 | 0 | 833‰ |
| `set_knob:deep_seconds` | 2 | 0 | 1 | 0‰ |
| `set_knob:evaluation_window` | 2 | 1 | 1 | 500‰ |
| `set_knob:fast_term_cap` | 7 | 4 | 0 | 571‰ |
| `set_knob:gf_term_cap` | 7 | 3 | 1 | 428‰ |
| `set_knob:park_cycles` | 16 | 3 | 7 | 187‰ |
| `set_knob:perturb_cooldown_cycles` | 2 | 0 | 1 | 0‰ |
| `set_knob:perturb_epsilon` | 1 | 0 | 0 | 0‰ |
| `set_knob:step_size` | 4 | 1 | 1 | 250‰ |

## Recent outcomes

- `kept` · card `—` · family `set_knob:park_cycles` · cycle `20261116T212728Z_656378` (baseline 4.0, trial 7.0)
- `reverted` · card `—` · family `set_knob:park_cycles` · cycle `20261116T230504Z_2f9546` (baseline 7.0, trial 6.0)
- `reverted` · card `—` · family `set_knob:park_cycles` · cycle `20261117T000430Z_7fec4f` (baseline 6.0, trial 4.0)
- `reverted` · card `—` · family `set_knob:park_cycles` · cycle `20261117T010509Z_15fab9` (baseline 4.0, trial 4.0)
- `voided` · card `—` · family `set_knob:park_cycles` · cycle `20261117T022831Z_add0c8` (baseline 4.0, trial None)
- `kept` · card `—` · family `set_knob:step_size` · cycle `20261117T115227Z_31a000` (baseline 5.0, trial 7.0)
- `voided` · card `—` · family `set_knob:step_size` · cycle `20261117T121839Z_ea1759` (baseline 7.0, trial None)
- `voided` · card `—` · family `set_knob:step_size` · cycle `20261117T141904Z_441571` (baseline 5.0, trial None)
- `reverted` · card `—` · family `set_knob:step_size` · cycle `20261118T052640Z_d72734` (baseline 4.0, trial 4.0)
- `kept` · card `—` · family `set_knob:park_cycles` · cycle `20261118T063231Z_f7d8ec` (baseline 4.0, trial 9.0)
- `kept` · card `—` · family `set_knob:evaluation_window` · cycle `20261118T084732Z_ecfd3b` (baseline 4.0, trial 6.0)
- `reverted` · card `—` · family `set_knob:evaluation_window` · cycle `20261118T102815Z_f488c2` (baseline 9.0, trial 2.0)

## Reading breadth (knowledge library)

knowledge: 265 papers across 14/14 fields, 143 concepts, 74 cards formed, 0 tested, 0 kept.

| Field | Papers | Concepts | Cards formed | Cards tested | Cards kept |
| --- | ---: | ---: | ---: | ---: | ---: |
| automated_reasoning | 26 | 4 | 0 | 0 | 0 |
| cognitive_science | 10 | 6 | 5 | 0 | 0 |
| consciousness_self_models | 10 | 6 | 2 | 0 | 0 |
| learning_theory | 15 | 17 | 1 | 0 | 0 |
| mathematics | 42 | 0 | 0 | 0 | 0 |
| meta_learning | 12 | 10 | 2 | 0 | 0 |
| multi_agent_systems | 9 | 4 | 1 | 0 | 0 |
| neural_architecture | 29 | 21 | 7 | 0 | 0 |
| open_endedness | 20 | 20 | 20 | 0 | 0 |
| optimization_search | 24 | 25 | 15 | 0 | 0 |
| physics_complex_systems | 19 | 8 | 3 | 0 | 0 |
| recursive_self_improvement | 21 | 2 | 4 | 0 | 0 |
| self_learning_loops | 17 | 10 | 5 | 0 | 0 |
| swarm_collective_intelligence | 11 | 10 | 9 | 0 | 0 |

## Architecture ideas (proposals for a human-built PR; never auto-executed)

- `novelty_archive` — 24 papers (consciousness_self_models, neural_architecture, open_endedness, recursive_self_improvement): Keep an archive of behaviourally different claim forms and prefer under-explored ones (novelty/quality-diversity archive).
- `specialist_routing` — 15 papers (neural_architecture, physics_complex_systems): A gating step that sends each target to a specialist desk (mixture-of-experts style routing).
- `swarm_topology` — 12 papers (multi_agent_systems, neural_architecture, physics_complex_systems, swarm_collective_intelligence): Several improver agents propose over one shared candidate pool and a vote picks one (swarm/consensus topology).
- `prediction_error_routing` — 7 papers (cognitive_science, learning_theory, neural_architecture, optimization_search, physics_complex_systems): Route work to targets where predicted and actual outcomes differ most (prediction-error-driven routing).
- `working_memory_buffer` — 7 papers (cognitive_science, consciousness_self_models, neural_architecture): A small per-cycle working-memory buffer of recent outcomes that every desk reads before choosing work.

Not AGI. Not discovery. Human authorize still required for durable accepts.

