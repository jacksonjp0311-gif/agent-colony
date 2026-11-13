"""Treatment vs control arm for a measured self-improvement experiment.

The treatment arm is the live colony: self-heal trials, checker-lane
adoption, Hive learning (when present), and perturb-policy knobs can
change. The control arm runs the same evolve pipeline, against the
same Oracle and the same gates, with every self-modification frozen
at the code defaults. Control writes only under ``control/``, a tree
seeded once from treatment state, so the two arms never share a
writable file.

Set ``COLONY_ARM=control`` (or ``python -m colony evolve --arm control``).
``COLONY_CONTROL_ROOT`` overrides the control tree (used by tests).
``COLONY_SEED_CONTROL=1`` allows the first-run snapshot copy.

This module does not loosen the Oracle, the P ≥ 0.70 gate, the 150
authored-check cap, or Athanor math, and it never authorizes. It
does not claim that a short lead is recursive self-improvement:
early differences are noise, and a lasting lead needs many paired
runs recorded on the twin scoreboard.
"""
from __future__ import annotations

import importlib.abc
import importlib.machinery
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

# Repo root: code, charter, defaults, and the treatment state tree.
# Never redirected. Shared artifacts (the twin scoreboard) hang off this.
REPO_ROOT = Path(__file__).resolve().parent.parent

CONTROL_DIRNAME = "control"
FORK_NAME = ".fork.json"
_HIVE_MODULES = ("hive.swarm", "hive.ops")
_HIVE_FUNCS = ("on_cycle", "run_cycle", "learn", "maybe_learn", "bind")
_HOOKS_INSTALLED = False
_HIVE_FINDER_INSTALLED = False

# Treatment files that must exist in the control tree after a seed.
# Evolve crashes without society_state.json (run 43354564616).
REQUIRED_SEED_FILES = ("data/society_state.json",)

# Directories copied into the control tree at seed time. These are the
# colony's writable state. Code under colony/, tests/, and .github stays
# shared, so both arms run the same program.
_SEED_TREES = ("data", "society")
# Huge append-only logs are not copied into the control tree. They
# already sit near GitHub's 50 MB warning (and would be duplicated).
# Control gets a frozen-prefix pointer and writes new events to its
# own segments. Existing committed copies are left in place (we do
# not rewrite history).
_SEED_SKIP_LOGS = frozenset({"ledger.jsonl", "witness.jsonl"})
_SEED_IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    ".desk_journal.json",
    ".desk_journal.tmp",
    ".lemma_backups",
    "*.gz.b64",
    "ledger.jsonl",
    "witness.jsonl",
)


class ControlSeedError(RuntimeError):
    """Control seed copied nothing, or a required file is missing.

    Raised so the CLI and the CI seed step exit nonzero. A quiet
    ``copied: []`` exit (run 43354564616) left the control arm
    unseeded and the evolve job crashed.
    """


def raw_join(base: Path | str, *parts: str | Path) -> Path:
    """Join path parts without the ``COLONY_ARM`` ``Path.__truediv__`` hook.

    The hook wraps the ``/`` operator so that ``REPO_ROOT / "data"``
    becomes ``control/data`` when ``COLONY_ARM=control``. ``Path(base,
    part)`` and ``os.path.join`` both bypass that wrap. Use this
    whenever treatment ``data/`` or ``society/`` must be *read* as
    the seed source while the hook is installed.
    """
    return Path(os.path.join(os.fspath(base), *(os.fspath(p) for p in parts)))


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def arm() -> str:
    raw = (os.environ.get("COLONY_ARM") or "treatment").strip().lower()
    return "control" if raw == "control" else "treatment"


def is_control() -> bool:
    return arm() == "control"


def self_mod_enabled() -> bool:
    """False on the control arm, or when COLONY_SELF_MOD is off.

    When this is false, self-heal trials do not start or close, checker
    candidates are not accepted for review, Hive learning does not run,
    and self-heal knobs report as unset so callers keep their defaults
    (including the perturb policy).
    """
    if is_control():
        return False
    v = (os.environ.get("COLONY_SELF_MOD") or "on").strip().lower()
    return v not in {"0", "off", "false", "no"}


def hive_learning_enabled() -> bool:
    """Whether Hive/swarm learning may run.

    Always false on the control arm. On treatment, a missing Hive
    package simply means there is nothing to run: this function can
    still return True, and callers import Hive behind a feature check.
    After Hive merges, the import hook in this module wraps Hive's
    ``on_cycle`` so a forgotten check still cannot learn in control.
    """
    if not self_mod_enabled():
        return False
    v = (os.environ.get("COLONY_HIVE_LEARNING") or "on").strip().lower()
    return v not in {"0", "off", "false", "no"}


