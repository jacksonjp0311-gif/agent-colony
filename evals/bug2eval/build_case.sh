#!/usr/bin/env bash
# Rebuild one bug2eval case from git history (before = FIX^ + the fix's regression test, after = FIX).
# usage: evals/bug2eval/build_case.sh CASE_ID FIX_SHA TEST_FILE "TITLE" TAGS
# needs: pip install "git+https://github.com/jacksonjp0311-gif/bug2eval"
set -euo pipefail
ID=$1; FIX=$2; TF=$3; TITLE=$4; TAGS=${5:-agent-colony}
ROOT=$(git rev-parse --show-toplevel); W=$(mktemp -d)
for side in before after; do
  ref=$FIX; [ "$side" = before ] && ref="$FIX^"
  mkdir -p "$W/$side/tests"
  git -C "$ROOT" archive "$ref" colony society/benchmarks society/systems tests/conftest.py \
      requirements.txt data/research_cache/offline_seeds.json | tar -x -C "$W/$side"
  git -C "$ROOT" show "$FIX:$TF" > "$W/$side/$TF"   # same verifier in both snapshots
done
bug2eval capture --id "$ID" --title "$TITLE" --before-dir "$W/before" --after-dir "$W/after" \
  --verify "python -m pytest -q -p no:cacheprovider $TF" --protect "$TF" --protect tests/conftest.py \
  --tags "$TAGS" --output "$W/case" --force
bug2eval pack "$W/case" --output "$ROOT/evals/bug2eval/cases/$ID.b2e"
rm -rf "$W"
