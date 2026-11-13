"""Append-only segment rotation for large JSONL logs.

When a log (``data/witness.jsonl``, ``data/ledger.jsonl``) passes a
byte threshold, new appends go to a new numbered segment file. Existing
bytes are never rewritten: the original file stays in place as
segment 1, and a small manifest lists every segment in order.

Readers iterate every segment in order. If a witness or ledger hash
chain is present on the records, it continues across the segment
boundary because the first line of the next segment is appended after
the last line of the previous one, with the previous last-line digest
recorded on the manifest.

The control arm uses the same machinery. At seed time the huge
treatment logs are not copied; a shared-prefix pointer records the
treatment file and the frozen byte length at seed (append-only, so
that prefix is stable). New control events go to control-owned
segments.

This module does not loosen the Oracle or any gate, and it never
authorizes. It never rewrites committed history.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterator, Mapping

# Rotate before GitHub's 50 MB warning; the hard limit is 100 MB.
DEFAULT_THRESHOLD = 40 * 1024 * 1024
THRESHOLD_ENV = "COLONY_LOG_SEGMENT_BYTES"

# Shared-prefix segments (control reading a frozen treatment prefix)
# are identified by this kind.
SHARED_PREFIX = "shared_prefix"


def threshold_bytes(override: int | None = None) -> int:
    if override is not None:
        return max(1, int(override))
    raw = (os.environ.get(THRESHOLD_ENV) or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return DEFAULT_THRESHOLD


def manifest_path(primary: Path) -> Path:
    """``data/witness.jsonl`` → ``data/witness.segments.json``."""
    return primary.parent / f"{primary.stem}.segments.json"


def segment_dir(primary: Path) -> Path:
    """``data/witness.jsonl`` → ``data/witness/``."""
    return primary.parent / primary.stem


def segment_file(primary: Path, n: int) -> Path:
    if int(n) <= 1:
        return primary
    return segment_dir(primary) / f"{primary.stem}-{int(n):04d}{primary.suffix}"


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(dict(data), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _file_bytes(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def last_line_sha256(path: Path) -> str:
    """SHA-256 of the last non-empty line (including its trailing newline).

    Used as the hash-chain hinge across a segment boundary. Empty or
    missing files return an empty string.
    """
    if not path.is_file() or path.stat().st_size == 0:
        return ""
    last = b""
    with path.open("rb") as fh:
        # Read from the end in chunks; files may be tens of MB.
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        pos = size
        buf = b""
        while pos > 0:
            step = min(4096, pos)
            pos -= step
            fh.seek(pos)
            buf = fh.read(step) + buf
            if buf.count(b"\n") >= 2 or (pos == 0 and buf):
                break
        parts = buf.split(b"\n")
        # Trailing newline produces a final empty part; pick the last
        # non-empty, then put the newline back.
        while parts and not parts[-1]:
            parts.pop()
        if not parts:
            return ""
        last = parts[-1] + b"\n"
    return hashlib.sha256(last).hexdigest()


def empty_manifest(primary: Path, *, threshold: int | None = None) -> dict[str, Any]:
    return {
        "version": 1,
        "kind": primary.stem,
        "primary": primary.name,
        "threshold_bytes": threshold_bytes(threshold),
        "segments": [],
        "note": (
            "Append-only segment list. Segment 1 is the original file, "
            "left untouched after rotation. New appends go to the active "
            "segment. Earlier bytes are never rewritten."
        ),
    }


def load_manifest(primary: Path) -> dict[str, Any] | None:
    return _load_json(manifest_path(primary))


def save_manifest(primary: Path, manifest: Mapping[str, Any]) -> None:
    _atomic_write_json(manifest_path(primary), manifest)


def _resolve(primary: Path, stored: Mapping[str, Any]) -> Path:
    raw = stored.get("path")
    if not raw:
        n = int(stored.get("id") or stored.get("n") or 1)
        return segment_file(primary, n)
    path = Path(str(raw))
    if path.is_absolute():
        return path
    # Relative to the primary's parent (the data/ directory).
    return primary.parent / path


def _rel_to_parent(primary: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(primary.parent.resolve()).as_posix()
    except ValueError:
        return str(path)


def segment_entries(primary: Path) -> list[dict[str, Any]]:
    """Return manifest segments, or a synthetic one-segment view."""
    man = load_manifest(primary)
    if man and isinstance(man.get("segments"), list) and man["segments"]:
        return [dict(s) for s in man["segments"] if isinstance(s, Mapping)]
    if primary.is_file():
        return [{
            "id": 1,
            "path": primary.name,
            "kind": "file",
            "status": "active",
            "bytes": _file_bytes(primary),
        }]
    return []


def segment_paths(primary: Path) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for entry in segment_entries(primary):
        path = _resolve(primary, entry)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    if not paths:
        paths.append(primary)
    return paths


def iter_lines(primary: Path, *, encoding: str = "utf-8") -> Iterator[str]:
    """Yield raw lines (with newlines) from every segment, in order.

    A shared-prefix segment is truncated at ``limit_bytes`` so a
    control arm can read a frozen treatment prefix without seeing
    later treatment appends.
    """
    entries = segment_entries(primary)
    if not entries:
        if primary.is_file():
            with primary.open("r", encoding=encoding) as fh:
                yield from fh
        return
    for entry in entries:
        path = _resolve(primary, entry)
        if not path.is_file():
            continue
        limit = entry.get("limit_bytes")
        if entry.get("kind") == SHARED_PREFIX or limit is not None:
            try:
                cap = int(limit) if limit is not None else path.stat().st_size
            except (TypeError, ValueError, OSError):
                cap = path.stat().st_size
            yield from _iter_prefixed(path, cap, encoding=encoding)
            continue
        with path.open("r", encoding=encoding) as fh:
            yield from fh


def _iter_prefixed(path: Path, limit_bytes: int, *, encoding: str) -> Iterator[str]:
    """Yield complete lines from the first ``limit_bytes`` of ``path``."""
    if limit_bytes <= 0:
        return
    with path.open("rb") as fh:
        remaining = int(limit_bytes)
        buf = b""
        while remaining > 0:
            chunk = fh.read(min(1024 * 256, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            buf += chunk
            while True:
                i = buf.find(b"\n")
                if i < 0:
                    break
                line, buf = buf[: i + 1], buf[i + 1 :]
                yield line.decode(encoding)
        # At a frozen seed cut the last byte is the end of a line
        # (the file ended there). If a mid-line remainder is left,
        # drop it: a partial JSON object is not a record.
        if remaining == 0:
            return
        if buf:
            yield buf.decode(encoding)


def count_lines(primary: Path) -> int:
    return sum(1 for line in iter_lines(primary) if line.strip())


def _close_entry(primary: Path, entry: dict[str, Any]) -> dict[str, Any]:
    path = _resolve(primary, entry)
    out = dict(entry)
    out["status"] = "closed"
    out["bytes"] = _file_bytes(path)
    out["last_line_sha256"] = last_line_sha256(path)
    return out


def _new_entry(
    primary: Path,
    n: int,
    *,
    prev_sha: str = "",
    status: str = "active",
    kind: str = "file",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    path = segment_file(primary, n)
    entry = {
        "id": n,
        "path": _rel_to_parent(primary, path) if n > 1 else primary.name,
        "kind": kind,
        "status": status,
        "bytes": _file_bytes(path),
        "prev_sha256": prev_sha,
    }
    if extra:
        entry.update(dict(extra))
    return entry


def ensure_manifest(primary: Path, *, threshold: int | None = None) -> dict[str, Any]:
    """Return the manifest, creating a one-segment view if needed (no rotate)."""
    man = load_manifest(primary)
    if man and man.get("segments"):
        return man
    man = empty_manifest(primary, threshold=threshold)
    if primary.is_file():
        man["segments"] = [_new_entry(primary, 1, status="active")]
        man["segments"][0]["bytes"] = _file_bytes(primary)
    return man


def maybe_rotate(primary: Path, *, threshold: int | None = None) -> dict[str, Any]:
    """If the active segment is at or over the threshold, open a new one.

    The previous file is not renamed, truncated, or rewritten. The
    manifest is the only thing that changes (plus a new empty file).
    """
    limit = threshold_bytes(threshold)
    man = ensure_manifest(primary, threshold=limit)
    segs = list(man.get("segments") or [])
    if not segs:
        # First write will create the primary as segment 1.
        man["segments"] = [_new_entry(primary, 1, status="active")]
        man["threshold_bytes"] = limit
        return man
    active = segs[-1]
    if active.get("kind") == SHARED_PREFIX:
        # Shared prefixes are read-only. Always append to a local segment.
        prev_sha = str(active.get("last_line_sha256") or "")
        if not prev_sha:
            prev_sha = last_line_sha256(_resolve(primary, active))
            active["last_line_sha256"] = prev_sha
        nxt = int(active.get("id") or 1) + 1
        # If a local segment already follows, use it.
        segs[-1] = dict(active, status="closed")
        new = _new_entry(primary, nxt, prev_sha=prev_sha, status="active")
        segs.append(new)
        man["segments"] = segs
        man["threshold_bytes"] = limit
        save_manifest(primary, man)
        path = _resolve(primary, new)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        return man
    path = _resolve(primary, active)
    size = _file_bytes(path)
    if size < limit:
        return man
    closed = _close_entry(primary, active)
    nxt = int(closed.get("id") or 1) + 1
    new = _new_entry(primary, nxt, prev_sha=str(closed.get("last_line_sha256") or ""), status="active")
    segs[-1] = closed
    segs.append(new)
    man["segments"] = segs
    man["threshold_bytes"] = limit
    save_manifest(primary, man)
    new_path = _resolve(primary, new)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    if not new_path.exists():
        new_path.touch()
    return man


def active_path(primary: Path, *, threshold: int | None = None) -> Path:
    """Path that the next append should write to. May rotate first."""
    man = maybe_rotate(primary, threshold=threshold)
    segs = list(man.get("segments") or [])
    if not segs:
        return primary
    # The last non-shared, active segment, else the last entry.
    for entry in reversed(segs):
        if entry.get("kind") == SHARED_PREFIX:
            continue
        path = _resolve(primary, entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return primary


def append_line(
    primary: Path,
    line: str,
    *,
    threshold: int | None = None,
    encoding: str = "utf-8",
) -> Path:
    """Append one line to the active segment, rotating first if needed.

    ``line`` should not include a trailing newline; one is added.
    Returns the path that was written. Earlier segment bytes are
    never modified.
    """
    dest = active_path(primary, threshold=threshold)
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = line if line.endswith("\n") else line + "\n"
    with dest.open("a", encoding=encoding) as fh:
        fh.write(body)
    # Keep the manifest byte count honest for the active segment.
    man = load_manifest(primary)
    if man and man.get("segments"):
        man["segments"][-1]["bytes"] = _file_bytes(dest)
        try:
            save_manifest(primary, man)
        except OSError:
            pass
    return dest


def attach_shared_prefix(
    primary: Path,
    source: Path,
    *,
    limit_bytes: int | None = None,
    source_label: str = "treatment",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Point a control log at a frozen prefix of a treatment log.

    Does not copy the source. The prefix length is the file size at
    seed time; later treatment appends sit past that cut and are not
    read. New control appends go to a local segment 2 (created on
    the first append via ``maybe_rotate``).
    """
    cap = int(limit_bytes if limit_bytes is not None else _file_bytes(source))
    last_sha = ""
    if source.is_file() and cap > 0:
        # Hash the last complete line of the prefix. At seed, cap is
        # the whole file, so this is last_line_sha256(source).
        if cap >= _file_bytes(source):
            last_sha = last_line_sha256(source)
    try:
        # Prefer a repo-relative path from the control primary's
        # parent (control/data) up to the treatment file. Fall back
        # to an absolute path if they don't share a parent.
        rel = os.path.relpath(os.fspath(source), os.fspath(primary.parent))
    except ValueError:
        rel = str(source)
    entry = {
        "id": 1,
        "path": rel,
        "kind": SHARED_PREFIX,
        "status": "closed",
        "bytes": cap,
        "limit_bytes": cap,
        "source": source_label,
        "last_line_sha256": last_sha,
        "note": (
            "Frozen prefix of the treatment log at seed. Not a copy. "
            "Later treatment appends past limit_bytes are not read."
        ),
    }
    if extra:
        entry.update(dict(extra))
    man = empty_manifest(primary)
    man["segments"] = [entry]
    man["shared_prefix"] = {
        "source": source_label,
        "path": rel,
        "limit_bytes": cap,
        "last_line_sha256": last_sha,
    }
    save_manifest(primary, man)
    return man