def control_root() -> Path:
    override = (os.environ.get("COLONY_CONTROL_ROOT") or "").strip()
    if override:
        return Path(override)
    return REPO_ROOT / CONTROL_DIRNAME


def state_root() -> Path:
    """Root that ``data/`` and ``society/`` hang off for the current arm."""
    if is_control():
        return control_root()
    return REPO_ROOT


def data_dir() -> Path:
    return state_root() / "data"


def society_dir() -> Path:
    return state_root() / "society"


def fork_path() -> Path:
    return control_root() / FORK_NAME


def redirect(base: Path, first: str) -> Path:
    """Map ``<repo>/data`` or ``<repo>/society`` onto the control tree.

    Other first components (``colony``, ``CHARTER.md``, ``tests``) are
    left on the repo root so both arms share the same code and defaults.
    """
    if str(first) in {"data", "society"} and is_control() and _is_repo_root(base):
        return control_root() / first
    return Path(base) / first


def _is_repo_root(p: Path | str) -> bool:
    try:
        s = os.path.normpath(os.fspath(p))
        return s == os.path.normpath(str(REPO_ROOT))
    except Exception:
        return False


def _install_path_hook() -> None:
    """Redirect ``<repo> / 'data'`` and ``<repo> / 'society'`` at use time.

    Module-level ``STATE_PATH = ROOT / "society" / ...`` is computed at
    import. For a CI control job, ``COLONY_ARM`` is set before the
    process starts, so those constants already point at ``control/``.
    Tests that set the env after import should use ``data_dir()`` /
    ``society_dir()`` or a subprocess.
    """
    if getattr(Path, "_colony_arm_wrap", False):
        return
    orig = Path.__truediv__

    def wrapped(self, key):  # noqa: ANN001
        try:
            if is_control() and _is_repo_root(self) and os.fspath(key) in {"data", "society"}:
                return orig(control_root(), key)
        except Exception:
            pass
        return orig(self, key)

    wrapped._colony_arm_wrap = True  # type: ignore[attr-defined]
    Path.__truediv__ = wrapped  # type: ignore[method-assign]
    Path._colony_arm_wrap = True  # type: ignore[attr-defined]


def _guarded(orig: Callable[..., Any], name: str) -> Callable[..., Any]:
    def guarded(*args: Any, **kwargs: Any) -> Any:
        if not hive_learning_enabled():
            return {
                "ok": True,
                "skipped": True,
                "reason": "control_arm",
                "learning": False,
                "name": name,
                "n_proposals": 0,
                "findings": [],
                "applied_to_live_oracle": False,
                "authorized": False,
            }
        return orig(*args, **kwargs)

    guarded._colony_arm_guard = True  # type: ignore[attr-defined]
    guarded._colony_arm_orig = orig  # type: ignore[attr-defined]
    return guarded


def wrap_hive_module(module: Any) -> None:
    """Wrap Hive entry points so control cannot learn, if Hive is present."""
    for name in _HIVE_FUNCS:
        fn = getattr(module, name, None)
        if not callable(fn) or getattr(fn, "_colony_arm_guard", False):
            continue
        # ``bind`` itself may still run so paths get set; learning
        # entry points are what we disable.
        if name == "bind":
            continue
        setattr(module, name, _guarded(fn, name))


def _install_hive_import_hook() -> None:
    """After Hive merges, wrap its cycle entry points on import."""
    global _HIVE_FINDER_INSTALLED
    if _HIVE_FINDER_INSTALLED:
        return
    # Already-imported (unusual at boot; useful for tests).
    for name in _HIVE_MODULES:
        mod = sys.modules.get(name)
        if mod is not None:
            wrap_hive_module(mod)

    class _HiveGuardFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):  # noqa: ANN001
            if fullname not in _HIVE_MODULES:
                return None
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is None or spec.loader is None:
                return None
            orig_loader = spec.loader

            class _WrappingLoader(importlib.abc.Loader):
                def create_module(self, spec):  # noqa: ANN001
                    create = getattr(orig_loader, "create_module", None)
                    if create is not None:
                        return create(spec)
                    return None

                def exec_module(self, module):  # noqa: ANN001
                    orig_loader.exec_module(module)
                    wrap_hive_module(module)

            # Preserve origin / is_package so relative imports in Hive work.
            spec.loader = _WrappingLoader()
            return spec

    # Insert in front so we see Hive imports first, then delegate.
    sys.meta_path.insert(0, _HiveGuardFinder())
    _HIVE_FINDER_INSTALLED = True


