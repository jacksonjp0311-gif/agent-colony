# Item 104: frozen-workload A/B of the new-data work allocation

`python scripts/item104_sched_ab.py --reps 3 --json ab_3reps.json` (box, 2026-11-16 ~13:45 UTC).
Same 12 frozen targets, real colony arithmetic (`colony.new_data.MENU`, method A and method B),
15 cycles, **0.6 CPU-s and 0.8 wall-s per cycle for both arms**. A = today's `new_data.run_cycle`
allocation (emulated); B = `colony.work_scheduler.Scheduler`. Order alternated between reps.

| metric (3 reps) | A baseline | B scheduler |
|---|---|---|
| verified units accepted | 16,171 / 38,241 / 38,241 | 187,595 / 190,648 / 184,801 |
| … excluding the one huge "hog" target | 16,025 / 19,492 / 19,492 | 19,508 / 19,508 / 19,508 |
| targets with ≥1 verified unit (of 10 honest) | 8 / 9 / 9 | 10 / 10 / 10 |
| targets completed to goal | 6 / 8 / 8 | 8 / 8 / 8 |
| marked intractable for good | giant+late_gbcls / late_gbcls / late_gbcls | none (late_gbcls parked over_budget, re-checked each cycle) |
| mean wait to first service (cycles) | 0.6 / 0.5 / 0.5 | 0.2 / 0.2 / 0.2 |
| mean latency to goal (cycles) | 1.0 / 0.62 / 0.62 | 0.75 / 0.88 / 0.75 |
| scheduler overhead (share of CPU) | 0.02 % | 2.0 % |
| cycles over CPU budget | 2 / 0 / 0 | 1 / 1 / 1 |
| cycles over wall budget | 0 / 0 / 0 | 1 / 0 / 1 |
| chunks over their planned share | n/a | 4 / 3 / 5 |
| CPU actually used (s, of 9.0 available) | 2.35 / 2.10 / 2.06 | 6.98 / 6.69 / 6.78 |
| verified units per CPU-s | 6.9k / 18.2k / 18.6k | 26.9k / 28.5k / 27.3k |
| wrong accepted values (vs clean recompute) | 0 | 0 |
| poison target: accepted / CPU retries | 0 / 13–14 retries (stays open) | 0 (8 probe units retracted; quarantined once) |
| crash between accept and checkpoint | n/a | recovered, 8 duplicates skipped, 0 double counted |

Schedule invariance: 3 schedules (different budgets, reversed admission order, chunk share 0.2)
agree on all 106,613 common units (one digest).

Cost hypothesis (per-work-type EWMA vs per-job last measurement, mean |log error|): the smoothed
model was **not** better on any work type with enough chunks (e.g. col_steps 0.06–0.10 vs
0.04–0.07); it was accepted in 0 of 27 type×rep cells in this run, so plans used the
conservative max of the two predictions. Negative result, kept.

Honest reading: nearly all of B's extra verified work is ONE large target that A pushes once and
marks done; on the bounded targets both arms finish the same work (19.5k units). B uses ~3x the
CPU A uses because A leaves ~75 % of its budget idle after its one-shot pushes. B's overhead is
higher (2 %) and its unknown-cost probes overran a cycle budget 1–2 times. The live new-data
index has 0 eligible targets today (12 done, 5 intractable), so none of this changes live output.
