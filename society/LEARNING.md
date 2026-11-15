# Colony learning loop

The colony proposes trials from public method cards and from its
own failures. Hive's deterministic vote chooses at most one legal
op. A change is **kept** only when the self-heal trial window is
strictly better than its baseline *and* the twin control does not
lead on Oracle passes or verified depth. Fitness alone never
decides a keep. Reverts and voids are recorded too. This is not
AGI, not a novel theorem, and not a breakthrough claim.

- Method cards tried: **0**
- Kept: **5**
- Reverted (including twin-not-better): **4**
- Voided (environment changed mid-trial): **9**
- Inconclusive (no signal in either window; not counted against the action): **3**
- Proposed this snapshot: **1**
- Waiting on a twin judgment: **0**
- Hive decision deferred **8** times (`set_knob:direction=up:name=fast_term_cap:value=10700`), waiting on a clean 6-cycle window (same Wilson 700‰ gate).
- Hive shadow picks: resolved 47, correct 0, pending 21, accuracy 0‰

## Per method card

_None yet._

## Per op family

| Family | Tried | Kept | Reverted | Keep rate |
| --- | ---: | ---: | ---: | ---: |
| `set_knob:deep_digits` | 3 | 3 | 0 | 1000‰ |
| `set_knob:deep_seconds` | 2 | 0 | 1 | 0‰ |
| `set_knob:fast_term_cap` | 4 | 1 | 0 | 250‰ |
| `set_knob:gf_term_cap` | 2 | 1 | 1 | 500‰ |
| `set_knob:park_cycles` | 4 | 0 | 1 | 0‰ |
| `set_knob:perturb_cooldown_cycles` | 2 | 0 | 1 | 0‰ |
| `set_knob:perturb_epsilon` | 1 | 0 | 0 | 0‰ |

## Recent outcomes

- `voided` · card `—` · family `set_knob:perturb_epsilon` · cycle `20261114T192118Z_6e8a46` (baseline 3.0, trial None)
- `voided` · card `—` · family `set_knob:fast_term_cap` · cycle `20261114T212240Z_58b193` (baseline 3.0, trial None)
- `inconclusive` · card `—` · family `set_knob:fast_term_cap` · cycle `20261114T222841Z_1f64d2` (baseline 3.0, trial 3.0)
- `voided` · card `—` · family `set_knob:fast_term_cap` · cycle `20261114T230121Z_d51dd0` (baseline 3.0, trial None)
- `kept` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T025824Z_a34dca` (baseline 0.0, trial 300.0)
- `kept` · card `—` · family `set_knob:deep_digits` · cycle `20261115T033809Z_03dc64` (baseline 0.0, trial 354.0)
- `kept` · card `—` · family `set_knob:deep_digits` · cycle `20261115T042451Z_fcdbe4` (baseline 0.0, trial 199.0)
- `voided` · card `—` · family `set_knob:deep_seconds` · cycle `20261115T054332Z_047561` (baseline 4.0, trial None)
- `kept` · card `—` · family `set_knob:deep_digits` · cycle `20261115T065010Z_f362e6` (baseline 0.0, trial 109.0)
- `inconclusive` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T073045Z_83bc39` (baseline 0.0, trial 0.0)
- `inconclusive` · card `—` · family `set_knob:deep_seconds` · cycle `20261115T081147Z_f93bc9` (baseline 0.0, trial 0.0)
- `kept` · card `—` · family `set_knob:fast_term_cap` · cycle `20261115T101616Z_e6eeff` (baseline 0.0, trial 2700.0)

Not AGI. Not discovery. Human authorize still required for durable accepts.

