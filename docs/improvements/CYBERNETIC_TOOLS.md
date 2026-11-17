# Evidence-Gated Evolution Tools

These optional tools implement the improvement plan while preserving the colony’s design:

- **Static agency**: runners remain time-based (GitHub Actions cron, `python -m colony evolve --cycles N`).
- **Cybernetic operation**: feedback loops (Oracle outcomes → keep/revert → lessons → genomes → next proposals) continue to close inside the society. The new tools make those loops cleaner and more attributable without adding external intelligence.

## Modules

| Module | Purpose |
|--------|---------|
| `colony/tools/evidence_graph.py` | Append-only shared graph of claims, counterexamples, method cards. Prevents silent loss of findings. |
| `colony/tools/statistical_keep_gate.py` | Sequential gate that bounds false-evolution rate before a keep is considered. |
| `colony/tools/invariant_contracts.py` | Machine-checkable preconditions (verified depth, no overlap, frontier safety). |

All are loadable. The colony proposes their use through the existing conjecture desk; the Oracle verifies; human authorization remains required for durable promotion. Twin-control arms stay frozen for comparison.

No running cycle is modified by the presence of these modules.
