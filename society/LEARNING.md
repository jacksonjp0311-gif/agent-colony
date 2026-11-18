# Colony learning loop

The colony proposes trials from public method cards and from its
own failures. Hive's deterministic vote chooses at most one legal
op. A change is **kept** only when the self-heal trial window is
strictly better than its baseline *and* the twin control does not
lead on Oracle passes or verified depth. Fitness alone never
decides a keep. Reverts and voids are recorded too. This is not
AGI, not a novel theorem, and not a breakthrough claim.

- Method cards tried: **0**
- Kept: **15**
- Reverted (including twin-not-better): **10**
- Voided (environment changed mid-trial): **18**
- Inconclusive (no signal in either window; not counted against the action): **6**
- Proposed this snapshot: **8**
- Waiting on a twin judgment: **0**
- Hive decision deferred **2** times (`set_knob:direction=up:name=park_cycles:value=11`), waiting on a clean 6-cycle window (same Wilson 700‰ gate).
- Hive shadow picks: resolved 52, correct 0, pending 148, accuracy 0‰

## Per method card

_None yet._

## Per op family

| Family | Tried | Kept | Reverted | Keep rate |
| --- | ---: | ---: | ---: | ---: |
| `set_knob:deep_digits` | 6 | 5 | 0 | 833‰ |
| `set_knob:deep_seconds` | 2 | 0 | 1 | 0‰ |
| `set_knob:fast_term_cap` | 7 | 4 | 0 | 571‰ |
| `set_knob:gf_term_cap` | 7 | 3 | 1 | 428‰ |
| `set_knob:park_cycles` | 15 | 2 | 7 | 133‰ |
| `set_knob:perturb_cooldown_cycles` | 2 | 0 | 1 | 0‰ |
| `set_knob:perturb_epsilon` | 1 | 0 | 0 | 0‰ |
| `set_knob:step_size` | 3 | 1 | 0 | 333‰ |

## Recent outcomes

- `reverted` · card `—` · family `set_knob:park_cycles` · cycle `20261116T173537Z_be43ea` (baseline 8.0, trial 5.0)
- `reverted` · card `—` · family `set_knob:park_cycles` · cycle `20261116T183049Z_7f7d82` (baseline 5.0, trial 4.0)
- `kept` · card `—` · family `set_knob:park_cycles` · cycle `20261116T192905Z_bc22f0` (baseline 4.0, trial 5.0)
- `reverted` · card `—` · family `set_knob:park_cycles` · cycle `20261116T202906Z_a13d81` (baseline 5.0, trial 4.0)
- `kept` · card `—` · family `set_knob:park_cycles` · cycle `20261116T212728Z_656378` (baseline 4.0, trial 7.0)
- `reverted` · card `—` · family `set_knob:park_cycles` · cycle `20261116T230504Z_2f9546` (baseline 7.0, trial 6.0)
- `reverted` · card `—` · family `set_knob:park_cycles` · cycle `20261117T000430Z_7fec4f` (baseline 6.0, trial 4.0)
- `reverted` · card `—` · family `set_knob:park_cycles` · cycle `20261117T010509Z_15fab9` (baseline 4.0, trial 4.0)
- `voided` · card `—` · family `set_knob:park_cycles` · cycle `20261117T022831Z_add0c8` (baseline 4.0, trial None)
- `kept` · card `—` · family `set_knob:step_size` · cycle `20261117T115227Z_31a000` (baseline 5.0, trial 7.0)
- `voided` · card `—` · family `set_knob:step_size` · cycle `20261117T121839Z_ea1759` (baseline 7.0, trial None)
- `voided` · card `—` · family `set_knob:step_size` · cycle `20261117T141904Z_441571` (baseline 5.0, trial None)

## Reading breadth (knowledge library)

knowledge: 221 papers across 14/14 fields, 121 concepts, 55 cards formed, 0 tested, 0 kept.

| Field | Papers | Concepts | Cards formed | Cards tested | Cards kept |
| --- | ---: | ---: | ---: | ---: | ---: |
| automated_reasoning | 25 | 4 | 0 | 0 | 0 |
| cognitive_science | 8 | 4 | 3 | 0 | 0 |
| consciousness_self_models | 9 | 4 | 1 | 0 | 0 |
| learning_theory | 13 | 15 | 1 | 0 | 0 |
| mathematics | 33 | 0 | 0 | 0 | 0 |
| meta_learning | 10 | 8 | 0 | 0 | 0 |
| multi_agent_systems | 9 | 4 | 1 | 0 | 0 |
| neural_architecture | 22 | 18 | 6 | 0 | 0 |
| open_endedness | 16 | 16 | 16 | 0 | 0 |
| optimization_search | 21 | 21 | 11 | 0 | 0 |
| physics_complex_systems | 18 | 7 | 3 | 0 | 0 |
| recursive_self_improvement | 13 | 1 | 2 | 0 | 0 |
| self_learning_loops | 14 | 10 | 3 | 0 | 0 |
| swarm_collective_intelligence | 10 | 9 | 8 | 0 | 0 |

## Architecture ideas (proposals for a human-built PR; never auto-executed)

- `novelty_archive` — 19 papers (consciousness_self_models, neural_architecture, open_endedness, recursive_self_improvement): Keep an archive of behaviourally different claim forms and prefer under-explored ones (novelty/quality-diversity archive).
- `swarm_topology` — 11 papers (multi_agent_systems, neural_architecture, physics_complex_systems, swarm_collective_intelligence): Several improver agents propose over one shared candidate pool and a vote picks one (swarm/consensus topology).
- `specialist_routing` — 11 papers (neural_architecture): A gating step that sends each target to a specialist desk (mixture-of-experts style routing).
- `meta_controller` — 7 papers (meta_learning, self_learning_loops): A meta-level desk that learns which kinds of self-heal trials tend to win and orders trials accordingly.
- `self_play_challenger` — 7 papers (self_learning_loops): A challenger role that generates harder variants of solved targets for the solver desks (self-play curriculum).

Not AGI. Not discovery. Human authorize still required for durable accepts.