def install_runtime_hooks() -> None:
    """Install path and Hive guards. Safe to call more than once."""
    global _HOOKS_INSTALLED
    _install_path_hook()
    _install_hive_import_hook()
    _HOOKS_INSTALLED = True


def git_sha(cwd: Path | None = None) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd or REPO_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or None
    except Exception:
        return None


def control_is_seeded(root: Path | None = None) -> bool:
    """True only when the control tree has the files evolve needs.

    Empty ``data/`` or ``society/`` directories (or a fork receipt
    with ``control_seeded: false``) do not count. The required
    marker is ``data/society_state.json``.
    """
    cr = root if root is not None else control_root()
    state = raw_join(cr, "data", "society_state.json")
    if not state.is_file():
        return False
    fork = _load_json(raw_join(cr, FORK_NAME)) or {}
    # An explicit false is only trusted if the required file is also
    # missing; a complete tree from a seed that died after the copy
    # but before the flag is still seeded.
    if fork.get("control_seeded") is False and not state.is_file():
        return False
    return True


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _dump_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def freeze_control_self_mod(control: Path) -> dict[str, Any]:
    """Reset self-mod state in a control tree to the code defaults.

    In-flight self-heal trials are dropped, knobs return to
    ``colony/self_heal_defaults.json``, adopt/revert counters are
    zeroed, and checker-lane adoption lists are cleared. Operational
    stall history is left as it was at the snapshot: only the *policy*
    knobs are frozen, so PERTURB still uses the module defaults.
    """
    report: dict[str, Any] = {"self_heal": None, "checker_lane": None}
    systems = control / "society" / "systems"

    # Self-heal: defaults, no trial, no quarantines, no adopts.
    heal_path = systems / "self_heal.json"
    existing = _load_json(heal_path) or {}
    frozen = _self_heal_empty()
    knobs = dict(frozen.get("knobs") or {})
    try:
        from colony.self_heal import default_knobs as _dk
        knobs = _dk()
    except Exception:
        pass
    frozen["knobs"] = knobs
    frozen["trial"] = None
    frozen["quarantine"] = frozen.get("quarantine") or {}
    frozen["adopted_count"] = 0
    frozen["reverted_count"] = 0
    frozen["last_self_change"] = None
    frozen["arm"] = "control"
    frozen["frozen"] = True
    frozen["frozen_at"] = _utc()
    frozen["frozen_note"] = (
        "Control arm: knobs held at defaults, no trial continued, "
        "no adopts. This is a policy freeze, not a rewrite of treatment state."
    )
    # Keep a copy of what was snapshotted, for audit, not for use.
    if existing:
        frozen["fork_snapshot"] = {
            "knobs": existing.get("knobs"),
            "trial_knob": (existing.get("trial") or {}).get("knob")
            if isinstance(existing.get("trial"), dict)
            else None,
            "adopted_count": existing.get("adopted_count"),
            "reverted_count": existing.get("reverted_count"),
        }
    # Evidence and metrics start clean so control diagnoses only itself.
    frozen.setdefault("evidence", [])
    frozen.setdefault("metrics", [])
    frozen.setdefault("failures", [])
    frozen.setdefault("cycles", [])
    frozen.setdefault("cycle_index", 0)
    _dump_json(heal_path, frozen)
    report["self_heal"] = {
        "knobs": knobs,
        "trial_cleared": bool(existing.get("trial")),
        "path": str(heal_path),
    }

    # Checker lane: no proposals awaiting review, no new accepts.
    for name in ("checker_lane.json",):
        path = systems / name
        data = _load_json(path)
        if data is None:
            continue
        data["awaiting_review"] = []
        data["arm"] = "control"
        data["adoption_frozen"] = True
        data["frozen_at"] = _utc()
        _dump_json(path, data)
        report["checker_lane"] = {"cleared_awaiting_review": True, "path": str(path)}
    return report


