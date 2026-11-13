"""Append-only segment split for the large society state file.

``data/society_state.json`` is a single JSON object that has grown
past 44 MiB, and it is rewritten on every treatment commit. GitHub
warns at 50 MiB and rejects files over 100 MiB, so a full rewrite
every run will eventually fail the evolve push. The growing parts
are append-only lists and maps (communications, history,
evolution_log, artifacts, cycle_diagnostics). Mutable keys stay in
a small live file.

Migration does not rewrite history. The original
``data/society_state.json`` is left in place as a frozen snapshot
(segment 1); its bytes and SHA-256 are recorded on a manifest and
never written again. New appends go to numbered JSONL segments
under ``data/society_state/``, using the same rotation and manifest
machinery as ``colony.log_segments`` (PR #12). A slim
``data/society_state.live.json`` holds the mutable keys.

Readers reconstruct the identical logical state: frozen lists plus
every later JSONL segment, overlaid with the live mutable keys.

The control arm uses the same machinery. Existing committed control
copies of the large file are left in place and migrate on their own
first save. New control seeds do not copy the huge file; they get a
shared-snapshot pointer at the treatment frozen file (stable,
because it is never rewritten) and write new events to
control-owned segments.

This module does not loosen the Oracle or any gate, and it never
authorizes. It never rewrites committed history.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from colony import log_segments as LS

# Rotate the live JSONL segments at the same 40 MiB threshold as
# ledger/witness. The society *file* itself is split well before
# GitHub's 50 MiB warning: any unmigrated state at or over this
# size is frozen on the next save.
DEFAULT_SPLIT_THRESHOLD = 8 * 1024 * 1024
SPLIT_THRESHOLD_ENV = "COLONY_STATE_SEGMENT_BYTES"

# Append-only lists: new items are only ever added at the end, and a
# later file is a prefix-extension of an earlier one.
APPEND_LIST_KEYS: tuple[str, ...] = (
    "communications",
    "history",
    "evolution_log",
    "artifacts",
)

# Append-only maps: new keys are added; existing keys are not
# rewritten. A later record for the same key last-writes-wins, so a
# rare in-place update is still reconstructable.
APPEND_DICT_KEYS: tuple[str, ...] = (
    "cycle_diagnostics",
)

APPEND_KEYS: frozenset[str] = frozenset(APPEND_LIST_KEYS + APPEND_DICT_KEYS)

LIVE_NAME = "society_state.live.json"
MANIFEST_NAME = "society_state.segments.json"
SEGMENTS_DIRNAME = "society_state"


def threshold_bytes(override: int | None = None) -> int:
    if override is not None:
        return max(1, int(override))
    raw = (os.environ.get(SPLIT_THRESHOLD_ENV) or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return DEFAULT_SPLIT_THRESHOLD


def manifest_path(primary: Path) -> Path:
    return primary.parent / MANIFEST_NAME


def live_path(primary: Path, manifest: Mapping[str, Any] | None = None) -> Path:
    if manifest and manifest.get("live"):
        p = Path(str(manifest["live"]))
        if not p.is_absolute():
            p = primary.parent / p
        return p
    return primary.parent / LIVE_NAME


def segments_dir(primary: Path) -> Path:
    return primary.parent / SEGMENTS_DIRNAME


def key_primary(primary: Path, key: str) -> Path:
    """JSONL primary for one append-only key (``.../society_state/{key}.jsonl``)."""
    return segments_dir(primary) / f"{key}.jsonl"


def file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _file_bytes(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _atomic_write_json(path: Path, data: Mapping[str, Any], *, indent: int | None = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(dict(data), indent=indent, ensure_ascii=False) + "\n"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def load_manifest(primary: Path) -> dict[str, Any] | None:
    return _load_json(manifest_path(primary))


def save_manifest(primary: Path, manifest: Mapping[str, Any]) -> None:
    _atomic_write_json(manifest_path(primary), manifest)


def is_split(primary: Path) -> bool:
    man = load_manifest(primary)
    return bool(man and isinstance(man.get("frozen"), Mapping))


def state_present(root_or_primary: Path, *, is_root: bool = False) -> bool:
    """True when a society state is readable at this path.

    Accepts either the legacy single file or a split layout
    (manifest + live file, with or without a local frozen snapshot).
    """
    primary = (root_or_primary / "data" / "society_state.json") if is_root else root_or_primary
    if primary.is_file() and _file_bytes(primary) > 0:
        return True
    man = load_manifest(primary)
    if not man:
        return False
    return live_path(primary, man).is_file() or _resolve_frozen(primary, man).is_file()


def _resolve_frozen(primary: Path, manifest: Mapping[str, Any]) -> Path:
    raw = (manifest.get("frozen") or {}).get("path") or primary.name
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return (primary.parent / path).resolve()


def _rel_to_parent(primary: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(primary.parent.resolve()).as_posix()
    except ValueError:
        return str(path)


def frozen_counts(manifest: Mapping[str, Any] | None) -> dict[str, int]:
    if not manifest:
        return {}
    raw = (manifest.get("frozen") or {}).get("counts") or {}
    return {str(k): int(v) for k, v in raw.items() if _is_int(v)}


def _is_int(v: Any) -> bool:
    try:
        int(v)
        return True
    except (TypeError, ValueError):
        return False


def _counts_from(data: Mapping[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key in APPEND_LIST_KEYS:
        arr = data.get(key)
        out[key] = len(arr) if isinstance(arr, list) else 0
    for key in APPEND_DICT_KEYS:
        d = data.get(key)
        out[key] = len(d) if isinstance(d, dict) else 0
    return out


def _iter_jsonl_records(primary: Path) -> Iterable[Any]:
    if not is_split(primary) and not LS.load_manifest(primary) and not primary.is_file():
        return
    for line in LS.iter_lines(primary):
        text = line.strip() if isinstance(line, str) else line.decode().strip()
        if not text:
            continue
        try:
            yield json.loads(text)
        except json.JSONDecodeError:
            continue


def load_data(primary: Path) -> dict[str, Any]:
    """Return the logical society state.

    After a split this is the frozen snapshot's append-only keys,
    plus every later JSONL segment, overlaid with the live mutable
    keys. Before a split it is exactly ``json.load`` of the file.
    The two views are equal for an unmigrated file, and equal to
    what a single-file rewrite would have contained after a
    migrated save.
    """
    man = load_manifest(primary)
    if not man or not isinstance(man.get("frozen"), Mapping):
        data = _load_json(primary)
        return dict(data) if data else {}

    frozen_path = _resolve_frozen(primary, man)
    frozen = _load_json(frozen_path) or {}
    live = _load_json(live_path(primary, man)) or {}

    data = dict(frozen)
    for key, value in live.items():
        if key in APPEND_KEYS:
            # Live must not wipe reconstructed append-only keys.
            continue
        data[key] = value

    for key in APPEND_LIST_KEYS:
        items = list(frozen.get(key) or []) if isinstance(frozen.get(key), list) else []
        for rec in _iter_jsonl_records(key_primary(primary, key)):
            items.append(rec)
        data[key] = items

    for key in APPEND_DICT_KEYS:
        mapping: dict[str, Any] = {}
        raw = frozen.get(key)
        if isinstance(raw, dict):
            mapping.update(raw)
        for rec in _iter_jsonl_records(key_primary(primary, key)):
            if not isinstance(rec, dict):
                continue
            kid = rec.get("id")
            if kid is None:
                continue
            if "value" in rec:
                mapping[str(kid)] = rec["value"]
            else:
                mapping[str(kid)] = {k: v for k, v in rec.items() if k != "id"}
        data[key] = mapping

    return data


def already_stored_count(primary: Path, key: str, *, manifest: Mapping[str, Any] | None = None) -> int:
    """How many items of ``key`` already live in frozen + JSONL segments."""
    man = manifest if manifest is not None else load_manifest(primary)
    n = int(frozen_counts(man).get(key, 0))
    kp = key_primary(primary, key)
    if LS.load_manifest(kp) or kp.is_file() or LS.manifest_path(kp).is_file():
        n += LS.count_lines(kp)
    return n


def already_stored_dict_ids(primary: Path, key: str, *, manifest: Mapping[str, Any] | None = None) -> set[str]:
    man = manifest if manifest is not None else load_manifest(primary)
    ids: set[str] = set()
    frozen_path = _resolve_frozen(primary, man) if man and man.get("frozen") else primary
    frozen = _load_json(frozen_path) or {}
    raw = frozen.get(key)
    if isinstance(raw, dict):
        ids.update(str(k) for k in raw)
    for rec in _iter_jsonl_records(key_primary(primary, key)):
        if isinstance(rec, dict) and rec.get("id") is not None:
            ids.add(str(rec["id"]))
    return ids


def should_split(primary: Path, *, threshold: int | None = None) -> bool:
    """True when an unmigrated file is large enough to freeze-and-split."""
    if is_split(primary):
        return False
    return _file_bytes(primary) >= threshold_bytes(threshold)


def migrate(
    primary: Path,
    *,
    threshold: int | None = None,
    live_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze the existing file as segment 1 and write a slim live file.

    The original file is not opened for write. Its SHA-256 and size
    are recorded. ``live_data``, when given, is the current in-memory
    logical state (possibly with new items not yet on disk); new
    append-only items are written to JSONL segments. Mutable keys go
    to the live file.
    """
    existing = load_manifest(primary)
    if existing and existing.get("frozen"):
        if live_data is not None:
            _write_live_and_segments(primary, live_data, existing)
            # Reload: counts are unchanged, segments may have grown.
            existing = load_manifest(primary) or existing
        return existing

    frozen_on_disk = _load_json(primary) or {}
    sha = file_sha256(primary) if primary.is_file() else ""
    size = _file_bytes(primary)
    counts = _counts_from(frozen_on_disk)
    man: dict[str, Any] = {
        "version": 1,
        "kind": "society_state",
        "primary": primary.name,
        "live": LIVE_NAME,
        "threshold_bytes": threshold_bytes(threshold),
        "frozen": {
            "id": 1,
            "path": primary.name,
            "kind": "frozen_snapshot",
            "status": "closed",
            "bytes": size,
            "sha256": sha,
            "counts": counts,
            "keys": list(APPEND_LIST_KEYS + APPEND_DICT_KEYS),
        },
        "append_keys": {
            key: {
                "kind": "list" if key in APPEND_LIST_KEYS else "dict",
                "segments_primary": _rel_to_parent(primary, key_primary(primary, key)),
            }
            for key in (APPEND_LIST_KEYS + APPEND_DICT_KEYS)
        },
        "note": (
            "Segment 1 is the original society_state.json, left "
            "untouched. New append-only items go to numbered JSONL "
            "segments under society_state/. Mutable keys live in "
            "society_state.live.json. Earlier bytes are never rewritten."
        ),
    }
    save_manifest(primary, man)
    logical = dict(live_data) if live_data is not None else dict(frozen_on_disk)
    _write_live_and_segments(primary, logical, man)
    return load_manifest(primary) or man


