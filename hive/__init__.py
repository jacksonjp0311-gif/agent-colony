"""Hive: a deterministic retrieval-based fix chooser, built on Bitwork.

Hive does not write free-form code, does not call an outside model, and
does not import the host application. A host such as Agent Colony talks
to it through a small adapter that passes plain dicts and paths in and
gets decisions out.

Public surface (see README.md for the full contract):

* ``hive.bitwork`` — FNV-1a 4096-bit encoder, category and prototype
  scores, Wilson 95% gate, ``Router``
* ``hive.ops`` — closed patch-operation vocabulary and validation
* ``hive.library`` — append-only fix library, seeds, router training
* ``hive.swarm`` — role proposals, vote, teach-from-outcome, cycle loop
* ``hive.host`` — optional call-time hooks a host may ``bind()``
"""
from __future__ import annotations

__version__ = "0.1.0"

from hive.bitwork import (
    BITS,
    MARGIN_BUCKETS,
    WILSON_ACCEPT_PERMILLE,
    Router,
    action_fingerprint,
    category_score,
    encode,
    fnv1a_64,
    normalize,
    prototype_score,
    wilson_lower_permille,
)
from hive.ops import OPS, ValidatedAction, describe, legal_knob_names, touches_invariant, validate
from hive.library import (
    append_record,
    ensure_seeded,
    held_out_cases,
    load_records,
    seed_patterns,
    train_router,
)
from hive.swarm import (
    MAX_ACTIONS_PER_CYCLE,
    SWARM_ROLES,
    format_visibility,
    on_cycle,
    run_cycle,
    teach_from_event,
    visibility,
    vote,
)

__all__ = (
    "BITS",
    "MARGIN_BUCKETS",
    "MAX_ACTIONS_PER_CYCLE",
    "OPS",
    "SWARM_ROLES",
    "WILSON_ACCEPT_PERMILLE",
    "Router",
    "ValidatedAction",
    "__version__",
    "action_fingerprint",
    "append_record",
    "category_score",
    "describe",
    "encode",
    "ensure_seeded",
    "fnv1a_64",
    "format_visibility",
    "held_out_cases",
    "legal_knob_names",
    "load_records",
    "normalize",
    "on_cycle",
    "prototype_score",
    "run_cycle",
    "seed_patterns",
    "teach_from_event",
    "touches_invariant",
    "train_router",
    "validate",
    "visibility",
    "vote",
    "wilson_lower_permille",
)