def verify_chain(primary: Path) -> tuple[bool, str]:
    """Check that each segment's prev_sha256 matches the previous last line.

    Returns ``(ok, reason)``. A single-segment or missing-chain
    log is ok: there is nothing to continue. A mismatch is not.
    """
    entries = segment_entries(primary)
    if len(entries) <= 1:
        return True, "single_segment"
    prev_sha = ""
    for i, entry in enumerate(entries):
        path = _resolve(primary, entry)
        if entry.get("kind") == SHARED_PREFIX:
            stored = str(entry.get("last_line_sha256") or "")
            prev_sha = stored or last_line_sha256(path)
            continue
        if i == 0:
            prev_sha = last_line_sha256(path) if path.is_file() else ""
            continue
        expected = str(entry.get("prev_sha256") or "")
        if expected and prev_sha and expected != prev_sha:
            return False, f"segment {entry.get('id')} prev_sha256 mismatch"
        if path.is_file() and path.stat().st_size > 0:
            prev_sha = last_line_sha256(path)
    return True, "ok"


__all__ = (
    "DEFAULT_THRESHOLD",
    "SHARED_PREFIX",
    "THRESHOLD_ENV",
    "active_path",
    "append_line",
    "attach_shared_prefix",
    "count_lines",
    "ensure_manifest",
    "iter_lines",
    "last_line_sha256",
    "load_manifest",
    "manifest_path",
    "maybe_rotate",
    "save_manifest",
    "segment_dir",
    "segment_entries",
    "segment_file",
    "segment_paths",
    "threshold_bytes",
    "verify_chain",
)