def empty_fork_record(*, fork_sha: str | None = None, fork_ts: str | None = None) -> dict[str, Any]:
    return {
        "version": 1,
        "arm": "control",
        "fork_sha": fork_sha,
        "fork_ts": fork_ts or _utc(),
        "fork_source": "origin/main",
        "seeded_sha": None,
        "seeded_ts": None,
        "frozen": True,
        "note": (
            "Control is a snapshot of treatment state taken once, at "
            "first seed. After that it evolves on its own tree. Self-heal "
            "knobs are reset to colony/self_heal_defaults.json; in-flight "
            "trials are not continued. Early treatment-minus-control "
            "differences are noise. The Oracle, the P ≥ 0.70 gate, the "
            "150 cap, and Athanor math are the same in both arms."
        ),
    }


def ensure_control_seed(
    *,
    source_root: Path | None = None,
    dest_root: Path | None = None,
    force: bool = False,
    fork_sha: str | None = None,
) -> dict[str, Any]:
    """Copy treatment ``data/`` and ``society/`` into the control tree.

    Already-seeded trees are left alone unless ``force`` is set (tests).
    After the copy, self-mod state in the *control* copy is frozen at
    defaults. Treatment files are never written.
    """
    src = Path(os.path.abspath(os.fspath(source_root or REPO_ROOT)))
    dest = Path(os.path.abspath(os.fspath(dest_root or control_root())))
    if dest == src or dest == Path(os.path.abspath(os.fspath(REPO_ROOT))):
        raise ValueError("control dest must not be the treatment repo root")
    # Refuse to copy a control tree into a path that *is* treatment data/.
    # Use raw_join so a live COLONY_ARM=control hook cannot point these
    # at control/data and skip the check.
    for tree in _SEED_TREES:
        tree_path = raw_join(src, tree)
        try:
            dest.relative_to(tree_path)
            raise ValueError(f"control dest must not sit inside treatment {tree}/")
        except ValueError as exc:
            if "must not" in str(exc):
                raise

    already = (not force) and control_is_seeded(dest)
    fork_file = raw_join(dest, FORK_NAME)
    record = _load_json(fork_file) or empty_fork_record(fork_sha=fork_sha or git_sha(src))
    if already:
        record["already_seeded"] = True
        record["control_seeded"] = True
        record["dest"] = str(dest)
        record["source"] = str(src)
        return record

    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    missing_sources: list[str] = []
    for tree in _SEED_TREES:
        # raw_join: treatment source, never the redirected control dest.
        from_dir = raw_join(src, tree)
        to_dir = raw_join(dest, tree)
        if not from_dir.exists():
            missing_sources.append(str(from_dir))
            continue
        if to_dir.exists() and force:
            shutil.rmtree(to_dir)
        if to_dir.exists():
            # Partial tree from a crashed seed: fill missing files only.
            _copy_missing(from_dir, to_dir)
        else:
            shutil.copytree(from_dir, to_dir, ignore=_SEED_IGNORE, symlinks=False)
        copied.append(tree)

    required_missing = [
        rel for rel in REQUIRED_SEED_FILES
        if not raw_join(dest, *rel.split("/")).is_file()
    ]
    if not copied or required_missing:
        record["copied"] = copied
        record["control_seeded"] = False
        record["seeded_sha"] = None
        record["dest"] = str(dest)
        record["source"] = str(src)
        # Do not write control_seeded true. Leave any receipt off the
        # success path so a retry is not treated as already seeded.
        reasons = []
        if not copied:
            reasons.append(
                "copied nothing "
                f"(treatment sources missing or unreadable: {missing_sources or list(_SEED_TREES)})"
            )
        if required_missing:
            reasons.append("required files missing after copy: " + ", ".join(required_missing))
        raise ControlSeedError("; ".join(reasons))

    freeze_report = freeze_control_self_mod(dest)
    log_pointers = _seed_log_pointers(src, dest)
    # Re-check required files after freeze (freeze only rewrites JSON
    # under society/systems; society_state must still be there).
    required_missing = [
        rel for rel in REQUIRED_SEED_FILES
        if not raw_join(dest, *rel.split("/")).is_file()
    ]
    if required_missing:
        raise ControlSeedError(
            "required files missing after freeze: " + ", ".join(required_missing)
        )

    record["seeded_sha"] = git_sha(src)
    record["seeded_ts"] = _utc()
    record["copied"] = copied
    record["control_seeded"] = True
    record["freeze"] = {
        "self_heal_trial_cleared": (freeze_report.get("self_heal") or {}).get("trial_cleared"),
        "checker_adoption_cleared": bool(freeze_report.get("checker_lane")),
    }
    if log_pointers:
        record["log_pointers"] = log_pointers
    if fork_sha and not record.get("fork_sha"):
        record["fork_sha"] = fork_sha
    _dump_json(fork_file, record)
    record["dest"] = str(dest)
    record["source"] = str(src)
    return record


