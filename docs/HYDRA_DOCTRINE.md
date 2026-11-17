# HYDRA Doctrine — Surgical Injection Protocol

**Status:** Active.  
**Applies to:** Agent Colony and One Mind.  
**Source:** HYDRA Injector operator order, adapted as doctrine (not as a runtime dependency).

## The operator

```text
H = Seal ∘ Retract ∘ Inject ∘ Anchor
```

Stage order is locked. Reordering changes the operator.

| Stage | Meaning here |
|---|---|
| **Anchor** | Name the exact call site (file + function). No anchor, no injection. |
| **Inject** | Place one pure function at that site. |
| **Retract** | Fail-open. Any error returns the prior behavior. Rollback is the old path. |
| **Seal** | Emit at most one telemetry line or receipt. No seal, no trust. |

## Locks

```text
No anchor, no injection.
No boundary, no promotion.
No seal, no trust.
```

## Surgical rules

1. One function, one call site.
2. Fail-open. Error leaves the sphere unchanged.
3. No new file unless a symbiotic element requires its own surface.
4. No dependencies beyond the stdlib already in use.
5. Never alter authority, keep logic, or the Oracle.
6. Under fifteen lines or it is a redesign and it waits.
7. Lineage is stamped. Import never rewrites identity.

## When to inject

Injection happens only when the human says **do the injections** (or equivalent: seat, perturb, inject).

Until that word:

- Research may extract invariants.
- Functions may be written into `surgical_implants.py`.
- They remain inert.

On that word:

- Each named implant is seated at its anchored site.
- The change is one insertion, not a rewrite.
- The result is pushed and reported.

## What is not HYDRA runtime

HYDRA Injector’s CLI, residual-field numerics, schemas, and Codeweave package are **not** imported into the evolve loop. They remain the external review gate for proposing new implants. The live systems speak only the operator order and the locks.

## Protocol record

An injection is complete when all of the following exist:

1. Anchor named in the commit message.
2. Function present and fail-open.
3. Call site is a single insertion.
4. Seal: telemetry or an explicit “no seal required” note.
5. Authority unchanged (stated in the commit).

## Non-claims

This doctrine does not claim:

- that seated implants improve outcomes,
- that the operator is a physical theory,
- that injection equals recursive self-improvement,
- that a sealed change is correct — only that it is bounded and retractable.
