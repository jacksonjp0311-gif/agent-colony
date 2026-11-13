# Data mirrors (authorize-complete state)

Live colony state after the trust-grant authorize pass is mirrored here when full JSONL exceeds connector payload limits.

- Manifest: `data/MIRROR_MANIFEST.json`
- Restore: `bash scripts/restore_colony_mirrors.sh`

Plain `data/ledger.jsonl` on GitHub may lag; prefer restoring from mirrors or the box copy.
