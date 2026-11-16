# Colony learning loop

The colony proposes trials from public method cards and from its
own failures. Hive's deterministic vote chooses at most one legal
op. A change is **kept** only when the self-heal trial window is
strictly better than its baseline *and* the twin control does not
lead on Oracle passes or verified depth. Fitness alone never
decides a keep. Reverts and voids are recorded too. This is not
AGI, not a novel theorem, and not a breakthrough claim.

- Method cards tried: **0**
- Kept: **11**
- Reverted (including twin-not-better): **4**
- Voided (environment changed mid-trial): **13**
- Inconclusive (no signal in either window; not counted against the action): **6**
- Proposed this snapshot: **7**
- Waiting on a twin judgment: **0**
- Hive decision deferred **2** times (`set_knob:direction=up:name=park_cycles:value=8`), waiting on a clean 6-cycle window (same Wilson 700‰ gate).
- Hive shadow picks: resolved 100, correct 0, pending 63, accuracy 0‰

## Per method card

_None yet._

## Per op family

| Family | Tried | Kept | Reverted | Keep rate |
| --- | ---: | ---: | ---: | ---: |
| `set_knob:deep_digits` | 4 | 4 | 0 | 1000‰ |
| `set_knob:deep_seconds` | 2 | 0 | 1 | 0‰ |
| `set_knob:fast_term_cap` | 7 | 4 | 0 | 571‰ |
| `set_knob:gf_term_cap` | 7 | 3 | 1 | 428‰ |
| `set_knob:park_cycles` | 5 | 0 | 1 | 0‰ |
| `set_knob:perturb_cooldown_cycles` | 2 | 0 | 1 | 0‰ |
| `set_knob:perturb_epsilon` | 1 | 0 | 0 | 0‰ |

## Recent outcomes

- `kept` · card `—` · family `set_knob:fast_term_cap` · cycle `20261115T113729Z_b3155f` (baseline 0.0, trial 2700.0)
- `kept` · card `—` · family `set_knob:fast_term_cap` · cycle `20261115T122007Z_b4802c` (baseline 0.0, trial 1200.0)
- `inconclusive` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T150158Z_ae4d61` (baseline 0.0, trial 0.0)
- `inconclusive` · card `—` · family `set_knob:deep_seconds` · cycle `20261115T154457Z_1ab8a3` (baseline 0.0, trial 0.0)
- `voided` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T160121Z_c4b068` (baseline 0.0, trial None)
- `kept` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T171106Z_386886` (baseline 0.0, trial 231.0)
- `kept` · card `—` · family `set_knob:deep_digits` · cycle `20261115T175054Z_8f2c59` (baseline 0.0, trial 324.0)
- `inconclusive` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T183448Z_55489d` (baseline 0.0, trial 0.0)
- `voided` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T195620Z_605bb7` (baseline 0.0, trial None)
- `kept` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T231100Z_0d2828` (baseline 0.0, trial 284.0)
- `voided` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T234549Z_0bd39c` (baseline 0.0, trial None)
- `voided` · card `—` · family `set_knob:park_cycles` · cycle `20261116T025134Z_61a584` (baseline 2.0, trial None)

## Reading breadth (knowledge library)

knowledge: 65 papers across 8/14 fields, 48 concepts, 17 cards formed, 0 tested, 0 kept.

| Field | Papers | Concepts | Cards formed | Cards tested | Cards kept |
| --- | ---: | ---: | ---: | ---: | ---: |
| automated_reasoning | 0 | 0 | 0 | 0 | 0 |
| cognitive_science | 8 | 4 | 3 | 0 | 0 |
| consciousness_self_models | 8 | 4 | 1 | 0 | 0 |
| learning_theory | 8 | 9 | 0 | 0 | 0 |
| mathematics | 8 | 0 | 0 | 0 | 0 |
| meta_learning | 8 | 7 | 0 | 0 | 0 |
| multi_agent_systems | 0 | 0 | 0 | 0 | 0 |
| neural_architecture | 8 | 9 | 4 | 0 | 0 |
| open_endedness | 0 | 0 | 0 | 0 | 0 |
| optimization_search | 0 | 0 | 0 | 0 | 0 |
| physics_complex_systems | 0 | 0 | 0 | 0 | 0 |
| recursive_self_improvement | 0 | 0 | 1 | 0 | 0 |
| self_learning_loops | 9 | 8 | 2 | 0 | 0 |
| swarm_collective_intelligence | 8 | 7 | 6 | 0 | 0 |

## Architecture ideas (proposals for a human-built PR; never auto-executed)

- `swarm_topology` — 7 papers (neural_architecture, swarm_collective_intelligence): Several improver agents propose over one shared candidate pool and a vote picks one (swarm/consensus topology).
- `meta_controller` — 6 papers (meta_learning, self_learning_loops): A meta-level desk that learns which kinds of self-heal trials tend to win and orders trials accordingly.
- `self_play_challenger` — 5 papers (self_learning_loops): A challenger role that generates harder variants of solved targets for the solver desks (self-play curriculum).
- `specialist_routing` — 5 papers (neural_architecture): A gating step that sends each target to a specialist desk (mixture-of-experts style routing).
- `self_model_calibration` — 4 papers (cognitive_science, consciousness_self_models): The colony tracks its own prediction accuracy per desk and uses it to weight proposals (calibrated self-model; not a consciousness claim).

Not AGI. Not discovery. Human authorize still required for durable accepts.

