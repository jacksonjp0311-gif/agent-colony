# Colony learning loop

The colony proposes trials from public method cards and from its
own failures. Hive's deterministic vote chooses at most one legal
op. A change is **kept** only when the self-heal trial window is
strictly better than its baseline *and* the twin control does not
lead on Oracle passes or verified depth. Fitness alone never
decides a keep. Reverts and voids are recorded too. This is not
AGI, not a novel theorem, and not a breakthrough claim.

- Method cards tried: **0**
- Kept: **2**
- Reverted (including twin-not-better): **4**
- Voided (environment changed mid-trial): **8**
- Inconclusive (no signal in either window; not counted against the action): **1**
- Proposed this snapshot: **1**
- Waiting on a twin judgment: **0**
- Hive decision deferred **8** times (`set_knob:direction=up:name=fast_term_cap:value=10700`), waiting on a clean 6-cycle window (same Wilson 700‰ gate).
- Hive shadow picks: resolved 22, correct 0, pending 12, accuracy 0‰

## Per method card

_None yet._

## Per op family

| Family | Tried | Kept | Reverted | Keep rate |
| --- | ---: | ---: | ---: | ---: |
| `set_knob:deep_digits` | 1 | 1 | 0 | 1000‰ |
| `set_knob:deep_seconds` | 1 | 0 | 1 | 0‰ |
| `set_knob:fast_term_cap` | 3 | 0 | 0 | 0‰ |
| `set_knob:gf_term_cap` | 2 | 1 | 1 | 500‰ |
| `set_knob:park_cycles` | 4 | 0 | 1 | 0‰ |
| `set_knob:perturb_cooldown_cycles` | 2 | 0 | 1 | 0‰ |
| `set_knob:perturb_epsilon` | 1 | 0 | 0 | 0‰ |

## Recent outcomes

- `voided` · card `—` · family `set_knob:park_cycles` · cycle `20261113T191238Z_f24225` (baseline 8.0, trial None)
- `reverted` · card `—` · family `set_knob:park_cycles` · cycle `20261113T230546Z_93eaed` (baseline 0.0, trial 0.0)
- `voided` · card `—` · family `set_knob:park_cycles` · cycle `20261114T001612Z_9266d8` (baseline 0.0, trial None)
- `voided` · card `—` · family `set_knob:fast_term_cap` · cycle `20261114T084449Z_66dcde` (baseline 4.0, trial None)
- `reverted` · card `—` · family `set_knob:gf_term_cap` · cycle `20261114T150332Z_6bd205` (baseline 3.0, trial 3.0)
- `reverted` · card `—` · family `set_knob:deep_seconds` · cycle `20261114T183045Z_d19c9c` (baseline 3.0, trial 3.0)
- `voided` · card `—` · family `set_knob:perturb_epsilon` · cycle `20261114T192118Z_6e8a46` (baseline 3.0, trial None)
- `voided` · card `—` · family `set_knob:fast_term_cap` · cycle `20261114T212240Z_58b193` (baseline 3.0, trial None)
- `inconclusive` · card `—` · family `set_knob:fast_term_cap` · cycle `20261114T222841Z_1f64d2` (baseline 3.0, trial 3.0)
- `voided` · card `—` · family `set_knob:fast_term_cap` · cycle `20261114T230121Z_d51dd0` (baseline 3.0, trial None)
- `kept` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T025824Z_a34dca` (baseline 0.0, trial 300.0)
- `kept` · card `—` · family `set_knob:deep_digits` · cycle `20261115T033809Z_03dc64` (baseline 0.0, trial 354.0)

Not AGI. Not discovery. Human authorize still required for durable accepts.

