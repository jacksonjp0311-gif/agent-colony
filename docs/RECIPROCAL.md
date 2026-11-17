# Reciprocal Exchange

One Mind (exploration) ↔ Agent Colony (validation)

## Protocol

1. Each system appends measured failures/residuals to `data/commons/exchange.jsonl`.
2. `reciprocal_exchange.merge_remote` fetches the other repo's file via raw GitHub.
3. Imported receipts are marked `_imported` and never carry the remote keep/reject as authority.
4. Local penalty uses foreign fingerprints as prior only.
5. `record_adoption` logs whether an imported fingerprint later coincided with a better local outcome.

## Rules

- No automatic inheritance of verdicts.
- Colony still requires Oracle + twin + human authorize.
- One Mind may use the prior more freely.
- Fail-open on network or parse errors.

## Status

Cross-repo fetch implemented. Adoption feedback log ready.
Independent adoption tests are the next measurement.
