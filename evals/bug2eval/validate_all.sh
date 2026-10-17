#!/usr/bin/env bash
# Validate every captured case: BEFORE snapshot must fail, AFTER must pass, verifier untampered.
set -euo pipefail
cd "$(dirname "$0")/cases"
rc=0
for c in *.b2e; do bug2eval validate "$c" || rc=1; done
exit $rc
