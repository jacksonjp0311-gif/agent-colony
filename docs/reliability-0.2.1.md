# Reliability review follow-up, 0.2.1

Base: `b98d690bfd46c7493b38e1d42fac26d7ce1502ac`
(2026-10-19 22:39:02 UTC). This is a reliability patch, not measured capability
improvement. Historical evaluation artifacts and the documented negative/mixed
results remain unchanged.

## Changes

- Routine entry and role synchronization cannot revive retired agents. The
  registry's explicit revival operation requires numeric metric pressure,
  capacity, and two completed intervening cycles; it records the evidence.
  Spawn-menu checks no longer bypass metrics for existing roles.
- Manual workflow selection uses one fail-closed selector. Confidence must be
  finite, in range, and above threshold; an explicit zero cannot fall back to a
  second confidence field. A matching latest Oracle PASS/fitness-credit record
  and healthy originating cycle are required. Prior human decisions are
  excluded. Scheduled requests are rejected in both workflow and selector.
  The explicit human `Authorizer` interface remains separate.
- Shifted checks report pass/fail/not-tested. Literal positive and negative
  steps are supported. Unsupported shapes, filtered comprehensions, no executed
  probes, and timeout cannot support survival. A subprocess bounds initialization
  and evaluation on Windows as well as Unix. Finite passes are not proofs.
- Society records critical failures and optional degradation in result, state,
  witness, and report. Failed retirement/selection prerequisites block growth.
  Ingestion remains fail-soft; failed cycle evidence cannot be selected for
  automatic machine-backed promotion.
- Read-only PR/main-push CI runs the full suite. It has no evolution,
  authorization, commit, or push step. It uses the existing declared Python
  dependencies and the same sieve backend as the evolution workflow.

## Before-fix evidence

Tests were run against a pristine export of the base commit, separately from
the working source. Initial regressions:

```text
python -m pytest tests/test_reliability_regressions.py -q --basetemp=../pytest-before
9 failed, 3 passed
```

The nine failures reproduced role-sync revival, spawn-menu revival without weak
metrics, acceptance of infinity/out-of-range/boolean confidence, successful
unapplied checks for no-range and dynamic-range expressions, a missed stepped
counterexample, and Oracle survival without an applied shift.

The old workflow's selection loop was also evaluated with synthetic candidates
and a recording `AuthorizeItem` stub, without importing or invoking Authorizer:

```text
missing_confidence selected=[synthetic_test_candidate] (expected [])
zero_P_with_high_confidence selected=[synthetic_test_candidate] (expected [])
```

The regression suite also exercises the actual Society → Spark → GrowthLoop
entrypoints in disposable offline trees. It retires a role using
`EvolutionEngine.maybe_retire`, runs two normal cycles, and checks persistence.
An observer detects transient reactivation even if the role is retired again
before the end of the cycle. Both entrypoint tests failed on the original source:
one observed `role_sync` revival, the other found no cycle failure diagnostics.
Separate fault injection checks stage failures and blocked growth. Historical
sieve entries are disabled only in this lifecycle fixture, because they assume
the optional native backend; the real lifecycle, fitness, and spawn code runs.

## Validation environment and limits

No dependencies were installed. Python 3.12 and an already available pytest
environment were used. The Windows host lacks the Unix `resource` module,
SymPy, and the optional native primesieve backend.

Baseline and patched full suites were compared with
`COLONY_SIEVE_MAX_SPAN=100000` to bound expensive fallback work. This changes the
test environment, not repository defaults, and deliberately makes oversized
sieve assertions fail. These runs are diagnostic comparisons, **not clean
full-suite passes**.

Windows also exposes pre-existing slash-path and text-newline assumptions in
tests. Checkout newline normalization was needed for the existing evaluation
manifest; no evaluation content or manifest was changed in the proposed patch.

The bounded full baseline run had 516 passes, 14 failures, and 14 skips. The
patched comparison had 546 passes, 13 failures, and 14 skips; all remaining
failures reproduced on the baseline. The absent-entry positive test was repaired
to use an actual shifted check rather than depend on the defect.

The final applicable Windows run passed **547 tests**, with 14 skips and 13
explicit deselections. It included all 30 new regression cases. Deselections were
the four `test_athanor_gate_v3` native-guard cases, the frontier authoring-guard
case, the pilot slash-path assertion, five sieve cases exceeding the diagnostic
span cap, the temporary-file newline manifest assertion, and the full bench gate
that depends on those environments. None was removed or skipped in CI.

Final commands/results are recorded in the task's validation report. A normal
Linux full-suite pass with the existing dependencies remains required for CI
verification; the Windows comparison cannot establish that result.
No authorization/evolution workflow was executed, no knowledge was authorized,
and no capability claim was published.
