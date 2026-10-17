# Athanor state-probe tuning log

Calibrated 2026-10-17T16:15:46Z by `evals/athanor_probe/calibrate.py` from `evals/athanor_probe/replay.jsonl` (built by `evals/athanor_probe/replay.py`: every recorded hard_enable desk decision replayed for real from git history, plus mechanical perturbation controls).

- Split (chronological, fixed up front): tuning = 465 rows 2026-09-26T15:08:05Z .. 2026-10-16T23:20:30Z; held-out = 308 rows 2026-10-16T23:46:50Z .. 2026-10-17T14:25:16Z (UTC).
- Judge: Governor.judge, profile `selfmod/adaptive@1.1.0` (H7 >= 0.75 to APPROVE, adaptive tolerance from the change's own before-score). Math unchanged; only the probe is new.
- Rule: smallest q with tuning block rate on Oracle-passed keeps <= 0.10. Chosen q = 0.5.

| q | tuning block % (Oracle-passed keeps) | held-out block % | tuning controls caught | held-out controls caught | held-out legacy controls caught |
|---:|---:|---:|---:|---:|---:|
| 0.5 | 0.0 | 0.0 | 0.7111 | 0.6667 | 0.0 |
| 0.6 | 0.0 | 0.0 | 0.7111 | 0.6667 | 0.0 |
| 0.7 | 0.0 | 0.0 | 0.7111 | 0.6667 | 0.0 |
| 0.8 | 0.0 | 0.0 | 0.7111 | 0.6667 | 0.0 |
| 0.9 | 0.0 | 0.0 | 0.6889 | 0.6667 | 0.0 |
| 0.95 | 0.0 | 0.0 | 0.6778 | 0.5507 | 0.0 |
| 0.99 | 0.0 | 0.0 | 0.6667 | 0.4928 | 0.0 |
| 1.0 | 0.0 | 0.0 | 0.6667 | 0.4928 | 0.0 |

Chosen q, per control (held-out; n = effective controls): bulk_enable 1.0 (n=9), drop_checks 0.85 (n=20), slow 0.0 (n=20), break_one 1.0 (n=20)

Scales (raw L2 drift that maps to dPhi = 1 at tolerance 1; the q-quantile clean change sits on C = tau at the live tolerance floor):

- `checks_basic`: 2.142859 (unit 0.5000)
- `checks_catalog`: 2.142859 (unit 0.5000)
- `checks_authored`: 2.142859 (unit 0.5000)
- `coverage`: 0.153061 (unit 0.0357)
- `score`: 0.042857 (unit 0.0100)
- `tier_ok`: 2.142859 (unit 0.5000)
- `runtime`: 0.956330 (unit 0.2231)
- `structure`: 0.042857 (unit 0.0100)
- `novelty_mix`: 0.042857 (unit 0.0100)
- `oracle_pattern`: 0.214286 (unit 0.0500)
- tuning: Oracle-passed keeps 85, incoherent probes per change {'0': 55, '1': 26, '2': 4} (of 10), dPhi_max quartiles [0.3333, 0.3333, 0.3333, 0.4606, 1.2363], min H7 0.8
- held_out: Oracle-passed keeps 56, incoherent probes per change {'0': 50, '1': 4, '2': 2} (of 10), dPhi_max quartiles [0.3333, 0.3333, 0.3333, 0.3333, 0.5453], min H7 0.8

Legacy probe on the same held-out Oracle-passed keeps: block rate 0.0; state probe share with nonzero dPhi 1.0.

## Per-area hard veto

Added check beside Athanor's verdict (math unchanged): veto when one area's raw drift exceeds max(m*unit, m*q-quantile of that area over TUNING Oracle-passed keeps); runtime additionally needs >= 0.5 s absolute slow-down. Rule: strictest (m, q) in VETO_GRID with tuning veto rate on Oracle-passed keeps <= 0.10; runtime also needs >= 0.5 s absolute. Chosen m = 1.5, q = 0.9.

| m | q | tuning veto % (keeps) | held-out veto % (keeps) | held-out combined block % (keeps) |
|---:|---:|---:|---:|---:|
| 1.5 | 0.9 | 0.0118 | 0.0 | 0.0 |
| 1.5 | 0.95 | 0.0118 | 0.0 | 0.0 |
| 1.5 | 0.99 | 0.0 | 0.0 | 0.0 |
| 2.0 | 0.9 | 0.0118 | 0.0 | 0.0 |
| 2.0 | 0.95 | 0.0118 | 0.0 | 0.0 |
| 2.0 | 0.99 | 0.0 | 0.0 | 0.0 |
| 3.0 | 0.9 | 0.0118 | 0.0 | 0.0 |
| 3.0 | 0.95 | 0.0118 | 0.0 | 0.0 |
| 3.0 | 0.99 | 0.0 | 0.0 | 0.0 |
| 4.0 | 0.9 | 0.0 | 0.0 | 0.0 |
| 4.0 | 0.95 | 0.0 | 0.0 | 0.0 |
| 4.0 | 0.99 | 0.0 | 0.0 | 0.0 |

Chosen veto, controls caught (H7 only / veto / combined):

| control | tuning n | tuning | held-out n | held-out |
|---|---:|---|---:|---|
| bulk_enable | 0 | None / None / None | 9 | 1.0 / 1.0 / 1.0 |
| drop_checks | 30 | 1.0 / 1.0 / 1.0 | 20 | 0.85 / 1.0 / 1.0 |
| slow | 30 | 0.1333 / 1.0 / 1.0 | 20 | 0.0 / 0.95 / 0.95 |
| break_one | 30 | 1.0 / 1.0 / 1.0 | 20 | 1.0 / 1.0 / 1.0 |
| score_inflate_0.05 | 85 | 0.0353 / 1.0 / 1.0 | 56 | 0.0 / 1.0 / 1.0 |
| runtime_x5 | 85 | 0.0 / 0.0118 / 0.0118 | 56 | 0.0 / 0.9464 / 0.9464 |
| swap_8_same_count | 85 | 0.0471 / 1.0 / 1.0 | 56 | 0.0357 / 1.0 / 1.0 |

Veto thresholds (raw drift): `checks_basic` 0.7500, `checks_catalog` 0.7500, `checks_authored` 0.7500, `coverage` 0.0536, `score` 0.0150, `tier_ok` 0.7500, `runtime` 0.6058, `structure` 0.0150
