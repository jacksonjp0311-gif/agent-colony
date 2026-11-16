# Colony learning loop

The colony proposes trials from public method cards and from its
own failures. Hive's deterministic vote chooses at most one legal
op. A change is **kept** only when the self-heal trial window is
strictly better than its baseline *and* the twin control does not
lead on Oracle passes or verified depth. Fitness alone never
decides a keep. Reverts and voids are recorded too. This is not
AGI, not a novel theorem, and not a breakthrough claim.

- Method cards tried: **0**
- Kept: **12**
- Reverted (including twin-not-better): **4**
- Voided (environment changed mid-trial): **15**
- Inconclusive (no signal in either window; not counted against the action): **6**
- Proposed this snapshot: **7**
- Waiting on a twin judgment: **0**
- Hive decision deferred **1** times (`set_knob:direction=up:name=park_cycles:value=8`), waiting on a clean 6-cycle window (same Wilson 700‰ gate).
- Hive shadow picks: resolved 100, correct 0, pending 71, accuracy 0‰

## Per method card

_None yet._

## Per op family

| Family | Tried | Kept | Reverted | Keep rate |
| --- | ---: | ---: | ---: | ---: |
| `set_knob:deep_digits` | 6 | 5 | 0 | 833‰ |
| `set_knob:deep_seconds` | 2 | 0 | 1 | 0‰ |
| `set_knob:fast_term_cap` | 7 | 4 | 0 | 571‰ |
| `set_knob:gf_term_cap` | 7 | 3 | 1 | 428‰ |
| `set_knob:park_cycles` | 6 | 0 | 1 | 0‰ |
| `set_knob:perturb_cooldown_cycles` | 2 | 0 | 1 | 0‰ |
| `set_knob:perturb_epsilon` | 1 | 0 | 0 | 0‰ |

## Recent outcomes

- `inconclusive` · card `—` · family `set_knob:deep_seconds` · cycle `20261115T154457Z_1ab8a3` (baseline 0.0, trial 0.0)
- `voided` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T160121Z_c4b068` (baseline 0.0, trial None)
- `kept` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T171106Z_386886` (baseline 0.0, trial 231.0)
- `kept` · card `—` · family `set_knob:deep_digits` · cycle `20261115T175054Z_8f2c59` (baseline 0.0, trial 324.0)
- `inconclusive` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T183448Z_55489d` (baseline 0.0, trial 0.0)
- `voided` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T195620Z_605bb7` (baseline 0.0, trial None)
- `kept` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T231100Z_0d2828` (baseline 0.0, trial 284.0)
- `voided` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T234549Z_0bd39c` (baseline 0.0, trial None)
- `voided` · card `—` · family `set_knob:park_cycles` · cycle `20261116T025134Z_61a584` (baseline 2.0, trial None)
- `voided` · card `—` · family `set_knob:park_cycles` · cycle `20261116T061643Z_252f96` (baseline 1.0, trial None)
- `voided` · card `—` · family `set_knob:deep_digits` · cycle `20261116T075057Z_0b95bb` (baseline 24.0, trial None)
- `kept` · card `—` · family `set_knob:deep_digits` · cycle `20261116T123849Z_0ac470` (baseline 0.0, trial 256.0)

## Reading breadth (knowledge library)

knowledge: 126 papers across 14/14 fields, 76 concepts, 30 cards formed, 0 tested, 0 kept.

| Field | Papers | Concepts | Cards formed | Cards tested | Cards kept |
| --- | ---: | ---: | ---: | ---: | ---: |
| automated_reasoning | 8 | 2 | 0 | 0 | 0 |
| cognitive_science | 8 | 4 | 3 | 0 | 0 |
| consciousness_self_models | 8 | 4 | 1 | 0 | 0 |
| learning_theory | 8 | 9 | 0 | 0 | 0 |
| mathematics | 16 | 0 | 0 | 0 | 0 |
| meta_learning | 8 | 7 | 0 | 0 | 0 |
| multi_agent_systems | 8 | 3 | 1 | 0 | 0 |
| neural_architecture | 14 | 12 | 5 | 0 | 0 |
| open_endedness | 6 | 6 | 6 | 0 | 0 |
| optimization_search | 7 | 7 | 3 | 0 | 0 |
| physics_complex_systems | 8 | 4 | 1 | 0 | 0 |
| recursive_self_improvement | 8 | 1 | 2 | 0 | 0 |
| self_learning_loops | 11 | 10 | 2 | 0 | 0 |
| swarm_collective_intelligence | 8 | 7 | 6 | 0 | 0 |

## Architecture ideas (proposals for a human-built PR; never auto-executed)

- `novelty_archive` — 9 papers (consciousness_self_models, neural_architecture, open_endedness, recursive_self_improvement): Keep an archive of behaviourally different claim forms and prefer under-explored ones (novelty/quality-diversity archive).
- `swarm_topology` — 8 papers (multi_agent_systems, neural_architecture, swarm_collective_intelligence): Several improver agents propose over one shared candidate pool and a vote picks one (swarm/consensus topology).
- `self_play_challenger` — 7 papers (self_learning_loops): A challenger role that generates harder variants of solved targets for the solver desks (self-play curriculum).
- `meta_controller` — 6 papers (meta_learning, self_learning_loops): A meta-level desk that learns which kinds of self-heal trials tend to win and orders trials accordingly.
- `specialist_routing` — 6 papers (neural_architecture): A gating step that sends each target to a specialist desk (mixture-of-experts style routing).

Not AGI. Not discovery. Human authorize still required for durable accepts.