def _seed_log_pointers(src: Path, dest: Path) -> dict[str, Any]:
    """Point control logs at a frozen prefix of the treatment logs.

    Does not copy ``ledger.jsonl`` or ``witness.jsonl``. Safe because
    those files are append-only: the first N bytes at seed time never
    change. New control events go to control-owned segments.
    """
    try:
        from colony.log_segments import attach_shared_prefix
    except Exception:
        return {}
    pointers: dict[str, Any] = {}
    for name in ("ledger.jsonl", "witness.jsonl"):
        source = raw_join(src, "data", name)
        dest_file = raw_join(dest, "data", name)
        if not source.is_file():
            continue
        # If a previous seed (before this change) already copied the
        # file, leave it in place as segment 1. Do not delete it and
        # do not rewrite history.
        if dest_file.is_file() and dest_file.stat().st_size > 0:
            pointers[name] = {
                "skipped": "already_present",
                "bytes": dest_file.stat().st_size,
                "note": "Existing control copy left in place; new appends rotate into local segments.",
            }
            continue
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        man = attach_shared_prefix(
            dest_file,
            source,
            limit_bytes=source.stat().st_size,
            source_label="treatment",
            extra={"seeded_from": str(source)},
        )
        pointers[name] = {
            "skipped": "shared_prefix",
            "limit_bytes": (man.get("shared_prefix") or {}).get("limit_bytes"),
            "manifest": str(dest_file.parent / f"{dest_file.stem}.segments.json"),
        }
    return pointers


def _copy_missing(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in {"__pycache__"} or item.suffix == ".pyc":
            continue
        if item.name in _SEED_SKIP_LOGS:
            continue
        target = dest / item.name
        if item.is_dir():
            _copy_missing(item, target)
        elif not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def prepare_arm(*, seed: bool | None = None) -> dict[str, Any]:
    """Install hooks and, on the control arm, make sure the tree exists."""
    install_runtime_hooks()
    # Re-bind Hive paths for the current arm, if Hive is present.
    try:
        from colony import hive_adapter as _hive_adapter
        _hive_adapter.bind()
    except Exception:
        pass
    info: dict[str, Any] = {"arm": arm(), "self_mod": self_mod_enabled(), "hive_learning": hive_learning_enabled()}
    if not is_control():
        info["state_root"] = str(state_root())
        return info
    info["control_root"] = str(control_root())
    want_seed = seed if seed is not None else (
        (os.environ.get("COLONY_SEED_CONTROL") or "").strip().lower() in {"1", "true", "yes", "on"}
    )
    if control_is_seeded():
        info["seeded"] = True
        return info
    if want_seed:
        info["seed"] = ensure_control_seed()
        info["seeded"] = control_is_seeded()
        if not info["seeded"]:
            raise ControlSeedError(
                "seed ran but control/data/society_state.json is still missing"
            )
        return info
    info["seeded"] = False
    info["error"] = (
        "COLONY_ARM=control but the control tree is not seeded. "
        "Run: COLONY_SEED_CONTROL=1 python -m colony seed-control"
    )
    return info


# ---------------------------------------------------------------------------
# Helpers used when self-heal's empty_state is not importable at freeze
# (kept here so freeze still works if that name changes).
# ---------------------------------------------------------------------------

def _fallback_empty_heal() -> dict[str, Any]:
    return {
        "version": 1,
        "knobs": {},
        "trial": None,
        "metrics": [],
        "quarantine": [],
        "failures": [],
        "evidence": [],
        "adopted_count": 0,
        "reverted_count": 0,
        "cycle_index": 0,
        "cycles": [],
        "last_self_change": None,
        "knob_last_trial": {},
    }


# Try to use the real empty state if the name exists; freeze_control
# already falls back.
def _self_heal_empty() -> dict[str, Any]:
    try:
        from colony import self_heal as sh
        for name in ("_empty_state", "empty_state"):
            fn = getattr(sh, name, None)
            if callable(fn):
                return fn()
    except Exception:
        pass
    return _fallback_empty_heal()


# Install hooks on import so `import colony.self_heal` in a control
# process (env already set) gets redirected module-level paths.
install_runtime_hooks()