def _dump_line(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def _write_live_and_segments(
    primary: Path,
    logical: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> None:
    for key in APPEND_LIST_KEYS:
        arr = logical.get(key)
        if not isinstance(arr, list) or not arr:
            continue
        already = already_stored_count(primary, key, manifest=manifest)
        if already < 0:
            already = 0
        new_items = arr[already:]
        kp = key_primary(primary, key)
        for item in new_items:
            LS.append_line(kp, _dump_line(item))

    for key in APPEND_DICT_KEYS:
        mapping = logical.get(key)
        if not isinstance(mapping, dict) or not mapping:
            continue
        known = already_stored_dict_ids(primary, key, manifest=manifest)
        kp = key_primary(primary, key)
        for kid, value in mapping.items():
            if str(kid) in known:
                continue
            LS.append_line(kp, _dump_line({"id": str(kid), "value": value}))

    live = {k: v for k, v in logical.items() if k not in APPEND_KEYS}
    live["_state_segments"] = {
        "manifest": _rel_to_parent(primary, manifest_path(primary)),
        "frozen": (manifest.get("frozen") or {}).get("path"),
        "frozen_sha256": (manifest.get("frozen") or {}).get("sha256"),
        "frozen_bytes": (manifest.get("frozen") or {}).get("bytes"),
    }
    _atomic_write_json(live_path(primary, manifest), live)


def save_split(
    primary: Path,
    logical: Mapping[str, Any],
    *,
    threshold: int | None = None,
) -> dict[str, Any]:
    """Write a split state. Migrates first if the original is still whole.

    Never writes the frozen snapshot. Returns the manifest.
    """
    if not is_split(primary) and (
        should_split(primary, threshold=threshold) or _file_bytes(primary) >= threshold_bytes(threshold)
    ):
        return migrate(primary, threshold=threshold, live_data=logical)
    if is_split(primary):
        man = load_manifest(primary) or {}
        _write_live_and_segments(primary, logical, man)
        return load_manifest(primary) or man
    # Small unmigrated file: the caller writes the single file itself.
    return {}


def attach_shared_state(dest_primary: Path, src_primary: Path) -> dict[str, Any]:
    """Point a control state at a frozen snapshot of treatment state.

    Does not copy the large frozen file. The control live file is a
    slim snapshot of mutable keys at seed time. Append-only JSONL
    already written by treatment is referenced as a shared prefix
    (later treatment appends past the seed cut are not read). New
    control events go to control-owned segments.
    """
    dest_primary.parent.mkdir(parents=True, exist_ok=True)
    src_man = load_manifest(src_primary)
    src_logical = load_data(src_primary) if (src_man or src_primary.is_file()) else {}

    # Frozen pointer: prefer the treatment's already-frozen file,
    # which will never be rewritten. If treatment has not migrated
    # yet, point at its society_state.json; after it migrates that
    # same file becomes its frozen snapshot and the pointer stays
    # valid (the file is then never written).
    if src_man and src_man.get("frozen"):
        frozen_src = _resolve_frozen(src_primary, src_man)
        src_counts = frozen_counts(src_man)
        src_sha = str((src_man.get("frozen") or {}).get("sha256") or file_sha256(frozen_src))
        src_size = int((src_man.get("frozen") or {}).get("bytes") or _file_bytes(frozen_src))
    else:
        frozen_src = src_primary
        src_counts = _counts_from(_load_json(src_primary) or {})
        src_sha = file_sha256(src_primary)
        src_size = _file_bytes(src_primary)

    man: dict[str, Any] = {
        "version": 1,
        "kind": "society_state",
        "primary": dest_primary.name,
        "live": LIVE_NAME,
        "threshold_bytes": threshold_bytes(),
        "frozen": {
            "id": 1,
            "path": _rel_to_parent(dest_primary, frozen_src),
            "kind": "shared_snapshot",
            "status": "closed",
            "bytes": src_size,
            "sha256": src_sha,
            "counts": src_counts,
            "source": "treatment",
            "keys": list(APPEND_LIST_KEYS + APPEND_DICT_KEYS),
            "note": (
                "Frozen snapshot of the treatment society state at "
                "seed. Not a copy. The file is never rewritten, so "
                "this pointer stays valid."
            ),
        },
        "append_keys": {
            key: {
                "kind": "list" if key in APPEND_LIST_KEYS else "dict",
                "segments_primary": _rel_to_parent(dest_primary, key_primary(dest_primary, key)),
            }
            for key in (APPEND_LIST_KEYS + APPEND_DICT_KEYS)
        },
        "note": (
            "Control arm: shared snapshot of treatment frozen state, "
            "no copy of the large file. New appends go to "
            "control-owned JSONL segments."
        ),
    }
    save_manifest(dest_primary, man)

    # Shared-prefix each treatment JSONL key at its current size.
    for key in APPEND_LIST_KEYS + APPEND_DICT_KEYS:
        src_kp = key_primary(src_primary, key)
        dest_kp = key_primary(dest_primary, key)
        src_entries = []
        if LS.load_manifest(src_kp) or src_kp.is_file():
            src_entries = LS.segment_entries(src_kp)
        if not src_entries:
            continue
        # Build a dest manifest with a shared_prefix entry per source
        # segment, capped at each file's size at seed.
        dest_man = LS.empty_manifest(dest_kp)
        dest_segs: list[dict[str, Any]] = []
        prev_sha = ""
        for i, entry in enumerate(src_entries):
            src_path = _resolve_src_segment(src_kp, entry)
            if not src_path.is_file():
                continue
            limit = src_path.stat().st_size
            last_sha = LS.last_line_sha256(src_path)
            dest_segs.append({
                "id": i + 1,
                "path": _rel_to_parent(dest_kp, src_path),
                "kind": LS.SHARED_PREFIX,
                "status": "closed",
                "bytes": limit,
                "limit_bytes": limit,
                "last_line_sha256": last_sha,
                "prev_sha256": prev_sha,
                "source": "treatment",
            })
            prev_sha = last_sha
        if dest_segs:
            dest_man["segments"] = dest_segs
            dest_man["shared_prefix"] = {
                "source": "treatment",
                "path": dest_segs[0]["path"],
                "limit_bytes": dest_segs[0]["limit_bytes"],
                "last_line_sha256": dest_segs[0]["last_line_sha256"],
            }
            LS.save_manifest(dest_kp, dest_man)

    # Slim live file: mutable keys at seed, no append-only lists.
    live = {k: v for k, v in src_logical.items() if k not in APPEND_KEYS}
    live["_state_segments"] = {
        "manifest": _rel_to_parent(dest_primary, manifest_path(dest_primary)),
        "frozen": man["frozen"]["path"],
        "frozen_sha256": src_sha,
        "frozen_bytes": src_size,
        "shared": True,
    }
    _atomic_write_json(live_path(dest_primary, man), live)
    return man


def _resolve_src_segment(primary: Path, entry: Mapping[str, Any]) -> Path:
    raw = entry.get("path")
    if not raw:
        n = int(entry.get("id") or entry.get("n") or 1)
        return LS.segment_file(primary, n)
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return primary.parent / path


def logical_keys_equal(a: Mapping[str, Any], b: Mapping[str, Any]) -> tuple[bool, str]:
    """Compare logical society state, ignoring split bookkeeping keys."""
    ignore = {"_state_segments", "_shards"}
    ka = set(a) - ignore
    kb = set(b) - ignore
    if ka != kb:
        missing = ka - kb
        extra = kb - ka
        return False, f"key mismatch missing={sorted(missing)} extra={sorted(extra)}"
    for key in sorted(ka):
        if a[key] != b[key]:
            return False, f"value mismatch at {key}"
    return True, "ok"


__all__ = (
    "APPEND_DICT_KEYS",
    "APPEND_KEYS",
    "APPEND_LIST_KEYS",
    "DEFAULT_SPLIT_THRESHOLD",
    "LIVE_NAME",
    "MANIFEST_NAME",
    "SPLIT_THRESHOLD_ENV",
    "already_stored_count",
    "attach_shared_state",
    "file_sha256",
    "frozen_counts",
    "is_split",
    "key_primary",
    "live_path",
    "load_data",
    "load_manifest",
    "logical_keys_equal",
    "manifest_path",
    "migrate",
    "save_split",
    "should_split",
    "state_present",
    "threshold_bytes",
)
