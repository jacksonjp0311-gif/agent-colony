# Control arm

This directory is the **control** half of a paired experiment. The
treatment arm is the live colony at the repo root (`data/`, `society/`).
Control runs the same evolve pipeline, against the same Oracle and the
same gates, with every self-modification turned off.

## What is frozen

- Self-heal trials do not start or close. Knobs stay at
  `colony/self_heal_defaults.json`.
- Checker-lane candidates are not accepted for review.
- Hive / swarm learning does not run. The disable goes through
  `colony/hive_adapter.py` (``on_cycle`` and ``run_cycle`` return
  without calling Hive), with a feature check and import hook in
  `colony/arm.py` as a backup.
- PERTURB still runs, but its policy knobs stay at the code defaults.

The Oracle, the P ≥ 0.70 authorize gate, the 150 authored-check cap, and
Athanor math are unchanged and are the same in both arms. Control never
authorizes.

## How to take this out and examine it

The control *state* lives here, once the first control evolve has
seeded it (a copy of treatment `data/` and `society/` at fork time,
then a policy freeze). The control *code* is the rest of the repo —
there is no second copy of `colony/`. To inspect a run:

```bash
# Metrics for this arm only
python3 -c "from colony.twin import collect_arm_metrics; from colony.arm import control_root; import json; print(json.dumps(collect_arm_metrics(control_root()), indent=2, default=str))"

# Run the control pipeline locally (writes only under control/)
COLONY_SEED_CONTROL=1 python3 -m colony seed-control   # first time only
python3 -m colony evolve --arm control --cycles 1 --offline
```

The fork record is `.fork.json`: it has the treatment SHA and the time
the snapshot was taken. After seed, control evolves on its own and is
not recopied from treatment. The seed reads treatment `data/` and
`society/` through paths that bypass the `COLONY_ARM=control` redirect
hook, fails with a nonzero exit if the copy is empty or
`control/data/society_state.json` is missing, and is idempotent
(already-seeded trees are left alone).

## How the two arms are compared

`society/systems/twin_scoreboard.json` (on the treatment tree) holds
both sides, the treatment-minus-control deltas, and an append-only
history. The growth chart on `society/DASHBOARD.html` plots Oracle
passes, total verified depth, and cumulative adopts. Early differences
are noise. A lasting lead needs many paired runs, and a gain that
traces to a change the treatment arm chose itself.

This is a measurement, not a claim of general intelligence.
