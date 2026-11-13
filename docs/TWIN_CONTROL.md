# Twin control colony

A measured comparison: the live (treatment) colony against a control
arm that runs the same evolve pipeline with self-modification off.

## Why

A gain only counts as self-improvement when it traces to a change the
colony chose itself. A code change, a deeper calculator limit, or a
lucky cycle can look like a win if there is nothing to compare it to.
The control arm is that comparison. Both arms start from the same
snapshot, run the same number of cycles on the same schedule, and are
scored on the same Oracle and the same gates. If treatment pulls ahead
and stays ahead, and the scoreboard can point at adopts that explain
the lead, that is evidence. Early differences are noise.

## How it is wired

- Environment: `COLONY_ARM=control` or `python -m colony evolve --arm control`.
- State: control writes only under `control/data/` and `control/society/`,
  seeded once from treatment at fork time (see `control/.fork.json` and
  `control/README.md`). Treatment files are never opened for write.
- Self-mod off: `colony.arm.self_mod_enabled()` is false, which freezes
  self-heal trials, checker-lane adoption, Hive learning, and policy
  knobs (PERTURB uses code defaults). Hive is disabled through
  `colony/hive_adapter.py`: `on_cycle` and `run_cycle` return without
  calling Hive. A feature check and import hook in `colony/arm.py` are
  a backup.
- Workflow: the existing `colony-evolve.yml` schedule (`26 */6 * * *`)
  and `workflow_dispatch` also run an `evolve-control` job for the same
  cycle count, then a `twin-scoreboard` job. Control never authorizes.
  A `run_control` input (default true) can skip the control job on a
  manual dispatch. Scheduled runs always include it.
- Scoreboard: `society/systems/twin_scoreboard.json`, append-only
  history, treatment-minus-control deltas, cycle counts on both sides.
- Chart: plaque-style SVG (charcoal, bone `#eeeee6`, sage `#b7c4b6`)
  on the existing dashboard. No purple, neon, gold, or emoji.

## What this does not do

It does not loosen the Oracle, the P ≥ 0.70 gate, the 150 cap, or
Athanor math. It does not authorize. It does not rewrite the witness
log. It does not claim a short lead is recursive self-improvement.

## Runtime

The control job skips the trust gate and the benches (those already
run on the shared code in the treatment job) and then runs the same
number of evolve cycles, typically about 10–15 minutes for the default
three cycles, in parallel with treatment. Wall-clock for a workflow
run therefore grows little; the added Actions minutes are one extra
job of that length. The first control run also copies treatment state
into `control/` and commits it, which is a larger push than later runs.
