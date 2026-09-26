#!/usr/bin/env bash
# Restore colony data mirrors from gzip+base64 (see data/MIRROR_MANIFEST.json)
set -euo pipefail
cd "$(dirname "$0")/.."
python3 <<'PY'
import base64, gzip, hashlib, json
from pathlib import Path
root = Path('.')
man = json.loads((root / 'data/MIRROR_MANIFEST.json').read_text())
for f in man['files']:
    b64 = ''.join((root / f['mirror']).read_text().split())
    raw = gzip.decompress(base64.b64decode(b64))
    got = hashlib.sha256(raw).hexdigest()
    assert got == f['sha256'], (f['path'], got, f['sha256'])
    Path(f['path']).parent.mkdir(parents=True, exist_ok=True)
    Path(f['path']).write_bytes(raw)
    print('restored', f['path'], len(raw))
print('ok')
PY
