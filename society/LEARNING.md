# Colony learning loop

The colony proposes trials from public method cards and from its
own failures. Hive's deterministic vote chooses at most one legal
op. A change is **kept** only when the self-heal trial window is
strictly better than its baseline *and* the twin control does not
lead on Oracle passes or verified depth. Fitness alone never
decides a keep. Reverts and voids are recorded too. This is not
AGI, not a novel theorem, and not a breakthrough claim.

- Method cards tried: **0**
- Kept: **0**
- Reverted (including twin-not-better): **2**
- Voided (environment changed mid-trial): **4**
- Inconclusive (no signal in either window; not counted against the action): **0**
- Proposed this snapshot: **1**
- Waiting on a twin judgment: **0**
- Hive decision deferred **28** times (`set_knob:direction=up:name=park_cycles:value=8`), waiting on a clean 6-cycle window (same Wilson 700‰ gate).
- Hive shadow picks: resolved 0, correct 0, pending 10, accuracy n/a

## Per method card

_None yet._

## Per op family

| Family | Tried | Kept | Reverted | Keep rate |
| --- | ---: | ---: | ---: | ---: |
| `set_knob:park_cycles` | 4 | 0 | 1 | 0‰ |
| `set_knob:perturb_cooldown_cycles` | 2 | 0 | 1 | 0‰ |

## Recent outcomes

- `voided` · card `—` · family `set_knob:perturb_cooldown_cycles` · cycle `20261113T025053Z_f9d404` (baseline 0.0, trial None)
- `reverted` · card `—` · family `set_knob:perturb_cooldown_cycles` · cycle `20261113T111928Z_824713` (baseline 0.0, trial 0.0)
- `voided` · card `—` · family `set_knob:park_cycles` · cycle `20261113T164820Z_eef78f` (baseline 0.0, trial None)
- `voided` · card `—` · family `set_knob:park_cycles` · cycle `20261113T191238Z_f24225` (baseline 8.0, trial None)
- `reverted` · card `—` · family `set_knob:park_cycles` · cycle `20261113T230546Z_93eaed` (baseline 0.0, trial 0.0)
- `voided` · card `—` · family `set_knob:park_cycles` · cycle `20261114T001612Z_9266d8` (baseline 0.0, trial None)

Not AGI. Not discovery. Human authorize still required for durable accepts.

