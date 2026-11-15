# Colony learning loop

The colony proposes trials from public method cards and from its
own failures. Hive's deterministic vote chooses at most one legal
op. A change is **kept** only when the self-heal trial window is
strictly better than its baseline *and* the twin control does not
lead on Oracle passes or verified depth. Fitness alone never
decides a keep. Reverts and voids are recorded too. This is not
AGI, not a novel theorem, and not a breakthrough claim.

- Method cards tried: **0**
- Kept: **10**
- Reverted (including twin-not-better): **4**
- Voided (environment changed mid-trial): **11**
- Inconclusive (no signal in either window; not counted against the action): **6**
- Proposed this snapshot: **1**
- Waiting on a twin judgment: **0**
- Hive decision deferred **8** times (`set_knob:direction=up:name=fast_term_cap:value=10700`), waiting on a clean 6-cycle window (same Wilson 700‰ gate).
- Hive shadow picks: resolved 100, correct 0, pending 40, accuracy 0‰

## Per method card

_None yet._

## Per op family

| Family | Tried | Kept | Reverted | Keep rate |
| --- | ---: | ---: | ---: | ---: |
| `set_knob:deep_digits` | 4 | 4 | 0 | 1000‰ |
| `set_knob:deep_seconds` | 2 | 0 | 1 | 0‰ |
| `set_knob:fast_term_cap` | 7 | 4 | 0 | 571‰ |
| `set_knob:gf_term_cap` | 5 | 2 | 1 | 400‰ |
| `set_knob:park_cycles` | 4 | 0 | 1 | 0‰ |
| `set_knob:perturb_cooldown_cycles` | 2 | 0 | 1 | 0‰ |
| `set_knob:perturb_epsilon` | 1 | 0 | 0 | 0‰ |

## Recent outcomes

- `inconclusive` · card `—` · family `set_knob:deep_seconds` · cycle `20261115T081147Z_f93bc9` (baseline 0.0, trial 0.0)
- `kept` · card `—` · family `set_knob:fast_term_cap` · cycle `20261115T101616Z_e6eeff` (baseline 0.0, trial 2700.0)
- `kept` · card `—` · family `set_knob:fast_term_cap` · cycle `20261115T105718Z_a218f5` (baseline 0.0, trial 2700.0)
- `kept` · card `—` · family `set_knob:fast_term_cap` · cycle `20261115T113729Z_b3155f` (baseline 0.0, trial 2700.0)
- `kept` · card `—` · family `set_knob:fast_term_cap` · cycle `20261115T122007Z_b4802c` (baseline 0.0, trial 1200.0)
- `inconclusive` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T150158Z_ae4d61` (baseline 0.0, trial 0.0)
- `inconclusive` · card `—` · family `set_knob:deep_seconds` · cycle `20261115T154457Z_1ab8a3` (baseline 0.0, trial 0.0)
- `voided` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T160121Z_c4b068` (baseline 0.0, trial None)
- `kept` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T171106Z_386886` (baseline 0.0, trial 231.0)
- `kept` · card `—` · family `set_knob:deep_digits` · cycle `20261115T175054Z_8f2c59` (baseline 0.0, trial 324.0)
- `inconclusive` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T183448Z_55489d` (baseline 0.0, trial 0.0)
- `voided` · card `—` · family `set_knob:gf_term_cap` · cycle `20261115T195620Z_605bb7` (baseline 0.0, trial None)

Not AGI. Not discovery. Human authorize still required for durable accepts.

