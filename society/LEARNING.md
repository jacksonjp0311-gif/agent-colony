# Colony learning loop

The colony proposes trials from public method cards and from its
own failures. Hive's deterministic vote chooses at most one legal
op. A change is **kept** only when the self-heal trial window is
strictly better than its baseline *and* the twin control does not
lead on Oracle passes or verified depth. Fitness alone never
decides a keep. Reverts and voids are recorded too. This is not
AGI, not a novel theorem, and not a breakthrough claim.

- Method cards tried: **2**
- Kept: **27**
- Reverted (including twin-not-better): **33**
- Voided (environment changed mid-trial): **26**
- Inconclusive (no signal in either window; not counted against the action): **6**
- Proposed this snapshot: **11**
- Waiting on a twin judgment: **0**
- Hive decision deferred **3** times (`add_skip_rule:cycles=8:target_kind=already_held_range`), waiting on a clean 6-cycle window (same Wilson 700‰ gate).
- Hive shadow picks: resolved 6, correct 0, pending 194, accuracy 0‰

## Per method card

| Card | Method | Tried | Kept | Reverted | Keep rate |
| --- | --- | ---: | ---: | ---: | ---: |
| `mc_bacbbd75d04b` | Perturb candidate claims a little more widely (annealing-style search). | 1 | 0 | 1 | 0‰ |
| `mc_e170e02332fe` | Remember already-tried targets for longer before retrying them (longer working memory). | 3 | 2 | 1 | 666‰ |

## Per op family

| Family | Tried | Kept | Reverted | Keep rate |
| --- | ---: | ---: | ---: | ---: |
| `set_knob:deep_digits` | 6 | 5 | 0 | 833‰ |
| `set_knob:deep_seconds` | 2 | 0 | 1 | 0‰ |
| `set_knob:evaluation_window` | 13 | 3 | 9 | 230‰ |
| `set_knob:fast_term_cap` | 7 | 4 | 0 | 571‰ |
| `set_knob:gf_term_cap` | 14 | 6 | 3 | 428‰ |
| `set_knob:park_cycles` | 21 | 4 | 9 | 190‰ |
| `set_knob:perturb_cooldown_cycles` | 3 | 0 | 2 | 0‰ |
| `set_knob:perturb_epsilon` | 2 | 0 | 1 | 0‰ |
| `set_knob:step_size` | 15 | 3 | 7 | 200‰ |
| `set_knob:unused_menu_cycles` | 3 | 2 | 1 | 666‰ |

## Recent outcomes

- `kept` · card `mc_e170e02332fe` · family `set_knob:unused_menu_cycles` · cycle `20261123T182437Z_d10804` (baseline 6.0, trial 22.0)
- `reverted` · card `mc_e170e02332fe` · family `set_knob:unused_menu_cycles` · cycle `20261123T210005Z_2f4d83` (baseline 21.0, trial 9.0)
- `reverted` · card `—` · family `set_knob:perturb_cooldown_cycles` · cycle `20261124T015904Z_56955f` (baseline 22.0, trial 15.0)
- `reverted` · card `—` · family `set_knob:step_size` · cycle `20261124T141738Z_446d2a` (baseline 29.0, trial 23.0)
- `reverted` · card `—` · family `set_knob:evaluation_window` · cycle `20261124T170959Z_af2c74` (baseline 19.0, trial 14.0)
- `kept` · card `—` · family `set_knob:step_size` · cycle `20261124T194032Z_8650dd` (baseline 18.0, trial 20.0)
- `kept` · card `—` · family `set_knob:step_size` · cycle `20261124T215001Z_33e498` (baseline 17.0, trial 25.0)
- `reverted` · card `—` · family `set_knob:evaluation_window` · cycle `20261125T004811Z_70ff30` (baseline 28.0, trial 25.0)
- `reverted` · card `—` · family `set_knob:gf_term_cap` · cycle `20261125T172433Z_95534a` (baseline 18.0, trial 17.0)
- `reverted` · card `—` · family `set_knob:evaluation_window` · cycle `20261125T203544Z_431fad` (baseline 27.0, trial 21.0)
- `kept` · card `—` · family `set_knob:evaluation_window` · cycle `20261126T005125Z_276c73` (baseline 13.0, trial 22.0)
- `kept` · card `—` · family `set_knob:evaluation_window` · cycle `20261126T035313Z_4f6575` (baseline 24.0, trial 25.0)

## Reading breadth (knowledge library)

knowledge: 690 papers across 14/14 fields, 359 concepts, 174 cards formed, 2 tested, 1 kept.

| Field | Papers | Concepts | Cards formed | Cards tested | Cards kept |
| --- | ---: | ---: | ---: | ---: | ---: |
| automated_reasoning | 69 | 10 | 3 | 0 | 0 |
| cognitive_science | 17 | 9 | 8 | 1 | 1 |
| consciousness_self_models | 16 | 12 | 2 | 0 | 0 |
| learning_theory | 39 | 45 | 2 | 0 | 0 |
| mathematics | 121 | 1 | 1 | 0 | 0 |
| meta_learning | 27 | 18 | 4 | 0 | 0 |
| multi_agent_systems | 15 | 8 | 2 | 0 | 0 |
| neural_architecture | 103 | 70 | 14 | 0 | 0 |
| open_endedness | 65 | 65 | 67 | 0 | 0 |
| optimization_search | 61 | 66 | 37 | 0 | 0 |
| physics_complex_systems | 37 | 12 | 3 | 0 | 0 |
| recursive_self_improvement | 60 | 6 | 7 | 0 | 0 |
| self_learning_loops | 42 | 21 | 11 | 1 | 0 |
| swarm_collective_intelligence | 18 | 16 | 13 | 0 | 0 |

## Architecture ideas (proposals for a human-built PR; never auto-executed)

- `novelty_archive` — 72 papers (consciousness_self_models, mathematics, neural_architecture, open_endedness, optimization_search, recursive_self_improvement): Keep an archive of behaviourally different claim forms and prefer under-explored ones (novelty/quality-diversity archive).
- `specialist_routing` — 54 papers (neural_architecture, physics_complex_systems): A gating step that sends each target to a specialist desk (mixture-of-experts style routing).
- `swarm_topology` — 21 papers (automated_reasoning, multi_agent_systems, neural_architecture, open_endedness, optimization_search, physics_complex_systems, swarm_collective_intelligence): Several improver agents propose over one shared candidate pool and a vote picks one (swarm/consensus topology).
- `self_play_challenger` — 17 papers (recursive_self_improvement, self_learning_loops): A challenger role that generates harder variants of solved targets for the solver desks (self-play curriculum).
- `meta_controller` — 14 papers (meta_learning, recursive_self_improvement, self_learning_loops): A meta-level desk that learns which kinds of self-heal trials tend to win and orders trials accordingly.

Not AGI. Not discovery. Human authorize still required for durable accepts.

