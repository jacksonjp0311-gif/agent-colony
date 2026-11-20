# Evidence-Gated Evolution Tools

These optional tools implement the full improvement plan while preserving the colony’s design.

- **Static agency**: runners remain time-based (GitHub Actions cron, `python -m colony evolve --cycles N`).
- **Cybernetic operation**: feedback loops (Oracle outcomes → keep/revert → lessons → genomes → next proposals) close inside the society. The tools make those loops cleaner, more attributable, and safer without adding external intelligence.

## Modules

| Module | Purpose |
|--------|---------|
| `evidence_graph.py` | Append-only shared graph of claims, counterexamples, method cards. Prevents silent loss. |
| `statistical_keep_gate.py` | Sequential gate that bounds false-evolution rate. |
| `invariant_contracts.py` | Machine-checkable preconditions (verified depth, no overlap, frontier safety). |
| `ablation_harness.py` | Paired with/without runs to measure causal influence of bus or method. |
| `method_composition.py` | Constrained language for combining existing Oracle-verified primitives. |
| `prospective_grading.py` | Score a method card before keep using historical rates. |
| `novelty_filter.py` | Reject proposals whose Oracle signature is too close to recent accepts. |
| `hunter_persistence.py` | Write confirmed counterexamples to the graph before state update. |
| `reward_isolation.py` | Refuse fitness/keep credit when invariants fail. |

All are loadable. The colony proposes their use through the existing conjecture desk; the Oracle verifies; human authorization remains required for durable promotion. Twin-control arms stay frozen for comparison.

No running cycle is modified by the presence of these modules. Phase 0 invariants are now available as callables the society can adopt.


## Sensory / Memory / Connective expansion

| Module | Role |
|--------|------|
| `sensory_surface.py` | Unified query over sensors, external array, PulseMesh, evidence graph |
| `memory_organ.py` | Multi-rate memory (working / durable / retained); mirrors into evidence graph |
| `connective.py` | Pulse summaries and route sense/recall to swarm and bus |

All fail-soft. Swarm calls them through the existing adapter. No free-form generation. Human authorize unchanged.


## Thin readers over existing surfaces (no new weight)

Swarm facade actions `sensors`, `athanor`, `residuals`, `failures` read the
colony's existing sensors snapshot, Athanor H₇, residual state, and
self-change failure log. They do not re-implement math or add authority.
Memory organ remains receipt-only. Canonical signals stay in Cortex sidecar,
Cerebrum boundary, and residuals.
