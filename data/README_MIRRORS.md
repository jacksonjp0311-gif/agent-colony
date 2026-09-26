# Data mirrors (authorize-complete state)

Live colony state after the trust-grant authorize pass (cycle 27, accepted=21)
is mirrored here when full JSONL exceeds connector payload limits.

- Manifest: `data/MIRROR_MANIFEST.json`
- Restore: `bash scripts/restore_colony_mirrors.sh`
- Each `*.gz.b64` is gzip(raw) then base64; sha256 of raw is in the manifest.

Plain `data/ledger.jsonl` on GitHub may lag until a larger-file push path exists;
prefer restoring from mirrors or the box copy.

Updated for hard-lemma mile (cycle_count=104); prefer mirrors for ledger/witness/society_state.
